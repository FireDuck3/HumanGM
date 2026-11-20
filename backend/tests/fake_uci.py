"""Tiny UCI process fixture used to exercise protocol and crash recovery."""
import os
import sys

import chess

position = "startpos"
for raw in sys.stdin:
    command = raw.strip()
    if command == "uci":
        print("id name HumanGM test UCI", flush=True)
        print("option name MultiPV type spin default 1 min 1 max 32", flush=True)
        print("uciok", flush=True)
    elif command == "isready":
        print("readyok", flush=True)
    elif command.startswith("position "):
        position = command[len("position "):]
    elif command.startswith("go"):
        marker = os.getenv("FAKE_UCI_CRASH_MARKER")
        if marker and not os.path.exists(marker):
            with open(marker, "w", encoding="utf-8") as handle:
                handle.write("crashed once")
            sys.exit(2)
        if position.startswith("fen "):
            board = chess.Board(position[len("fen "):].split(" moves ")[0])
        else:
            board = chess.Board()
        move = next(iter(board.legal_moves))
        print(f"info depth 1 multipv 1 score cp 15 pv {move.uci()}", flush=True)
        print(f"bestmove {move.uci()}", flush=True)
    elif command == "quit":
        break
