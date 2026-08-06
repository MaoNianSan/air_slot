from __future__ import annotations

import math

import numpy as np


ALLOWED_RULE_TYPES = {
    "CONTINUOUS_ACCUMULATION",
    "EXCESS_ACCUMULATION",
    "PIECEWISE_MARGINAL",
    "THRESHOLD_EVENT",
    "BOUNDED_CONTEXT_MULTIPLIER",
}


def _finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"M2_RULE_INPUT_NONFINITE:{name}")
    return result


def _nonnegative(value: float, name: str) -> float:
    return max(_finite(value, name), 0.0)


def continuous(x: float, exposure: float = 1.0) -> float:
    return _nonnegative(x, "x") * _nonnegative(exposure, "exposure")


def excess(x: float, buffer: float = 0.0, exposure: float = 1.0) -> float:
    return max(_finite(x, "x") - _finite(buffer, "buffer"), 0.0) * _nonnegative(
        exposure, "exposure"
    )


def piecewise(
    x: float,
    slopes: tuple[float, ...],
    breakpoints: tuple[float, ...],
) -> float:
    if len(breakpoints) > 2 or len(slopes) != len(breakpoints) + 1:
        raise ValueError("M2_RULE_COMPLEXITY_LIMIT")
    value = _nonnegative(x, "x")
    clean_slopes = tuple(_finite(slope, "slope") for slope in slopes)
    clean_breakpoints = tuple(_nonnegative(point, "breakpoint") for point in breakpoints)
    if clean_breakpoints != tuple(sorted(clean_breakpoints)):
        raise ValueError("M2_RULE_BREAKPOINT_ORDER_INVALID")
    result = clean_slopes[0] * value
    for slope, point in zip(clean_slopes[1:], clean_breakpoints):
        result += slope * max(value - point, 0.0)
    return max(result, 0.0)


def threshold(x: float, point: float, exposure: float = 1.0) -> float:
    return _nonnegative(exposure, "exposure") if _finite(x, "x") > _finite(
        point, "point"
    ) else 0.0


def bounded_multiplier(
    value: float,
    gamma: float,
    lower: float,
    upper: float,
) -> float:
    context = _finite(value, "context")
    if not 0.0 <= context <= 1.0:
        raise ValueError("M2_CONTEXT_UNIT_INTERVAL_REQUIRED")
    gamma_value = _finite(gamma, "gamma")
    lower_value = _finite(lower, "lower")
    upper_value = _finite(upper, "upper")
    if lower_value < 1.0 or upper_value < lower_value:
        raise ValueError("M2_CONTEXT_MULTIPLIER_BOUNDS_INVALID")
    return float(
        np.clip(1.0 + gamma_value * context, lower_value, upper_value)
    )
