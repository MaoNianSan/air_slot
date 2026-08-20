from pathlib import Path

import pytest

from model.M3.action_response import ActionEvaluationEnvelope, ActionResponseRule
from model.M4.residual_risk import RankingAuthority, RiskEvaluationEnvelope


@pytest.fixture
def model_versions():
    return {"M1": "M1_FIXTURE_V1", "M2": "M2_FIXTURE_V1", "M3": "M3_FIXTURE_V1", "M4": "M4_FIXTURE_V1"}


@pytest.fixture
def recording_executors():
    calls = []

    def m3_executor(*, variant_id, scenarios, consequences, m3_artifact):
        calls.append(("M3", variant_id, scenarios.variant_id, consequences.variant_id))
        rule = ActionResponseRule.model_construct(
            rule_hash=m3_artifact.response_registry_hash,
        )
        return (ActionEvaluationEnvelope.model_construct(
            action_id="A00",
            action_family="null",
            response_rule=rule,
            input_scenario_ids=tuple(item.scenario_id for item in scenarios.samples),
        ),)

    def m4_evaluator(*, variant_id, m3_envelopes, m4_artifact):
        calls.append(("M4", variant_id, tuple(item.action_id for item in m3_envelopes)))
        envelope = m3_envelopes[0]
        return (RiskEvaluationEnvelope.model_construct(
            action_id=envelope.action_id,
            m3_envelope_hash=envelope.envelope_hash,
            monetary_system_id="TEST_ONLY",
            monetary_mapping_registry_hash=m4_artifact.monetary_mapping_hash,
            risk_policy_hash=m4_artifact.risk_policy_hash,
            alpha=0.95,
            ranking_authority=RankingAuthority.CONDITIONAL,
            residual_risk_objective=float(len(variant_id)),
            monetary_loss_cvar_alpha=float(len(variant_id)) + 1.0,
        ),)

    return calls, m3_executor, m4_evaluator


@pytest.fixture
def execution_fixture(request):
    """Reuse the execution-adapter artifact fixture without copying its contract."""

    return request.getfixturevalue("_execution_fixture_shared")


@pytest.fixture(name="_execution_fixture_shared")
def shared_execution_fixture(tmp_path):
    # Importing the helper keeps the pipeline test focused on orchestration while
    # creating a fresh, local set of content-addressed test artifacts.
    from tests.experiment.test_exp2_execution.conftest import execution_fixture as fixture

    return fixture.__wrapped__(tmp_path)
