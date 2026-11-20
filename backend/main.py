from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path

import chess
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.decision.move_selector import Candidate, GM_TARGET_RATING, analysis_loss_budget, recommend_analysis
from backend.engines.engine_manager import EngineManager

load_dotenv()
engine = EngineManager()
analysis_slot = threading.Lock()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        yield
    finally:
        engine.close()


app = FastAPI(title="HumanGM Chess Analysis", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


class AnalysisRequest(BaseModel):
    initial_fen: str | None = Field(default=None, max_length=160)
    moves: list[str] = Field(default_factory=list, max_length=2048)
    target_rating: int = Field(default=GM_TARGET_RATING, ge=1200, le=3000)


def replay_position(data: AnalysisRequest) -> chess.Board:
    try:
        board = chess.Board(data.initial_fen) if data.initial_fen else chess.Board()
        if not board.is_valid():
            raise ValueError("invalid board")
    except ValueError as exc:
        raise HTTPException(400, "Початкова позиція FEN некоректна.") from exc

    for ply, raw in enumerate(data.moves, 1):
        try:
            move = chess.Move.from_uci(raw)
            if move not in board.legal_moves:
                raise ValueError("illegal move")
        except ValueError as exc:
            raise HTTPException(400, f"Нелегальний хід на кроці {ply}: {raw}.") from exc
        board.push(move)
    return board


def describe_candidate(board: chess.Board, candidate: Candidate, rank: int, best: Candidate) -> dict:
    cp = int(candidate.stockfish_cp) if candidate.stockfish_mate is None else None
    loss = int(best.stockfish_cp - candidate.stockfish_cp) if cp is not None and best.stockfish_mate is None else None
    return {
        "uci": candidate.move.uci(),
        "san": board.san(candidate.move),
        "stockfish_rank": rank,
        "stockfish_cp": cp,
        "mate": candidate.stockfish_mate,
        "loss_cp": loss,
        "maia_probability": candidate.maia_probability,
        "maia_rank": candidate.maia_rank,
    }


@app.get("/healthz")
def health():
    return {"status": "ready"}


@app.post("/api/analyze")
def analyze(data: AnalysisRequest):
    board = replay_position(data)
    if board.is_game_over():
        raise HTTPException(409, "У цій позиції партія вже завершена.")
    if not analysis_slot.acquire(blocking=False):
        raise HTTPException(429, "Рушії завершують інший аналіз. Спробуй ще раз за кілька секунд.")
    try:
        result = engine.analyze(board, data.target_rating)
    finally:
        analysis_slot.release()
    if not result.candidates:
        raise HTTPException(503, "Stockfish не зміг проаналізувати позицію. Спробуй ще раз.")

    max_loss = analysis_loss_budget(data.target_rating)
    preferred, used_maia = recommend_analysis(result.candidates, max_loss)
    best = result.candidates[0]
    rows = [describe_candidate(board, candidate, rank, best) for rank, candidate in enumerate(result.candidates, 1)]
    return {
        "fen": board.fen(),
        "target_rating": data.target_rating,
        "recommended": next(row for row in rows if row["uci"] == preferred.move.uci()),
        "candidates": rows,
        "stockfish": result.stockfish,
        "maia": result.maia,
        "selection": "hybrid" if used_maia else "stockfish",
        "max_loss_cp": max_loss,
    }


frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
