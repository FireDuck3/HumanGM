import chess
from backend.decision.move_selector import Candidate, select_move
from backend.evaluation.rating import estimate_elo


def test_special_moves_are_legal_and_applied():
    board = chess.Board("r3k2r/8/8/3pP3/8/8/8/R3K2R w KQkq d6 0 1")
    for uci in ("e1g1", "e5d6"):
        move = chess.Move.from_uci(uci)
        assert move in board.legal_moves
        clone = board.copy()
        clone.push(move)
        assert clone.is_valid()


def test_promotion_and_mate_stalemate_detection():
    promotion = chess.Board("7k/P7/8/8/8/8/8/7K w - - 0 1")
    move = chess.Move.from_uci("a7a8q")
    assert move in promotion.legal_moves
    promotion.push(move)
    assert promotion.piece_at(chess.A8).piece_type == chess.QUEEN
    mate = chess.Board("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1")
    stale = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert mate.is_checkmate()
    assert stale.is_stalemate()


def test_repetition_and_fifty_move_rule():
    board = chess.Board()
    for uci in ("g1f3", "g8f6", "f3g1", "f6g8") * 2:
        board.push_uci(uci)
    assert board.is_repetition(3)
    fifty = chess.Board("8/8/8/8/8/8/4k3/7K w - - 100 51")
    assert fifty.is_fifty_moves()


def test_selector_always_returns_a_legal_candidate():
    board = chess.Board()
    candidates = [Candidate(move=m, stockfish_cp=-15, maia_rank=i + 1) for i, m in enumerate(list(board.legal_moves)[:5])]
    chosen = select_move(board, candidates, style="Dynamic", target_rating=2400)
    assert chosen.move in board.legal_moves


def test_rating_calibration_returns_uncertainty():
    estimate, uncertainty = estimate_elo([1, 0.5, 1, 0], [1800, 1800, 2000, 2000])
    assert 1800 <= estimate <= 2000
    assert uncertainty > 0
