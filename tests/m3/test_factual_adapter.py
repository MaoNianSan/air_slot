"""Focused PRE-to-M3 factual adapter and support-boundary tests."""

from datetime import datetime, timezone
from pathlib import Path

from model.M3.factual_layer.adapter import FactualState, adapt_pre_state
from model.M3.instantiation_layer.builder import instantiate_candidates
from model.M3.registry_layer.actions import ActionRegistry
from model.M3.response_registry import ResponseScenarioRegistry
from model.PRE.contracts.pre_state import DecisionNodeRecord, PREState
from model.common.enums import EvidenceClass, OperationalStage, SupportState
from model.common.value_objects import SupportedValue


ROOT = Path("registries/action_templates.yaml")
RESPONSE_ROOT = Path("registries/m3_response_scenarios.yaml")


def _supported(value, *, unit="record"):
    return SupportedValue(
        value=value,
        unit=unit,
        evidence_class=EvidenceClass.EMPIRICAL_REFERENCE,
        support_ceiling=EvidenceClass.EMPIRICAL_REFERENCE,
        support_state=SupportState.SUPPORTED,
    )


def _pre(*, successor_state=None, reference_state=None):
    node = DecisionNodeRecord(
        decision_node_id="node-1",
        episode_id="episode-1",
        decision_time=datetime(2019, 1, 1, tzinfo=timezone.utc),
        information_cutoff=datetime(2019, 1, 1, tzinfo=timezone.utc),
        operational_stage=OperationalStage.POST_IB_PRE_OB,
        roll_minutes=15,
        node_index=0,
        status="CONSTRUCTED",
        formal_eligible=True,
        config_hash="sha256:config",
        registry_manifest_hash="sha256:registry",
        legal_record_ids=(),
    )
    return PREState(
        decision_node=node,
        successor_state=successor_state or {},
        reference_state={"entries": reference_state or {}},
    )


def test_supported_schedule_reference_maps_to_successor_schedule():
    pre = _pre(successor_state={"schedule_reference": _supported({"departure": "12:00"})})
    adapted = adapt_pre_state(pre)

    fact = adapted.facts["successor_schedule"]
    assert fact.state is FactualState.TRUE
    assert fact.source_family == "successor_state"
    assert fact.source_key == "schedule_reference"
    assert fact.conversion_rule == "SCHEDULE_REFERENCE_OBJECT_PRESENT"
    assert "source_key=schedule_reference" in fact.provenance

    registry = ActionRegistry.load(ROOT)
    candidate = next(item for item in instantiate_candidates(pre, registry) if item.template_id == "A21")
    assert candidate.precondition_state == "UNKNOWN"
    assert candidate.precondition_reason == "CONTRACT_UNDERSPECIFIED"


def test_a21_contract_gap_overrides_true_published_schedule_fact():
    registry = ActionRegistry.load(ROOT)
    candidate = next(
        item
        for item in instantiate_candidates(
            {"episode_id": "e", "decision_node_id": "n", "facts": {"successor_schedule": True}},
            registry,
        )
        if item.template_id == "A21"
    )
    assert candidate.precondition_state == "UNKNOWN"
    assert candidate.precondition_reason == "CONTRACT_UNDERSPECIFIED"


def test_a71_a72_capability_labels_never_upgrade_contemporaneous_authority():
    registry = ActionRegistry.load(ROOT)
    candidates = {
        item.template_id: item
        for item in instantiate_candidates(
            {
                "episode_id": "e",
                "decision_node_id": "n",
                "facts": {"cancellation_authority": True, "network_authority": True},
            },
            registry,
        )
    }
    for action_id, missing in (
        ("A71", "contract_missing=contemporaneous_cancellation_authority"),
        ("A72", "contract_missing=contemporaneous_network_authority"),
    ):
        candidate = candidates[action_id]
        assert candidate.precondition_state == "UNKNOWN"
        assert candidate.precondition_reason == "CONTRACT_UNDERSPECIFIED"
        assert missing in candidate.factual_provenance


def test_missing_gate_resource_remains_unknown():
    registry = ActionRegistry.load(ROOT)
    candidate = next(item for item in instantiate_candidates(_pre(), registry) if item.template_id == "A41")
    assert candidate.precondition_state == "UNKNOWN"


def test_proxy_reference_does_not_upgrade_passenger_itinerary():
    pre = _pre(reference_state={"passenger_reference": _supported({"count": 20})})
    adapted = adapt_pre_state(pre)
    assert "passenger_itinerary" not in adapted.facts
    registry = ActionRegistry.load(ROOT)
    candidate = next(item for item in instantiate_candidates(pre, registry) if item.template_id == "A31")
    assert candidate.precondition_state == "UNKNOWN"


def test_non_boolean_values_never_use_python_truthiness():
    registry = ActionRegistry.load(ROOT)
    for value in (
        0,
        0.0,
        "",
        "available",
        {},
        {"present": True},
        datetime(2019, 1, 1, tzinfo=timezone.utc),
        object(),
    ):
        candidate = next(
            item for item in instantiate_candidates(
                {"episode_id": "e", "decision_node_id": "n",
                 "facts": {"replacement_aircraft": value}, "parameters": {}},
                registry,
            )
            if item.template_id == "A51"
        )
        assert candidate.precondition_state == "UNKNOWN"


def test_a00_is_identity_baseline_and_not_recommendation():
    registry = ActionRegistry.load(ROOT)
    candidate = next(item for item in instantiate_candidates(_pre(), registry) if item.template_id == "A00")
    assert candidate.precondition_state == "TRUE"
    assert candidate.parameters["episode_id"] == "episode-1"
    assert candidate.template_id == "A00"


def test_scenario_response_does_not_become_supported():
    registry = ActionRegistry.load(ROOT)
    response_registry = ResponseScenarioRegistry.load(
        RESPONSE_ROOT, structural_registry=registry
    )
    candidate = next(
        item for item in instantiate_candidates(
            _pre(), registry, response_registry=response_registry
        )
        if item.template_id == "A11"
    )
    assert candidate.precondition_state == "UNKNOWN"
    response = response_registry.parameters("A11", sensitivity="BASE")
    assert response["response_provenance"] in {"PURE_SCENARIO", "ASSUMPTION_GROUNDED"}
    assert response["response_parameter_status"] in {"FROZEN", "NOT_FROZEN"}
