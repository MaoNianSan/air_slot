"""M3 Train-derived Stage-II support (Phase 3).

The nominal specifications come from manuscript section 4:

- ``T^{turn,lb} = Q_0.20(T^turn | Train)`` with the 10th and 30th percentiles
  retained as sensitivity specifications;
- ``U_max = 5 * floor(Q_0.90(H^{+,fact}_Train) / 5)`` with the 80th and 95th
  percentiles retained as support sensitivities.

Both are empirical references, not certified physical minima. Quantiles are the
linear-interpolation (type-7/NumPy) definition over sorted Train values, and only
strictly positive factual headroom enters the ``U_max`` quantile.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from pydantic import Field

from model.common.decision_contracts import HeadroomSummary
from model.common.errors import ContractError
from model.common.value_objects import FrozenModel


__all__ = [
    "FLOOR_TO_MINUTES",
    "HEADROOM_QUANTILE_NOMINAL",
    "HEADROOM_QUANTILE_SENSITIVITY",
    "QUANTILE_RULE",
    "TURNAROUND_QUANTILE_ALLOWED",
    "TURNAROUND_QUANTILE_NOMINAL",
    "TURNAROUND_QUANTILE_SENSITIVITY",
    "TrainQuantileRule",
    "build_headroom_summary",
    "floor_to_grid",
    "max_recovery_minutes",
    "turnaround_lower_bound_minutes",
]


QUANTILE_RULE = "LINEAR_INTERPOLATION_SORTED_TRAIN"
TURNAROUND_QUANTILE_NOMINAL = 0.20
TURNAROUND_QUANTILE_SENSITIVITY: tuple[float, ...] = (0.10, 0.30)
TURNAROUND_QUANTILE_ALLOWED: tuple[float, ...] = (
    TURNAROUND_QUANTILE_SENSITIVITY[0],
    TURNAROUND_QUANTILE_NOMINAL,
    TURNAROUND_QUANTILE_SENSITIVITY[1],
)
HEADROOM_QUANTILE_NOMINAL = 0.90
HEADROOM_QUANTILE_SENSITIVITY: tuple[float, ...] = (0.80, 0.95)
HEADROOM_QUANTILE_ALLOWED: tuple[float, ...] = (
    HEADROOM_QUANTILE_SENSITIVITY[0],
    HEADROOM_QUANTILE_NOMINAL,
    HEADROOM_QUANTILE_SENSITIVITY[1],
)
FLOOR_TO_MINUTES = 5.0


class TrainQuantileRule(FrozenModel):
    """Manuscript-predefined quantile specification for the Stage-II boundary."""

    turnaround_quantile: float = Field(default=TURNAROUND_QUANTILE_NOMINAL, gt=0.0, lt=1.0)
    headroom_quantile: float = Field(default=HEADROOM_QUANTILE_NOMINAL, gt=0.0, lt=1.0)
    floor_to_minutes: float = Field(default=FLOOR_TO_MINUTES, gt=0.0)
    turnaround_allowed: tuple[float, ...] = TURNAROUND_QUANTILE_ALLOWED
    headroom_allowed: tuple[float, ...] = HEADROOM_QUANTILE_ALLOWED
    quantile_rule: str = QUANTILE_RULE

    def validate(self) -> "TrainQuantileRule":
        if not any(
            abs(self.turnaround_quantile - allowed) <= 1e-9
            for allowed in self.turnaround_allowed
        ):
            raise ContractError(
                "M3_TURNAROUND_QUANTILE_OUTSIDE_MANUSCRIPT_SPECIFICATION:"
                f"{self.turnaround_quantile}"
            )
        if not any(
            abs(self.headroom_quantile - allowed) <= 1e-9
            for allowed in self.headroom_allowed
        ):
            raise ContractError(
                "M3_HEADROOM_QUANTILE_OUTSIDE_MANUSCRIPT_SPECIFICATION:"
                f"{self.headroom_quantile}"
            )
        return self


def _quantile(values: Sequence[float], q: float) -> float:
    resolved = np.asarray([float(value) for value in values], dtype=float)
    if resolved.size == 0:
        raise ContractError("M3_TRAIN_QUANTILE_EMPTY_INPUT")
    if not np.all(np.isfinite(resolved)):
        raise ContractError("M3_TRAIN_QUANTILE_NON_FINITE_INPUT")
    return float(np.quantile(resolved, q))


def turnaround_lower_bound_minutes(
    turnaround_minutes: Sequence[float],
    *,
    quantile: float = TURNAROUND_QUANTILE_NOMINAL,
) -> float:
    """``T^{turn,lb} = Q_q(T^turn | Train)`` at a manuscript-predefined quantile."""

    rule = TrainQuantileRule(turnaround_quantile=quantile).validate()
    return _quantile(turnaround_minutes, rule.turnaround_quantile)


def floor_to_grid(value: float, *, floor_to_minutes: float = FLOOR_TO_MINUTES) -> float:
    """``floor_to_minutes * floor(value / floor_to_minutes)``."""

    if floor_to_minutes <= 0.0:
        raise ContractError("M3_FLOOR_TO_MINUTES_NOT_POSITIVE")
    if value < 0.0:
        raise ContractError("M3_FLOOR_NEGATIVE_VALUE")
    return float(floor_to_minutes * np.floor(float(value) / floor_to_minutes))


def max_recovery_minutes(
    headroom_minutes: Sequence[float],
    *,
    quantile: float = HEADROOM_QUANTILE_NOMINAL,
    floor_to_minutes: float = FLOOR_TO_MINUTES,
) -> float:
    """``U_max`` from strictly positive factual Train headroom."""

    rule = TrainQuantileRule(
        headroom_quantile=quantile, floor_to_minutes=floor_to_minutes
    ).validate()
    positive = [float(value) for value in headroom_minutes if float(value) > 0.0]
    if not positive:
        raise ContractError("M3_NO_POSITIVE_TRAIN_HEADROOM")
    return floor_to_grid(
        _quantile(positive, rule.headroom_quantile),
        floor_to_minutes=rule.floor_to_minutes,
    )


def build_headroom_summary(
    *,
    turnaround_minutes: Sequence[float],
    headroom_minutes: Sequence[float],
    source_id: str,
    turnaround_quantile: float = TURNAROUND_QUANTILE_NOMINAL,
    headroom_quantile: float = HEADROOM_QUANTILE_NOMINAL,
    floor_to_minutes: float = FLOOR_TO_MINUTES,
) -> HeadroomSummary:
    """Materialize the representation-independent Train-side action cap."""

    rule = TrainQuantileRule(
        turnaround_quantile=turnaround_quantile,
        headroom_quantile=headroom_quantile,
        floor_to_minutes=floor_to_minutes,
    ).validate()
    positive_headroom = [
        float(value) for value in headroom_minutes if float(value) > 0.0
    ]
    if not positive_headroom:
        raise ContractError("M3_NO_POSITIVE_TRAIN_HEADROOM")
    return HeadroomSummary(
        u_max=max_recovery_minutes(
            headroom_minutes,
            quantile=rule.headroom_quantile,
            floor_to_minutes=rule.floor_to_minutes,
        ),
        turnaround_lower_bound_q=_quantile(
            turnaround_minutes, rule.turnaround_quantile
        ),
        turnaround_quantile=rule.turnaround_quantile,
        headroom_quantile=rule.headroom_quantile,
        headroom_positive_n=len(positive_headroom),
        source_id=source_id,
        floor_to_minutes=rule.floor_to_minutes,
    )
