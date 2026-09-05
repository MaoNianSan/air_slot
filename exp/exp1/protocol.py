"""Frozen Exp1 protocol constants and lightweight contract checks."""

from __future__ import annotations

from dataclasses import dataclass

PRIMARY_MODEL_HIDDEN_SIZE = 16
LOWER_CAPACITY_HIDDEN_SIZE = 8
HIGHER_CAPACITY_HIDDEN_SIZE = 32
BOOTSTRAP_REPS = 2000
CI_LEVEL = 0.95
VARIOGRAM_P = 0.5
HISTORY_VARIANTS = ("H16_HISTORY", "H16_CURRENT")
REPRESENTATIONS = ("Joint", "Point", "Marginal")
COMPONENT_ORDER = (
    "F_continuity",
    "F_execution",
    "F_propagation",
    "P_time",
    "P_itinerary",
    "P_service",
    "R_operating",
)


class ProtocolError(ValueError):
    """Raised when an Exp1 contract invariant is violated."""


@dataclass(frozen=True)
class Exp1Protocol:
    primary_hidden_size: int = PRIMARY_MODEL_HIDDEN_SIZE
    bootstrap_reps: int = BOOTSTRAP_REPS
    ci_level: float = CI_LEVEL
    variogram_p: float = VARIOGRAM_P
    history_variants: tuple[str, ...] = HISTORY_VARIANTS

    def validate(self) -> None:
        validate_primary_model(self.primary_hidden_size)
        if self.bootstrap_reps != BOOTSTRAP_REPS:
            raise ProtocolError("EXP1_BOOTSTRAP_REPS_MUST_BE_2000")
        if self.ci_level != CI_LEVEL:
            raise ProtocolError("EXP1_CI_LEVEL_MUST_BE_0.95")
        if self.variogram_p != VARIOGRAM_P:
            raise ProtocolError("EXP1_PRIMARY_VARIogram_P_MUST_BE_0.5")
        if self.history_variants != HISTORY_VARIANTS:
            raise ProtocolError("EXP1_HISTORY_VARIANTS_INVALID")


def validate_primary_model(hidden_size: int) -> None:
    if int(hidden_size) != PRIMARY_MODEL_HIDDEN_SIZE:
        raise ProtocolError("EXP1_PRIMARY_MODEL_MUST_BE_H16")


def validate_capacity_sensitivity(hidden_size: int) -> None:
    if int(hidden_size) not in (LOWER_CAPACITY_HIDDEN_SIZE, HIGHER_CAPACITY_HIDDEN_SIZE):
        raise ProtocolError("EXP1_CAPACITY_SENSITIVITY_MUST_BE_H8_OR_H32")
