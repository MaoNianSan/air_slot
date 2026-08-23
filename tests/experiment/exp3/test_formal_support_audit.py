import json
from pathlib import Path

from exp.exp3.formal_support_audit import audit


ROOT = Path(__file__).resolve().parents[3]


def test_formal_support_audit_preserves_non_a00_blocker(tmp_path):
    paths = audit(root=ROOT, output_root=tmp_path)
    artifact = json.loads(paths["artifact"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    assert artifact["status"] == "EXP3_FORMAL_COHORT_BLOCKED"
    assert artifact["executable_action_ids"] == ["A00"]
    assert artifact["non_a00_executable_action_ids"] == []
    assert artifact["formal_multi_action_cohort"]["node_count"] == 0
    assert manifest["formal_multi_action_cohort_status"] == "BLOCKED_NO_EXECUTABLE_NON_A00_ACTION"
    assert artifact["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert artifact["safety"]["PAPER_FULL_RUN"] is False
