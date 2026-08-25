"""Focused checks for the current-stage Development cohort refreeze."""

import json
from hashlib import sha256
from pathlib import Path

from exp.workflows.m1_v2_development_current_stage_refreeze import refreeze_current_stage_cohort


ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def test_current_stage_refreeze_preserves_parent_and_validates_frozen_m1(tmp_path):
    historical = ROOT / "artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT.json"
    historical_before = historical.read_bytes()
    outputs = refreeze_current_stage_cohort(root=ROOT, output_root=tmp_path)
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    cohort = json.loads(outputs["cohort"].read_text(encoding="utf-8"))
    feature_report = json.loads(outputs["feature_report"].read_text(encoding="utf-8"))
    m1_report = json.loads(outputs["m1_report"].read_text(encoding="utf-8"))

    assert manifest["status"] == "NEW_DEVELOPMENT_COHORT_REFROZEN"
    assert manifest["next_gate"] == "M1_CURRENT_STAGE_JOINT_SCENARIO_ARTIFACT_REQUIRED"
    assert cohort["cohort_hash"] != manifest["historical_cohort"]["cohort_hash"]
    assert _sha256(historical) == manifest["historical_cohort"]["sha256_before"]
    assert historical.read_bytes() == historical_before
    assert manifest["new_cohort"]["node_count"] == 69
    assert manifest["stage_audit"]["changed_node_count"] == 3
    assert manifest["stage_audit"]["current"] == {
        "PRE_IB": 5,
        "POST_IB_PRE_OB": 58,
        "POST_OB_PRE_TO": 6,
    }
    assert feature_report["status"] == "PASS_FROZEN_M1_FEATURE_TENSOR_COMPATIBILITY"
    assert feature_report["total_feature_count"] == 43
    assert feature_report["feature_schema_modified"] is False
    assert feature_report["support_modified"] is False
    assert m1_report["status"] == "PASS_FROZEN_M1_ARTIFACT_VALID_FOR_CURRENT_STAGE_INPUTS"
    assert m1_report["positive_tail_policy"] == "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS"
    for payload in (manifest, cohort, feature_report, m1_report):
        assert payload["FINAL_TEST_ACCESS_COUNT"] == 0
        assert payload["PAPER_FULL_RUN"] is False
        assert payload["FULL"] is False
