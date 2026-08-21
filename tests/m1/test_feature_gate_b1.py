from pathlib import Path

from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_NAMES
from validation.m1_v2_feature_gate_b1 import load_a2_cache, run
from validation.m1_v2_feature_profile import feature_profiles, missing_encoding_audit
from validation.m1_v2_feature_redundancy import redundancy_audit
from validation.m1_v2_feature_semantics import (
    encoder_static_scan,
    feature_inventory,
    history_semantics,
    semantic_table,
)


def test_b1_inventory_is_generated_from_current_code():
    inventory = feature_inventory()
    assert inventory["dynamic_count"] == len(FEATURE_NAMES_V2) == 103
    assert inventory["static_count"] == len(STATIC_FEATURE_NAMES) == 2
    assert inventory["total_count"] == 105
    assert inventory["ordered_dynamic_features"] == list(FEATURE_NAMES_V2)
    assert inventory["ordered_static_features"] == list(STATIC_FEATURE_NAMES)


def test_b1_semantics_expose_delta_ar_and_structural_zero_contracts():
    rows = {row["FEATURE"]: row for row in semantic_table()}
    assert rows["delta.weather.temperature_c"]["HISTORY_SCOPE"] == "PREVIOUS_NODE_LOCAL"
    assert rows["delta.weather.temperature_c"]["TRANSFORMATION"] == (
        "DIFFERENCE_OF_TRAIN_STANDARDIZED_VALUES"
    )
    assert rows["ar.weather.temperature_c"]["HISTORY_SCOPE"] == "FULL_PREFIX_SUMMARY"
    scan = encoder_static_scan()
    assert scan["ast_structural_zero_loop_found"] is True
    assert len(scan["features"]) == 9
    history = history_semantics()
    assert history["AR_ACTUAL_SEMANTICS"]["classification"] == (
        "FULL_PREFIX_CUMULATIVE_MEAN"
    )
    assert history["EXP1B_HISTORY_SEPARATION_STATUS"] == "HISTORY_DUPLICATED_IN_RFAST"


def test_b1_a2_cache_profile_and_redundancy_are_train_only():
    cache, manifest, _ = load_a2_cache()
    assert manifest["final_test_access_count"] == 0
    profiles = feature_profiles(cache)
    assert len(profiles["profiles"]["train"]) == 105
    assert all(row["count"] == 1880 for row in profiles["profiles"]["train"])
    assert len(profiles["static_contract_violations"]) == 4
    redundancy = redundancy_audit(cache)
    assert redundancy["basis"] == "TRAIN_CURRENT_ROWS_ONLY_NO_LABELS"
    assert redundancy["row_count"] == 1880
    assert redundancy["weather_object_level_masks"]["stale"][
        "all_train_rows_exactly_equal"
    ] is True
    assert redundancy["weather_object_level_masks"]["fallback"][
        "all_train_rows_exactly_equal"
    ] is True


def test_b1_missing_audit_detects_wind_cosine_non_neutral_missing_encoding():
    cache, _, _ = load_a2_cache()
    audit = missing_encoding_audit(cache)
    wind = next(
        row for row in audit["checks"]
        if row["numeric"] == "weather.wind_direction_deg.cos"
    )
    assert wind["missing_rows"] > 0
    assert wind["violations"] == wind["missing_rows"]
    assert audit["all_checked_encodings_exact"] is False


def test_b1_runner_stops_before_b2_and_writes_decision_packet(tmp_path: Path):
    report = run(tmp_path)
    assert report["FEATURE_GATE_STATUS"] == "FEATURE_GATE_B1_DATA_INCONSISTENCY"
    assert report["safety"] == {
        "M1_TRAINING_RUNS": 0,
        "TUNING_RUNS": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "GATE_B_ENTERED": True,
        "GATE_B2_FEATURE_FREEZE": False,
    }
    assert report["automatic_decisions_applied"] is False
    assert report["validation_gates"]["data_usage_status"] == (
        "DATA_USAGE_CONTRACT_AUDIT_PASS"
    )
    assert report["validation_gates"]["ownership_status"] == "PASS"
    assert [row["decision_id"] for row in report["human_decisions"]][:6] == [
        "B1-D01", "B1-D02", "B1-D03", "B1-D04", "B1-D05", "B1-D06"
    ]
    assert (tmp_path / "AIR_SLOT_M1_V2_FEATURE_GATE_B1.json").is_file()
    assert (tmp_path / "FEATURE_DECISION_PACKET.md").is_file()
