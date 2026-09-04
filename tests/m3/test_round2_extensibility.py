"""M3 exact-library and independent instantiation/factual-state tests.

- U: the active registry is exactly the frozen 23-action set.
- V: missing instantiation parameter -> I(a)=0 -> candidate not in A.
- W: structural UNKNOWN is distinct from I(a)=0 and keeps the candidate.
- X: an unversioned extra action is rejected by the active registry.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from model.M3.contracts import ActionTemplate
from model.M3.instantiation_layer.builder import instantiate_candidates
from model.M3.registry_layer.actions import PRINCIPAL_IDS, ActionRegistry
from model.M3.response_registry import ResponseScenarioRegistry, load_response_registry
from model.M1.contracts import STOCHASTIC_TARGETS
from model.M2.contracts import COMPONENTS

ROOT_DIR = Path(__file__).resolve().parents[2]
RESPONSE_PATH = ROOT_DIR / "registries" / "m3_response_scenarios.yaml"
STRUCTURAL_PATH = ROOT_DIR / "registries" / "action_templates.yaml"

EXTRA_TEMPLATE = ActionTemplate(
    template_id="A99",
    name="Round2 extensible structural action",
    family="timing",
    required_facts=("aircraft_identity",),
    authority_capabilities=("FLIGHT",),
    mitigation={"F_execution": 0.2},
    induced={"R_operating": 1},
    response_model="BERNOULLI_BETA",
    response_provenance="PURE_SCENARIO",
    response_parameter_status="NOT_FROZEN",
    coverage="PARTIAL",
    preparation_time_minutes=5,
)


def test_u_active_registry_is_exactly_23_and_rejects_extra_action():
    standard = ActionRegistry.load(STRUCTURAL_PATH)
    assert {item.template_id for item in standard.templates} == set(PRINCIPAL_IDS)
    assert tuple(item.template_id for item in standard.templates) == PRINCIPAL_IDS
    assert len(standard.templates) == 23
    payload = standard.model_dump(mode="json")
    payload["templates"].append(EXTRA_TEMPLATE.model_dump(mode="json"))
    with pytest.raises(Exception, match="PRINCIPAL_ACTION_EXACT_SET_MISMATCH"):
        ActionRegistry.model_validate(payload)


def test_u_missing_principal_id_fails_closed():
    standard = ActionRegistry.load(STRUCTURAL_PATH)
    dropped = standard.model_copy(
        update={"templates": tuple(item for item in standard.templates if item.template_id != "A13")}
    )
    with pytest.raises(Exception, match="PRINCIPAL_ACTION_EXACT_SET_MISMATCH"):
        ActionRegistry.model_validate(dropped.model_dump(mode="json"))


def test_v_missing_instantiation_parameter_means_i0_not_in_a():
    template = ActionTemplate(
        template_id="A98",
        name="parameterized action",
        family="timing",
        required_parameters=("gate_availability",),
    )
    registry = ActionRegistry(
        schema_version="test", templates=(template,), enforce_principal_ids=False
    )
    present = instantiate_candidates(
        {"episode_id": "e", "decision_node_id": "n",
         "facts": {}, "parameters": {"gate_availability": "G12"}},
        registry,
    )
    missing = instantiate_candidates(
        {"episode_id": "e", "decision_node_id": "n",
         "facts": {}, "parameters": {}},
        registry,
    )
    assert len(present) == 1
    assert present[0].instantiable is True
    assert present[0].parameters["gate_availability"] == "G12"
    assert len(missing) == 0


def test_w_structural_unknown_keeps_candidate_with_p_unknown():
    template = ActionTemplate(
        template_id="A97",
        name="unknown structural",
        family="crew_recovery",
        required_facts=("standby_aircraft",),
    )
    registry = ActionRegistry(
        schema_version="test", templates=(template,), enforce_principal_ids=False
    )
    candidates = instantiate_candidates(
        {"episode_id": "e", "decision_node_id": "n",
         "facts": {}, "parameters": {}},
        registry,
    )
    assert len(candidates) == 1
    assert candidates[0].precondition_state == "UNKNOWN"
    assert candidates[0].instantiable is True


def test_w_factual_false_keeps_formed_instance_with_false_fact_state():
    template = ActionTemplate(
        template_id="A96",
        name="false structural",
        family="aircraft_recovery",
        required_facts=("replacement_aircraft",),
    )
    registry = ActionRegistry(
        schema_version="test", templates=(template,), enforce_principal_ids=False
    )
    candidates = instantiate_candidates(
        {"episode_id": "e", "decision_node_id": "n",
         "facts": {"replacement_aircraft": False}, "parameters": {}},
        registry,
    )
    assert len(candidates) == 1
    assert candidates[0].instantiable is True
    assert candidates[0].precondition_state == "FALSE"


def test_x_extra_action_requires_new_versioned_registry():
    standard = ActionRegistry.load(STRUCTURAL_PATH)
    payload = standard.model_dump(mode="json")
    payload["templates"].append(EXTRA_TEMPLATE.model_dump(mode="json"))
    with pytest.raises(Exception, match="PRINCIPAL_ACTION_EXACT_SET_MISMATCH"):
        ActionRegistry.model_validate(payload)
    assert STOCHASTIC_TARGETS == ("R_IB", "DELTA_OB", "T_TX")
    assert tuple(COMPONENTS) == (
        "F_continuity", "F_execution", "F_propagation",
        "P_time", "P_itinerary", "P_service", "R_operating",
    )


def test_x_response_registry_rejects_extra_or_missing_action():
    registry = load_response_registry(RESPONSE_PATH, structural_path=STRUCTURAL_PATH)
    payload = registry.model_dump(mode="json")
    payload["actions"]["A99"] = {
        "template_id": "A99",
        "tier": "",
        "response_parameter_status": "NOT_FROZEN",
        "response_provenance": "PURE_SCENARIO",
        "response_model": "BERNOULLI_BETA",
        "value": None,
    }
    with pytest.raises(Exception, match="M3_RESPONSE_PRINCIPAL_ACTION_EXACT_SET_MISMATCH"):
        ResponseScenarioRegistry.model_validate(payload)
    dropped_payload = registry.model_dump(mode="json")
    del dropped_payload["actions"]["A11"]
    with pytest.raises(Exception, match="M3_RESPONSE_PRINCIPAL_ACTION_EXACT_SET_MISMATCH"):
        ResponseScenarioRegistry.model_validate(dropped_payload)
