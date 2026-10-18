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


def test_required_episode_parameters_are_instantiated_without_guessing():
    template = ActionTemplate(template_id="A99", name="parameterized", family="timing",
                              required_parameters=("target_flight_id",))
    registry = ActionRegistry(schema_version="test", templates=(template,), enforce_principal_ids=False)
    present = instantiate_candidates({"episode_id": "e", "decision_node_id": "n",
        "facts": {}, "parameters": {"target_flight_id": "F2"}}, registry)[0]
    missing = instantiate_candidates({"episode_id": "e", "decision_node_id": "n",
        "facts": {}, "parameters": {}}, registry)[0]
    assert present.parameters["target_flight_id"] == "F2"
    assert present.precondition_state == "TRUE"
    assert missing.parameters["target_flight_id"] is None
    assert missing.precondition_state == "UNKNOWN"


def test_principal_registry_remains_exactly_frozen():
    registry = ActionRegistry.load(Path("registries/action_templates.yaml"))
    assert len(registry.templates) == 23
