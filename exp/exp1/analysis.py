"""Small pure analysis helpers for Exp1 summary construction."""

from __future__ import annotations

from typing import Mapping, Sequence

from .metrics import variogram_score, weighted_crps, weighted_wasserstein_1
from .representations import JointRepresentation, MarginalRepresentation, PointRepresentation


def history_delta_crps(
    history_values: Sequence[float],
    history_weights: Sequence[float],
    current_values: Sequence[float],
    current_weights: Sequence[float],
    observation: float,
) -> tuple[float, float, float]:
    history = weighted_crps(history_values, history_weights, observation)
    current = weighted_crps(current_values, current_weights, observation)
    return history, current, history - current


def state_variogram_contrasts(
    joint: JointRepresentation,
    point: PointRepresentation,
    marginal: MarginalRepresentation,
    observation: Sequence[float],
    *,
    p: float = 0.5,
) -> tuple[float, float, float]:
    joint_score = variogram_score(joint.values, joint.weights, observation, p=p)
    point_score = variogram_score(point.values, point.weights, observation, p=p)
    marginal_score = variogram_score(
        marginal.values,
        marginal.weights,
        observation,
        p=p,
        marginal_values=tuple(tuple(value for value, _ in axis) for axis in marginal.marginals),
        marginal_weights=tuple(tuple(weight for _, weight in axis) for axis in marginal.marginals),
    )
    return point_score - joint_score, marginal_score - joint_score, joint_score


def consequence_wasserstein(
    variant_values: Sequence[float],
    variant_weights: Sequence[float],
    joint_values: Sequence[float],
    joint_weights: Sequence[float],
    scale: float,
) -> float:
    if scale <= 0:
        raise ValueError("EXP1_COMPONENT_SCALE_MUST_BE_POSITIVE")
    return weighted_wasserstein_1(
        variant_values, variant_weights, joint_values, joint_weights
    ) / float(scale)
