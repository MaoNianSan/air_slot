import json
from pathlib import Path

from exp.exp3.conditional_action_support_acceptance import materialize


ROOT = Path(__file__).resolve().parents[3]


def test_conditional_hybrid_support_materializes_without_formal_upgrade(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    artifact = json.loads(paths["artifact"].read_text(encoding="utf-8"))
    rows = artifact["action_support_table"]
    assert artifact["status"] == "M3_CONDITIONAL_HYBRID_SUPPORT_MATERIALIZED"
    assert artifact["conditional_action_count"] == 22
    assert artifact["formal_support_upgrade"] is False
    assert artifact["non_a00_v2_execution_enabled"] is True
    assert artifact["conditional_scenario_lane"] == "READY"
    assert artifact["formal_multi_action_lane"] == "READY_SCENARIO_CONDITIONAL_AUTHORITATIVE_RANKING_GATED"
    assert rows[0]["support"]["support_state"] == "SUPPORTED"
    assert all(row["support"]["support_state"] == "CONDITIONAL" for row in rows[1:])
    assert all(row["support"]["evidence_bases"] == ["PUBLISHED_EVIDENCE", "ASSUMPTION_GROUNDED_SCENARIO"] for row in rows[1:])
    assert all(row["support"].get("assumption_grounded") is not None for row in rows[1:])
    assert all(row["support"]["effect_identification"] == "NOT_EMPIRICALLY_IDENTIFIED" for row in rows[1:])
    assert all(row["authoritative_ranking_allowed"] is False for row in rows)
    assert artifact["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
