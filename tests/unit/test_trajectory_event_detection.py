from datetime import datetime, timedelta, timezone

from model.common.enums import SupportState
from model.PRE.episode.event_detection import (
    MotionState,
    TrajectoryDetectorConfig,
    detect_operational_events,
)


UTC = timezone.utc
T0 = datetime(2019, 1, 1, 0, 0, tzinfo=UTC)


def obs(t, *, on_ground=None, v=None, alt=None, lat=48.0, lon=2.0, aircraft='A', seq=0):
    return {
        'aircraft_id': aircraft, 'event_time': t, 'on_ground': on_ground,
        'velocity_mps': v, 'baro_altitude_m': alt,
        'latitude_deg': lat, 'longitude_deg': lon, '_seq': seq,
    }


def test_frozen_threshold_defaults_are_explicit():
    config = TrajectoryDetectorConfig()
    assert config.eps_position_deg == 0.001
    assert config.v_static_mps == 1.0
    assert config.eps_altitude_m == 15.0
    assert config.v_taxi_min_mps == 5.0
    assert config.v_air_mps == 60.0
    assert config.gap_off_minutes == 10.0
    assert config.r_airport_km == 20.0
    assert config.w_seconds == 60.0
    assert config.parameters() == (
        'eps_position_deg=0.001', 'v_static_mps=1.0', 'eps_altitude_m=15.0',
        'v_taxi_min_mps=5.0', 'v_air_mps=60.0', 'gap_off_minutes=10.0',
        'r_airport_km=20.0', 'w_seconds=60.0',
    )


def test_onground_flip_emits_takeoff_and_landing_with_crosscheck():
    rows = [
        obs(T0, on_ground=True, v=2.0, lat=48.0, lon=2.0),
        obs(T0 + timedelta(seconds=30), on_ground=True, v=8.0, lat=48.002, lon=2.001),
        obs(T0 + timedelta(seconds=60), on_ground=False, v=90.0, alt=200.0),
        obs(T0 + timedelta(seconds=90), on_ground=False, v=120.0, alt=800.0),
        obs(T0 + timedelta(seconds=120), on_ground=False, v=80.0, alt=300.0),
        obs(T0 + timedelta(seconds=150), on_ground=True, v=10.0, lat=48.0, lon=2.0),
    ]
    events = detect_operational_events(rows)
    by_type = {}
    for event in events:
        by_type.setdefault(event.event_type, []).append(event)
    takeoffs = by_type.get('TAKEOFF', [])
    landings = by_type.get('LANDING', [])
    assert len(takeoffs) == 1 and len(landings) == 1
    assert takeoffs[0].event_time == T0 + timedelta(seconds=60)
    assert takeoffs[0].prev_state is MotionState.TAXI
    assert takeoffs[0].cur_state is MotionState.AIR
    assert takeoffs[0].support_state is SupportState.SUPPORTED
    assert takeoffs[0].quality_flags == ()
    assert landings[0].event_time == T0 + timedelta(seconds=150)
    assert landings[0].support_state is SupportState.SUPPORTED
    assert 'OUT_BLOCK_PROXY' in by_type


def test_crosscheck_mismatch_degrades_takeoff_but_keeps_primary_signal():
    rows = [
        obs(T0, on_ground=True, v=0.5, lat=48.0, lon=2.0),
        obs(T0 + timedelta(seconds=60), on_ground=False, v=3.0, alt=5.0),
    ]
    events = detect_operational_events(rows)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == 'TAKEOFF'
    assert event.support_state is SupportState.DEGRADED
    assert 'STATE_MACHINE_CROSSCHECK_MISMATCH' in event.quality_flags
    assert event.reason_code == 'STATE_MACHINE_CROSSCHECK_MISMATCH'


def test_onground_missing_uses_state_machine_inference_with_flag():
    rows = [
        obs(T0, on_ground=None, v=2.0),
        obs(T0 + timedelta(seconds=60), on_ground=None, v=8.0),
        obs(T0 + timedelta(seconds=120), on_ground=None, v=90.0, alt=200.0),
        obs(T0 + timedelta(seconds=180), on_ground=None, v=8.0),
    ]
    events = detect_operational_events(rows)
    inferred = [e for e in events if e.event_type in ('TAKEOFF', 'LANDING')]
    assert len(inferred) == 2
    assert all(e.support_state is SupportState.DEGRADED for e in inferred)
    assert all('ONGROUND_MISSING_INFERRED' in e.quality_flags for e in inferred)
    assert inferred[0].event_type == 'TAKEOFF'
    assert inferred[1].event_type == 'LANDING'


def test_out_block_and_in_block_proxies_from_state_machine():
    rows = [
        obs(T0, on_ground=True, v=0.5, lat=48.0, lon=2.0),
        obs(T0 + timedelta(seconds=30), on_ground=True, v=8.0, lat=48.002, lon=2.001),
        obs(T0 + timedelta(seconds=60), on_ground=True, v=0.5, lat=48.0, lon=2.0),
    ]
    events = detect_operational_events(rows)
    by_type = {event.event_type: event for event in events}
    assert by_type['OUT_BLOCK_PROXY'].event_time == T0 + timedelta(seconds=30)
    assert by_type['IN_BLOCK_PROXY'].event_time == T0 + timedelta(seconds=60)
    assert by_type['OUT_BLOCK_PROXY'].support_state is SupportState.SUPPORTED


def test_power_off_on_gated_by_airport_radius():
    rows = [
        obs(T0, on_ground=True, v=0.5, lat=48.0, lon=2.0),
        obs(T0 + timedelta(minutes=15), on_ground=True, v=0.5, lat=55.0, lon=10.0),
    ]
    events = detect_operational_events(rows, airport_reference=((48.0, 2.0),))
    power_off = [e for e in events if e.event_type == 'POWER_OFF']
    power_on = [e for e in events if e.event_type == 'POWER_ON']
    assert len(power_off) == 1 and len(power_on) == 1
    assert power_off[0].support_state is SupportState.SUPPORTED
    assert power_on[0].support_state is SupportState.ABSTAIN
    assert 'AIRPORT_RADIUS_OUT_OF_SCOPE' in power_on[0].quality_flags
    assert power_on[0].reason_code == 'POWER_EVENT_AIRPORT_REFERENCE_REQUIRED'


def test_detection_is_row_order_invariant():
    rows = [
        obs(T0, on_ground=True, v=2.0, lat=48.0, lon=2.0),
        obs(T0 + timedelta(seconds=30), on_ground=True, v=8.0, lat=48.002, lon=2.001),
        obs(T0 + timedelta(seconds=60), on_ground=False, v=90.0, alt=200.0),
        obs(T0 + timedelta(seconds=150), on_ground=True, v=10.0, lat=48.0, lon=2.0),
    ]
    forward = detect_operational_events(rows)
    shuffled = detect_operational_events(list(reversed(rows)))
    assert [(e.event_type, e.event_time) for e in forward] == [
        (e.event_type, e.event_time) for e in shuffled]


def test_insufficient_observations_return_no_events():
    assert detect_operational_events([]) == ()
    assert detect_operational_events([obs(T0)]) == ()
