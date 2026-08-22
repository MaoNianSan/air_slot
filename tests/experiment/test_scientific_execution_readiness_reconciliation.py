import json
from pathlib import Path

from exp.scientific_execution_readiness_reconciliation import reconcile


ROOT = Path(__file__).resolve().parents[2]


def test_reconciliation_preserves_real_blockers_and_claim_boundaries(tmp_path):
    paths = reconcile(root=ROOT, output_root=tmp_path)
    report = json.loads(paths["reconciliation"].read_text(encoding="utf-8"))
    readiness = json.loads(paths["readiness"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    assert report["status"] == "READY_WITH_CURRENT_ARTIFACT_BLOCKERS"
    assert report["current_contracts"]["M1"]["model_id"] == "M1_V2_GRU_H32"
    assert report["current_contracts"]["M1"]["development_inference_status"] == "NEW_DEVELOPMENT_COHORT_REFROZEN"
    assert report["current_contracts"]["M1"]["current_stage_node_count"] == 69
    assert report["current_contracts"]["M1"]["current_stage_changed_node_count"] == 3
    assert report["current_contracts"]["M2"]["artifact_status"] == "BLOCKED_M2_V2_FORMAL_VALUES_AND_AGGREGATE"
    assert report["current_contracts"]["M3"]["non_a00_v2_execution_enabled"] is False
    assert report["current_contracts"]["M4"]["production_mapping_enabled"] is False
    assert report["minimum_real_artifacts"]["Exp2"]["current_status"] == "BLOCKED_BEFORE_METRIC_GENERATION"
    assert report["minimum_real_artifacts"]["Exp3"]["current_status"] == "BLOCKED_CURRENT_FROZEN_ARTIFACT_GATES"
    assert report["minimum_real_artifacts"]["Exp4"]["current_status"] == "BLOCKED_CURRENT_ARTIFACT_AND_BASELINE_GATES"
    assert report["manuscript_claim_audit"]["claims"][1]["current_status"] == "BLOCKED"
    assert report["prohibitions"]["legacy_v1_promotion"] is True
    assert readiness["status"] == "AIR_SLOT_SCIENTIFIC_EXECUTION_READY"
    assert readiness["execution_status"] == "BLOCKED_CURRENT_REAL_ARTIFACT_GATES"
    assert readiness["first_human_gate"] == "M1_POSITIVE_TAIL_DECISION_REQUIRED"
    assert readiness["manuscript_implementation_mismatch_count"] >= 2
    mismatches = report["manuscript_claim_audit"]["implementation_alignment"]["mismatches"]
    assert all(item["code"] == "MANUSCRIPT_IMPLEMENTATION_MISMATCH" for item in mismatches)
    assert manifest["m3_binding"]["non_a00_v2_execution_enabled"] is False
    assert manifest["m4_binding"]["mapping_status"] == "MONETARY_MAPPING_BLOCKED"
    assert manifest["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert manifest["safety"]["PAPER_FULL_RUN"] is False
    assert manifest["safety"]["FULL"] is False
