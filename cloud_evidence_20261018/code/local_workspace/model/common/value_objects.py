from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import (
    AvailabilityBasis, DecisionTimeRole, EvidenceClass, SupportState,
    weaker_or_equal,
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", use_enum_values=False)


class ProvenanceRef(FrozenModel):
    dataset_instance_id: str = Field(min_length=1)
    logical_source: str = Field(min_length=1)
    source_record_id: str | None = None
    source_field: str | None = None
    rule_id: str = Field(min_length=1)
    source_version: str = Field(min_length=1)


class TimeContext(FrozenModel):
    event_time: datetime | None = None
    availability_time: datetime | None = None
    availability_basis: AvailabilityBasis
    reference_period: str | None = None
    schedule_time: datetime | None = None
    decision_time_role: DecisionTimeRole

    @model_validator(mode="after")
    def validate_time_semantics(self):
        for value in (self.event_time, self.availability_time, self.schedule_time):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("timestamps must be timezone-aware UTC")
            if value is not None and value.astimezone(timezone.utc).utcoffset() is None:
                raise ValueError("invalid timestamp")
        if self.availability_basis in {
            AvailabilityBasis.OBSERVED_AVAILABILITY,
            AvailabilityBasis.REPLAY_EVENT_TIME,
        } and self.availability_time is None:
            raise ValueError("availability_time required for observed/replay evidence")
        if self.availability_basis in {
            AvailabilityBasis.POSTHOC_ONLY, AvailabilityBasis.UNAVAILABLE,
        } and self.decision_time_role is DecisionTimeRole.INFERENCE_EVIDENCE:
            raise ValueError("post-hoc/unavailable records cannot be inference evidence")
        return self


class SupportedValue(FrozenModel):
    value: Any | None
    unit: str = Field(min_length=1)
    evidence_class: EvidenceClass
    support_ceiling: EvidenceClass
    support_state: SupportState
    formal_input_support: EvidenceClass | None = None
    realized_outcome_support: EvidenceClass | None = None
    reason_code: str | None = None
    quality_flags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_support(self):
        if not weaker_or_equal(self.evidence_class, self.support_ceiling):
            raise ValueError("evidence_class exceeds support_ceiling")
        abstaining = (
            self.support_state is SupportState.ABSTAIN
            or self.evidence_class is EvidenceClass.UNSUPPORTED
        )
        if abstaining and (self.value is not None or not self.reason_code):
            raise ValueError("unsupported/abstain requires null value and reason_code")
        if self.value is None and not self.reason_code:
            raise ValueError("null value requires reason_code")
        if self.support_state is SupportState.DEGRADED and not self.reason_code:
            raise ValueError("degraded value requires reason_code")
        if tuple(sorted(self.quality_flags)) != self.quality_flags:
            raise ValueError("quality_flags must be sorted")
        return self
