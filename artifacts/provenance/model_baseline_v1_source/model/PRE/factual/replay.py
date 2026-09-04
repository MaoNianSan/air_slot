"""Factual-replay publication: one source record, multiple roles (Tranche 3).

The same realized operational event record may act as:

A. TRAIN_LABEL          (label construction; posthoc, no inference role)
B. EVAL_OUTCOME         (evaluation; posthoc, no inference role)
C. FACTUAL_REPLAY_EVIDENCE (may enter a subsequent rolling state ONLY when
                            availability_time <= information_cutoff)

We never copy/fabricate actual values: the record is reused; only the
factual-replay role computes a typed availability time (event_time + declared
lag/rule) and passes the cutoff gate.  Future outcomes that already exist in
the archive are still blocked by the gate.
"""

from __future__ import annotations

from datetime import datetime

from model.common.enums import (
    AvailabilityBasis,
    DecisionTimeRole,
    EvidenceClass,
    SupportState,
)
from model.common.value_objects import SupportedValue
from model.PRE.contracts.canonical import OperationalEventRecord
from model.PRE.factual.availability import (
    Data2FactualReplayAvailabilityPolicy,
    factual_availability_time,
    factual_replay_legal,
)

_REALIZED_ROLES = {DecisionTimeRole.TRAIN_LABEL, DecisionTimeRole.EVAL_OUTCOME}
_OUTCOME_EVENT_TYPE = "COMPLETED_OPERATIONAL_OUTCOME"


def _outcome_value(
    record: OperationalEventRecord,
    *,
    replay_event_time: datetime,
    availability_time: datetime,
    policy: Data2FactualReplayAvailabilityPolicy,
    declared_lag_minutes: float,
):
    field_times = {
        "actual_departure_utc": record.actual_departure_utc,
        "wheels_off_utc": record.wheels_off_utc,
        "wheels_on_utc": record.wheels_on_utc,
        "actual_arrival_utc": record.actual_arrival_utc,
    }
    field_availability = {
        name: factual_availability_time(
            timestamp, policy, declared_lag_minutes=declared_lag_minutes
        )
        for name, timestamp in field_times.items()
        if timestamp is not None
    }
    return {
        "flight_id": record.flight_id,
        "event_type": record.event_type,
        "actual_departure_utc": record.actual_departure_utc,
        "wheels_off_utc": record.wheels_off_utc,
        "wheels_on_utc": record.wheels_on_utc,
        "actual_arrival_utc": record.actual_arrival_utc,
        "taxi_out_minutes": record.taxi_out_minutes,
        "taxi_in_minutes": record.taxi_in_minutes,
        "cancelled": record.cancelled,
        "diverted": record.diverted,
        "event_time": replay_event_time,
        "canonical_event_time": record.event_time,
        "availability_time": availability_time,
        "declared_availability_time": availability_time,
        "declared_replay_rule_id": "D2-BTS-FACTUAL-REPLAY",
        "declared_replay_policy": policy.value,
        "declared_lag_minutes": float(declared_lag_minutes),
        "declared_availability_by_field": field_availability,
        "availability_basis": AvailabilityBasis.FACTUAL_REPLAY_RULE.value,
        "decision_time_role": DecisionTimeRole.FACTUAL_REPLAY_EVIDENCE.value,
        "source_record_id": record.canonical_record_id,
        "provenance_rule_id": record.provenance_rule_id,
    }


def publish_factual_replay(
    records,
    *,
    predecessor_id: str,
    successor_id: str,
    policy: Data2FactualReplayAvailabilityPolicy | str,
    information_cutoff: datetime,
    declared_lag_minutes: float | None = None,
) -> tuple[SupportedValue | None, SupportedValue | None]:
    """Return (predecessor_fact, successor_fact) legal at the cutoff.

    Each fact is a SupportedValue carrying the FACTUAL_REPLAY_EVIDENCE role
    and its typed availability provenance.  Records that do not clear the
    availability gate are simply not published (never fabricated, never
    copied into inference).
    """
    candidates = [
        item
        for item in records
        if isinstance(item, OperationalEventRecord)
        and item.event_type == _OUTCOME_EVENT_TYPE
        and item.decision_time_role in _REALIZED_ROLES
        and item.event_time is not None
    ]
    facts: dict[str, SupportedValue] = {}
    for record in candidates:
        role = None
        if record.flight_id == predecessor_id:
            role = "predecessor"
            candidate_time = record.actual_arrival_utc
        elif record.flight_id == successor_id:
            role = "successor"
            candidate_time = record.actual_departure_utc
        if role is None or candidate_time is None:
            continue
        availability_time = factual_availability_time(
            candidate_time, policy, declared_lag_minutes=declared_lag_minutes
        )
        if not factual_replay_legal(
            event_time=candidate_time,
            availability_time=availability_time,
            information_cutoff=information_cutoff,
            policy=policy,
        ):
            continue
        facts[role] = SupportedValue(
            value=_outcome_value(
                record,
                replay_event_time=candidate_time,
                availability_time=availability_time,
                policy=Data2FactualReplayAvailabilityPolicy(policy),
                declared_lag_minutes=float(declared_lag_minutes or 0.0),
            ),
            unit="canonical",
            evidence_class=EvidenceClass.DIRECT,
            support_ceiling=EvidenceClass.DIRECT,
            support_state=SupportState.SUPPORTED,
            quality_flags=record.quality_flags,
        )
    return facts.get("predecessor"), facts.get("successor")
