import json
from pathlib import Path

from exp.exp3.formal_support_audit import audit


ROOT = Path(__file__).resolve().parents[3]


def test_formal_support_audit_preserves_non_a00_blocker(tmp_path):
    paths = audit(root=ROOT, output_root=tmp_path)
    artifact = json.loads(paths["artifact"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    assert artifact["status"] == "EXP3_FORMAL_COHORT_ASSUMPTION_GROUNDED_READY"
    assert artifact["executable_action_ids"][0] == "A00"
    assert len(artifact["executable_action_ids"]) == 23
    assert len(artifact["non_a00_executable_action_ids"]) == 22
    assert artifact["non_a00_executable_action_ids"][0] == "A11"
    assert artifact["formal_multi_action_cohort"]["node_count"] == 0
    assert artifact["formal_multi_action_cohort"]["status"] == "READY_SCENARIO_CONDITIONAL_AUTHORITATIVE_RANKING_GATED"
    assert manifest["formal_multi_action_cohort_status"] == "READY_SCENARIO_CONDITIONAL_AUTHORITATIVE_RANKING_GATED"
    assert artifact["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert artifact["safety"]["PAPER_FULL_RUN"] is False
