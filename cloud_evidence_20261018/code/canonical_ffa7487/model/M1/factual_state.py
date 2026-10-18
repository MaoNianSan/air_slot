"""PRE -> M1 observed-state adapter (Tranche 3 cross-stage contraction).

The PRE typed factual state (FACTUAL_REPLAY_EVIDENCE, cutoff-legal) fixes the
corresponding unresolved stochastic components:

    PRE_IB:            nothing fixed (all stochastic)
    POST_IB_PRE_OB:    T_IB_A00 fixed to the legal factual event time
    POST_OB_PRE_TO:    T_IB_A00 + D_OB fixed
    COMPLETED:         T_IB_A00 + D_OB + D_TX fixed

``observed`` is NEVER assembled by callers from arbitrary future truth: it is
derived here from the PRE published factual state, and every entry re-verifies
the availability cutoff provenance at the M1 boundary.
"""

from __future__ import annotations

from datetime import datetime

from model.common.enums import DecisionTimeRole, SupportState
from model.PRE import PREState


def _fact(pre: PREState, family: str, variable: str) -> dict | None:
    value = getattr(pre, family).get(variable)
    if value is None or value.support_state is SupportState.ABSTAIN:
        return None
    if not isinstance(value.value, dict):
        return None
    payload = value.value
    if (
        payload.get("decision_time_role")
        != DecisionTimeRole.FACTUAL_REPLAY_EVIDENCE.value
    ):
        return None
    availability = payload.get("availability_time")
    cutoff = pre.decision_node.information_cutoff
    if availability is None:
        return None
    if isinstance(availability, str):
        availability = datetime.fromisoformat(availability)
    if availability > cutoff:
        return None
    return payload


def _field_legal(payload: dict, field: str, cutoff: datetime) -> bool:
    by_field = payload.get("declared_availability_by_field") or {}
    availability = by_field.get(field, payload.get("availability_time"))
    if availability is None:
        return False
    if isinstance(availability, str):
        availability = datetime.fromisoformat(availability)
    return availability <= cutoff


def _schedule_departure(pre: PREState):
    schedule = pre.successor_state.get("schedule_reference")
    if schedule is None or not isinstance(schedule.value, dict):
        return None
    return schedule.value.get("scheduled_departure_utc")


def factual_observed_state(
    pre_state: PREState,
    *,
    taxi_reference_minutes: float | None = None,
) -> dict[str, object]:
    """Derive the M1 observed-state dict from PRE typed factual evidence.

    Only FACTUAL_REPLAY_EVIDENCE entries that cleared the availability cutoff
    (verified again here) fix their component; the public absolute event
    timestamp ``T_IB_A00`` is preserved (never dropped because R_IB == 0).
    """
    observed: dict[str, object] = {}
    predecessor = _fact(pre_state, "current_state", "predecessor_operational_fact")
    if (
        predecessor is not None
        and predecessor.get("actual_arrival_utc") is not None
        and _field_legal(
            predecessor,
            "actual_arrival_utc",
            pre_state.decision_node.information_cutoff,
        )
    ):
        arrival = predecessor["actual_arrival_utc"]
        observed["T_IB_A00"] = (
            arrival.isoformat() if isinstance(arrival, datetime) else str(arrival)
        )
    if taxi_reference_minutes is None:
        # The COMPLETED-stage D_TX fact is derived from the SAME frozen taxi
        # reference PRE published as a MODEL_FEATURE (lineage equality); the
        # caller may still pass an explicit override for scenarios where the
        # reference is supplied out-of-band.
        taxi_value = pre_state.successor_state.get("taxi_reference")
        if taxi_value is not None and isinstance(taxi_value.value, dict):
            taxi_reference_minutes = taxi_value.value.get("value")
    successor = _fact(pre_state, "successor_state", "successor_operational_fact")
    if (
        successor is not None
        and not successor.get("cancelled")
        and not successor.get("diverted")
    ):
        departure = successor.get("actual_departure_utc")
        scheduled = _schedule_departure(pre_state)
        if (
            departure is not None
            and scheduled is not None
            and _field_legal(
                successor,
                "actual_departure_utc",
                pre_state.decision_node.information_cutoff,
            )
        ):
            if isinstance(departure, str):
                departure = datetime.fromisoformat(departure)
            if isinstance(scheduled, str):
                scheduled = datetime.fromisoformat(scheduled)
            d_ob = max(0.0, (departure - scheduled).total_seconds() / 60.0)
            observed["D_OB"] = d_ob
        taxi_out = successor.get("taxi_out_minutes")
        if (
            taxi_out is not None
            and taxi_reference_minutes is not None
            and _field_legal(
                successor, "wheels_off_utc", pre_state.decision_node.information_cutoff
            )
        ):
            observed["D_TX"] = max(0.0, float(taxi_out) - float(taxi_reference_minutes))
    return observed
