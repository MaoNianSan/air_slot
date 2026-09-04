"""Synthetic M4 regression: compare numerically, never select."""

from pathlib import Path

import pytest

from model.M4.authority_layer.prohibition import project_authority
from model.M4.residual_risk import (
    NumericalComparisonStatus,
    NumericalEvaluationState,
    evaluate_residual_risk,
    rank_risk_evaluations,
)
from model.common.errors import ContractError
from tests.m4.test_v2_monetary_residual_risk import _action_input, _mapping, _policy


def test_complete_numerics_are_independent_of_unknown_facts():
    evaluation = evaluate_residual_risk(
        _action_input(action_id="A21", eligibility_state="UNKNOWN"),
        monetary_mapping=_mapping(status="FROZEN"), risk_policy=_policy(status="FROZEN"),
    )
    assert evaluation.numerical_state is NumericalEvaluationState.DEFINED
    assert evaluation.comparison_status is NumericalComparisonStatus.CONDITIONAL_INPUTS

    incomplete = _action_input(action_id="A21", eligibility_state="UNKNOWN")
    incomplete = incomplete.model_copy(update={
        "scenario_consequences": tuple(
            scenario.model_copy(update={
                "components": tuple(
                    component.model_copy(update={"C_a_CU": None, "support_state": "ABSTAIN"})
                    if component.component_id == "F_continuity" else component
                    for component in scenario.components
                )
            })
            for scenario in incomplete.scenario_consequences
        )
    })
    undefined = evaluate_residual_risk(
        incomplete, monetary_mapping=_mapping(status="FROZEN"), risk_policy=_policy(status="FROZEN"),
    )
    assert undefined.numerical_state is NumericalEvaluationState.UNDEFINED
    assert undefined.comparison_status is NumericalComparisonStatus.NOT_COMPARABLE


def test_a00_and_a21_can_be_compared_without_operational_selection():
    better_a21 = evaluate_residual_risk(
        _action_input(action_id="A21", scenario_values=(0.5, 1.0), eligibility_state="UNKNOWN"),
        monetary_mapping=_mapping(status="FROZEN"), risk_policy=_policy(status="FROZEN"),
    )
    a00 = evaluate_residual_risk(
        _action_input(action_id="A00", scenario_values=(2.0, 3.0)),
        monetary_mapping=_mapping(status="FROZEN"), risk_policy=_policy(status="FROZEN"),
    )
    assert better_a21.residual_risk_objective < a00.residual_risk_objective
    lower_a00 = evaluate_residual_risk(
        _action_input(action_id="A00", scenario_values=(0.5, 1.0)),
        monetary_mapping=_mapping(status="FROZEN"), risk_policy=_policy(status="FROZEN"),
    )
    worse_a21 = evaluate_residual_risk(
        _action_input(action_id="A21", scenario_values=(2.0, 3.0), eligibility_state="UNKNOWN"),
        monetary_mapping=_mapping(status="FROZEN"), risk_policy=_policy(status="FROZEN"),
    )
    assert lower_a00.residual_risk_objective < worse_a21.residual_risk_objective
    assert better_a21.selection_state.value == "UNIMPLEMENTED"
    assert a00.selection_state.value == "UNIMPLEMENTED"
    with pytest.raises(ContractError, match="M4_SELECTION_NOT_AUTHORIZED"):
        project_authority()


def test_a00_is_not_a_fallback_when_non_a00_is_undefined():
    a00 = evaluate_residual_risk(
        _action_input(action_id="A00"), monetary_mapping=_mapping(status="FROZEN"), risk_policy=_policy(status="FROZEN")
    )
    source = _action_input(action_id="A21", eligibility_state="UNKNOWN")
    undefined_input = source.model_copy(update={
        "scenario_consequences": tuple(
            scenario.model_copy(update={
                "components": tuple(
                    component.model_copy(update={"C_a_CU": None, "support_state": "ABSTAIN"})
                    if component.component_id == "F_continuity" else component
                    for component in scenario.components
                )
            })
            for scenario in source.scenario_consequences
        )
    })
    undefined = evaluate_residual_risk(
        undefined_input,
        monetary_mapping=_mapping(status="FROZEN"), risk_policy=_policy(status="FROZEN"),
    )
    ranking = rank_risk_evaluations((a00, undefined))
    assert a00.action_id == "A00"
    assert undefined.action_id == "A21"
    assert undefined.action_id in ranking.not_comparable_action_ids
    assert not hasattr(ranking, "recommended_action_id")
