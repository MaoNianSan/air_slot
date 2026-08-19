import pytest

from model.M3.contracts import ResponseParameterStatus, ResponseProvenance
from model.M4.decision import _compatible_formal_ranking, evaluate_decision
from model.M4.response import response_value
from model.common.errors import ContractError
from model.common.estimand import FormalEstimandStatus
from tests.fixtures.p0_p1_contracts import (
    candidate,
    consequence,
    coverage_contract,
    monetary_fixture,
    scope_fixture,
)


def m1():
    return [{"scenario_id": 0, "scenario_weight": 1.0, "deadline_minutes": 30}]


def test_nonmaterial_missingness_does_not_demote_and_emits_quality_flag():
    result = evaluate_decision(
        "e",
        m1(),
        (consequence(missing=("P_service",)),),
        (candidate("A00"), candidate("A11")),
        material_coverage_contract=coverage_contract(p_service_nonmaterial=True),
        monetary_mapping=monetary_fixture(),
    )
    action = next(item for item in result.actions if item.template_id == "A11")
    assert action.lane == "FORMAL"
    assert "NONMATERIAL_COMPONENT_MISSING" in action.quality_flags


def test_material_resource_burden_missing_cannot_be_formal():
    scope = scope_fixture(components=("F_execution", "R_operating"))
    result = evaluate_decision(
        "e",
        m1(),
        (consequence(scope=scope, missing=("R_operating",)),),
        (candidate("A00"), candidate("A11")),
        material_coverage_contract=coverage_contract(resource_required=True),
        monetary_mapping=monetary_fixture(),
    )
    action = next(item for item in result.actions if item.template_id == "A11")
    assert action.lane == "SCENARIO"


def test_unknown_is_conditional_and_false_is_excluded():
    consequence_row = consequence()
    contract = coverage_contract()
    unknown = evaluate_decision(
        "e",
        m1(),
        (consequence_row,),
        (candidate("A00"), candidate("A11", precondition="UNKNOWN")),
        material_coverage_contract=contract,
        monetary_mapping=monetary_fixture(),
    )
    closed_candidate = candidate("A11").model_copy(
        update={"precondition_state": "FALSE"}
    )
    closed = evaluate_decision(
        "e",
        m1(),
        (consequence_row,),
        (candidate("A00"), closed_candidate),
        material_coverage_contract=contract,
        monetary_mapping=monetary_fixture(),
    )
    assert next(item for item in unknown.actions if item.template_id == "A11").lane == "CONDITIONAL"
    assert next(item for item in closed.actions if item.template_id == "A11").lane == "EXCLUDED"


def test_material_pure_scenario_response_is_scenario():
    action = candidate(
        "A11",
        provenance=ResponseProvenance.PURE_SCENARIO,
        parameter_status=ResponseParameterStatus.NOT_FROZEN,
    )
    result = evaluate_decision(
        "e",
        m1(),
        (consequence(),),
        (candidate("A00"), action),
        material_coverage_contract=coverage_contract(),
        monetary_mapping=monetary_fixture(),
    )
    assert next(item for item in result.actions if item.template_id == "A11").lane == "SCENARIO"


def test_operator_unfrozen_response_never_claims_formal_aggregate():
    action = candidate(
        "A11",
        provenance=ResponseProvenance.OPERATOR_INDUSTRY,
        parameter_status=ResponseParameterStatus.NOT_FROZEN,
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
    assert (
        evaluation.formal_aggregate_status
        is FormalEstimandStatus.FORMAL_AGGREGATE_UNRESOLVED
    )


def test_missing_a00_comparator_makes_authoritative_decision_unavailable():
    result = evaluate_decision(
        "e",
        m1(),
        (consequence(missing=("F_execution",)),),
        (candidate("A00"), candidate("A11")),
        material_coverage_contract=coverage_contract(),
        monetary_mapping=monetary_fixture(),
    )
    assert result.decision_outcome == "AUTHORITATIVE_DECISION_UNAVAILABLE"
    assert result.authoritative_ranking == ()


def test_a00_only_formal_does_not_claim_optimality():
    result = evaluate_decision(
        "e",
        m1(),
        (consequence(),),
        (
            candidate("A00"),
            candidate(
                "A11",
                provenance=ResponseProvenance.PURE_SCENARIO,
                parameter_status=ResponseParameterStatus.NOT_FROZEN,
            ),
        ),
        material_coverage_contract=coverage_contract(),
        monetary_mapping=monetary_fixture(),
    )
    assert result.decision_outcome == "NO_OTHER_ACTION_CURRENTLY_FORMALLY_COMPARABLE"


def test_stable_action_and_candidate_index_break_ties():
    result = evaluate_decision(
        "e",
        m1(),
        (consequence(),),
        (
            candidate("A00"),
            candidate("A11", action_index=2, candidate_index=1, mitigation={}),
            candidate("A11", action_index=1, candidate_index=0, mitigation={}),
        ),
        material_coverage_contract=coverage_contract(),
        monetary_mapping=monetary_fixture(),
    )
    action_order = tuple(item for item in result.authoritative_ranking if item.startswith("A11"))
    assert action_order == (
        "A11:instance-0",
        "A11:instance-1",
    )


def test_different_estimand_or_scope_cannot_share_formal_ranking():
    first = candidate("A11")
    from model.M4.decision import ActionEvaluation

    def evaluation(estimand, scope_hash, index):
        return ActionEvaluation(
            candidate_action_id=f"a{index}", template_id="A11",
            action_index=index, candidate_index=0, lane="FORMAL",
            opportunity_probability=1, estimand_id=estimand,
            estimand_version="1", scope_hash=scope_hash,
            cu_normalization_registry_id="cu-v1", monetary_system="RMB",
            monetary_mapping_registry_id="rmb-v1",
            monetary_mapping_registry_hash="sha256:rmb",
            formal_aggregate_status=FormalEstimandStatus.FORMAL_AVAILABLE,
            expected_residual=1, var=1, cvar=1, residual_risk_j=1,
            post_totals=(1,), quality_flags=(), coverage_explanation=())
    with pytest.raises(ContractError, match="FORMAL_RANKING_ESTIMAND_SCOPE_MISMATCH"):
        _compatible_formal_ranking((evaluation("e1", "h1", 0), evaluation("e2", "h2", 1)))


def test_unfrozen_response_parameters_do_not_receive_hidden_defaults():
    action = candidate("A11").model_copy(
        update={
            "response_parameter_status": ResponseParameterStatus.NOT_FROZEN,
            "response_parameters": {},
        }
    )
    with pytest.raises(ContractError, match="ACTION_RESPONSE_PARAMETERS_NOT_FROZEN"):
        response_value(action, seed=1, episode="e", scenario=0)
