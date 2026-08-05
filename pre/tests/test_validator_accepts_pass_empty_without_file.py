from __future__ import annotations

from core_v2_bundle_fixture import build_synthetic_bundle
from src.core.validation import validate_existing_bundle


def test_validator_accepts_pass_empty_partition_without_file(tmp_path) -> None:
    bundle = build_synthetic_bundle(tmp_path, include_pass_empty=True)
    result = validate_existing_bundle(tmp_path, bundle["cfg"], write_report=False)
    assert result["status"] == "PASS", result
    assert result["checks"]["observations"]["pass_empty_count"] == 1
    assert result["checks"]["membership_uniqueness"]["pass_empty"] == 1
