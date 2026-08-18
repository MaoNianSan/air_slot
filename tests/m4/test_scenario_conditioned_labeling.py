"""M4 scenario-conditioned labeling closure tests.

FROZEN scenario responses never upgrade an action to FORMAL support; the
post totals they produce are SCENARIO_CONDITIONED / NON_AUTHORITATIVE and
must be labeled as such on ActionEvaluation.
"""

from model.M3.contracts import ResponseParameterStatus, ResponseProvenance
from model.M4.decision import evaluate_decision
from tests.fixtures.p0_p1_contracts import (
    candidate,
    consequence,
    coverage_contract,
)


def m1():
    return [{"scenario_id": 0, "scenario_weight": 1.0, "deadline_minutes": 30}]


def test_pure_scenario_frozen_response_is_scenario_conditioned_non_authoritative():
    action = candidate(
        "A11",
        provenance=ResponseProvenance.PURE_SCENARIO,
        parameter_status=ResponseParameterStatus.FROZEN,
    )
    result = evaluate_decision(
        "e",
        m1(),
        (consequence(),),
        (candidate("A00"), action),
        material_coverage_contract=coverage_contract(),
    )
    evaluation = next(item for item in result.actions if item.template_id == "A11")
    assert evaluation.lane == "SCENARIO"
    assert evaluation.scenario_conditioned is True
    assert evaluation.post_total_status == "SCENARIO_CONDITIONED"
    assert evaluation.residual_risk_j is not None
    # scenario-conditioned totals are numerical, never FORMAL evidence
    assert evaluation.lane != "FORMAL"
    assert result.decision_outcome in {
        "NO_OTHER_ACTION_CURRENTLY_FORMALLY_COMPARABLE",
        "AUTHORITATIVE_DECISION_UNAVAILABLE",
    }


def test_a00_post_totals_are_formal_estimand_not_scenario_conditioned():
    result = evaluate_decision(
        "e",
        m1(),
        (consequence(),),
        (candidate("A00"),),
        material_coverage_contract=coverage_contract(),
    )
    evaluation = next(item for item in result.actions if item.template_id == "A00")
    assert evaluation.lane == "FORMAL"
    assert evaluation.scenario_conditioned is False
    assert evaluation.post_total_status == "FORMAL_ESTIMAND"
    assert evaluation.post_totals == (10.0,)


def test_incomplete_post_totals_are_not_computed():
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
    )
    evaluation = next(item for item in result.actions if item.template_id == "A11")
    assert evaluation.lane == "SCENARIO"
    assert evaluation.scenario_conditioned is False
    assert evaluation.post_total_status == "NOT_COMPUTED"
    assert evaluation.residual_risk_j is None


def test_mixed_open_closed_scenarios_remain_scenario_conditioned():
    action = candidate(
        "A11",
        provenance=ResponseProvenance.PURE_SCENARIO,
        parameter_status=ResponseParameterStatus.FROZEN,
    )
    scenarios = [
        {"scenario_id": 0, "scenario_weight": 0.5, "deadline_minutes": 30},
        {"scenario_id": 1, "scenario_weight": 0.5, "deadline_minutes": 5},
    ]
    rows = (
        consequence(scenario_id=0),
        consequence(scenario_id=1),
    )
    result = evaluate_decision(
        "e",
        scenarios,
        rows,
        (candidate("A00"), action),
        material_coverage_contract=coverage_contract(),
    )
    evaluation = next(item for item in result.actions if item.template_id == "A11")
    assert evaluation.lane == "SCENARIO"
    assert evaluation.scenario_conditioned is True
    assert evaluation.post_total_status == "SCENARIO_CONDITIONED"
