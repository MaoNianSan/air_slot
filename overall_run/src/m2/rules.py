from __future__ import annotations

import numpy as np


ALLOWED_RULE_TYPES = {
    "CONTINUOUS_ACCUMULATION",
    "EXCESS_ACCUMULATION",
    "PIECEWISE_MARGINAL",
    "THRESHOLD_EVENT",
    "BOUNDED_CONTEXT_MULTIPLIER",
}


def continuous(x: float, exposure: float = 1.0) -> float:
    return max(float(x), 0.0) * max(float(exposure), 0.0)


def excess(x: float, buffer: float = 0.0, exposure: float = 1.0) -> float:
    return max(float(x) - float(buffer), 0.0) * max(float(exposure), 0.0)


def piecewise(x: float, slopes: tuple[float, ...], breakpoints: tuple[float, ...]) -> float:
    if len(breakpoints) > 2 or len(slopes) != len(breakpoints) + 1:
        raise ValueError("M2_RULE_COMPLEXITY_LIMIT")
    result = float(slopes[0]) * max(float(x), 0.0)
    for slope, point in zip(slopes[1:], breakpoints):
        result += float(slope) * max(float(x) - float(point), 0.0)
    return max(result, 0.0)


def threshold(x: float, point: float, exposure: float = 1.0) -> float:
    return max(float(exposure), 0.0) if float(x) > float(point) else 0.0


def bounded_multiplier(value: float, gamma: float, lower: float = 1.0, upper: float = 2.0) -> float:
    return float(np.clip(1.0 + float(gamma) * float(value), lower, upper))
