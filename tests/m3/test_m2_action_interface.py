import pytest
from pydantic import ValidationError

from model.M2.contracts import COMPONENTS
from model.M3.m2_action_interface import (
    ActionConditionedCUQuantity,
    M3ActionConditionedConsequence,
    M3BaselineConsequenceInput,
)
from model.common.enums import SupportState
from tests.m2.test_v2_design_alignment import _input, _runtime


def _baseline():
    mapper, context = _runtime()
    return mapper.map_m1_scenarios((_input(),), context)[0]


def _conditioned_rows(baseline):
    rows = []
    for row in baseline.component_vector.rows:
        abstain = row.constructed_value_cu is None
        rows.append(
            ActionConditionedCUQuantity(
                component_id=row.component_id,
                scenario_id=baseline.scenario_id,
                scenario_weight=baseline.scenario_weight,
                baseline_cu_artifact_id=row.cu_artifact_id,
                adjusted_value_cu=(
                    None if abstain else row.constructed_value_cu + 1.0
                ),
                support_state=(
                    SupportState.ABSTAIN if abstain else SupportState.SUPPORTED
                ),
                action_response_reference_id="M3_RESPONSE_TEST_ONLY",
                action_response_parameter_version="TEST-1",
                reason_code="BASELINE_CU_UNAVAILABLE" if abstain else None,
            )
        )
    return tuple(rows)


def test_m2_baseline_is_action_free_and_wrapper_does_not_mutate_it():
    baseline = _baseline()
    before = baseline.model_dump()
    wrapped = M3BaselineConsequenceInput.model_validate(
        baseline.m3_baseline_payload()
    )
    hypothetical_action = "A11"
    assert hypothetical_action not in wrapped.model_dump_json()
    assert wrapped.action_id is None
    assert wrapped.action_adjustments_applied is False
    assert baseline.model_dump() == before


def test_m3_future_interface_requires_action_conditioned_cu_only():
    baseline = _baseline()
    result = M3ActionConditionedConsequence(
        episode_id=baseline.episode_id,
        decision_node_id=baseline.decision_node_id,
        scenario_id=baseline.scenario_id,
        scenario_weight=baseline.scenario_weight,
        action_id="A11",
        baseline_consequence_id=baseline.consequence_artifact_id,
        component_quantities=_conditioned_rows(baseline),
    )
    assert result.consequence_state == "ACTION_CONDITIONED"
    assert result.action_response_applied is True
    assert tuple(item.component_id for item in result.component_quantities) == COMPONENTS
    with pytest.raises(ValidationError):
        ActionConditionedCUQuantity.model_validate(
            {
                **result.component_quantities[0].model_dump(),
                "native_quantity": 999.0,
            }
        )


def test_m3_baseline_contract_rejects_action_leakage():
    baseline = _baseline()
    with pytest.raises(ValidationError):
        M3BaselineConsequenceInput.model_validate(
            {
                **baseline.m3_baseline_payload(),
                "consequence_state": "ACTION_CONDITIONED",
                "action_id": "A11",
                "action_adjustments_applied": True,
            }
        )


def test_action_conditioned_result_cannot_be_action_free():
    baseline = _baseline()
    payload = {
        "episode_id": baseline.episode_id,
        "decision_node_id": baseline.decision_node_id,
        "scenario_id": baseline.scenario_id,
        "scenario_weight": baseline.scenario_weight,
        "action_id": "",
        "baseline_consequence_id": baseline.consequence_artifact_id,
        "component_quantities": _conditioned_rows(baseline),
    }
    with pytest.raises(ValidationError):
        M3ActionConditionedConsequence(**payload)
