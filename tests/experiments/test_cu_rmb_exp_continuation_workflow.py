import json
from pathlib import Path

from exp.workflows.cu_rmb_exp_continuation_workflow import materialize


ROOT = Path(__file__).resolve().parents[2]


def test_continuation_workflow_preserves_approved_cu_and_abstain_policy(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    report = json.loads(paths["report"].read_text(encoding="utf-8"))
    abstain = json.loads(paths["abstain"].read_text(encoding="utf-8"))
    m2 = json.loads(paths["m2_binding"].read_text(encoding="utf-8"))
    assert report["chain"] == "E -> S -> C -> CU -> RMB -> risk -> decision"
    assert report["scientific_decisions"]["cu_transformation"] == "TRAIN_POSITIVE_MEDIAN"
    assert abstain["principal_strategy"] == "A_KEEP_ABSTAIN_AND_EVALUATE_SUPPORTED_DIMENSIONS_ONLY"
    assert abstain["secondary_strategy"] == "C_SCENARIO_SENSITIVITY_ONLY_WITH_SEPARATE_NON_PRINCIPAL_LABEL"
    assert m2["formal_scope"] == ["F_continuity", "F_execution", "F_propagation", "P_time", "R_operating"]
    assert m2["abstain_components"] == ["P_itinerary", "P_service"]


def test_continuation_workflow_keeps_downstream_gates_honest(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    rmb = json.loads(paths["rmb_binding"].read_text(encoding="utf-8"))
    m4 = json.loads(paths["m4_readiness"].read_text(encoding="utf-8"))
    exp2 = json.loads(paths["exp2_readiness"].read_text(encoding="utf-8"))
    exp3 = json.loads(paths["exp3_readiness"].read_text(encoding="utf-8"))
    exp4 = json.loads(paths["exp4_readiness"].read_text(encoding="utf-8"))
    assert rmb["cu_to_rmb"] == "RMB_k = 1.0 * CU_k"
    assert rmb["authoritative_ranking_allowed"] is False
    assert m4["status"] == "SCENARIO_CONDITIONED_NON_AUTHORITATIVE_READY"
    assert exp2["status"] == "BLOCKED_UNSUPPORTED_MAPPING"
    assert exp3["status"] == "BLOCKED_FORMAL_COHORT_AND_MAPPING"
    assert exp4["status"] == "BLOCKED_PREDICTIVE_ARTIFACTS_AND_MAPPING"
    assert report_safety_zero(report=m4)


def report_safety_zero(*, report: dict) -> bool:
    safety = report["safety"]
    return safety["FINAL_TEST_ACCESS_COUNT"] == 0 and safety["PAPER_FULL_RUN"] is False
