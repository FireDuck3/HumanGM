from __future__ import annotations
import math


def estimate_elo(results: list[float], opponent_elos: list[int]) -> tuple[float, float]:
    """Approximate performance rating and 95% interval from scored games.

    Uses a logistic model and a conservative binomial standard error. This is
    a calibration aid, not a FIDE/online rating estimator for small samples.
    """
    if not results or len(results) != len(opponent_elos) or any(x not in (0, .5, 1) for x in results):
        raise ValueError("Provide matching non-empty scores (0, 0.5, 1) and opponent ratings")
    average = sum(opponent_elos) / len(opponent_elos)
    score = sum(results) / len(results)
    p = min(.999, max(.001, score))
    perf = average + 400 * math.log10(p / (1 - p))
    se = 400 / math.log(10) * math.sqrt(max(1e-6, 1 / (len(results) * p * (1 - p))))
    return perf, 1.96 * se
