from __future__ import annotations

from core_fixtures import core_cfg
from core_v2_bundle_fixture import build_synthetic_bundle
from src.core.existing_bundle_validator import validate_existing_bundle


def test_existing_bundle_validator_recomputes_instead_of_trusting_json(tmp_path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "core_validation.json").write_text('{"status": "PASS"}', encoding="utf-8")
    result = validate_existing_bundle(tmp_path, core_cfg())
    assert result["status"] == "FAIL"
    assert result["reason"] == "MANIFEST_UNREADABLE"
    assert (reports / "core_validation_recomputed.json").exists()


def test_existing_bundle_validator_passes_complete_synthetic_bundle(tmp_path) -> None:
    bundle = build_synthetic_bundle(tmp_path)
    result = validate_existing_bundle(tmp_path, bundle["cfg"])
    assert result["status"] == "PASS", result
