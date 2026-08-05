from __future__ import annotations

import numpy as np


def point_metrics(actual: np.ndarray, predicted_median: np.ndarray) -> dict[str, float]:
    truth = np.asarray(actual, dtype=float)
    prediction = np.asarray(predicted_median, dtype=float)
    error = prediction - truth
    return {
        "mae_median": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "median_absolute_error": float(np.median(np.abs(error))),
        "bias": float(np.mean(error)),
    }


def distribution_quantile(
    probabilities: np.ndarray,
    lower_minutes: np.ndarray,
    quantile: float,
) -> np.ndarray:
    cdf = np.cumsum(np.asarray(probabilities, dtype=float), axis=1)
    indices = np.argmax(cdf >= quantile, axis=1)
    return np.asarray(lower_minutes, dtype=float)[indices]
