from typing import Literal, Sequence

from pydantic import Field, model_validator

from model.common.value_objects import FrozenModel

from .contracts import AlignedScenario


PRINCIPAL_WARNING_EVENT = "D_TO_POST_GT_30"
PRINCIPAL_WARNING_THRESHOLD_MINUTES = 30.0


class WarningProbability(FrozenModel):
    """Weighted probability for the frozen signed-M1 takeoff-delay event."""

    episode_id: str | None
    decision_node_id: str | None
    event_id: str
    comparison: Literal["STRICT_GT"] = "STRICT_GT"
    delay_threshold_minutes: float = Field(ge=0)
    probability: float | None = Field(default=None, ge=0, le=1)
    support_state: Literal["SUPPORTED", "ABSTAIN"]
    reason_code: str
    scenario_count: int = Field(ge=0)
    scenario_weight_sum: float = Field(ge=0)
    exceedance_weight: float = Field(ge=0)
    estimator: Literal["WEIGHTED_ALIGNED_SCENARIO_FREQUENCY"] = (
        "WEIGHTED_ALIGNED_SCENARIO_FREQUENCY"
    )
    tail_value_policy: Literal["TARGET_BIN_REPRESENTATIVE"] = "TARGET_BIN_REPRESENTATIVE"
    tail_representative_used: bool = False
    taxi_reference_id: str | None = None
    taxi_reference_hash: str | None = None

    @model_validator(mode="after")
    def status_matches_probability(self):
        if self.support_state == "SUPPORTED" and self.probability is None:
            raise ValueError("supported warning probability requires a value")
        if self.support_state == "ABSTAIN" and self.probability is not None:
            raise ValueError("abstained warning probability cannot carry a value")
        return self


def warning_probability(
    scenarios: Sequence[AlignedScenario],
    *,
    threshold_minutes: float = PRINCIPAL_WARNING_THRESHOLD_MINUTES,
    event_id: str = PRINCIPAL_WARNING_EVENT,
) -> WarningProbability:
    """Estimate P(D_TO > threshold) from one aligned joint-scenario bundle.

    The function never drops unsupported scenarios. If the train-frozen taxi
    reference or any derived D_TO value is unavailable, the whole node abstains.
    """

    if threshold_minutes < 0:
        raise ValueError("warning threshold must be nonnegative")
    rows = tuple(scenarios)
    if not rows:
        return WarningProbability(
            episode_id=None,
            decision_node_id=None,
            event_id=event_id,
            delay_threshold_minutes=threshold_minutes,
            support_state="ABSTAIN",
            reason_code="NO_ALIGNED_SCENARIOS",
            scenario_count=0,
            scenario_weight_sum=0.0,
            exceedance_weight=0.0,
        )

    identities = {(row.episode_id, row.decision_node_id) for row in rows}
    if len(identities) != 1:
        raise ValueError("warning probability requires one episode/decision node")
    if len({row.scenario_id for row in rows}) != len(rows):
        raise ValueError("warning probability requires unique scenario ids")
    if any(row.scenario_weight <= 0 for row in rows):
        raise ValueError("warning probability requires positive scenario weights")

    episode_id, decision_node_id = next(iter(identities))
    weight_sum = float(sum(row.scenario_weight for row in rows))
    reference_ids = {row.taxi_reference_id for row in rows}
    reference_hashes = {row.taxi_reference_hash for row in rows}
    reference_states = {row.taxi_reference_support_state for row in rows}
    formal_reference = (
        len(reference_ids) == 1
        and None not in reference_ids
        and len(reference_hashes) == 1
        and None not in reference_hashes
        and reference_states == {"SUPPORTED"}
    )
    derived = tuple(row.d_to_minutes for row in rows)
    tail_used = any(
        row.underflow_delta_ob or row.overflow_delta_ob or row.overflow_tx
        for row in rows
    )
    if not formal_reference or any(value is None for value in derived):
        return WarningProbability(
            episode_id=episode_id,
            decision_node_id=decision_node_id,
            event_id=event_id,
            delay_threshold_minutes=threshold_minutes,
            support_state="ABSTAIN",
            reason_code="TRAIN_FROZEN_TAXI_REFERENCE_OR_D_TO_UNAVAILABLE",
            scenario_count=len(rows),
            scenario_weight_sum=weight_sum,
            exceedance_weight=0.0,
            tail_representative_used=tail_used,
            taxi_reference_id=next(iter(reference_ids)) if len(reference_ids) == 1 else None,
            taxi_reference_hash=next(iter(reference_hashes)) if len(reference_hashes) == 1 else None,
        )

    exceedance_weight = float(
        sum(
            row.scenario_weight
            for row, value in zip(rows, derived)
            if value is not None and value > threshold_minutes
        )
    )
    return WarningProbability(
        episode_id=episode_id,
        decision_node_id=decision_node_id,
        event_id=event_id,
        delay_threshold_minutes=threshold_minutes,
        probability=exceedance_weight / weight_sum,
        support_state="SUPPORTED",
        reason_code="SIGNED_D_TO_ALIGNED_SCENARIOS",
        scenario_count=len(rows),
        scenario_weight_sum=weight_sum,
        exceedance_weight=exceedance_weight,
        tail_representative_used=tail_used,
        taxi_reference_id=next(iter(reference_ids)),
        taxi_reference_hash=next(iter(reference_hashes)),
    )
