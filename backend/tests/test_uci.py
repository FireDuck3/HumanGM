import json
import sys
from pathlib import Path

import chess

from backend.engines.engine_manager import EngineManager


def test_uci_exchange_and_engine_restarts_after_crash(monkeypatch, tmp_path):
    helper = Path(__file__).with_name("fake_uci.py")
    marker = tmp_path / "crash-once.txt"
    monkeypatch.setenv("STOCKFISH_PATH", sys.executable)
    monkeypatch.setenv("STOCKFISH_ARGS_JSON", json.dumps([str(helper)]))
    monkeypatch.setenv("MAIA3_PATH", "")
    monkeypatch.setenv("FAKE_UCI_CRASH_MARKER", str(marker))
    manager = EngineManager()

    try:
        first = manager.analyze(chess.Board(), 2000)
        assert not first.candidates
        assert first.stockfish.startswith("error:")

        second = manager.analyze(chess.Board(), 2000)
        assert second.candidates[0].move in chess.Board().legal_moves
        assert second.stockfish.startswith("connected")
    finally:
        manager.close()
