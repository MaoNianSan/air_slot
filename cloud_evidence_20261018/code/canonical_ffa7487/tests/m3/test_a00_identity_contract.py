"""Synthetic A00 identity and structural-contract regressions."""

from pathlib import Path
from hashlib import sha256

from model.M3.action_response import (
    ActionEligibility,
    ActionResponseRule,
    ActionResponseType,
    EligibilityState,
    ResponseSourceType,
    ResponseSupportClass,
    build_a00_identity_envelope,
)
from model.M3.contracts import InstantiationState
from model.M3.instantiation_layer.builder import instantiate_action_records
from model.M3.m2_action_interface import (
    M3BaselineCUQuantity,
    M3BaselineConsequenceInput,
)
from model.M3.registry_layer.actions import ActionRegistry
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import SupportState
from model.common.identity import content_id


ROOT = Path(__file__).resolve().parents[2]


def _hash(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


def _identity_rule() -> ActionResponseRule:
    return ActionResponseRule.create(
        response_rule_id="M3_V2_A00_IDENTITY",
        action_id="A00",
        action_family="null",
        affected_components=(),
        response_types=(ActionResponseType.IDENTITY,),
        response_rule="Copy the baseline CU envelope exactly.",
        parameter_source=ResponseSourceType.OPERATIONAL_RULE,
        support_state=ResponseSupportClass.SUPPORTED,
        source_references=("TEST_A00_IDENTITY",),
        parameter_version="TEST-A00-1",
        freeze_id="TEST-A00-FREEZE",
        parameters=(),
        provenance=("C_A00_EQUALS_C_0_EXACT",),
    )


def _baselines() -> tuple[M3BaselineConsequenceInput, ...]:
    rows = []
    weights = (0.2, 0.3, 0.5)
    for scenario_id, weight in enumerate(weights):
        quantities = tuple(
            M3BaselineCUQuantity(
                component_id=component,
                scenario_id=scenario_id,
                scenario_weight=weight,
                value_cu=float(scenario_id + index + 1),
                native_support_state=SupportState.SUPPORTED,
                support_state=SupportState.SUPPORTED,
                cu_artifact_id=_hash(f"cu-{scenario_id}-{index}"),
                reference_lineage_hash=_hash(f"lineage-{scenario_id}-{index}"),
            )
            for index, component in enumerate(CONSEQUENCE_COMPONENTS)
        )
        payload = {
            "episode_id": "episode-a00",
            "decision_node_id": "node-a00",
            "scenario_id": scenario_id,
            "scenario_weight": weight,
            "baseline_consequence_id": _hash(f"baseline-{scenario_id}"),
            "component_ids": CONSEQUENCE_COMPONENTS,
            "native_artifact_ids": tuple(_hash(f"native-{scenario_id}-{i}") for i in range(7)),
            "cu_artifact_ids": tuple(item.cu_artifact_id for item in quantities),
            "component_quantities": quantities,
            "reference_lineage": tuple(item.reference_lineage_hash for item in quantities),
            "consequence_state": "BASELINE",
            "action_id": None,
            "action_adjustments_applied": False,
        }
        rows.append(
            M3BaselineConsequenceInput(
                **payload,
                baseline_interface_hash=content_id(payload),
            )
        )
    return tuple(rows)


def test_a00_exact_identity_preserves_all_scenario_component_metadata():
    baselines = _baselines()
    envelope = build_a00_identity_envelope(
        baselines,
        eligibility=ActionEligibility.create(
            action_id="A00",
            action_family="null",
            decision_node_id="node-a00",
            state=EligibilityState.ELIGIBLE,
            eligibility_conditions=("identity baseline",),
            fact_reference_ids=(),
            provenance=("TEST_A00",),
        ),
        response_rule=_identity_rule(),
    )
    assert len(envelope.scenario_evaluations) == 3
    for baseline, evaluated in zip(baselines, envelope.scenario_evaluations, strict=True):
        assert evaluated.scenario_id == baseline.scenario_id
        assert evaluated.scenario_weight == baseline.scenario_weight
        assert tuple(row.component_id for row in evaluated.component_quantities) == CONSEQUENCE_COMPONENTS
        assert tuple(row.value_cu for row in baseline.component_quantities) == tuple(
            row.adjusted_value_cu for row in evaluated.component_quantities
        )
        assert tuple(row.support_state for row in baseline.component_quantities) == tuple(
            row.support_state for row in evaluated.component_quantities
        )
        assert tuple(row.baseline_reference_lineage_hash for row in evaluated.component_quantities) == tuple(
            row.reference_lineage_hash for row in baseline.component_quantities
        )
        assert all(row.response_intensity is None and row.response_draw_id is None for row in evaluated.component_quantities)
        assert all(row.response_source_type == "OPERATIONAL_RULE" for row in evaluated.component_quantities)


def test_a00_instantiation_and_opportunity_are_baseline_specific():
    registry = ActionRegistry.load(ROOT / "registries" / "action_templates.yaml")
    records = instantiate_action_records(
        {
            "episode_id": "episode-a00",
            "decision_node_id": "node-a00",
            "facts": {
                "crew": False,
                "gate_resource": False,
                "aircraft": False,
                "authority": False,
            },
        },
        registry,
    )
    a00 = next(record for record in records if record.template_id == "A00")
    assert a00.instantiation_state is InstantiationState.FORMED
    assert a00.candidate is not None
    assert a00.candidate.precondition_state == "TRUE"

    baselines = _baselines()
    envelope = build_a00_identity_envelope(
        baselines,
        eligibility=ActionEligibility.create(
            action_id="A00", action_family="null", decision_node_id="node-a00",
            state=EligibilityState.ELIGIBLE, eligibility_conditions=("identity",),
            fact_reference_ids=(), provenance=("TEST_A00",),
        ),
        response_rule=_identity_rule(),
    )
    assert envelope.m4_payload()["opportunity_state"] == "NOT_REQUIRED"
