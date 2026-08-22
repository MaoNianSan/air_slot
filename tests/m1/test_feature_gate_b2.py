import validation.m1_v2_feature_gate_b2 as gate_b2


def test_b2_stops_before_freeze_on_exact_duplicates(tmp_path):
    for name in (
        "M1_V2_FEATURE_SCHEMA_FROZEN_B2.json",
        "M1_V2_STATIC_NORMALIZATION_B2.json",
        "M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz",
        "M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json",
    ):
        (tmp_path / name).write_text("stale", encoding="utf-8")
    report = gate_b2.run(tmp_path)

    assert report["FEATURE_GATE_STATUS"] == "FEATURE_GATE_B2_CONTRACT_FAILURE"
    assert report["gate_checks"]["exact_duplicates"] is False
    assert report["redundancy"]["exact_duplicate_count"] == 3
    assert report["frozen_schema_hash"] is None
    assert report["frozen_cache_key"] is None
    assert report["cache"]["tensor_equivalence"]["status"] == "NOT_CREATED"
    assert report["safety"]["GATE_B2_FEATURE_FREEZE"] is False
    assert not (tmp_path / "M1_V2_FEATURE_SCHEMA_FROZEN_B2.json").exists()
    assert not (tmp_path / "M1_V2_STATIC_NORMALIZATION_B2.json").exists()
    assert not (tmp_path / "M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz").exists()
    assert not (
        tmp_path / "M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json"
    ).exists()


def test_b2_pass_path_records_freeze_and_roundtrip_equivalence(
    tmp_path, monkeypatch
):
    original_audit = gate_b2.redundancy_audit

    def resolved_redundancy(cache):
        result = original_audit(cache)
        return {**result, "exact_duplicate_groups": []}

    monkeypatch.setattr(gate_b2, "redundancy_audit", resolved_redundancy)
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
