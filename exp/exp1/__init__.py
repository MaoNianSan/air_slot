"""Exp1 rolling-state adequacy evaluation primitives.

This package contains evaluation-only orchestration helpers.  Scientific model
semantics remain in :mod:`model` and are never reimplemented here.
"""

from .metrics import (
    energy_score,
    variogram_score,
    weighted_crps,
    weighted_wasserstein_1,
)
from .protocol import (
    BOOTSTRAP_REPS,
    COMPONENT_ORDER,
    PRIMARY_MODEL_HIDDEN_SIZE,
    ProtocolError,
    validate_primary_model,
)
from .representations import (
    JointRepresentation,
    MarginalRepresentation,
    PointRepresentation,
    ScenarioState,
    build_marginal,
    build_point,
)

__all__ = [
    "BOOTSTRAP_REPS",
    "COMPONENT_ORDER",
    "PRIMARY_MODEL_HIDDEN_SIZE",
    "ProtocolError",
    "validate_primary_model",
    "ScenarioState",
    "JointRepresentation",
    "PointRepresentation",
    "MarginalRepresentation",
    "build_point",
    "build_marginal",
    "weighted_crps",
    "weighted_wasserstein_1",
    "variogram_score",
    "energy_score",
]
