from datetime import datetime, timedelta, timezone

from model.common.enums import SupportState
from model.PRE.canonical.normalization import (canonicalize_flightlist_row,
                                               canonicalize_trajectory_event)
from model.PRE.episode.event_detection import (MotionState, TrajectoryEventRecord,
                                               TrajectoryDetectorConfig)
from model.PRE.realized.routing import (route_predecessor_arrival,
                                        route_successor_taxi_out)


UTC = timezone.utc
T0 = datetime(2019, 1, 1, 0, 0, tzinfo=UTC)


def traj(event_type, t, *, aircraft="a1", flags=()):
    return canonicalize_trajectory_event(TrajectoryEventRecord(
        event_type=event_type, event_time=t, aircraft_id=aircraft,
        prev_time=t - timedelta(minutes=1), cur_time=t,
        prev_state=MotionState.TAXI, cur_state=MotionState.AIR,
        support_state=SupportState.SUPPORTED, quality_flags=flags,
        detector_parameters=TrajectoryDetectorConfig().parameters()), flight_id="F1")


def proxy_row(first, last):
    return canonicalize_flightlist_row({"callsign": "ABC1", "day": "2019-01-01",
        "origin": "LSZH", "destination": "EGLL", "icao24": "a1",
        "firstseen": first.isoformat(), "lastseen": last.isoformat()})[1]


def test_trajectory_in_block_proxy_preferred_over_landing():
    events = (traj("LANDING", T0 + timedelta(minutes=100)),
              traj("IN_BLOCK_PROXY", T0 + timedelta(minutes=110)))
    result = route_predecessor_arrival(flight_id="F1", aircraft_id="a1",
        window_start=T0, window_end=T0 + timedelta(minutes=120), events=events)
    assert result.arrival_utc == T0 + timedelta(minutes=110)
    assert result.source == "IN_BLOCK_PROXY"
    assert result.support_state is SupportState.SUPPORTED
    assert "ARRIVAL_SOURCE_TRAJECTORY" in result.quality_flags


def test_landing_used_when_in_block_proxy_missing():
    events = (traj("LANDING", T0 + timedelta(minutes=100)),)
    result = route_predecessor_arrival(flight_id="F1", aircraft_id="a1",
        window_start=T0, window_end=T0 + timedelta(minutes=120), events=events)
    assert result.arrival_utc == T0 + timedelta(minutes=100)
    assert result.source == "LANDING"
    assert result.support_state is SupportState.SUPPORTED


def test_proxy_fallback_degraded_when_no_trajectory_event():
    proxy = proxy_row(T0 + timedelta(minutes=5), T0 + timedelta(minutes=95))
    result = route_predecessor_arrival(flight_id="F1", aircraft_id="a1",
        window_start=T0, window_end=T0 + timedelta(minutes=120), events=(),
        proxy_event=proxy)
    assert result.arrival_utc == T0 + timedelta(minutes=95)
    assert result.source == "FLIGHTLIST_PROXY"
    assert result.support_state is SupportState.DEGRADED
    assert result.reason_code == "TRAJECTORY_EVENT_UNAVAILABLE_PROXY_FALLBACK"


def test_no_evidence_abstains():
    result = route_predecessor_arrival(flight_id="F1", aircraft_id="a1",
        window_start=T0, window_end=T0 + timedelta(minutes=120), events=())
    assert result.arrival_utc is None
    assert result.support_state is SupportState.ABSTAIN
    assert result.reason_code == "NO_REALIZED_ARRIVAL_EVIDENCE"


def test_events_outside_flight_window_are_excluded():
    proxy = proxy_row(T0 + timedelta(minutes=5), T0 + timedelta(minutes=95))
    outside = traj("LANDING", T0 + timedelta(minutes=200))
    result = route_predecessor_arrival(flight_id="F1", aircraft_id="a1",
        window_start=T0, window_end=T0 + timedelta(minutes=120),
        events=(outside,), proxy_event=proxy)
    assert result.source == "FLIGHTLIST_PROXY"
    assert result.arrival_utc == T0 + timedelta(minutes=95)


def test_degraded_detector_flag_propagates_to_arrival():
    events = (traj("LANDING", T0 + timedelta(minutes=100),
                   flags=("ONGROUND_MISSING_INFERRED",)),)
    result = route_predecessor_arrival(flight_id="F1", aircraft_id="a1",
        window_start=T0, window_end=T0 + timedelta(minutes=120), events=events)
    assert result.support_state is SupportState.DEGRADED
    assert "ONGROUND_MISSING_INFERRED" in result.quality_flags


def test_taxi_out_from_out_block_takeoff_pair():
    events = (traj("OUT_BLOCK_PROXY", T0 + timedelta(minutes=10)),
              traj("TAKEOFF", T0 + timedelta(minutes=25)))
    result = route_successor_taxi_out(flight_id="F1", aircraft_id="a1",
        window_start=T0, window_end=T0 + timedelta(minutes=120), events=events)
    assert result.taxi_out_minutes == 15.0
    assert result.source == "OUT_BLOCK_TAKEOFF_PAIR"
    assert result.support_state is SupportState.SUPPORTED
    assert len(result.parent_record_ids) == 2


def test_taxi_out_incomplete_pair_abstains():
    events = (traj("TAKEOFF", T0 + timedelta(minutes=25)),)
    result = route_successor_taxi_out(flight_id="F1", aircraft_id="a1",
        window_start=T0, window_end=T0 + timedelta(minutes=120), events=events)
    assert result.taxi_out_minutes is None
    assert result.support_state is SupportState.ABSTAIN
    assert result.reason_code == "TAXI_OUT_TRAJECTORY_PAIR_REQUIRED"


def test_taxi_out_event_order_invalid_abstains():
    events = (traj("OUT_BLOCK_PROXY", T0 + timedelta(minutes=30)),
              traj("TAKEOFF", T0 + timedelta(minutes=10)))
    result = route_successor_taxi_out(flight_id="F1", aircraft_id="a1",
        window_start=T0, window_end=T0 + timedelta(minutes=120), events=events)
    assert result.support_state is SupportState.ABSTAIN
    assert result.reason_code == "TAXI_OUT_EVENT_ORDER_INVALID"


def test_taxi_out_proxy_fallback_is_explicitly_unsupported():
    proxy = proxy_row(T0 + timedelta(minutes=5), T0 + timedelta(minutes=95))
    result = route_successor_taxi_out(flight_id="F1", aircraft_id="a1",
        window_start=T0, window_end=T0 + timedelta(minutes=120), events=(),
        proxy_event=proxy)
    assert result.taxi_out_minutes is None
    assert result.support_state is SupportState.ABSTAIN
    assert result.reason_code == "FLIGHTLIST_PROXY_CANNOT_CONSTRUCT_TAXI_OUT"


def test_canonical_trajectory_event_contract():
    record = traj("LANDING", T0 + timedelta(minutes=100))
    assert record.event_type == "TRAJECTORY_LANDING"
    assert record.decision_time_role.value == "EVAL_OUTCOME"
    assert record.availability_basis.value == "POSTHOC_ONLY"
    assert record.provenance_rule_id == "D1-TRAJECTORY-EVENT"
    assert record.aircraft_id == "a1" and record.flight_id == "F1"
    assert record.event_time_lower == record.event_time_upper == record.event_time