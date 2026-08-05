from __future__ import annotations

from typing import Any

import numpy as np

from .distribution_metrics import (
    discrete_crps,
    interval_metrics,
    negative_log_likelihood,
    overflow_rate,
)
from .point_metrics import distribution_quantile, point_metrics
from .threshold_metrics import exceedance_probability, threshold_metrics


def evaluate_distribution(
    actual: np.ndarray,
    actual_indices: np.ndarray,
    raw_probabilities: np.ndarray,
    calibrated_probabilities: np.ndarray,
    lower_minutes: np.ndarray,
    thresholds: tuple[int, ...] = (15, 30, 60),
) -> dict[str, Any]:
    def metrics(probabilities: np.ndarray) -> dict[str, float]:
        median = distribution_quantile(probabilities, lower_minutes, 0.5)
        result = {
            **point_metrics(actual, median),
            "crps": discrete_crps(actual, probabilities, lower_minutes),
            "nll": negative_log_likelihood(actual_indices, probabilities),
            "overflow_rate": overflow_rate(probabilities),
            **interval_metrics(actual, probabilities, lower_minutes, 0.5),
            **interval_metrics(actual, probabilities, lower_minutes, 0.9),
        }
        for threshold in thresholds:
            probability = exceedance_probability(probabilities, lower_minutes, threshold)
            result.update(
                {
                    f"threshold_{threshold}_{key}": value
                    for key, value in threshold_metrics(actual, probability, threshold).items()
                }
            )
        return result

    raw = metrics(raw_probabilities)
    calibrated = metrics(calibrated_probabilities)
    return {
        "raw_metrics": raw,
        "calibrated_metrics": calibrated,
        "delta_metrics": {key: calibrated[key] - raw[key] for key in raw},
    }
