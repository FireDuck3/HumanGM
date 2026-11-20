from __future__ import annotations

import json
import math
import os
import shlex
import threading
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.engine

from backend.decision.move_selector import Candidate, GM_TARGET_RATING


@dataclass
class AnalysisPool:
    candidates: list[Candidate]
    stockfish: str
    maia: str


class EngineManager:
    """Keep optional UCI engines alive and combine their distinct strengths."""

    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[2]
        self.maia_cache = self.project_root / "data" / "maia-cache"
        self.maia_cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(self.maia_cache))
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        self.stockfish_path = os.getenv("STOCKFISH_PATH", "").strip()
        self.stockfish_args = json.loads(os.getenv("STOCKFISH_ARGS_JSON", "[]"))
        if not isinstance(self.stockfish_args, list) or not all(isinstance(arg, str) for arg in self.stockfish_args):
            raise ValueError("STOCKFISH_ARGS_JSON must be a JSON array of strings")
        self.maia_path = os.getenv("MAIA3_PATH", "").strip()
        self.maia_args = shlex.split(os.getenv("MAIA3_ARGS", "--model maia3-5m --use-uci-history --device cpu --no-use-amp"))
        self._lock = threading.Lock()
        self._engines: dict[str, tuple[tuple[str, ...], chess.engine.SimpleEngine]] = {}

    @staticmethod
    def _available(command: str) -> bool:
        if not command:
            return False
        p = Path(command)
        return p.is_file() if p.is_absolute() or "/" in command or "\\" in command else True

    def _engine(self, name: str, command: list[str], timeout: float) -> chess.engine.SimpleEngine:
        key = tuple(command)
        current = self._engines.get(name)
        if current and current[0] == key:
            if current[1].transport.get_returncode() is None:
                return current[1]
            self._close(name)
        elif current:
            self._close(name)
        child_env = os.environ.copy()
        child_env.setdefault("PYTHONIOENCODING", "utf-8")
        engine = chess.engine.SimpleEngine.popen_uci(command, timeout=timeout, cwd=self.project_root, env=child_env)
        self._engines[name] = (key, engine)
        return engine

    def _close(self, name: str) -> None:
        current = self._engines.pop(name, None)
        if current:
            try:
                current[1].close()
            except Exception:
                pass

    def close(self) -> None:
        """Stop child processes when the application shuts down."""
        with self._lock:
            for name in list(self._engines):
                self._close(name)

    @staticmethod
    def _configure_if_supported(engine: chess.engine.SimpleEngine, options: dict[str, object]) -> None:
        supported = {name: value for name, value in options.items() if name in engine.options}
        if supported:
            engine.configure(supported)

    @staticmethod
    def _apply_maia_info(rows: list[dict], candidates: dict[chess.Move, Candidate]) -> None:
        prefix = "maia_policy "
        policy: dict[str, float] = {}
        for rank, row in enumerate(rows, 1):
            move = next(iter(row.get("pv", ())), None)
            if move in candidates:
                candidates[move].maia_rank = row.get("multipv", rank)
            message = row.get("string", "")
            if message.startswith(prefix):
                try:
                    reported = json.loads(message[len(prefix):])
                except ValueError:
                    continue
                if isinstance(reported, dict):
                    policy.update(reported)
        for move in candidates:
            probability = policy.get(move.uci())
            if isinstance(probability, (int, float)) and math.isfinite(probability) and 0 <= probability <= 1:
                candidates[move].maia_probability = probability
        ranked = sorted(
            (candidate for candidate in candidates.values() if candidate.maia_probability is not None),
            key=lambda candidate: candidate.maia_probability,
            reverse=True,
        )
        for rank, candidate in enumerate(ranked, 1):
            candidate.maia_rank = rank

    def analyze(self, board: chess.Board, target_rating: int) -> AnalysisPool:
        legal = list(board.legal_moves)
        if not legal:
            raise ValueError("Game is over")

        candidates_by_move = {move: Candidate(move=move) for move in legal}
        stockfish_moves: list[chess.Move] = []
        stockfish_status = "offline"
        maia_status = "offline"
        multipv = min(max(1, int(os.getenv("ENGINE_CANDIDATES", "6"))), 6, len(legal))
        move_time = float(os.getenv("ENGINE_MOVE_TIME", "1.5"))
        if target_rating >= GM_TARGET_RATING:
            move_time = max(move_time, float(os.getenv("GM_MOVE_TIME", "3.0")))

        with self._lock:
            if self._available(self.stockfish_path):
                try:
                    sf = self._engine("stockfish", [self.stockfish_path, *self.stockfish_args], 10)
                    self._configure_if_supported(sf, {
                        "UCI_LimitStrength": False,
                        "Skill Level": 20,
                        "Threads": int(os.getenv("STOCKFISH_THREADS", "4")),
                        "Hash": int(os.getenv("STOCKFISH_HASH_MB", "128")),
                    })
                    info = sf.analyse(
                        board,
                        chess.engine.Limit(time=move_time),
                        multipv=multipv,
                    )
                    for row in info if isinstance(info, list) else [info]:
                        move = next(iter(row.get("pv", ())), None)
                        score = row.get("score")
                        if move in candidates_by_move and score is not None:
                            score = score.pov(board.turn)
                            candidates_by_move[move].stockfish_cp = score.score(mate_score=100000)
                            candidates_by_move[move].stockfish_mate = score.mate()
                            if move not in stockfish_moves:
                                stockfish_moves.append(move)
                    stockfish_status = "connected | full strength" if stockfish_moves else "error: no scored moves"
                except Exception as exc:
                    self._close("stockfish")
                    stockfish_moves.clear()
                    stockfish_status = f"error: {type(exc).__name__}"

            if stockfish_moves and self._available(self.maia_path):
                try:
                    # The first isready may load the model weights and initialize PyTorch on CPU.
                    maia = self._engine("maia", [self.maia_path, *self.maia_args], float(os.getenv("MAIA_START_TIMEOUT", "50")))
                    # Maia-3 models human move preferences conditioned on both Elo values.
                    self._configure_if_supported(maia, {"SelfElo": target_rating, "OppoElo": target_rating})
                    # Maia ranks its legal moves globally and ignores UCI searchmoves.
                    info = maia.analyse(
                        board,
                        chess.engine.Limit(time=float(os.getenv("MAIA_MOVE_TIME", "0.5"))),
                        multipv=min(len(legal), 20, maia.options["MultiPV"].max or 20),
                    )
                    self._apply_maia_info(info if isinstance(info, list) else [info], candidates_by_move)
                    has_policy = any(candidate.maia_rank is not None for candidate in candidates_by_move.values())
                    maia_status = f"connected | Elo {target_rating}" if has_policy else "error: no policy"
                except Exception as exc:
                    self._close("maia")
                    maia_status = f"error: {type(exc).__name__}"

        candidates = sorted(
            (candidates_by_move[move] for move in stockfish_moves),
            key=lambda candidate: candidate.stockfish_cp,
            reverse=True,
        )
        return AnalysisPool(candidates, stockfish_status, maia_status)
