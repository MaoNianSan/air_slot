"""V2 structural footprint and coefficient-boundary regressions."""

from math import nan
from pathlib import Path

import pytest
from pydantic import ValidationError

from model.M3.contracts import (
    ActionTemplate,
    FootprintLevel,
    FootprintRole,
)
from model.M3.instantiation_layer.builder import instantiate_action_records
from model.M3.registry_layer.actions import ActionRegistry
from model.M3.readiness import (
    NumericalParameterState,
    build_action_numerical_readiness,
)
from model.M3.response_layer.core import scenario_update
from model.M3.response_registry import ResponseScenarioRegistry
from model.common.errors import ContractError
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS


ROOT = Path(__file__).resolve().parents[2]


def test_active_registry_has_explicit_23_by_7_footprints():
    registry = ActionRegistry.load(ROOT / "registries" / "action_templates.yaml")
    assert len(registry.templates) == 23
    for template in registry.templates:
        assert tuple(template.footprint) == CONSEQUENCE_COMPONENTS
        for component, cell in template.footprint.items():
            if component in template.mitigation:
                assert cell.role is FootprintRole.MITIGATION
            elif component in template.induced:
                assert cell.role is FootprintRole.INDUCED
            else:
                assert cell.role is not FootprintRole.UNTOUCHED or cell.level is FootprintLevel.NONE


def test_authoritative_special_footprints_are_explicit():
    registry = ActionRegistry.load(ROOT / "registries" / "action_templates.yaml")
    by_id = {item.template_id: item for item in registry.templates}
    assert by_id["A13"].footprint["P_time"].level is FootprintLevel.SECONDARY
    assert by_id["A13"].footprint["P_itinerary"].level is FootprintLevel.SECONDARY
    assert by_id["A31"].footprint["P_time"].level is FootprintLevel.CONDITIONAL_SECONDARY
    assert by_id["A54"].footprint["P_itinerary"].level is FootprintLevel.CONDITIONAL_SECONDARY
    for action_id in ("A71", "A72"):
        cell = by_id[action_id].footprint["F_continuity"]
        assert cell.role is FootprintRole.MITIGATION
        assert cell.level is FootprintLevel.SECONDARY
        assert by_id[action_id].footprint["R_operating"].level is FootprintLevel.SECONDARY
    assert by_id["A33"].footprint["P_service"].role is FootprintRole.INDUCED


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("mitigation", {"F_execution": 1.01}, "INVALID_MITIGATION_COEFFICIENT"),
        ("mitigation", {"F_execution": nan}, "INVALID_MITIGATION_COEFFICIENT"),
        ("induced", {"R_operating": -1.0}, "INVALID_INDUCED_COEFFICIENT"),
        ("induced", {"R_operating": nan}, "INVALID_INDUCED_COEFFICIENT"),
    ],
)
def test_action_template_rejects_invalid_effect_coefficients(field, value, message):
    payload = {
        "template_id": "A99",
        "name": "test",
        "family": "timing",
        "response_parameter_status": "NOT_FROZEN",
        field: value,
    }
    with pytest.raises(ValidationError, match=message):
        ActionTemplate.model_validate(payload)


def test_a00_cannot_carry_effect_coefficients():
    with pytest.raises(ValidationError, match="A00_MUST_HAVE_NO_EFFECT_COEFFICIENTS"):
        ActionTemplate.model_validate(
            {
                "template_id": "A00",
                "name": "identity",
                "family": "null",
                "response_parameter_status": "NOT_REQUIRED",
                "mitigation": {"F_execution": 0.1},
            }
        )


def test_action_attempt_burden_is_present_when_rho_is_zero():
    assert scenario_update(
        pre_cu=1.0,
        mitigation_coefficient=0.0,
        rho=0.0,
        induced_score=2.0,
        induced_score_to_cu=0.10,
    ) == pytest.approx(1.2)


def test_response_registry_freezes_induced_score_units_and_scope():
    structural = ActionRegistry.load(ROOT / "registries" / "action_templates.yaml")
    registry = ResponseScenarioRegistry.load(
        ROOT / "registries" / "m3_response_scenarios.yaml",
        structural_registry=structural,
    )
    assert registry.induced_score_unit == "INDUCED_SCORE"
    assert registry.induced_score_to_cu_unit == "CU_PER_INDUCED_SCORE"
    assert registry.induced_burden_semantics == "ACTION_ATTEMPT_BURDEN"
    assert registry.induced_burden_requires_realized_mitigation is False
    assert registry.induced_burden_components == CONSEQUENCE_COMPONENTS
    assert registry.formal_support_upgrade is False


def test_scenario_update_rejects_invalid_runtime_bounds():
    checks = [
        ({"mitigation_coefficient": -0.1}, "M3_SCENARIO_UPDATE_MITIGATION_OUT_OF_RANGE"),
        ({"induced_score": -1.0}, "M3_SCENARIO_UPDATE_INDUCED_SCORE_INVALID"),
        ({"induced_score_to_cu": 0.0}, "M3_SCENARIO_UPDATE_INDUCED_CONVERSION_INVALID"),
    ]
    base = {
        "pre_cu": 1.0,
        "mitigation_coefficient": 0.0,
        "rho": 0.0,
        "induced_score": 0.0,
        "induced_score_to_cu": 0.1,
    }
    for update, message in checks:
        with pytest.raises(ContractError, match=message):
            scenario_update(**{**base, **update})


def test_action_numerical_readiness_separates_structural_zero_and_missing_response():
    structural = ActionRegistry.load(ROOT / "registries" / "action_templates.yaml")
    response = ResponseScenarioRegistry.load(
        ROOT / "registries" / "m3_response_scenarios.yaml",
        structural_registry=structural,
    )
    readiness = build_action_numerical_readiness(
        structural,
        response_registry=response,
    )
    by_id = {item.action_id: item for item in readiness}

    a11 = by_id["A11"]
    assert a11.structural_status == "COMPLETE"
    assert a11.response_parameter_status == "PARTIAL"
    assert a11.missing_response_cells == ("F_propagation",)
    assert a11.chi_num == "UNDEFINED"
    assert a11.reason == "RESPONSE_PARAMETER_NOT_MATERIALIZED"
    assert (
        a11.parameter_states["F_propagation"]
        is NumericalParameterState.NUMERICAL_PARAMETER_NOT_MATERIALIZED
    )
    assert (
        a11.parameter_states["F_continuity"]
        is NumericalParameterState.STRUCTURAL_ZERO
    )

    a22 = by_id["A22"]
    assert a22.response_parameter_status == "FROZEN"
    assert a22.missing_response_cells == ()
    assert a22.chi_num == "DEFINED"

    a00 = by_id["A00"]
    assert a00.response_parameter_status == "NOT_REQUIRED"
    assert a00.chi_num == "DEFINED"


def test_missing_response_cell_does_not_make_action_instantiation_fail():
    structural = ActionRegistry.load(ROOT / "registries" / "action_templates.yaml")
    response = ResponseScenarioRegistry.load(
        ROOT / "registries" / "m3_response_scenarios.yaml",
        structural_registry=structural,
    )
    records = instantiate_action_records(
        {
            "episode_id": "readiness-episode",
            "decision_node_id": "readiness-node",
            "facts": {"passenger_connection": True},
        },
        structural,
        response_registry=response,
    )
    a11 = next(item for item in records if item.template_id == "A11")
    assert a11.instantiation_state.value == "FORMED"
    assert a11.candidate is not None


def test_explicit_footprint_hard_gates_missing_active_coefficient():
    structural = ActionRegistry.load(ROOT / "registries" / "action_templates.yaml")
    template = next(item for item in structural.templates if item.template_id == "A11")
    pre = {component: 1.0 for component in CONSEQUENCE_COMPONENTS}
    with pytest.raises(
        ContractError,
        match="M3_RESPONSE_PARAMETER_NOT_MATERIALIZED:F_propagation",
    ):
        from model.M3.response_layer.core import action_post_consequences

        action_post_consequences(
            pre_by_component=pre,
            mitigation=template.mitigation,
            induced=template.induced,
            footprint=template.footprint,
            rho=0.0,
            induced_score_to_cu=0.10,
            included_components=CONSEQUENCE_COMPONENTS,
        )


def test_complete_action_path_remains_numerically_defined():
    structural = ActionRegistry.load(ROOT / "registries" / "action_templates.yaml")
    template = next(item for item in structural.templates if item.template_id == "A22")
    pre = {component: 1.0 for component in CONSEQUENCE_COMPONENTS}
    from model.M3.response_layer.core import action_post_consequences

    post = action_post_consequences(
        pre_by_component=pre,
        mitigation=template.mitigation,
        induced=template.induced,
        footprint=template.footprint,
        rho=0.0,
        induced_score_to_cu=0.10,
        included_components=CONSEQUENCE_COMPONENTS,
    )
    assert tuple(post) == CONSEQUENCE_COMPONENTS
    assert all(value >= 0.0 for value in post.values())

