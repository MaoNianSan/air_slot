import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from model.M2.contracts import COMPONENTS
from model.M3.action_response import (
    ActionEligibility,
    ActionResponseRule,
    ActionResponseType,
    EligibilityState,
    ResponseSourceType,
    ResponseSupportClass,
    build_a00_identity_envelope,
)
from model.M3.m2_action_interface import (
    ActionConditionedCUQuantity,
    M3BaselineConsequenceInput,
)
from model.M3.registry import ActionRegistry
from model.M3.response_registry import ResponseScenarioRegistry
from model.M4.m3_action_interface import M4ActionEnvelopeInput
from model.common.enums import SupportState
from tests.m2.test_v2_design_alignment import (
    _input,
    _m1_scenario,
    _runtime,
)


def _baselines():
    mapper, context = _runtime()
    consequences = mapper.map_m1_scenarios(
        (
            _input(_m1_scenario(7, 0.25)),
            _input(_m1_scenario(8, 0.75, d_ob=30.0, d_tx=12.0)),
        ),
        context,
    )
    return consequences, tuple(
        M3BaselineConsequenceInput.model_validate(item.m3_baseline_payload())
        for item in consequences
    )


def _eligibility():
    return ActionEligibility.create(
        action_id="A00",
        action_family="null",
        decision_node_id="node-1",
        state=EligibilityState.ELIGIBLE,
        eligibility_conditions=("always available",),
        fact_reference_ids=(),
        provenance=("ACTION_TEMPLATES_V1:A00",),
    )


def _identity_rule():
    return ActionResponseRule.create(
        response_rule_id="M3_V2_A00_IDENTITY",
        action_id="A00",
        action_family="null",
        affected_components=(),
        response_types=(ActionResponseType.IDENTITY,),
        response_rule="No additional recovery; copy each M2 C0 CU component.",
        parameter_source=ResponseSourceType.OPERATIONAL_RULE,
        support_state=ResponseSupportClass.SUPPORTED,
        source_references=("ROUND2_M3_V2_A00_IDENTITY",),
        parameter_version="M3_V2_IDENTITY_1",
        freeze_id="ROUND2_M3_V2_DESIGN",
        parameters=(),
        provenance=("C_A00_CU_EQUALS_C0_CU",),
    )


def _envelope():
    _, baselines = _baselines()
    return build_a00_identity_envelope(
        baselines, eligibility=_eligibility(), response_rule=_identity_rule()
    )


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key).lower()
            yield from _keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _keys(item)


def test_a_m3_consumes_only_serialized_m2_baseline_contract():
    consequences, baselines = _baselines()
    assert len(baselines) == len(consequences)
    with pytest.raises(ValidationError):
        M3BaselineConsequenceInput.model_validate(
            {**consequences[0].m3_baseline_payload(), "m1_scenario_seed": "leak"}
        )


def test_b_m2_baseline_is_unchanged_by_m3_identity_evaluation():
    _, baselines = _baselines()
    before = tuple(item.model_dump() for item in baselines)
    build_a00_identity_envelope(
        baselines, eligibility=_eligibility(), response_rule=_identity_rule()
    )
    assert tuple(item.model_dump() for item in baselines) == before


def test_c_a00_is_exact_componentwise_identity():
    _, baselines = _baselines()
    envelope = build_a00_identity_envelope(
        baselines, eligibility=_eligibility(), response_rule=_identity_rule()
    )
    for baseline, evaluated in zip(
        baselines, envelope.scenario_evaluations, strict=True
    ):
        assert tuple(row.value_cu for row in baseline.component_quantities) == tuple(
            row.adjusted_value_cu for row in evaluated.component_quantities
        )
        assert tuple(row.support_state for row in baseline.component_quantities) == tuple(
            row.support_state for row in evaluated.component_quantities
        )


def test_d_eligibility_and_response_are_independent_frozen_objects():
    eligibility_fields = set(ActionEligibility.model_fields)
    response_fields = set(ActionResponseRule.model_fields)
    assert "eligibility_conditions" not in response_fields
    assert "parameters" not in eligibility_fields
    with pytest.raises(ValidationError):
        ActionEligibility.model_validate(
            {**_eligibility().model_dump(), "response_parameter": 0.5}
        )


def test_e_unsupported_baseline_or_response_cannot_silently_be_supported():
    envelope = _envelope()
    abstaining = next(
        row
        for row in envelope.scenario_evaluations[0].component_quantities
        if row.baseline_support_state is SupportState.ABSTAIN
    )
    with pytest.raises(
        ValidationError, match="M3_BASELINE_ABSTAIN_CANNOT_BECOME_SUPPORTED"
    ):
        ActionConditionedCUQuantity.model_validate(
            {
                **abstaining.model_dump(),
                "support_state": SupportState.SUPPORTED,
                "adjusted_value_cu": 1.0,
                "reason_code": None,
            }
        )
    with pytest.raises(ValidationError, match="SCENARIO_OR_EXPERT_RESPONSE"):
        ActionResponseRule.create(
            **{
                **_identity_rule().model_dump(exclude={"rule_hash"}),
                "parameter_source": ResponseSourceType.SCENARIO_ASSUMPTION,
            }
        )


def test_f_g_all_scenarios_and_weights_are_preserved_without_aggregation():
    envelope = _envelope()
    assert envelope.input_scenario_ids == (7, 8)
    assert envelope.input_scenario_weights == (0.25, 0.75)
    assert tuple(item.scenario_id for item in envelope.scenario_evaluations) == (7, 8)
    assert tuple(item.scenario_weight for item in envelope.scenario_evaluations) == (
        0.25,
        0.75,
    )


def test_h_response_provenance_is_mandatory():
    payload = _identity_rule().model_dump(exclude={"rule_hash", "provenance"})
    with pytest.raises(ValidationError):
        ActionResponseRule.create(**payload)


def test_i_m3_and_m4_payload_have_no_monetary_fields():
    payload = _envelope().m4_payload()
    prohibited = ("money", "monetary", "rmb", "currency")
    assert not any(any(word in key for word in prohibited) for key in _keys(payload))


def test_j_m4_payload_is_full_cu_distribution_with_support_and_provenance():
    payload = _envelope().m4_payload()
    consumed = M4ActionEnvelopeInput.model_validate(payload)
    assert payload["scenario_ids"] == (7, 8)
    assert payload["scenario_weights"] == (0.25, 0.75)
    assert len(payload["scenario_consequences"]) == 2
    assert all(
        tuple(component["component_id"] for component in scenario["components"])
        == COMPONENTS
        for scenario in payload["scenario_consequences"]
    )
    assert all(
        {"C_a_CU", "support_state", "baseline_reference_lineage_hash"}
        <= set(component)
        for scenario in payload["scenario_consequences"]
        for component in scenario["components"]
    )
    assert payload["response_provenance"]
    assert consumed.scenario_ids == (7, 8)
    with pytest.raises(ValidationError):
        M4ActionEnvelopeInput.model_validate({**payload, "monetary_system": "RMB"})


def test_action_response_design_registry_covers_exact_current_action_order():
    root = Path(__file__).resolve().parents[2]
    actions = ActionRegistry.load(root / "registries" / "action_templates.yaml")
    legacy = ResponseScenarioRegistry.load(
        root / "registries" / "m3_response_scenarios.yaml"
    )
    design = json.loads(
        (root / "registries" / "m3_v2_action_response_design.json").read_text(
            encoding="utf-8"
        )
    )
    assert design["action_registry_hash"] == actions.digest()
    assert design["legacy_response_registry_hash"] == legacy.digest()
    assert tuple(row["action_id"] for row in design["responses"]) == tuple(
        template.template_id for template in actions.templates
    )
    required = {
        "action_id",
        "affected_components",
        "response_rule",
        "parameter_source",
        "support_state",
        "source_reference",
        "parameter_version",
        "freeze_id",
        "provenance",
    }
    assert all(required <= set(row) for row in design["responses"])
    assert all(
        row["support_state"] == "SCENARIO_ASSUMPTION"
        and row["executable_v2"] is False
        for row in design["responses"]
        if row["action_id"] != "A00"
    )
