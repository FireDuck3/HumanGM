"""Position-sensitive style features used to rank legal candidates."""
from __future__ import annotations

import chess

STYLE_WEIGHTS: dict[str, dict[str, float]] = {
    "Aggressive": {"check": 0.55, "capture": 0.18, "center": 0.08, "risk": 0.16},
    "Positional": {"check": 0.02, "capture": 0.06, "center": 0.28, "risk": -0.12},
    "Universal": {"check": 0.16, "capture": 0.12, "center": 0.18, "risk": -0.02},
    "Solid": {"check": -0.02, "capture": 0.05, "center": 0.12, "risk": -0.32},
    "Dynamic": {"check": 0.24, "capture": 0.14, "center": 0.12, "risk": -0.08,
                "development": 0.24, "king_pressure": 0.28},
}


def style_features(board: chess.Board, move: chess.Move) -> dict[str, float]:
    """Cheap interpretable features; all inputs are legal moves from board."""
    piece = board.piece_at(move.from_square)
    capture = board.is_capture(move)
    center = chess.square_file(move.to_square) in (2, 3, 4, 5) and chess.square_rank(move.to_square) in (2, 3, 4, 5)
    risk = 0.0
    if piece and piece.piece_type != chess.PAWN:
        risk = float(board.attackers(not board.turn, move.to_square) != chess.SquareSet())
    home_rank = 0 if board.turn == chess.WHITE else 7
    develops = (board.fullmove_number <= 12 and piece is not None
                and piece.piece_type in (chess.KNIGHT, chess.BISHOP)
                and chess.square_rank(move.from_square) == home_rank
                and chess.square_rank(move.to_square) != home_rank)
    board.push(move)
    check = board.is_check()
    king = board.king(board.turn)
    pressure = bool(king is not None and board.attacks(move.to_square) & chess.BB_KING_ATTACKS[king])
    board.pop()
    return {"check": float(check), "capture": float(capture), "center": float(center), "risk": risk,
            "development": float(develops), "king_pressure": float(pressure)}
