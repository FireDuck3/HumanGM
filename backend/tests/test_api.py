import chess
import pytest
from fastapi.testclient import TestClient

from backend.decision.move_selector import Candidate
from backend.engines.engine_manager import AnalysisPool
from backend.main import app, engine


client = TestClient(app)


def candidate(uci, cp, probability=None, mate=None):
    return Candidate(chess.Move.from_uci(uci), stockfish_cp=cp,
                     maia_probability=probability, stockfish_mate=mate)


def test_analysis_picks_most_human_safe_move_without_playing_it(monkeypatch):
    def analyze(board, rating, *, use_maia):
        assert board.fen() == chess.STARTING_FEN
        assert rating == 2800
        assert use_maia is True
        return AnalysisPool([
            candidate("e2e4", 30, .06),
            candidate("d2d4", 20, .33),
            candidate("g1f3", 0, .52),
        ], "connected", "connected | Elo 2800")

    monkeypatch.setattr(engine, "analyze", analyze)
    response = client.post("/api/analyze", json={})
    assert response.status_code == 200
    result = response.json()
    assert result["fen"] == chess.STARTING_FEN
    assert result["recommended"]["san"] == "d4"
    assert result["recommended"]["loss_cp"] == 10
    assert result["selection"] == "hybrid"
    assert [row["uci"] for row in result["candidates"]] == ["e2e4", "d2d4", "g1f3"]
    assert client.post("/api/engine-move").status_code in (404, 405)


def test_analysis_replays_legal_history_and_preserves_mate(monkeypatch):
    start = "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"

    def analyze(board, _rating, *, use_maia):
        assert board.fen() == start
        return AnalysisPool([
            candidate("e1e8", 99999, .01, mate=1),
            candidate("e1e7", 90, .9),
        ], "connected", "connected")

    monkeypatch.setattr(engine, "analyze", analyze)
    result = client.post("/api/analyze", json={"initial_fen": start}).json()
    assert result["recommended"]["san"] == "Re8#"
    assert result["recommended"]["mate"] == 1
    assert result["recommended"]["stockfish_cp"] is None
    assert result["selection"] == "stockfish"


@pytest.mark.parametrize("payload", [
    {"moves": ["e2e5"]},
    {"initial_fen": "8/8/8/8/8/8/8/8 w - - 0 1"},
])
def test_analysis_rejects_invalid_position(payload):
    assert client.post("/api/analyze", json=payload).status_code == 400


def test_analysis_without_maia_recommends_stockfish(monkeypatch):
    monkeypatch.setattr(engine, "analyze", lambda board, rating, **options: AnalysisPool(
        [candidate("e7e5", 40), candidate("c7c5", 32)], "connected", "offline",
    ))
    result = client.post("/api/analyze", json={"moves": ["e2e4"]}).json()
    assert result["fen"] == chess.Board.from_epd(
        "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -"
    )[0].fen()
    assert result["recommended"]["san"] == "e5"
    assert result["recommended"]["maia_probability"] is None
    assert result["selection"] == "stockfish"


def test_stockfish_only_analysis_for_practice(monkeypatch):
    def analyze(board, rating, *, use_maia):
        assert use_maia is False
        return AnalysisPool([candidate("e2e4", 30)], "connected", "skipped")

    monkeypatch.setattr(engine, "analyze", analyze)
    result = client.post("/api/analyze", json={"use_maia": False}).json()
    assert result["recommended"]["uci"] == "e2e4"
    assert result["selection"] == "stockfish"
    assert result["maia"] == "skipped"
