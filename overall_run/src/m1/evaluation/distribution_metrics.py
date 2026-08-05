from __future__ import annotations

import numpy as np

from .point_metrics import distribution_quantile


def discrete_crps(
    actual: np.ndarray,
    probabilities: np.ndarray,
    lower_minutes: np.ndarray,
    bin_minutes: float = 5.0,
) -> float:
    truth = np.asarray(actual, dtype=float)
    probs = np.asarray(probabilities, dtype=float)
    lower = np.asarray(lower_minutes, dtype=float)
    cdf = np.cumsum(probs, axis=1)
    observed = (lower[None, :] >= truth[:, None]).astype(float)
    return float(np.mean(np.sum((cdf - observed) ** 2, axis=1) * bin_minutes))


def negative_log_likelihood(actual_indices: np.ndarray, probabilities: np.ndarray) -> float:
    indices = np.asarray(actual_indices, dtype=int)
    probs = np.asarray(probabilities, dtype=float)
    selected = probs[np.arange(len(indices)), indices]
    return float(-np.log(np.clip(selected, 1e-12, 1.0)).mean())


def interval_metrics(
    actual: np.ndarray,
    probabilities: np.ndarray,
    lower_minutes: np.ndarray,
    level: float,
) -> dict[str, float]:
    alpha = (1.0 - level) / 2.0
    low = distribution_quantile(probabilities, lower_minutes, alpha)
    high = distribution_quantile(probabilities, lower_minutes, 1.0 - alpha)
    truth = np.asarray(actual, dtype=float)
    coverage = float(np.mean((truth >= low) & (truth <= high)))
    return {
        f"coverage_{int(level * 100)}": coverage,
        f"width_{int(level * 100)}": float(np.mean(high - low)),
        f"coverage_error_{int(level * 100)}": coverage - level,
    }


def overflow_rate(probabilities: np.ndarray) -> float:
    return float(np.asarray(probabilities, dtype=float)[:, -1].mean())
