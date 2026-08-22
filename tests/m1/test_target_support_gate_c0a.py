from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from validation.m1_v2_target_support_c0a_source import (
    classify_departure_consistency,
    classify_departure_values,
)
from validation.m1_v2_target_support_gate_c0a import (
    EXPECTED_CACHE_HASH,
    EXPECTED_SCHEMA_HASH,
    _episode_values,
    run,
)


@pytest.mark.parametrize(
    ("schedule", "actual", "zone", "delay", "expected"),
    [
        (
            datetime(2019, 3, 10, 6, 30, tzinfo=timezone.utc),
            datetime(2019, 3, 10, 7, 30, tzinfo=timezone.utc),
            "America/New_York",
            120,
            "DST_CLOCK_BASIS_EXPLAINED",
        ),
        (
            datetime(2019, 11, 3, 4, 30, tzinfo=timezone.utc),
            datetime(2019, 11, 3, 7, 30, tzinfo=timezone.utc),
            "America/New_York",
            120,
            "DST_CLOCK_BASIS_EXPLAINED",
        ),
        (
            datetime(2019, 1, 1, 15, 0, tzinfo=timezone.utc),
            datetime(2019, 1, 1, 16, 0, tzinfo=timezone.utc),
            "America/New_York",
            60,
            "SOURCE_CONSISTENT",
        ),
        (
            datetime(2019, 1, 1, 15, 0, tzinfo=timezone.utc),
            datetime(2019, 1, 3, 16, 0, tzinfo=timezone.utc),
            "America/New_York",
            2940,
            "SOURCE_CONSISTENT",
        ),
    ],
)
def test_departure_clock_classification(schedule, actual, zone, delay, expected):
    assert classify_departure_consistency(
        schedule_utc=schedule,
        direct_utc=actual,
        timezone_name=zone,
        signed_delay=delay,
    ) == expected


def test_real_265_minute_source_case_is_a_direct_signed_conflict():
    clock = classify_departure_values(
        schedule_utc=datetime(2019, 3, 27, 12, 0, tzinfo=timezone.utc),
        direct_utc=datetime(2019, 3, 27, 16, 16, tzinfo=timezone.utc),
        timezone_name="America/New_York",
        signed_delay=-9,
        old_difference=265,
    )

    assert clock["classification"] == "DIRECT_CLOCK_SIGNED_DELAY_CONFLICT"
    assert clock["local_wall_clock_residual_minutes"] == 265
    assert clock["residual_minutes"] == 265


def test_episode_selection_units_deduplicate_outcomes_and_maximize_hazard():
    d_ob, d_ob_check = _episode_values({"moderate": [189.0] * 12}, "D_OB")
    d_tx, d_tx_check = _episode_values({"shift": [98.0] * 12}, "D_TX")
    t_ib, t_ib_check = _episode_values(
        {"long": [320.0, 325.0, 330.0, 360.0, 365.0]},
        "T_IB_REMAINING_HAZARD",
    )

    assert d_ob == {"moderate": 189.0}
    assert d_tx == {"shift": 98.0}
    assert t_ib == {"long": 365.0}
    assert d_ob_check["status"] == d_tx_check["status"] == t_ib_check["status"] == "PASS"


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_c0a_episode_audit_preserves_b2_and_final_test_boundary(tmp_path):
    root = Path(__file__).resolve().parents[2]
    b2 = root / "artifacts" / "diagnostics" / "m1_v2_feature_gate_b2"
    guarded = (
        b2 / "M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz",
        b2 / "M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json",
        root / "configs" / "scientific" / "foundation.yaml",
    )
    before = {path: _digest(path) for path in guarded}

    report = run(tmp_path, source_scan=False)

    assert {path: _digest(path) for path in guarded} == before
    assert report["TARGET_SUPPORT_C0A_STATUS"] == "TARGET_SUPPORT_C0A_WEIGHTING_REVIEW_REQUIRED"
    assert report["status_flags"] == ["TARGET_SUPPORT_C0A_WEIGHTING_REVIEW_REQUIRED"]
    assert report["b2_immutability"]["schema_hash"] == EXPECTED_SCHEMA_HASH
    assert report["b2_immutability"]["cache_hash"] == EXPECTED_CACHE_HASH
    assert report["b2_immutability"]["labels_unchanged"] is True
    assert report["b2_immutability"]["active_masks_unchanged"] is True
    assert report["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert report["safety"]["M1_TRAINING_RUNS"] == 0
    assert report["safety"]["TUNING_RUNS"] == 0


def test_c0a_frozen_episode_profiles_and_recommendations(tmp_path):
    report = run(tmp_path, source_scan=False)
    train = report["episode_balance"]["profiles"]["train"]
    calibration = report["episode_balance"]["profiles"]["calibration"]
    development = report["episode_balance"]["profiles"]["development"]

    assert (train["T_IB_REMAINING_HAZARD"]["row_active_count"],
            train["T_IB_REMAINING_HAZARD"]["unique_episode_count"],
            train["T_IB_REMAINING_HAZARD"]["episode_profile"]["current_support_count"]) == (342, 40, 1)
    assert (train["D_OB"]["row_active_count"], train["D_OB"]["unique_episode_count"],
            train["D_OB"]["episode_profile"]["current_support_count"]) == (1793, 128, 3)
    assert (train["D_TX"]["row_active_count"], train["D_TX"]["unique_episode_count"],
            train["D_TX"]["episode_profile"]["current_support_count"]) == (1880, 128, 0)
    assert calibration["D_OB"]["episode_profile"]["current_support_count"] == 2
    assert development["D_TX"]["episode_profile"]["current_support_count"] == 3
    assert [item["recommendation"] for item in report["human_decisions"]] == [
        "KEEP_360",
        "EXPAND_TO_210",
        "KEEP_60",
    ]
    assert report["training_weighting"]["row_weighted_loss_detected"] is True
