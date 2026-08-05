from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class DiscreteBins:
    lower_minutes: tuple[float, ...]
    upper_minutes: tuple[float | None, ...]

    @property
    def count(self) -> int:
        return len(self.lower_minutes)


def bins_to_upper(maximum_minutes: float, bin_minutes: int = 5) -> DiscreteBins:
    upper = max(bin_minutes, int(ceil(float(maximum_minutes) / bin_minutes)) * bin_minutes)
    lower = tuple(float(value) for value in range(0, upper + 1, bin_minutes))
    ends = tuple(float(value) for value in range(bin_minutes, upper + 1, bin_minutes)) + (None,)
    return DiscreteBins(lower, ends)


def predecessor_bins(bin_minutes: int = 5) -> DiscreteBins:
    return bins_to_upper(480, bin_minutes)


def learned_upper_bins(
    train_values: Iterable[float],
    *,
    quantile: float = 0.995,
    bin_minutes: int = 5,
) -> DiscreteBins:
    values = np.asarray(list(train_values), dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        raise ValueError("M1_TRAIN_BIN_SUPPORT_MISSING")
    return bins_to_upper(float(np.quantile(values, quantile)), bin_minutes)


def hard_label(value: float, bins: DiscreteBins) -> np.ndarray:
    result = np.zeros(bins.count, dtype=float)
    for index, (lower, upper) in enumerate(zip(bins.lower_minutes, bins.upper_minutes)):
        if upper is None or lower <= value < upper:
            result[index] = 1.0
            return result
    result[-1] = 1.0
    return result


def interval_soft_label(lower_value: float, upper_value: float, bins: DiscreteBins) -> np.ndarray:
    if upper_value < lower_value:
        raise ValueError("M1_SOFT_LABEL_INTERVAL_INVALID")
    if upper_value == lower_value:
        return hard_label(lower_value, bins)
    weights = np.zeros(bins.count, dtype=float)
    for index, (lower, upper) in enumerate(zip(bins.lower_minutes, bins.upper_minutes)):
        right = float("inf") if upper is None else upper
        overlap = max(0.0, min(upper_value, right) - max(lower_value, lower))
        weights[index] = overlap
    if weights.sum() <= 0:
        weights[-1] = 1.0
    return weights / weights.sum()
