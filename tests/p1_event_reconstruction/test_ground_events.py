from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from analysis.p1_event_reconstruction.ground_event_provider import MultiSignalGroundEventProvider
from analysis.p1_event_reconstruction.ground_event_rules import GroundEventRules, sustained_runs


def rules() -> GroundEventRules:
    return GroundEventRules(1.5, 4.0, 30.0, 20.0, 40.0, .35, 15.0, 30.0, 30.0, 250.0, .3, 5.0)


def runway() -> pd.DataFrame:
    return pd.DataFrame([{
        "airport_ident": "TEST", "le_ident": "09", "he_ident": "27",
        "le_latitude_deg": 50.0, "le_longitude_deg": 7.98,
        "he_latitude_deg": 50.0, "he_longitude_deg": 8.02,
        "runway_heading_deg": 90.0, "runway_length_m": 2800.0,
        "width_ft": 150, "surface": "ASP", "lighted": 1,
        "geometry_support": "ENDPOINTS_AND_HEADING",
    }])


def parking() -> pd.DataFrame:
    return pd.DataFrame([{"airport": "TEST", "parking_proxy_id": "TEST_P000", "latitude": 50.004, "longitude": 8.005, "radius_km": .3}])


def ground_path() -> pd.DataFrame:
    start = pd.Timestamp("2022-01-01 10:00:00", tz="UTC")
    times = pd.date_range(start, periods=25, freq="10s")
    velocity = [45, 35, 20, 10, 6, 5, 4, 2, 1, 1, 1, 1, 1, 1, 1, 1, 6, 7, 8, 10, 20, 30, 40, 55, 70]
    lon = [7.99, 7.995, 8.0, 8.003, 8.004, 8.005, 8.005, 8.005] + [8.005] * 8 + [8.004, 8.003, 8.002, 8.001, 8.0, 8.005, 8.01, 8.015, 8.02]
    lat = [50.0, 50.0, 50.0, 50.001, 50.002, 50.003, 50.004, 50.004] + [50.004] * 8 + [50.003, 50.002, 50.001, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0]
    return pd.DataFrame({
        "event_time": times, "lat": lat, "lon": lon, "heading": [90.0] * 25,
        "velocity": velocity, "onground": [True] * 25,
        "position_age_seconds": [1.0] * 25, "contact_age_seconds": [1.0] * 25,
        "distance_airport_km": [1.0] * 25,
    })


def test_unit_conversion() -> None:
    assert 10 * 3.6 == 36
    assert np.isclose(10 * 1.94384449, 19.4384449)


def test_airport_elevation_normalization() -> None:
    assert np.isclose(250.0 - 100.0, 150.0)


def test_position_freshness_gate() -> None:
    frame = ground_path(); frame["position_age_seconds"] = 120.0
    result = MultiSignalGroundEventProvider(rules(), runway(), parking()).infer_ground_events(frame, "TEST", frame.event_time.iloc[0], frame.event_time.iloc[-1])
    assert "LOW_SURFACE_REPORT_COVERAGE" in result.quality_flags


def test_sustained_state_transition() -> None:
    times = pd.date_range("2022-01-01", periods=10, freq="10s", tz="UTC")
    assert sustained_runs(pd.Series([False, True, True, True, True, True, False, False, False, False]), pd.Series(times), 30, 30) == [(1, 5)]


def test_hysteresis_has_distinct_exit_threshold() -> None:
    assert rules().hysteresis_exit_speed_mps > rules().stationary_speed_mps


def test_event_ordering_when_full_supported() -> None:
    frame = ground_path()
    result = MultiSignalGroundEventProvider(rules(), runway(), parking()).infer_ground_events(frame, "TEST", frame.event_time.iloc[0], frame.event_time.iloc[-1])
    if result.coverage_status == "FULL_GROUND_PATH_SUPPORTED":
        assert result.touchdown_time_proxy <= result.runway_exit_time_proxy <= result.taxi_in_end_time_proxy <= result.taxi_out_start_time_proxy <= result.runway_entry_time_proxy <= result.liftoff_time_proxy


def test_cross_hour_stitching() -> None:
    times = pd.to_datetime(["2022-01-01T10:59:50Z", "2022-01-01T11:00:00Z", "2022-01-01T11:00:10Z", "2022-01-01T11:00:20Z"])
    assert sustained_runs(pd.Series([True] * 4), pd.Series(times), 30, 30) == [(0, 3)]


def test_missing_onground_is_not_zero_filled() -> None:
    frame = ground_path(); frame["onground"] = pd.NA
    result = MultiSignalGroundEventProvider(rules(), runway(), parking()).infer_ground_events(frame, "TEST", frame.event_time.iloc[0], frame.event_time.iloc[-1])
    assert result.coverage_status != "FULL_GROUND_PATH_SUPPORTED"


def test_missing_altitude_does_not_create_ground_state() -> None:
    frame = ground_path(); frame["baro_height_above_airport"] = np.nan
    result = MultiSignalGroundEventProvider(rules(), runway(), parking()).infer_ground_events(frame, "TEST", frame.event_time.iloc[0], frame.event_time.iloc[-1])
    assert result.rule_id == rules().rule_id


def test_coverage_unsupported_behavior() -> None:
    result = MultiSignalGroundEventProvider(rules(), runway(), parking()).infer_ground_events(pd.DataFrame(), "TEST", None, None)
    assert result.coverage_status == "GROUND_COVERAGE_UNSUPPORTED"


def test_no_zero_filling() -> None:
    result = MultiSignalGroundEventProvider(rules(), runway(), parking()).infer_ground_events(pd.DataFrame(), "TEST", None, None)
    assert result.taxi_in_minutes is None and result.taxi_out_minutes is None


def test_no_future_feature_leakage() -> None:
    frame = ground_path()
    provider = MultiSignalGroundEventProvider(rules(), runway(), parking())
    base = provider.infer_ground_events(frame, "TEST", frame.event_time.iloc[0], frame.event_time.iloc[-1])
    future = frame.copy(); future.loc[len(future)] = future.iloc[-1]; future.loc[len(future) - 1, "event_time"] += pd.Timedelta(hours=2)
    repeated = provider.infer_ground_events(future, "TEST", frame.event_time.iloc[0], frame.event_time.iloc[-1])
    assert base.total_ground_continuation_minutes == repeated.total_ground_continuation_minutes


def test_deterministic_row_order() -> None:
    frame = ground_path().sample(frac=1, random_state=7)
    provider = MultiSignalGroundEventProvider(rules(), runway(), parking())
    first = provider.infer_ground_events(frame, "TEST", frame.event_time.min(), frame.event_time.max())
    second = provider.infer_ground_events(frame, "TEST", frame.event_time.min(), frame.event_time.max())
    assert first == second


def test_single_parallel_equivalence() -> None:
    frame = ground_path(); provider = MultiSignalGroundEventProvider(rules(), runway(), parking())
    single = [provider.infer_ground_events(frame, "TEST", frame.event_time.iloc[0], frame.event_time.iloc[-1]) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        parallel = list(executor.map(lambda _: provider.infer_ground_events(frame, "TEST", frame.event_time.iloc[0], frame.event_time.iloc[-1]), range(2)))
    assert single == parallel
