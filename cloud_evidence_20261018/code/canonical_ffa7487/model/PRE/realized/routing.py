from dataclasses import dataclass
from datetime import datetime

from model.common.enums import SupportState
from model.PRE.contracts.canonical import OperationalEventRecord

RULE_ID = "DATA1_REALIZED_EVENT_ROUTING"
RULE_VERSION = "1.0.0"

_DEGRADED_DETECTOR_FLAGS = {
    "STATE_MACHINE_CROSSCHECK_MISMATCH",
    "ONGROUND_MISSING_INFERRED",
}
_ARRIVAL_PRIORITY = ("IN_BLOCK_PROXY", "LANDING")


@dataclass(frozen=True)
class RoutedArrival:
    flight_id: str
    arrival_utc: datetime | None
    source: str
    support_state: SupportState
    reason_code: str | None
    parent_record_ids: tuple[str, ...]
    quality_flags: tuple[str, ...]
    rule_id: str = RULE_ID
    rule_version: str = RULE_VERSION


@dataclass(frozen=True)
class RoutedTaxiOut:
    flight_id: str
    taxi_out_minutes: float | None
    source: str
    support_state: SupportState
    reason_code: str | None
    parent_record_ids: tuple[str, ...]
    quality_flags: tuple[str, ...]
    rule_id: str = RULE_ID
    rule_version: str = RULE_VERSION


def _in_window(
    event: OperationalEventRecord,
    *,
    aircraft_id: str | None,
    window_start: datetime,
    window_end: datetime,
) -> bool:
    if event.dataset_instance_id != "data1_2019":
        return False
    if event.event_time is None:
        return False
    if aircraft_id is not None and event.aircraft_id != aircraft_id:
        return False
    return window_start <= event.event_time <= window_end


def _latest(events: list[OperationalEventRecord]) -> OperationalEventRecord:
    return max(events, key=lambda event: event.event_time)


def _detector_support(event: OperationalEventRecord) -> SupportState:
    if _DEGRADED_DETECTOR_FLAGS.intersection(event.quality_flags):
        return SupportState.DEGRADED
    return SupportState.SUPPORTED


def route_predecessor_arrival(
    *,
    flight_id: str,
    aircraft_id: str | None,
    window_start: datetime,
    window_end: datetime,
    events: tuple[OperationalEventRecord, ...],
    proxy_event: OperationalEventRecord | None = None,
) -> RoutedArrival:
    for event_type in _ARRIVAL_PRIORITY:
        matches = [
            event
            for event in events
            if event.event_type == f"TRAJECTORY_{event_type}"
            and _in_window(
                event,
                aircraft_id=aircraft_id,
                window_start=window_start,
                window_end=window_end,
            )
        ]
        if matches:
            chosen = _latest(matches)
            return RoutedArrival(
                flight_id=flight_id,
                arrival_utc=chosen.event_time,
                source=event_type,
                support_state=_detector_support(chosen),
                reason_code=None,
                parent_record_ids=(chosen.canonical_record_id,),
                quality_flags=("ARRIVAL_SOURCE_TRAJECTORY",) + chosen.quality_flags,
            )
    if (
        proxy_event is not None
        and proxy_event.event_type == "ARCHIVE_FLIGHT_INTERVAL_PROXY"
        and proxy_event.event_time_upper is not None
    ):
        return RoutedArrival(
            flight_id=flight_id,
            arrival_utc=proxy_event.event_time_upper,
            source="FLIGHTLIST_PROXY",
            support_state=SupportState.DEGRADED,
            reason_code="TRAJECTORY_EVENT_UNAVAILABLE_PROXY_FALLBACK",
            parent_record_ids=(proxy_event.canonical_record_id,),
            quality_flags=("ARRIVAL_SOURCE_FLIGHTLIST_PROXY",),
        )
    return RoutedArrival(
        flight_id=flight_id,
        arrival_utc=None,
        source="NONE",
        support_state=SupportState.ABSTAIN,
        reason_code="NO_REALIZED_ARRIVAL_EVIDENCE",
        parent_record_ids=(),
        quality_flags=(),
    )


def route_successor_taxi_out(
    *,
    flight_id: str,
    aircraft_id: str | None,
    window_start: datetime,
    window_end: datetime,
    events: tuple[OperationalEventRecord, ...],
    proxy_event: OperationalEventRecord | None = None,
) -> RoutedTaxiOut:
    out_blocks = [
        event
        for event in events
        if event.event_type == "TRAJECTORY_OUT_BLOCK_PROXY"
        and _in_window(
            event,
            aircraft_id=aircraft_id,
            window_start=window_start,
            window_end=window_end,
        )
    ]
    takeoffs = [
        event
        for event in events
        if event.event_type == "TRAJECTORY_TAKEOFF"
        and _in_window(
            event,
            aircraft_id=aircraft_id,
            window_start=window_start,
            window_end=window_end,
        )
    ]
    if out_blocks and takeoffs:
        out_block = _latest(out_blocks)
        takeoff = _latest(takeoffs)
        if takeoff.event_time <= out_block.event_time:
            return RoutedTaxiOut(
                flight_id=flight_id,
                taxi_out_minutes=None,
                source="NONE",
                support_state=SupportState.ABSTAIN,
                reason_code="TAXI_OUT_EVENT_ORDER_INVALID",
                parent_record_ids=(
                    out_block.canonical_record_id,
                    takeoff.canonical_record_id,
                ),
                quality_flags=(),
            )
        minutes = (takeoff.event_time - out_block.event_time).total_seconds() / 60.0
        support = (
            SupportState.DEGRADED
            if _DEGRADED_DETECTOR_FLAGS.intersection(
                out_block.quality_flags + takeoff.quality_flags
            )
            else SupportState.SUPPORTED
        )
        return RoutedTaxiOut(
            flight_id=flight_id,
            taxi_out_minutes=minutes,
            source="OUT_BLOCK_TAKEOFF_PAIR",
            support_state=support,
            reason_code=None,
            parent_record_ids=(
                out_block.canonical_record_id,
                takeoff.canonical_record_id,
            ),
            quality_flags=("TAXI_OUT_SOURCE_TRAJECTORY_PAIR",),
        )
    if (
        proxy_event is not None
        and proxy_event.event_type == "ARCHIVE_FLIGHT_INTERVAL_PROXY"
    ):
        return RoutedTaxiOut(
            flight_id=flight_id,
            taxi_out_minutes=None,
            source="NONE",
            support_state=SupportState.ABSTAIN,
            reason_code="FLIGHTLIST_PROXY_CANNOT_CONSTRUCT_TAXI_OUT",
            parent_record_ids=(proxy_event.canonical_record_id,),
            quality_flags=(),
        )
    return RoutedTaxiOut(
        flight_id=flight_id,
        taxi_out_minutes=None,
        source="NONE",
        support_state=SupportState.ABSTAIN,
        reason_code="TAXI_OUT_TRAJECTORY_PAIR_REQUIRED",
        parent_record_ids=(),
        quality_flags=(),
    )
