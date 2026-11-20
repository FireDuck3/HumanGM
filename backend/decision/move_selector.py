"""Experimental hybrid move ranker.

Stockfish supplies tactical scores. Maia-3 supplies human move preferences.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import os
import random
import chess

from .styles import STYLE_WEIGHTS, style_features


GM_TARGET_RATING = 2800
GM_STYLE = "Dynamic"


def ranker_config() -> dict:
    path = Path(os.getenv("RANKER_CONFIG", Path(__file__).resolve().parents[2] / "config" / "ranker.json"))
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        return config if isinstance(config, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


@dataclass
class Candidate:
    move: chess.Move
    stockfish_cp: float | None = None
    maia_rank: int | None = None
    style_score: float = 0.0
    final_score: float = 0.0
    maia_probability: float | None = None
    stockfish_mate: int | None = None


def analysis_loss_budget(target_rating: int) -> int:
    """Allow a wider tactical margin for a lower target human rating."""
    return round(120 - 100 * (min(2800, target_rating) - 1200) / 1600) if target_rating <= 2800 else round(
        20 - 8 * (target_rating - 2800) / 200
    )


def recommend_analysis(candidates: list[Candidate], max_loss: int) -> tuple[Candidate, bool]:
    """Recommend the most likely human move within the allowed Stockfish loss."""
    best = candidates[0]
    if best.stockfish_mate is not None:
        return best, False
    safe = [
        candidate for candidate in candidates
        if candidate.stockfish_mate is None and best.stockfish_cp - candidate.stockfish_cp <= max_loss
    ]
    with_probability = [candidate for candidate in safe if candidate.maia_probability is not None]
    if with_probability:
        return max(with_probability, key=lambda candidate: candidate.maia_probability), True
    with_rank = [candidate for candidate in safe if candidate.maia_rank is not None]
    if with_rank:
        return min(with_rank, key=lambda candidate: candidate.maia_rank), True
    return best, False


def _select_grandmaster(board: chess.Board, scored: list[Candidate], best: Candidate,
                       rating: int, style_weights: dict[str, float],
                       maia_peak_probability: float | None) -> Candidate:
    # Preserve the fastest winning mate or the longest defense against mate.
    if best.stockfish_mate is not None:
        return best

    max_loss = 20.0 - 0.04 * (rating - GM_TARGET_RATING)
    # Maia ranks globally. Require an alternative to have a meaningful share
    # of the policy mass before trading away any of Stockfish's evaluation.
    candidates = [best]
    for candidate in scored:
        if candidate is best or best.stockfish_cp - candidate.stockfish_cp > max_loss:
            continue
        if maia_peak_probability is not None:
            plausible = (candidate.maia_probability or 0) >= max(0.02, 0.10 * maia_peak_probability)
        else:
            plausible = candidate.maia_rank is not None and candidate.maia_rank <= 5
        if plausible:
            candidates.append(candidate)

    def preference(candidate: Candidate) -> float:
        if maia_peak_probability is not None:
            relative = (candidate.maia_probability or 0) / maia_peak_probability
            human_score = 8.0 * math.log(max(0.025, relative))
        else:
            human_score = -4.0 * min(5, (candidate.maia_rank or 6) - 1)
        features = style_features(board, candidate.move)
        style_score = sum(float(style_weights.get(key, 0.0)) * value for key, value in features.items())
        return candidate.stockfish_cp + human_score + 10.0 * style_score

    return max(candidates, key=preference)


def select_move(board: chess.Board, candidates: list[Candidate], style: str = "Universal",
                target_rating: int = 2000, maia_weight: float | None = None,
                style_weight: float | None = None, safety_cp: float | None = None,
                maia_peak_probability: float | None = None) -> Candidate:
    if not candidates:
        raise ValueError("At least one candidate is required")
    legal = set(board.legal_moves)
    if any(candidate.move not in legal for candidate in candidates):
        raise ValueError("Candidate list contains an illegal move")
    if style not in STYLE_WEIGHTS:
        raise ValueError(f"Unknown style: {style}")
    config = ranker_config()
    maia_weight = float(config.get("maia_weight", 0.16) if maia_weight is None else maia_weight)
    style_weight = float(config.get("style_weight", 12.0) if style_weight is None else style_weight)
    safety_cp = float(config.get("safety_cp", 115.0) if safety_cp is None else safety_cp)
    style_weights = config.get("styles", STYLE_WEIGHTS).get(style, STYLE_WEIGHTS[style])
    rating = max(1200, min(3000, int(target_rating)))
    scored = [c for c in candidates if c.stockfish_cp is not None]
    if scored:
        best_move = max(scored, key=lambda candidate: candidate.stockfish_cp)
        if rating >= GM_TARGET_RATING:
            return _select_grandmaster(board, scored, best_move, rating, style_weights, maia_peak_probability)
        best_cp = best_move.stockfish_cp
        # The configured rating controls how far from Stockfish's best move
        # the human prior may choose. Maia is also conditioned on that rating.
        tolerance = max(25.0, safety_cp * (1.65 - 1.25 * (rating - 1200) / 1800))
        safe = [c for c in scored if best_cp - c.stockfish_cp <= tolerance]
    else:
        best_cp = 0.0
        safe = list(candidates)

    for c in safe:
        loss = max(0.0, best_cp - float(c.stockfish_cp)) if c.stockfish_cp is not None else 0.0
        rank = c.maia_rank or len(candidates)
        maia_bonus = max(0.0, (len(candidates) - rank + 1) / max(1, len(candidates)))
        f = style_features(board, c.move)
        c.style_score = sum(float(style_weights.get(name, 0.0)) * value for name, value in f.items())
        # Maia MultiPV is an ordering, not a probability. This bonus only
        # expresses a preference within Stockfish's rating-dependent safety band.
        c.final_score = -loss + maia_weight * 120.0 * maia_bonus + style_weight * c.style_score
    best = max(safe, key=lambda c: c.final_score)
    # Sample among safe human-like options at lower ratings. High ratings use
    # a near-greedy temperature, so Stockfish's best moves dominate there.
    ranked_by_maia = len({c.maia_rank for c in safe if c.maia_rank is not None}) > 1
    if not scored and not ranked_by_maia:
        return best
    rating_fraction = (rating - 1200) / 1800
    low_temperature = float(config.get("low_rating_temperature_cp", 35.0))
    high_temperature = float(config.get("high_rating_temperature_cp", 2.0))
    temperature = max(0.1, low_temperature + (high_temperature - low_temperature) * rating_fraction)
    top_score = best.final_score
    weights = [math.exp(max(-50.0, (candidate.final_score - top_score) / temperature)) for candidate in safe]
    return random.choices(safe, weights=weights, k=1)[0]
