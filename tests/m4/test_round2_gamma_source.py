"""Round 2 focused tests Y / AB — provenance vs eligibility and gamma single source.

- Y: provenance class alone does not automatically block model comparison.
- AB: gamma comes from the frozen response registry, not a hard-code; a
  candidate without a registry-supplied gamma cannot be evaluated.
"""

import pytest

from model.M3.contracts import (
    ActionResponseSupport,
    ActionResponseSupportState,
    EvidenceBasis,
    ResponseParameterStatus,
    ResponseProvenance,
)
from model.M4.decision import evaluate_decision
from model.common.errors import ContractError
from tests.fixtures.p0_p1_contracts import (
    candidate,
    consequence,
    coverage_contract,
    monetary_fixture,
)


def m1():
    return [{"scenario_id": 0, "scenario_weight": 1.0, "deadline_minutes": 30}]


def test_y_structured_scenario_provenance_does_not_block_comparison():
    action = candidate(
        "A11",
        provenance=ResponseProvenance.PURE_SCENARIO,
        parameter_status=ResponseParameterStatus.FROZEN,
    ).model_copy(
        update={
            "response_support": ActionResponseSupport(
                evidence_bases=(EvidenceBasis.SCENARIO_ASSUMPTION,),
                source_refs=("round2-test",),
                support_state=ActionResponseSupportState.CONDITIONAL,
                hybrid=False,
            )
        }
    )
    result = evaluate_decision(
        "e",
        m1(),
        (consequence(),),
        (candidate("A00"), action),
        material_coverage_contract=coverage_contract(),
        monetary_mapping=monetary_fixture(),
    )
    evaluation = next(item for item in result.actions if item.template_id == "A11")
    assert evaluation.lane == "FORMAL"
    assert evaluation.interpretation_class == "SCENARIO_ASSUMPTION"


def test_y_unsupported_response_contract_is_not_comparable():
    action = candidate(
        "A11",
        parameter_status=ResponseParameterStatus.FROZEN,
    ).model_copy(
        update={
            "response_support": ActionResponseSupport(
                evidence_bases=(EvidenceBasis.UNSUPPORTED,),
                source_refs=(),
                support_state=ActionResponseSupportState.UNSUPPORTED,
                hybrid=False,
            )
        }
    )
    result = evaluate_decision(
        "e",
        m1(),
        (consequence(),),
        (candidate("A00"), action),
        material_coverage_contract=coverage_contract(),
        monetary_mapping=monetary_fixture(),
    )
    evaluation = next(item for item in result.actions if item.template_id == "A11")
    assert evaluation.lane == "SCENARIO"
    assert evaluation.interpretation_class == "UNSUPPORTED"


def test_ab_gamma_comes_from_response_registry_not_hard_code():
    # Response contract supplies gamma = 0.25; post must reflect it exactly.
    action = candidate("A11", parameter_status=ResponseParameterStatus.FROZEN).model_copy(
        update={"response_parameters": {"value": 1.0, "induced_score_to_cu": 0.25}}
    )
    result = evaluate_decision(
        "e",
        m1(),
        (consequence(),),
        (candidate("A00"), action),
        material_coverage_contract=coverage_contract(),
        monetary_mapping=monetary_fixture(),
    )
    evaluation = next(item for item in result.actions if item.template_id == "A11")
    # A11: pre F_execution=10.0, mitigation=0.5, rho=1.0, induced={} -> 10*(1-0.5)=5.0.
    assert evaluation.post_totals == (5.0,)
    # A different gamma changes the induced term: add induced F_execution=4.0.
    induced_action = action.model_copy(
        update={"induced": {"F_execution": 4.0}}
    )
    result2 = evaluate_decision(
        "e",
        m1(),
        (consequence(),),
        (candidate("A00"), induced_action),
        material_coverage_contract=coverage_contract(),
        monetary_mapping=monetary_fixture(),
    )
    evaluation2 = next(item for item in result2.actions if item.template_id == "A11")
    assert evaluation2.post_totals == (5.0 + 0.25 * 4.0,)


def test_ab_missing_gamma_is_a_hard_contract_error():
    action = candidate("A11", parameter_status=ResponseParameterStatus.FROZEN).model_copy(
        update={"response_parameters": {"value": 1.0}}
    )
    with pytest.raises(ContractError, match="M4_INDUCED_SCORE_TO_CU_SOURCE_MISSING"):
        evaluate_decision(
            "e",
            m1(),
            (consequence(),),
            (candidate("A00"), action),
            material_coverage_contract=coverage_contract(),
            monetary_mapping=monetary_fixture(),
        )
