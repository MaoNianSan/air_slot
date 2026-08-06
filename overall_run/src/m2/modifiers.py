from __future__ import annotations

from .rules import bounded_multiplier


def apply_bounded_exposure_modifier(
    quantity: float,
    context_value: float,
    *,
    gamma: float,
    lower: float,
    upper: float,
) -> float:
    return max(float(quantity), 0.0) * bounded_multiplier(
        context_value, gamma, lower, upper
    )
