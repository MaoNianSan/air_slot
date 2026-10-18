"""Phase 6 lineage, hash, and metadata-diff tests."""

from __future__ import annotations

from validation.v2_phase6.lineage_hash_validation import (
    build_validation_report,
    reconstruct_metadata_diff,
)


def test_phase6_lineage_hash_validation_passes():
    report = build_validation_report()
    assert report["status"] == "PASS"
    assert report["failures"] == []
    assert report["baseline_commit"] == "2d74af9ee5a1cb5db59e0e94fac83f2aa608db01"
    assert report["baseline_tree"] == "4bb3257666421c46e18bd17703c11d2a78d347d2"
    assert report["final_test_access_count"] == 1
    assert report["current_freeze_run_increment"] == 0
    assert report["new_final_test_execution"] is False
    assert report["phase_7_entered"] is False
    assert report["no_final_test_path_read"] is True


def test_train_support_correction_is_metadata_only():
    diff = reconstruct_metadata_diff()
    assert diff["status"] == "PASS"
    assert diff["unexpected_differences"] == []
    assert diff["preserved_all_required_fields"] is True
    assert diff["numeric_payload_unchanged"] is True
    assert diff["sample_membership_unchanged"] is True
    assert diff["scientific_statistics_unchanged"] is True
    allowed_paths = {item["path"] for item in diff["allowed_differences"]}
    assert "artifact_hash" in allowed_paths
    assert "turnaround_reference.scope" in allowed_paths
    assert "turnaround_count_authority.artifact_hash" in allowed_paths
    assert "stage2_turnaround_lower_bound" in allowed_paths


def test_sample_arrays_are_exactly_unchanged():
    diff = reconstruct_metadata_diff()
    arrays = diff["sample_arrays"]
    assert arrays["status"] == "PASS"
    assert arrays["file_bytes_equal"] is True
    assert arrays["baseline_file_sha256"] == (
        "sha256:0dbbcc329f6c94fb02e734fd1414bb727a4341627b9141380f24e642db74b7a5"
    )
    assert arrays["current_file_sha256"] == arrays["baseline_file_sha256"]
    for name in ("turnaround_minutes", "headroom_nominal_minutes"):
        item = arrays["arrays"][name]
        assert item["exact_equal"] is True
        assert item["sorted_membership_equal"] is True
        assert item["unique_membership_equal"] is True
        assert item["baseline_array_sha256"] == item["current_array_sha256"]
