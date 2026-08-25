import json
from pathlib import Path

from exp.workflows.m4_cu_rmb_readiness_audit import materialize


ROOT = Path(__file__).resolve().parents[2]


def test_cu_rmb_audit_is_fail_closed_and_non_executing(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    artifact = json.loads(paths["artifact"].read_text(encoding="utf-8"))
    assert artifact["chain"] == "C -> CU -> RMB -> risk"
    assert artifact["readiness_status"] == "BLOCKED_M4_RMB_MAPPING_SCIENTIFIC_DECISION_REQUIRED"
    assert all(artifact["checks"].values())
    assert artifact["mapping_gate"]["status"] == "HUMAN_SCIENTIFIC_DECISION_REQUIRED"
    assert artifact["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert artifact["safety"]["PAPER_FULL_RUN"] is False


def test_cu_rmb_audit_emits_decision_packet_and_manifest(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    decision = json.loads(paths["decision_packet"].read_text(encoding="utf-8"))
    assert manifest["readiness_status"] == decision["status"]
    assert decision["decision_required"]["required_decisions"]
