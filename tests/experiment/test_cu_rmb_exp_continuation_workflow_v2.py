import json
from pathlib import Path

from exp.cu_rmb_exp_continuation_workflow_v2 import materialize
from exp.exp2.artifacts.artifact_schema import Exp2MonetaryMappingBundle, Exp2RiskPolicyBundle


ROOT = Path(__file__).resolve().parents[2]


def test_v2_materializes_frozen_internal_loss_bundle_without_rmb_overclaim(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    mapping = Exp2MonetaryMappingBundle.model_validate(json.loads(paths["mapping"].read_text(encoding="utf-8")))
    policy = Exp2RiskPolicyBundle.model_validate(json.loads(paths["risk_policy"].read_text(encoding="utf-8")))
    report = json.loads(paths["report"].read_text(encoding="utf-8"))
    assert mapping.support_status.value == "FROZEN"
    assert mapping.interpretation == "CONSTRUCTED_INTERNAL_LOSS_UNIT"
    assert policy.support_status.value == "FROZEN"
    assert report["rmb_baseline"] == "RMB_k = 1.0 * CU_k"
    assert report["scientific_boundary"]["real_currency_claim"] is False
    assert report["scientific_boundary"]["authoritative_ranking_allowed"] is False


def test_v2_keeps_m3_and_predictive_blockers(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    exp2 = json.loads(paths["exp2_readiness"].read_text(encoding="utf-8"))
    exp3 = json.loads(paths["exp3_readiness"].read_text(encoding="utf-8"))
    exp4 = json.loads(paths["exp4_readiness"].read_text(encoding="utf-8"))
    assert exp2["status"] == "BLOCKED_M3_NON_A00_CONDITIONAL_RESPONSE_GATE"
    assert exp3["status"] == "BLOCKED_M3_FORMAL_COHORT"
    assert exp4["status"] == "BLOCKED_PREDICTIVE_ARTIFACTS"
    for payload in (exp2, exp3, exp4):
        assert payload["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
        assert payload["safety"]["PAPER_FULL_RUN"] is False
