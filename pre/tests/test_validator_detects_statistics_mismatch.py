from __future__ import annotations

import json

from core_v2_bundle_fixture import build_synthetic_bundle
from src.core.existing_bundle_validator import validate_existing_bundle


def test_validator_detects_stored_statistics_mismatch(tmp_path) -> None:
    bundle = build_synthetic_bundle(tmp_path)
    stored_path = tmp_path / "reports/core_validation.json"
    stored = json.loads(stored_path.read_text(encoding="utf-8"))
    stored["statistics"]["events_rows"] += 1
    stored_path.write_text(json.dumps(stored), encoding="utf-8")
    result = validate_existing_bundle(tmp_path, bundle["cfg"], write_report=False)
    assert result["status"] == "FAIL"
    assert result["reason"] == "STORED_AND_RECOMPUTED_STATISTICS_MISMATCH"
    assert "events_rows" in result["checks"]["statistics_recomputation"]["mismatches"]
