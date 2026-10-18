from pathlib import Path

import pytest
from pydantic import ValidationError

from model.M3.contracts import ActionTemplate, InstantiationState
from model.M3.instantiation_layer.builder import (
    evaluate_action_instantiation,
    instantiate_action_records,
    instantiate_candidates,
)
from model.M3.factual_layer.adapter import adapt_pre_state
from model.M3.registry_layer.actions import ActionRegistry


def test_unknown_consequence_key_is_a_hard_registry_error():
    with pytest.raises(ValidationError, match="UNKNOWN_M2_CONSEQUENCE_COMPONENT"):
        ActionTemplate(template_id="A99", name="bad", family="timing",
                       mitigation={"NOT_AN_M2_COMPONENT": 0.2})


def test_missing_parameter_means_not_instantiable_i0():
    # Round 2 spec 6.3: missing required parameter -> I(a)=0 -> not in A.
    template = ActionTemplate(template_id="A99", name="parameterized", family="timing",
                              required_parameters=("target_flight_id",))
    registry = ActionRegistry(schema_version="test", templates=(template,), enforce_principal_ids=False)
    present = instantiate_candidates({"episode_id": "e", "decision_node_id": "n",
        "facts": {}, "parameters": {"target_flight_id": "F2"}}, registry)
    missing = instantiate_candidates({"episode_id": "e", "decision_node_id": "n",
        "facts": {}, "parameters": {}}, registry)
    assert len(present) == 1 and present[0].instantiable
    assert present[0].instantiation_state is InstantiationState.FORMED
    assert present[0].parameters["target_flight_id"] == "F2"
    assert present[0].precondition_state == "TRUE"
    assert len(missing) == 0
    missing_state = evaluate_action_instantiation(
        template,
        adapt_pre_state(
            {"episode_id": "e", "decision_node_id": "n", "facts": {}, "parameters": {}}
        ),
    )
    assert missing_state.state is InstantiationState.NOT_FORMED
    assert missing_state.missing_parameters == ("target_flight_id",)
    assert missing_state.reason == "REQUIRED_PARAMETER_MISSING"


def test_template_records_retain_not_formed_instances_and_lineage():
    template = ActionTemplate(
        template_id="A99",
        name="parameterized",
        family="timing",
        required_parameters=("target_flight_id",),
    )
    registry = ActionRegistry(
        schema_version="test", templates=(template,), enforce_principal_ids=False
    )
    records = instantiate_action_records(
        {"episode_id": "e", "decision_node_id": "n", "facts": {}, "parameters": {}},
        registry,
    )
    assert len(records) == 1
    record = records[0]
    assert record.template_id == "A99"
    assert record.instantiation_state is InstantiationState.NOT_FORMED
    assert record.candidate is None
    assert record.missing_required_parameters == ("target_flight_id",)
    assert record.reason == "REQUIRED_PARAMETER_MISSING"
    assert "registry_id=ACTION_TEMPLATES_V1" in record.source
    assert "episode_id=e" in record.lineage
    assert "decision_node_id=n" in record.lineage


def test_principal_templates_always_have_one_instantiation_record_each():
    registry = ActionRegistry.load(Path("registries/action_templates.yaml"))
    records = instantiate_action_records(
        {"episode_id": "e", "decision_node_id": "n", "facts": {}, "parameters": {}},
        registry,
    )
    assert len(records) == 23
    assert tuple(record.template_id for record in records) == tuple(
        template.template_id for template in registry.templates
    )
    assert all(record.candidate is not None for record in records if record.instantiation_state is InstantiationState.FORMED)
    assert all(record.candidate is None for record in records if record.instantiation_state is InstantiationState.NOT_FORMED)


def test_structural_unknown_is_distinct_from_i0():
    # Round 2 spec 6.3: unknown structural fact -> I=1, P=UNKNOWN -> candidate kept.
    template = ActionTemplate(template_id="A99", name="unknown-fact", family="timing",
                              required_facts=("standby_aircraft",))
    registry = ActionRegistry(schema_version="test", templates=(template,), enforce_principal_ids=False)
    candidates = instantiate_candidates({"episode_id": "e", "decision_node_id": "n",
        "facts": {}, "parameters": {}}, registry)
    assert len(candidates) == 1
    assert candidates[0].precondition_state == "UNKNOWN"
    assert candidates[0].instantiable is True
    assert candidates[0].instantiation_state is InstantiationState.FORMED


def test_principal_registry_remains_exactly_frozen():
    registry = ActionRegistry.load(Path("registries/action_templates.yaml"))
    assert len(registry.templates) == 23
