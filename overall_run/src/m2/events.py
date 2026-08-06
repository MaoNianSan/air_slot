from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Mapping

from .contracts import AvailabilityStatus, FlightContext


EVENT_NAMES = (
    "turn_deficit",
    "extra_offblock_wait",
    "extra_taxi_delay",
    "takeoff_delay",
)


@dataclass(frozen=True)
class RuntimeEvents:
    event_value: Mapping[str, float | None]
    event_status: Mapping[str, AvailabilityStatus]
    event_semantics: Mapping[str, str]
    event_source: Mapping[str, str]

    @property
    def turn_deficit_minutes(self) -> float | None:
        return self.event_value["turn_deficit"]

    @property
    def turn_deficit_semantics(self) -> str:
        return self.event_semantics["turn_deficit"]

    @property
    def extra_offblock_wait_minutes(self) -> float | None:
        return self.event_value["extra_offblock_wait"]

    @property
    def extra_taxi_minutes(self) -> float | None:
        return self.event_value["extra_taxi_delay"]

    @property
    def takeoff_delay_minutes(self) -> float | None:
        return self.event_value["takeoff_delay"]


def _finite(value: object) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _predicted_primitive(
    sample: object,
    *,
    value: object,
    target: str,
    observed_event: str,
    dependency_targets: tuple[str, ...] | None = None,
) -> tuple[float | None, AvailabilityStatus, str, str]:
    number = _finite(value)
    targets = dependency_targets or (target,)
    overflow = any(
        bool(getattr(sample, "overflow_flags", {}).get(name, False))
        for name in targets
    )
    if number is None:
        status = (
            AvailabilityStatus.TAIL_UNRESOLVED
            if overflow
            else AvailabilityStatus.MISSING
        )
        return None, status, status.value, f"M1_SCENARIO_V2:{target}"
    observed = bool(getattr(sample, "observed_event_mask", {}).get(observed_event, False))
    semantics = "OBSERVED" if observed else "PREDICTED"
    return number, AvailabilityStatus.AVAILABLE, semantics, f"M1_SCENARIO_V2:{target}"


def build_events(sample: object, flight: FlightContext) -> RuntimeEvents:
    values: dict[str, float | None] = {}
    statuses: dict[str, AvailabilityStatus] = {}
    semantics: dict[str, str] = {}
    sources: dict[str, str] = {}

    wait = _predicted_primitive(
        sample,
        value=getattr(sample, "r_ob_minutes", None),
        target="R_OB",
        observed_event="AOBT_PLUS",
    )
    taxi = _predicted_primitive(
        sample,
        value=getattr(sample, "extra_taxi_delay", None),
        target="T_TX",
        observed_event="ATOT_PLUS",
        dependency_targets=("R_IB", "R_OB", "T_TX"),
    )
    takeoff_overflow = any(
        bool(getattr(sample, "overflow_flags", {}).get(target, False))
        for target in ("R_IB", "R_OB", "T_TX")
    )
    takeoff_value = _finite(getattr(sample, "total_takeoff_delay", None))
    if takeoff_value is None:
        takeoff = (
            None,
            AvailabilityStatus.TAIL_UNRESOLVED
            if takeoff_overflow
            else AvailabilityStatus.MISSING,
            "TAIL_UNRESOLVED" if takeoff_overflow else "MISSING",
            "M1_SCENARIO_V2:STRUCTURAL_TAKEOFF_DELAY",
        )
    else:
        observed = bool(
            getattr(sample, "observed_event_mask", {}).get("ATOT_PLUS", False)
        )
        takeoff = (
            takeoff_value,
            AvailabilityStatus.AVAILABLE,
            "OBSERVED" if observed else "PREDICTED",
            "M1_SCENARIO_V2:STRUCTURAL_TAKEOFF_DELAY",
        )

    inblock = getattr(sample, "T_predecessor_inblock", None)
    inblock_overflow = bool(
        getattr(sample, "overflow_flags", {}).get("R_IB", False)
    )
    if inblock is None:
        turn = (
            None,
            AvailabilityStatus.TAIL_UNRESOLVED
            if inblock_overflow
            else AvailabilityStatus.MISSING,
            "TAIL_UNRESOLVED" if inblock_overflow else "MISSING",
            "M1_SCENARIO_V2:T_PREDECESSOR_INBLOCK",
        )
    elif flight.turnaround_reference_minutes is None or flight.successor_sobt is None:
        turn = (
            None,
            AvailabilityStatus.UNSUPPORTED,
            "UNSUPPORTED",
            "M1_SCENARIO_V2_PLUS_M2_TURNAROUND_REFERENCE",
        )
    else:
        required = inblock + timedelta(minutes=float(flight.turnaround_reference_minutes))
        deficit = max(
            (required - flight.successor_sobt).total_seconds() / 60.0,
            0.0,
        )
        is_proxy = flight.turnaround_reference_type in {
            "OPERATIONAL_INFERENCE",
            "EMPIRICAL_REFERENCE",
        }
        turn = (
            deficit,
            AvailabilityStatus.PROXY_AVAILABLE
            if is_proxy
            else AvailabilityStatus.AVAILABLE,
            "PROXY" if is_proxy else "OFFICIAL_FLOOR",
            "M1_SCENARIO_V2_PLUS_M2_TURNAROUND_REFERENCE",
        )

    for name, primitive in (
        ("turn_deficit", turn),
        ("extra_offblock_wait", wait),
        ("extra_taxi_delay", taxi),
        ("takeoff_delay", takeoff),
    ):
        values[name], statuses[name], semantics[name], sources[name] = primitive
    return RuntimeEvents(values, statuses, semantics, sources)


def aggregate_event_status(
    events: tuple[RuntimeEvents, ...],
) -> dict[str, AvailabilityStatus]:
    result: dict[str, AvailabilityStatus] = {}
    for name in EVENT_NAMES:
        statuses = {event.event_status[name] for event in events}
        if AvailabilityStatus.UNSUPPORTED in statuses:
            result[name] = AvailabilityStatus.UNSUPPORTED
        elif AvailabilityStatus.MISSING in statuses:
            result[name] = AvailabilityStatus.MISSING
        elif AvailabilityStatus.AVAILABLE in statuses:
            result[name] = AvailabilityStatus.AVAILABLE
        elif AvailabilityStatus.PROXY_AVAILABLE in statuses:
            result[name] = AvailabilityStatus.PROXY_AVAILABLE
        else:
            result[name] = AvailabilityStatus.TAIL_UNRESOLVED
    return result
