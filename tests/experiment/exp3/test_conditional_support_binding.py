import json
from pathlib import Path

from exp.exp3.conditional_support_binding import bind


ROOT = Path(__file__).resolve().parents[3]


def test_conditional_support_is_bound_to_exp3_without_formal_upgrade(tmp_path):
    paths = bind(root=ROOT, output_root=tmp_path)
    artifact = json.loads(paths["artifact"].read_text(encoding="utf-8"))
    assert artifact["status"] == "EXP3_CONDITIONAL_SCENARIO_LANE_BOUND"
    assert artifact["conditional_action_count"] == 22
    assert artifact["formal_multi_action_status"] == "BLOCKED_UNCHANGED"
    assert artifact["authoritative_ranking_allowed"] is False
    assert artifact["causal_effect_claim_allowed"] is False
    assert artifact["monetary_chain"] == "C^a -> CU^a -> RMB^a -> risk"
    assert artifact["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
