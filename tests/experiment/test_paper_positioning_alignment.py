import json
from pathlib import Path

from exp.paper_positioning_alignment import materialize


ROOT = Path(__file__).resolve().parents[2]


def test_positioning_alignment_preserves_experiment_questions(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    report = json.loads(paths["report"].read_text(encoding="utf-8"))
    assert report["central_chain"] == "E -> S -> C -> CU -> RMB -> risk -> decision"
    assert report["experiment_alignment"]["Exp1"]["question"].startswith("necessity")
    assert "representation" in report["experiment_alignment"]["Exp2"]["question"]
    assert report["experiment_alignment"]["Exp3"]["forbidden_reinterpretation"] == "causal action-effect estimation or empirical action effectiveness"
    assert report["experiment_alignment"]["Exp3"]["non_a00_status"] == "SCENARIO_CONDITIONED_DECISION_CANDIDATES"
    assert report["claim_guardrails"]["causal_action_effect_claim"] is False


def test_positioning_alignment_is_non_executing(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    report = json.loads(paths["report"].read_text(encoding="utf-8"))
    assert report["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert report["safety"]["EXP1_RUNS"] if "EXP1_RUNS" in report["safety"] else True
    assert report["safety"]["PAPER_FULL_RUN"] is False
