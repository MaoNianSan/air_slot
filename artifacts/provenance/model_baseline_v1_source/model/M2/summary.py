"""Scenario-distribution summaries without collapsing M1 uncertainty in M2."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from model.M2.contracts import (
    ConsequenceState,
    ScenarioConsequence,
    ScenarioConsequenceDistribution,
)
from model.common.estimand import FormalEstimandStatus
from model.common.value_objects import FrozenModel


class ConsequenceDistributionSummary(FrozenModel):
    episode_id: str
    decision_node_id: str
    scenario_ids: tuple[int, ...]
    scenario_weights: tuple[float, ...]
    consequence_state: ConsequenceState = ConsequenceState.BASELINE
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    mean_cu: float | None
    variance_cu2: float | None
    cvar_alpha: float = Field(gt=0, lt=1)
    cvar_cu: float | None
    tail_threshold_cu: float
    tail_probability: float | None
    reason_code: str | None = None

    @model_validator(mode="after")
    def explicit_availability(self):
        values = (
            self.mean_cu,
            self.variance_cu2,
            self.cvar_cu,
            self.tail_probability,
        )
        if self.status == "AVAILABLE" and any(value is None for value in values):
            raise ValueError("M2_DISTRIBUTION_AVAILABLE_REQUIRES_ALL_METRICS")
        if self.status == "UNAVAILABLE" and (
            any(value is not None for value in values) or not self.reason_code
        ):
            raise ValueError("M2_DISTRIBUTION_UNAVAILABLE_REQUIRES_NULL_AND_REASON")
        return self


def summarize_formal_consequence(
    consequences: tuple[ScenarioConsequence, ...] | ScenarioConsequenceDistribution,
    *,
    cvar_alpha: float = 0.95,
    tail_threshold_cu: float = 0.0,
) -> ConsequenceDistributionSummary:
    """Summarize a single node's preserved scenario distribution."""
    if not 0.0 < cvar_alpha < 1.0:
        raise ValueError("M2_CVAR_ALPHA_OUT_OF_RANGE")
    items = (
        consequences.consequences
        if isinstance(consequences, ScenarioConsequenceDistribution)
        else consequences
    )
    if not items:
        raise ValueError("M2_DISTRIBUTION_REQUIRES_SCENARIOS")
    identities = {(item.episode_id, item.decision_node_id) for item in items}
    if len(identities) != 1:
        raise ValueError("M2_DISTRIBUTION_MIXED_DECISION_NODES")
    episode_id, decision_node_id = next(iter(identities))
    scenario_ids = tuple(item.scenario_id for item in items)
    scenario_weights = tuple(item.scenario_weight for item in items)
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError("M2_DISTRIBUTION_DUPLICATE_SCENARIO_ID")
    if any(
        item.formal_estimand_value.status is not FormalEstimandStatus.FORMAL_AVAILABLE
        for item in items
    ):
        return ConsequenceDistributionSummary(
            episode_id=episode_id,
            decision_node_id=decision_node_id,
            scenario_ids=scenario_ids,
            scenario_weights=scenario_weights,
            status="UNAVAILABLE",
            mean_cu=None,
            variance_cu2=None,
            cvar_alpha=cvar_alpha,
            cvar_cu=None,
            tail_threshold_cu=tail_threshold_cu,
            tail_probability=None,
            reason_code="FORMAL_SCENARIO_CONSEQUENCE_UNAVAILABLE",
        )

    total_weight = sum(item.scenario_weight for item in items)
    if abs(total_weight - 1.0) > 1e-6:
        raise ValueError("M2_DISTRIBUTION_WEIGHTS_MUST_SUM_TO_ONE")
    weighted = tuple(
        (float(item.formal_estimand_value.value_cu), item.scenario_weight)
        for item in items
    )
    mean = sum(value * weight for value, weight in weighted)
    variance = sum(weight * (value - mean) ** 2 for value, weight in weighted)
    tail_probability = sum(
        weight for value, weight in weighted if value >= tail_threshold_cu
    )
    tail_mass = 1.0 - cvar_alpha
    remaining = tail_mass
    tail_sum = 0.0
    for value, weight in sorted(weighted, reverse=True):
        take = min(weight, remaining)
        tail_sum += value * take
        remaining -= take
        if remaining <= 1e-12:
            break
    return ConsequenceDistributionSummary(
        episode_id=episode_id,
        decision_node_id=decision_node_id,
        scenario_ids=scenario_ids,
        scenario_weights=scenario_weights,
        status="AVAILABLE",
        mean_cu=mean,
        variance_cu2=variance,
        cvar_alpha=cvar_alpha,
        cvar_cu=tail_sum / tail_mass,
        tail_threshold_cu=tail_threshold_cu,
        tail_probability=tail_probability,
    )


__all__ = ["ConsequenceDistributionSummary", "summarize_formal_consequence"]
