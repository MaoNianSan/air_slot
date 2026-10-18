"""Model-level Development selection rules for M1.

This module contains only deterministic selection logic.  It does not load a
cohort, train a model, execute an experiment, or write an artifact.
"""

from __future__ import annotations


SECONDARY_TRAINING_SEEDS: tuple[int, ...] = (
    20260813,
    20260814,
    20260815,
)


def recommend_history_window(
    candidate_means: dict[int, float],
    *,
    practical_equivalence_threshold: float = 0.005,
) -> tuple[int, int, dict[int, float], dict[int, bool]]:
    """Select the shortest window practically equivalent to the raw best.

    Scores are Development losses, so lower is better.  The function rejects
    empty/non-positive inputs because relative-loss equivalence is undefined
    for them.
    """

    if not candidate_means:
        raise ValueError("M1_HISTORY_WINDOW_CANDIDATES_REQUIRED")
    if practical_equivalence_threshold < 0:
        raise ValueError("M1_HISTORY_WINDOW_EQUIVALENCE_THRESHOLD_INVALID")
    normalized = {int(window): float(score) for window, score in candidate_means.items()}
    if any(window <= 0 or window % 5 for window in normalized):
        raise ValueError("M1_HISTORY_WINDOW_MUST_ALIGN_TO_FIVE_MINUTE_GRID")
    if any(score <= 0 for score in normalized.values()):
        raise ValueError("M1_HISTORY_WINDOW_SCORE_MUST_BE_POSITIVE")

    best_raw = min(normalized, key=lambda window: (normalized[window], window))
    best_score = normalized[best_raw]
    relative = {
        window: (score - best_score) / best_score
        for window, score in normalized.items()
    }
    equivalent = {
        window: difference <= practical_equivalence_threshold
        for window, difference in relative.items()
    }
    recommendation = min(window for window, accepted in equivalent.items() if accepted)
    return best_raw, recommendation, relative, equivalent


__all__ = ["SECONDARY_TRAINING_SEEDS", "recommend_history_window"]
