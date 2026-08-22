import json
from pathlib import Path

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_NAMES
from validation.m1_v2_feature_gate_b1r import DEFAULT_OUTPUT, load_a2_baseline
from validation.m1_v2_feature_semantics import (
    encoder_static_scan,
    feature_inventory,
    history_semantics,
    semantic_table,
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_current_inventory_is_the_b2r_frozen_source_schema():
    inventory = feature_inventory()
    assert inventory["dynamic_count"] == len(FEATURE_NAMES_V2) == 39
    assert inventory["static_count"] == len(STATIC_FEATURE_NAMES) == 4
    assert inventory["total_count"] == 43
    assert inventory["ordered_dynamic_features"] == list(FEATURE_NAMES_V2)
    assert inventory["ordered_static_features"] == list(STATIC_FEATURE_NAMES)
    assert not any(name.startswith("ar.weather.") for name in FEATURE_NAMES_V2)
    assert not any(".evidence." in name for name in FEATURE_NAMES_V2)
    assert "delta.schedule.signed_minutes_to_crs_departure" not in FEATURE_NAMES_V2
    assert (
        "delta.schedule.signed_minutes_to_crs_departure.derived_missing_mask"
        not in FEATURE_NAMES_V2
    )


def test_b1r_semantics_keep_local_delta_and_remove_full_prefix_history():
    rows = {row["FEATURE"]: row for row in semantic_table()}
    assert rows["delta.weather.temperature_c"]["HISTORY_SCOPE"] == "PREVIOUS_NODE_LOCAL"
    assert rows["delta.weather.temperature_c"]["TRANSFORMATION"] == (
        "DIFFERENCE_OF_TRAIN_STANDARDIZED_VALUES"
    )
    assert "ar.weather.temperature_c" not in rows
    assert rows["turnaround_reference_minutes"]["NORMALIZATION"] == "TRAIN_STANDARDIZED"
    assert rows["taxi_reference_minutes.missing_mask"]["NORMALIZATION"] == (
        "BINARY_NO_SCALE"
    )
    scan = encoder_static_scan()
    assert scan["ast_structural_zero_loop_found"] is False
    assert scan["features"] == []
    history = history_semantics()
    assert history["FULL_PREFIX_HISTORY_FEATURE_COUNT"] == 0
    assert history["EXP1B_HISTORY_SEPARATION_STATUS"] == "CLEAN"


def test_b1r_loads_frozen_a2_only_through_explicit_legacy_path():
    cache, manifest, result, old_names = load_a2_baseline()
    assert manifest["cache_schema_version"] == "M1_V2_DEVELOPMENT_BASE_CACHE_V3"
    assert manifest["cache_hash"] == (
        "sha256:7cb35178323aecdd288010b0b70daf15112695baf627b53d2bef03136393b082"
    )
    assert result["DATA_GATE_STATUS"] == "DATA_GATE_A2_PASS_READY_FOR_GATE_B"
    assert len(old_names) == cache.store.values_flat.shape[1] == 103


def test_historical_b1r_artifact_remains_unchanged():
    report = _read_json(DEFAULT_OUTPUT / "AIR_SLOT_M1_V2_FEATURE_GATE_B1R.json")
    assert report["FEATURE_GATE_STATUS"] == "FEATURE_GATE_B1R_PASS_CANDIDATE_READY_FOR_B2"
    assert report["wind_direction"]["missing_rows"] == 3087
    assert report["wind_direction"]["violations"] == 0
    assert report["missing_invariants"] == {
        "MISSING_NUMERIC_NOT_ZERO": 0,
        "DERIVED_INVALID_NUMERIC_NOT_ZERO": 0,
        "MISSING_MASK_VALUE_VIOLATIONS": 0,
        "STATIC_MISSING_BLOCK_ZERO_FILLED_WITHOUT_MASK": 0,
        "PARTIAL_STATIC_OBSERVED_VALUE_LOST": 0,
    }
    assert report["static"]["partial_missing_cases"] == 4
    assert report["static"]["observed_counterpart_retained"] is True
    assert report["exp1b"]["FULL_PREFIX_HISTORY_FEATURE_COUNT"] == 0
    assert report["target"]["label_profile_unchanged"] is True
    assert report["target"]["overflow"] == 90


def test_historical_b1r_candidate_cache_roundtrip_is_preserved():
    output = DEFAULT_OUTPUT
    report = _read_json(output / "AIR_SLOT_M1_V2_FEATURE_GATE_B1R.json")
    manifest_path = output / "M1_V2_FEATURE_GATE_B1R_CANDIDATE_CACHE_MANIFEST.json"
    data_path = output / "M1_V2_FEATURE_GATE_B1R_CANDIDATE_CACHE.npz"
    loaded = M1DevelopmentBaseCache.load(
        data_path,
        manifest_path,
        expected_cache_key=report["cache"]["candidate_cache_key"],
    )
    assert loaded.store.values_flat.shape[1] == 41
    assert loaded.store.static_values.shape[1] == 4
    assert report["cache"]["roundtrip"]["status"] == "PASS"
    assert all(
        report["cache"]["a2_identity_labels_active_lineage_ids_unchanged"].values()
    )
    assert report["validation_gates"]["data_usage_status"] == (
        "DATA_USAGE_CONTRACT_AUDIT_PASS"
    )
    assert report["safety"] == {
        "M1_TRAINING_RUNS": 0,
        "TUNING_RUNS": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "GATE_B_ENTERED": True,
        "GATE_B2_FEATURE_FREEZE": False,
    }
    assert (output / "M1_V2_FEATURE_SCHEMA_CANDIDATE_B1R.json").is_file()
    assert (output / "M1_V2_FEATURE_GATE_B2_CANDIDATE_PACKET.md").is_file()
