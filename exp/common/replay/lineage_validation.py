"""Generic replay lineage checks across selected PRE, M1, and M2 envelopes."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .episode_replay import ReplayEpisodeRecord, ReplayScenarioBinding


class ReplayConsequenceBinding(BaseModel):
    """M2 input that must preserve a constructed M1 scenario identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    ERROR_NAMESPACE: ClassVar[str] = "REPLAY"

    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    scenario_ids: tuple[int, ...] = Field(min_length=1)
    scenario_lineage: tuple[str, ...] = Field(min_length=1)

    def reason_code(self, suffix: str) -> str:
        return f"{type(self).ERROR_NAMESPACE}_{suffix}"

    @model_validator(mode="after")
    def validate_scenario_identity(self) -> "ReplayConsequenceBinding":
        if len(self.scenario_ids) != len(set(self.scenario_ids)):
            raise ValueError(self.reason_code("DUPLICATE_SCENARIO_ID"))
        if len(self.scenario_lineage) != len(set(self.scenario_lineage)):
            raise ValueError(self.reason_code("DUPLICATE_SCENARIO_LINEAGE_ID"))
        return self


class ReplayLineageValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pre_compatible: bool
    m1_compatible: bool
    m2_compatible: bool
    reason_codes: tuple[str, ...]


def validate_replay_lineage(
    episode: ReplayEpisodeRecord,
    decision_node_id: str,
    m1: ReplayScenarioBinding,
    m2: ReplayConsequenceBinding,
) -> ReplayLineageValidationResult:
    """Require identity, cutoff, and scenario preservation without scoring outputs."""
    if not isinstance(episode, ReplayEpisodeRecord):
        raise TypeError("REPLAY_EPISODE_RECORD_REQUIRED")
    if not isinstance(m1, ReplayScenarioBinding):
        raise TypeError("REPLAY_SCENARIO_BINDING_REQUIRED")
    if not isinstance(m2, ReplayConsequenceBinding):
        raise TypeError("REPLAY_CONSEQUENCE_BINDING_REQUIRED")

    reasons: list[str] = []
    record = next(
        (item for item in episode.decision_records if item.decision_node_id == decision_node_id),
        None,
    )
    pre_compatible = record is not None
    if record is None:
        reasons.append("PRE_DECISION_NODE_MISSING_FROM_REPLAY_EPISODE")
    else:
        if record.information_cutoff > record.decision_time:
            pre_compatible = False
            reasons.append("PRE_INFORMATION_CUTOFF_EXCEEDS_DECISION_TIME")
        if any(
            value > record.information_cutoff
            for value in record.legal_record_availability_times
        ):
            pre_compatible = False
            reasons.append("PRE_FUTURE_INFORMATION_LEAKAGE")

    m1_compatible = pre_compatible
    if (m1.episode_id, m1.decision_node_id) != (episode.episode_id, decision_node_id):
        m1_compatible = False
        reasons.append("M1_SCENARIO_IDENTITY_MISMATCH")
    if record is not None and (
        m1.decision_time != record.decision_time
        or m1.information_cutoff != record.information_cutoff
    ):
        m1_compatible = False
        reasons.append("M1_DECISION_TIME_ALIGNMENT_MISMATCH")
    if m1.scenario_lineage != episode.scenario_lineage:
        m1_compatible = False
        reasons.append("M1_SCENARIO_LINEAGE_MISMATCH")
    if len(m1.scenario_ids) != len(set(m1.scenario_ids)):
        m1_compatible = False
        reasons.append("M1_DUPLICATE_SCENARIO_ID")

    m2_compatible = m1_compatible
    if (m2.episode_id, m2.decision_node_id) != (episode.episode_id, decision_node_id):
        m2_compatible = False
        reasons.append("M2_CONSEQUENCE_IDENTITY_MISMATCH")
    if m2.scenario_ids != m1.scenario_ids:
        m2_compatible = False
        reasons.append("M2_SCENARIO_IDENTITY_NOT_PRESERVED")
    if m2.scenario_lineage != m1.scenario_lineage:
        m2_compatible = False
        reasons.append("M2_SCENARIO_LINEAGE_NOT_PRESERVED")
    return ReplayLineageValidationResult(
        pre_compatible=pre_compatible,
        m1_compatible=m1_compatible,
        m2_compatible=m2_compatible,
        reason_codes=tuple(reasons) or (episode.reason_code("LINEAGE_COMPATIBLE"),),
    )


__all__ = [
    "ReplayConsequenceBinding",
    "ReplayLineageValidationResult",
    "validate_replay_lineage",
]
