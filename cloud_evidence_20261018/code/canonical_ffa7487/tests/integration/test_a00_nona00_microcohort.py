"""Ten-node synthetic A00/non-A00 regression cohort."""

from model.M4.residual_risk import (
    NumericalComparisonStatus,
    NumericalEvaluationState,
    evaluate_residual_risk,
)
from tests.m4.test_v2_monetary_residual_risk import _action_input, _mapping, _policy


def test_ten_node_microcohort_preserves_conditional_non_a00_path():
    counts = {
        "a00_formed": 0, "a21_formed": 0, "a21_factual_unknown": 0,
        "a21_numerical_defined": 0, "a21_conditional": 0,
        "operational_selections": 0, "a00_recommendations": 0,
    }
    for index in range(10):
        a00 = evaluate_residual_risk(
            _action_input(action_id="A00"), monetary_mapping=_mapping(status="FROZEN"), risk_policy=_policy(status="FROZEN")
        )
        a21 = _action_input(action_id="A21", eligibility_state="UNKNOWN")
        a21 = a21.model_copy(update={"decision_node_id": f"node-{index}"})
        a21_eval = evaluate_residual_risk(
            a21, monetary_mapping=_mapping(status="FROZEN"), risk_policy=_policy(status="FROZEN")
        )
        counts["a00_formed"] += int(a00.instantiation_state.value == "FORMED")
        counts["a21_formed"] += int(a21_eval.instantiation_state.value == "FORMED")
        counts["a21_factual_unknown"] += int(a21_eval.eligibility_state.value == "UNKNOWN")
        counts["a21_numerical_defined"] += int(a21_eval.numerical_state is NumericalEvaluationState.DEFINED)
        counts["a21_conditional"] += int(a21_eval.comparison_status is NumericalComparisonStatus.CONDITIONAL_INPUTS)
        counts["operational_selections"] += int(a21_eval.selection_state.value != "UNIMPLEMENTED")
        counts["a00_recommendations"] += int(a00.action_id == "A00" and a00.selection_state.value != "UNIMPLEMENTED")
    assert counts == {
        "a00_formed": 10, "a21_formed": 10, "a21_factual_unknown": 10,
        "a21_numerical_defined": 10, "a21_conditional": 10,
        "operational_selections": 0, "a00_recommendations": 0,
    }
