import pytest

from exp.common.result_schema import SupportStatus
from exp.exp2.evaluator import Exp2EvaluationPayload, Exp2Evaluator
from model.M4.residual_risk import RankingAuthority, RiskEvaluationEnvelope


def _risk(action_id, residual, cvar):
    return RiskEvaluationEnvelope.model_construct(
        action_id=action_id,
        monetary_system_id="RMB_FIXTURE",
        monetary_mapping_registry_hash="sha256:" + "a" * 64,
        risk_policy_hash="sha256:" + "b" * 64,
        alpha=0.9,
        ranking_authority=RankingAuthority.AUTHORITATIVE,
        residual_risk_objective=residual,
        monetary_loss_cvar_alpha=cvar,
    )


def test_common_evaluator_records_decision_and_m4_risk_differences():
    metrics = Exp2Evaluator().evaluate(Exp2EvaluationPayload(
        reference_variant_id="EXP2A_JOINT",
        variant_id="EXP2A_MARGINAL",
        reference_m4=(_risk("A00", 1.0, 1.5), _risk("A01", 2.0, 2.5)),
        variant_m4=(_risk("A00", 3.0, 3.5), _risk("A01", 2.0, 2.5)),
    ))

    assert metrics["STATE_CRPS"].support_status is SupportStatus.NOT_RUN
    assert metrics["DECISION_ACTION_DISAGREEMENT"].value == 1.0
    assert metrics["DECISION_RANKING_CHANGE"].value == 1.0
    assert metrics["DECISION_RISK_DIFFERENCE"].value == pytest.approx(1.0)
    assert metrics["DECISION_CVAR_DIFFERENCE"].value == pytest.approx(1.0)
    assert metrics["DECISION_RISK_DIFFERENCE"].metadata["difference_direction"] == "variant_minus_reference"
