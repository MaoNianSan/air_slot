from pathlib import Path

import pytest
from pydantic import ValidationError

from model.M3.contracts import ActionTemplate
from model.M3.instantiate import instantiate_candidates
from model.M3.registry import ActionRegistry


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
    assert present[0].parameters["target_flight_id"] == "F2"
    assert present[0].precondition_state == "TRUE"
    assert len(missing) == 0


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


def test_principal_registry_remains_exactly_frozen():
    registry = ActionRegistry.load(Path("registries/action_templates.yaml"))
    assert len(registry.templates) == 23
