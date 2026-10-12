"""Bootstrap utilities for JATM Section 5."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np


def percentile_ci(values: Sequence[float], *, alpha: float = 0.05) -> tuple[float | None, float | None]:
    array = np.asarray([float(value) for value in values if value is not None], dtype=float)
    if array.size == 0:
        return None, None
    return float(np.quantile(array, alpha / 2.0)), float(np.quantile(array, 1.0 - alpha / 2.0))


def paired_information_increment_contrast(
    point_values: Sequence[float],
    marginal_values: Sequence[float],
    *,
    seed: int,
    replicates: int = 2000,
) -> dict[str, float | int | None]:
    """Paired episode bootstrap of ``Point - Marginal`` losses."""

    point = np.asarray(point_values, dtype=float)
    marginal = np.asarray(marginal_values, dtype=float)
    if point.shape != marginal.shape:
        raise ValueError("PAIRED_INCREMENT_SHAPE_MISMATCH")
    if point.ndim != 1 or point.size == 0:
        raise ValueError("PAIRED_INCREMENT_REQUIRES_NONEMPTY_VECTOR")
    mask = np.isfinite(point) & np.isfinite(marginal)
    point = point[mask]
    marginal = marginal[mask]
    if point.size == 0:
        return {
            "estimate": None,
            "ci_low": None,
            "ci_high": None,
            "replicate_count": 0,
        }
    rng = np.random.default_rng(int(seed))
    estimates = np.empty(int(replicates), dtype=float)
    for index in range(int(replicates)):
        draw = rng.integers(0, point.size, size=point.size)
        estimates[index] = float(np.mean(point[draw] - marginal[draw]))
    return {
        "estimate": float(np.mean(point - marginal)),
        "ci_low": float(np.quantile(estimates, 0.025)),
        "ci_high": float(np.quantile(estimates, 0.975)),
        "replicate_count": int(replicates),
    }


def bootstrap_estimates(
    *,
    episode_ids: Sequence[str],
    seed: int,
    replicates: int,
    statistic: Callable[[Sequence[str]], float | None],
) -> np.ndarray:
    ids = tuple(str(value) for value in episode_ids)
    if not ids:
        raise ValueError("BOOTSTRAP_EMPTY_EPISODE_POPULATION")
    rng = np.random.default_rng(int(seed))
    values: list[float] = []
    for _ in range(int(replicates)):
        draw = rng.integers(0, len(ids), size=len(ids))
        value = statistic(tuple(ids[index] for index in draw))
        if value is not None and np.isfinite(float(value)):
            values.append(float(value))
    return np.asarray(values, dtype=float)


def summarize_bootstrap(values: np.ndarray, *, estimate: float | None) -> dict[str, float | int | None]:
    if values.size == 0:
        return {
            "estimate": estimate,
            "ci_low": None,
            "ci_high": None,
            "replicate_count": 0,
        }
    return {
        "estimate": estimate,
        "ci_low": float(np.quantile(values, 0.025)),
        "ci_high": float(np.quantile(values, 0.975)),
        "replicate_count": int(values.size),
    }


__all__ = [
    "bootstrap_estimates",
    "paired_information_increment_contrast",
    "percentile_ci",
    "summarize_bootstrap",
]
