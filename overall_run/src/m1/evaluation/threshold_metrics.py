from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    recall_score,
)


def exceedance_probability(
    probabilities: np.ndarray,
    lower_minutes: np.ndarray,
    threshold: float,
) -> np.ndarray:
    mask = np.asarray(lower_minutes, dtype=float) >= float(threshold)
    return np.asarray(probabilities, dtype=float)[:, mask].sum(axis=1)


def threshold_metrics(actual: np.ndarray, probability: np.ndarray, threshold: float) -> dict[str, float]:
    labels = np.asarray(actual, dtype=float) >= float(threshold)
    probs = np.asarray(probability, dtype=float)
    prediction = probs >= 0.5
    return {
        "brier": float(np.mean((probs - labels.astype(float)) ** 2)),
        "pr_auc": float(average_precision_score(labels, probs)) if labels.any() else float("nan"),
        "balanced_accuracy": float(balanced_accuracy_score(labels, prediction)),
        "recall": float(recall_score(labels, prediction, zero_division=0)),
        "f1": float(f1_score(labels, prediction, zero_division=0)),
        "accuracy": float(accuracy_score(labels, prediction)),
    }
