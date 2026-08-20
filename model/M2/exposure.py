"""Decision-visible node-specific operational exposure for M2 V2."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import Field, model_validator

from model.M2.contracts import (
    ExposureConfidence,
    ExposureSupportLevel,
    ScientificContextValue,
    SourceType,
)
from model.PRE.transformation import ConstructionType
from model.common.enums import EvidenceClass, SupportState
from model.common.identity import content_id
from model.common.value_objects import FrozenModel


class ScheduledLegReference(FrozenModel):
    """Schedule-only leg visible at the decision cutoff.

    Realized departure/arrival fields are deliberately absent and rejected by
    the strict model, preventing future operational outcomes from entering M2.
    """

    flight_id: str = Field(min_length=1)
    aircraft_id: str = Field(min_length=1)
    origin_airport_id: str = Field(min_length=1)
    destination_airport_id: str = Field(min_length=1)
    scheduled_departure_utc: datetime
    scheduled_arrival_utc: datetime
    availability_time_utc: datetime
    reference_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_schedule_times(self):
        for value in (
            self.scheduled_departure_utc,
            self.scheduled_arrival_utc,
            self.availability_time_utc,
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("M2_SCHEDULE_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        if self.scheduled_arrival_utc < self.scheduled_departure_utc:
            raise ValueError("M2_SCHEDULE_ARRIVAL_PRECEDES_DEPARTURE")
        return self


class NodeExposureRequest(FrozenModel):
    decision_node_id: str = Field(min_length=1)
    current_flight_id: str = Field(min_length=1)
    current_aircraft_id: str | None = None
    connection_airport_id: str = Field(min_length=1)
    successor_destination_airport_id: str = Field(min_length=1)
    scheduled_arrival_anchor_utc: datetime
    information_cutoff_utc: datetime
    schedule_snapshot_complete: bool = False
    horizon_minutes: int = Field(default=360, gt=0)

    @model_validator(mode="after")
    def aware_times(self):
        for value in (
            self.scheduled_arrival_anchor_utc,
            self.information_cutoff_utc,
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("M2_EXPOSURE_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return self


class NodeExposureReferences(FrozenModel):
    same_route: ScientificContextValue | None = None
    airport: ScientificContextValue | None = None
    global_reference: ScientificContextValue | None = None


def _reference_fallback(
    value: ScientificContextValue | None,
    *,
    level: ExposureSupportLevel,
    confidence: ExposureConfidence,
) -> ScientificContextValue | None:
    if value is None or value.support_state is SupportState.ABSTAIN:
        return None
    return value.model_copy(
        update={
            "support_level": level,
            "confidence": confidence,
            "reference_source": value.object_id,
            "provenance": tuple(
                sorted(set((*value.provenance, f"fallback_level={level.value}")))
            ),
        }
    )


def resolve_node_specific_exposure(
    request: NodeExposureRequest,
    schedule_legs: tuple[ScheduledLegReference, ...],
    references: NodeExposureReferences,
) -> ScientificContextValue:
    """Resolve exposure using the frozen V2 hierarchy.

    Hierarchy: same-aircraft successor chain, same-route reference, airport
    reference, global reference. A complete decision-visible schedule makes a
    zero same-aircraft count a supported zero; missing evidence never does.
    """
    cutoff = request.information_cutoff_utc.astimezone(timezone.utc)
    for leg in schedule_legs:
        if leg.availability_time_utc.astimezone(timezone.utc) > cutoff:
            raise ValueError("M2_FUTURE_SCHEDULE_REFERENCE_NOT_VISIBLE")

    if request.current_aircraft_id and request.schedule_snapshot_complete:
        anchor = request.scheduled_arrival_anchor_utc
        horizon = anchor + timedelta(minutes=request.horizon_minutes)
        successors = tuple(
            leg
            for leg in schedule_legs
            if leg.flight_id != request.current_flight_id
            and leg.aircraft_id == request.current_aircraft_id
            and leg.origin_airport_id == request.connection_airport_id
            and anchor < leg.scheduled_departure_utc <= horizon
        )
        reference_ids = tuple(sorted({leg.reference_id for leg in schedule_legs}))
        return ScientificContextValue(
            object_id=f"M2_NODE_EXPOSURE:{request.decision_node_id}",
            value=float(len(successors)),
            unit="legs",
            support_state=SupportState.SUPPORTED,
            evidence_class=EvidenceClass.DERIVED,
            construction_type=ConstructionType.RELATIONAL_DERIVATION,
            source_time=request.information_cutoff_utc,
            provenance=(
                f"decision_node_id={request.decision_node_id}",
                f"horizon_minutes={request.horizon_minutes}",
                *(f"schedule_reference_id={item}" for item in reference_ids),
                *(f"successor_flight_id={leg.flight_id}" for leg in successors),
            ),
            source_type=SourceType.DATA,
            support_level=ExposureSupportLevel.SAME_AIRCRAFT_SUCCESSOR_CHAIN,
            reference_source="DECISION_VISIBLE_SCHEDULE_SNAPSHOT",
            reference_id=content_id(
                {"schedule_reference_ids": reference_ids}
            ),
            reference_version="M2_NODE_SCHEDULE_EXPOSURE_V1",
            confidence=ExposureConfidence.HIGH,
        )

    ordered = (
        (
            references.same_route,
            ExposureSupportLevel.SAME_ROUTE_PROPAGATION,
            ExposureConfidence.MEDIUM,
        ),
        (
            references.airport,
            ExposureSupportLevel.AIRPORT_REFERENCE,
            ExposureConfidence.LOW,
        ),
        (
            references.global_reference,
            ExposureSupportLevel.GLOBAL_REFERENCE,
            ExposureConfidence.LOW,
        ),
    )
    for value, level, confidence in ordered:
        resolved = _reference_fallback(value, level=level, confidence=confidence)
        if resolved is not None:
            return resolved

    return ScientificContextValue(
        object_id=f"M2_NODE_EXPOSURE:{request.decision_node_id}",
        value=None,
        unit="legs",
        support_state=SupportState.ABSTAIN,
        evidence_class=EvidenceClass.UNSUPPORTED,
        construction_type=ConstructionType.UNSUPPORTED,
        reason_code="NO_NODE_ROUTE_AIRPORT_OR_GLOBAL_EXPOSURE",
        source_type=SourceType.DATA,
        support_level=ExposureSupportLevel.UNSUPPORTED,
        reference_source="NONE",
        confidence=ExposureConfidence.NONE,
    )


__all__ = [
    "NodeExposureReferences",
    "NodeExposureRequest",
    "ScheduledLegReference",
    "resolve_node_specific_exposure",
]
