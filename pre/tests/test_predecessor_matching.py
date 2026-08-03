from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from src.predecessor_matcher import (
    M1_PREDECESSOR_MODEL_FEATURES,
    apply_predecessor_support_rule,
    attach_predecessor_features_to_snapshots,
    build_predecessor_candidates,
    build_predecessor_features,
)
from src.pipeline_config import load_config
from src.snapshot import build_snapshot_grid


class _MovementReference:
    def resolve(self, row: pd.Series):
        return 100.0, "fixture", 10, ""


class _TurnaroundReference:
    def resolve(self, airport: str, aircraft_group: str, time_bin: str):
        return 60.0, 30.0, 30.0, 0.8, "fixture", 10


class _ProgrammingErrorMovementReference:
    def resolve(self, row: pd.Series):
        raise RuntimeError("fixture programming error")


def _legs(*, overlap: bool = False, continuity: bool = True) -> pd.DataFrame:
    previous_end = "2022-05-02T12:30:00Z" if overlap else "2022-05-02T11:00:00Z"
    current_origin = "EDDM" if not continuity else "EDDF"
    rows = [
        {
            "episode_id": "prev", "flight_id": "prev", "icao24": "abc123",
            "origin": "EHAM", "destination": "EDDF",
            "firstseen_utc": pd.Timestamp("2022-05-02T10:00:00Z"),
            "lastseen_utc": pd.Timestamp(previous_end),
            "observed_movement_time": 60.0, "aircraft_group": "narrow_body",
            "typecode": "A320", "registration": "N12345",
            "state_day_complete": True, "firstseen_month": 5,
            "firstseen_time_bin": "06_12", "distance_bin": "500_1000",
            "origin_region": "NW_EUROPE", "destination_region": "CENTRAL_EUROPE",
            "region_pair": "NW_EUROPE__CENTRAL_EUROPE",
        },
        {
            "episode_id": "current", "flight_id": "current", "icao24": "abc123",
            "origin": current_origin, "destination": "LEMD",
            "firstseen_utc": pd.Timestamp("2022-05-02T12:00:00Z"),
            "lastseen_utc": pd.Timestamp("2022-05-02T14:00:00Z"),
            "observed_movement_time": 120.0, "aircraft_group": "narrow_body",
            "typecode": "A320", "registration": "N12345",
            "state_day_complete": True, "firstseen_month": 5,
            "firstseen_time_bin": "12_18", "distance_bin": "1000_1500",
            "origin_region": "CENTRAL_EUROPE", "destination_region": "IBERIA",
            "region_pair": "CENTRAL_EUROPE__IBERIA",
        },
    ]
    return pd.DataFrame(rows)


def test_predecessor_same_aircraft_and_time_order() -> None:
    cfg = load_config(mode="fast")
    result = apply_predecessor_support_rule(build_predecessor_candidates(_legs(), cfg), cfg)
    current = result[result["episode_id"].eq("current")].iloc[0]
    assert current["predecessor_flight_id"] == "prev"
    assert bool(current["has_supported_predecessor"])
    assert current["observed_ground_gap_minutes"] == 60.0


def test_predecessor_no_overlap() -> None:
    cfg = load_config(mode="fast")
    result = apply_predecessor_support_rule(
        build_predecessor_candidates(_legs(overlap=True), cfg), cfg
    )
    current = result[result["episode_id"].eq("current")].iloc[0]
    assert not bool(current["has_supported_predecessor"])
    assert current["predecessor_rejection_reason"] == "TEMPORAL_OVERLAP"


def test_predecessor_airport_continuity() -> None:
    cfg = load_config(mode="fast")
    result = apply_predecessor_support_rule(
        build_predecessor_candidates(_legs(continuity=False), cfg), cfg
    )
    current = result[result["episode_id"].eq("current")].iloc[0]
    assert not bool(current["has_supported_predecessor"])
    assert current["predecessor_rejection_reason"] == "AIRPORT_DISCONTINUITY"


def test_missing_predecessor_keeps_episode_and_uses_null_not_zero() -> None:
    cfg = load_config(mode="fast")
    features = build_predecessor_features(
        _legs(), _MovementReference(), _TurnaroundReference(), cfg
    )
    previous = features[features["episode_id"].eq("prev")].iloc[0]
    assert not bool(previous["has_supported_predecessor"])
    assert previous["predecessor_support_status"] == "UNSUPPORTED"
    numeric = [
        "predecessor_observed_duration", "observed_ground_gap_minutes",
        "turnaround_pressure_proxy", "continuation_risk_proxy",
    ]
    assert previous[numeric].isna().all()


def test_R3_threshold_loaded_from_config() -> None:
    cfg = load_config(mode="fast")
    strict = copy.deepcopy(cfg)
    strict["predecessor_matching"]["gap_threshold_minutes"] = 30.0
    result = apply_predecessor_support_rule(
        build_predecessor_candidates(_legs(), strict), strict
    )
    current = result[result["episode_id"].eq("current")].iloc[0]
    assert current["predecessor_rejection_reason"] == "R3_GAP_THRESHOLD_EXCEEDED"


def test_t1_t2_t3_use_only_available_information() -> None:
    cfg = load_config(mode="fast")
    episodes = pd.DataFrame([{
        "episode_id": "current", "episode_valid": True,
        "firstseen_utc": pd.Timestamp("2022-05-02T12:00:00Z"),
        "lastseen_utc": pd.Timestamp("2022-05-02T15:00:00Z"),
        "reference_movement_time": 100.0, "split": "train", "airport": "LEMD",
        "origin": "EDDF", "destination": "LEMD", "icao24": "abc123",
    }])
    legs = pd.DataFrame([{
        "episode_id": "current", "aircraft_group": "narrow_body",
        "aircraft_type_unknown": False,
    }])
    snapshots = build_snapshot_grid(episodes, legs, cfg)
    primary = snapshots[snapshots["snapshot_stage"].isin(["t1", "t2", "t3"])]
    expected = {"t1": 20.0, "t2": 50.0, "t3": 80.0}
    for row in primary.itertuples(index=False):
        assert row.decision_time_utc == episodes.iloc[0]["firstseen_utc"] + pd.Timedelta(
            minutes=expected[row.snapshot_stage]
        )


def test_no_future_successor_leakage_and_snapshot_availability() -> None:
    cfg = load_config(mode="fast")
    features = build_predecessor_features(
        _legs(), _MovementReference(), _TurnaroundReference(), cfg
    )
    snapshots = pd.DataFrame([{
        "episode_id": "current", "decision_time_utc": pd.Timestamp("2022-05-02T12:20:00Z")
    }])
    attached = attach_predecessor_features_to_snapshots(snapshots, features)
    assert bool(attached.iloc[0]["has_supported_predecessor"])
    assert all("successor" not in feature for feature in M1_PREDECESSOR_MODEL_FEATURES)


def _with_overlapping_candidates(count: int) -> pd.DataFrame:
    legs = _legs()
    current = legs.loc[legs["episode_id"].eq("current")].iloc[0]
    overlaps = []
    for index in range(count):
        row = current.copy()
        row["episode_id"] = f"overlap-{index}"
        row["flight_id"] = f"overlap-{index}"
        row["origin"] = "LEMD"
        row["destination"] = "EDDF"
        row["firstseen_utc"] = pd.Timestamp("2022-05-02T11:30:00Z") - pd.Timedelta(
            minutes=index * 5
        )
        row["lastseen_utc"] = pd.Timestamp("2022-05-02T12:30:00Z") + pd.Timedelta(
            minutes=index * 5
        )
        overlaps.append(row)
    return pd.concat([legs, pd.DataFrame(overlaps)], ignore_index=True)


def test_overlapping_adjacent_leg_does_not_mask_valid_older_predecessor() -> None:
    cfg = load_config(mode="fast")
    result = apply_predecessor_support_rule(
        build_predecessor_candidates(_with_overlapping_candidates(1), cfg), cfg
    )
    current = result[result["episode_id"].eq("current")].iloc[0]
    assert current["nearest_raw_candidate_id"] == "overlap-0"
    assert current["raw_candidate_rejection_reason"] == "TEMPORAL_OVERLAP"
    assert current["selected_supported_predecessor_id"] == "prev"
    assert current["predecessor_flight_id"] == "prev"
    assert current["search_depth"] == 2


def test_multiple_overlapping_rows_searches_back_to_latest_valid() -> None:
    cfg = load_config(mode="fast")
    result = apply_predecessor_support_rule(
        build_predecessor_candidates(_with_overlapping_candidates(3), cfg), cfg
    )
    current = result[result["episode_id"].eq("current")].iloc[0]
    assert current["predecessor_flight_id"] == "prev"
    assert bool(current["has_supported_predecessor"])
    assert current["search_depth"] == 4


def test_no_valid_predecessor_keeps_episode() -> None:
    cfg = load_config(mode="fast")
    invalid = _legs(overlap=True)
    features = build_predecessor_features(
        invalid, _MovementReference(), _TurnaroundReference(), cfg
    )
    current = features[features["episode_id"].eq("current")].iloc[0]
    assert current["predecessor_support_status"] == "UNSUPPORTED"
    assert pd.isna(current["selected_supported_predecessor_id"])


def test_programming_error_not_converted_to_nan() -> None:
    cfg = load_config(mode="fast")
    with pytest.raises(RuntimeError, match="fixture programming error"):
        build_predecessor_features(
            _legs(),
            _ProgrammingErrorMovementReference(),
            _TurnaroundReference(),
            cfg,
        )
