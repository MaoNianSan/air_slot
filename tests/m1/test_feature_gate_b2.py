import shutil

import pytest

import validation.m1_v2_feature_gate_b2 as gate_b2
from validation.m1_v2_feature_gate_b2r import DEFAULT_OUTPUT as REPO_B2R_OUTPUT


@pytest.fixture()
def isolated_b2r_output(tmp_path, monkeypatch):
    """Point the B2 gate at a private copy of the frozen B2R diagnostics.

    gate_b2 links the B2 freeze back into the B2R directory it read from, so
    running against the repository copy leaves tracked artifacts modified for
    the rest of the session and trips the phase-7 clean-tree gates.
    """
    target = tmp_path / "b2r"
    shutil.copytree(REPO_B2R_OUTPUT, target)
    monkeypatch.setattr(gate_b2, "B2R_OUTPUT", target)
    return target


def test_b2_freezes_after_semantic_redundancy_repair(tmp_path, isolated_b2r_output):
    for name in (
        "M1_V2_FEATURE_SCHEMA_FROZEN_B2.json",
        "M1_V2_STATIC_NORMALIZATION_B2.json",
        "M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz",
        "M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json",
    ):
        (tmp_path / name).write_text("stale", encoding="utf-8")
    report = gate_b2.run(tmp_path)

    assert report["FEATURE_GATE_STATUS"] == "FEATURE_GATE_B2_PASS_TARGET_SUPPORT_REVIEW_NEXT"
    assert report["gate_checks"]["contract_exact_duplicates"] is True
    assert report["redundancy"]["empirical_exact_duplicate_count"] == 2
    assert report["frozen_schema_hash"]
    assert report["frozen_cache_key"]
    assert report["cache"]["tensor_equivalence"]["status"] == "PASS"
    assert report["safety"]["GATE_B2_FEATURE_FREEZE"] is True
    assert (tmp_path / "M1_V2_FEATURE_SCHEMA_FROZEN_B2.json").is_file()
    assert (tmp_path / "M1_V2_STATIC_NORMALIZATION_B2.json").is_file()
    assert (tmp_path / "M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz").is_file()


def test_b2_pass_path_records_freeze_and_roundtrip_equivalence(tmp_path, isolated_b2r_output):
    report = gate_b2.run(tmp_path)

    assert report["FEATURE_GATE_STATUS"] == (
        "FEATURE_GATE_B2_PASS_TARGET_SUPPORT_REVIEW_NEXT"
    )
    assert report["frozen_schema_hash"]
    assert report["frozen_cache_key"]
    assert report["cache"]["tensor_equivalence"]["status"] == "PASS"
    assert report["safety"]["GATE_B2_FEATURE_FREEZE"] is True
    assert report["safety"]["M1_TARGET_SUPPORT_FROZEN"] is False
    assert report["safety"]["HYPERPARAMETER_TUNING_AUTHORIZED"] is False
    assert (tmp_path / "M1_V2_FEATURE_SCHEMA_FROZEN_B2.json").is_file()
    assert (tmp_path / "M1_V2_STATIC_NORMALIZATION_B2.json").is_file()
    assert (tmp_path / "M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz").is_file()
    assert (
        tmp_path / "M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json"
    ).is_file()
