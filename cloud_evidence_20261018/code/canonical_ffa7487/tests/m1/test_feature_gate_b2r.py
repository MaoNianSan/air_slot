import numpy as np

from validation.m1_v2_feature_gate_b2r import run as run_b2r
from validation.m1_v2_feature_gate_b2 import run as run_b2
from validation.m1_v2_feature_redundancy import _exact_groups


def test_train_exact_equal_different_source_is_empirical_only():
    names = ("weather.temperature_c.missing_mask", "weather.dewpoint_c.missing_mask")
    matrix = np.array([[0.0, 0.0], [1.0, 1.0]], dtype=float)
    splits = np.asarray(["train", "train"])

    groups = _exact_groups(matrix, names, splits)

    assert groups[0]["classification"] == "EMPIRICAL_EXACT_DUPLICATE"


def test_same_contract_exact_equal_is_a_blocker():
    names = ("state.ib_realized", "state.ob_realized")
    matrix = np.array([[0.0, 0.0], [1.0, 1.0]], dtype=float)
    splits = np.asarray(["train", "train"])

    groups = _exact_groups(matrix, names, splits)

    assert groups[0]["classification"] == "CONTRACT_EXACT_DUPLICATE"


def test_train_equal_development_diverges_remains_empirical():
    names = ("weather.temperature_c.missing_mask", "weather.dewpoint_c.missing_mask")
    matrix = np.array([[0.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=float)
    splits = np.asarray(["train", "train", "development"])

    groups = _exact_groups(matrix, names, splits)

    assert groups[0]["classification"] == "EMPIRICAL_EXACT_DUPLICATE"
    assert groups[0]["train_equal"] is True
    assert groups[0]["development_equal"] is False


def test_b2r_preserves_partial_static_and_removes_schedule_delta(tmp_path):
    report = run_b2r(tmp_path)

    assert report["FEATURE_GATE_STATUS"] == "FEATURE_GATE_B2R_PASS_CANDIDATE_READY_FOR_B2"
    assert report["feature_counts"] == {"dynamic": 39, "static": 4, "total": 43}
    assert report["schedule_delta"]["present_in_candidate"] is False
    assert report["static"]["partial_missing_preserved"] is True
    assert report["static"]["partial_missing_cases"] == 4
    assert report["redundancy"]["contract_exact_duplicate_count"] == 0
    assert report["redundancy"]["empirical_exact_duplicate_count"] == 2


def test_b2_freeze_only_after_contract_blockers_are_clear(tmp_path):
    b2r = run_b2r()
    assert b2r["FEATURE_GATE_STATUS"] == "FEATURE_GATE_B2R_PASS_CANDIDATE_READY_FOR_B2"

    report = run_b2(tmp_path)

    assert report["FEATURE_GATE_STATUS"] == "FEATURE_GATE_B2_PASS_TARGET_SUPPORT_REVIEW_NEXT"
    assert report["feature_counts"] == {"dynamic": 39, "static": 4, "total": 43}
    assert report["redundancy"]["contract_exact_duplicate_count"] == 0
    assert report["redundancy"]["empirical_exact_duplicate_count"] == 2
    assert report["cache"]["tensor_equivalence"]["status"] == "PASS"
    assert report["safety"]["GATE_B2_FEATURE_FREEZE"] is True
    assert report["safety"]["M1_TARGET_SUPPORT_FROZEN"] is False
    assert report["safety"]["HYPERPARAMETER_TUNING_AUTHORIZED"] is False
    assert (tmp_path / "M1_V2_FEATURE_SCHEMA_FROZEN_B2.json").is_file()
    assert (tmp_path / "M1_V2_STATIC_NORMALIZATION_B2.json").is_file()
    assert (tmp_path / "M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz").is_file()
