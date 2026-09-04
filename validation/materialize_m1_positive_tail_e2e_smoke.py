"""Bounded Development-only PRE -> M1 -> M2 V4 -> M3 A00 -> M4 smoke."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from model.M1.contracts import M1V2Scenario
from model.M2.context import (
    AirportReferenceKeys,
    build_m2_frozen_scope,
    build_m2_v4_context,
    build_node_exposure_references,
    load_data2_reference_bundle,
)
from model.M2.contracts import M2ScenarioInput
from model.M2.mapper import M2Mapper
from model.M2.scientific_registry import load_active_m2_cu_registry
from model.M2.cu.registry import FrozenData2CUNormalizationRegistry
from model.M3.action_response import (
    ActionEligibility,
    ActionResponseRule,
    ActionResponseType,
    EligibilityState,
    ResponseSourceType,
    ResponseSupportClass,
    build_a00_identity_envelope,
)
from model.M3.m2_action_interface import M3BaselineConsequenceInput
from model.M4.m3_action_interface import (
    ComparisonScopeStatus,
    ComparisonSupportRequirement,
    ConsequenceComparisonScope,
    M4ActionEnvelopeInput,
)
from model.M4.residual_risk import evaluate_residual_risk, load_active_risk_policy
from model.M4.scientific_registry import load_active_rmb_mapping
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT


SCENARIO_PATH = PROJECT_ROOT / "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_FROZEN_H8_DEVELOPMENT_SCENARIOS.json"
OUTPUT = PROJECT_ROOT / "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_POSITIVE_TAIL_E2E_SMOKE_V1.json"
V5 = PROJECT_ROOT / "artifacts/diagnostics/v5_development_freeze"
V4 = PROJECT_ROOT / "artifacts/diagnostics/passenger_reference_freeze_v4"


def _payloads() -> dict:
    def read(directory: Path, name: str) -> dict:
        return json.loads((directory / name).read_text(encoding="utf-8"))

    return {
        "turnaround": read(V5, "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json"),
        "taxi": read(V5, "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json"),
        "downstream_exposure": read(V5, "DATA2_DOWNSTREAM_EXPOSURE_REFERENCE_TRAIN_FROZEN_V1.json"),
        "passenger": read(V5, "DATA2_PASSENGER_REFERENCE_H1_TRAIN_FROZEN_V1.json"),
        "expected_passengers": read(V4, "T100_EXPECTED_PAX_PER_FLIGHT_REFERENCE.json"),
        "connection_share": read(V4, "DB1B_CONNECTION_SHARE_REFERENCE.json"),
    }


def _m1(row: dict) -> M1V2Scenario:
    return M1V2Scenario.model_validate(
        {
            "episode_id": row["episode_id"],
            "decision_node_id": row["decision_node_id"],
            "scenario_id": row["scenario_id"],
            "scenario_weight": row["scenario_weight"],
            "operational_stage": row["operational_stage"],
            "decision_time_utc": row["decision_time_utc"],
            "t_ib_a00_utc": row["t_ib_a00_utc"],
            "d_ob_minutes": row["d_ob_minutes"],
            "d_tx_minutes": row["d_tx_minutes"],
            "scheduled_ob_utc": row.get("scheduled_ob_utc"),
            "t_ib_observed": row.get("t_ib_observed", False),
            "d_ob_observed": row.get("d_ob_observed", False),
            "d_tx_observed": row.get("d_tx_observed", False),
            "t_ib_support": row.get("t_ib_support", "SUPPORTED"),
            "d_ob_support": row.get("d_ob_support", "SUPPORTED"),
            "d_tx_support": row.get("d_tx_support", "SUPPORTED"),
            "scenario_seed_key": row["scenario_seed_key"],
            "taxi_reference_id": row.get("taxi_reference_id"),
            "taxi_reference_hash": row.get("taxi_reference_hash"),
            "positive_tail_used": row.get("positive_tail_used", False),
            "positive_tail_targets": tuple(row.get("positive_tail_targets", ())),
            "tail_continuation_id": row.get("tail_continuation_id"),
            "tail_reference_hash": row.get("tail_reference_hash"),
        }
    )


def materialize(output: Path = OUTPUT) -> dict:
    scenario_payload = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    by_node: dict[str, list[dict]] = {}
    for row in scenario_payload["scenarios"]:
        by_node.setdefault(row["decision_node_id"], []).append(row)
    node_meta = {item["decision_node_id"]: item for item in scenario_payload["nodes"]}
    bundle = load_data2_reference_bundle(_payloads())
    cu_registry = FrozenData2CUNormalizationRegistry(load_active_m2_cu_registry())
    m2_scope = build_m2_frozen_scope()
    mapper = M2Mapper(cu_registry, m2_scope)
    rmb = load_active_rmb_mapping()
    risk_policy = load_active_risk_policy()
    comparison_scope = ConsequenceComparisonScope(
        scope_id="M4_RMB_BASE_MAPPING_V2_SCOPE",
        component_ids=tuple(CONSEQUENCE_COMPONENTS),
        support_requirements={
            component: ComparisonSupportRequirement.NON_ABSTAIN_FINITE_CU
            for component in CONSEQUENCE_COMPONENTS
        },
        valuation_measurement_registry_id=rmb.registry_id,
        version="M4_RMB_BASE_MAPPING_V2",
        provenance=("M1_POSITIVE_TAIL_E2E_DEVELOPMENT_SMOKE",),
        status=ComparisonScopeStatus.FROZEN,
    )
    attempts = []
    selected = None
    for node_id, rows in sorted(by_node.items()):
        rows = sorted(rows, key=lambda row: row["scenario_id"])
        first = rows[0]
        meta = node_meta[node_id]
        decision_time = datetime.fromisoformat(first["decision_time_utc"])
        keys = AirportReferenceKeys(
            connection_airport_id=meta["connection_airport_id"],
            successor_destination_airport_id=meta["successor_destination_airport_id"],
            carrier_id=None,
            month=decision_time.month,
            quarter=(decision_time.month - 1) // 3 + 1,
        )
        refs = build_node_exposure_references(bundle, keys)
        context = build_m2_v4_context(
            bundle,
            keys,
            node_specific_exposure=refs.airport,
        )
        m2_inputs = tuple(
            M2ScenarioInput.from_m1(
                _m1(row),
                pre_lineage=("M1_FROZEN_H8_DEVELOPMENT_SCENARIOS", first["decision_node_id"]),
                reference_lineage=(scenario_payload["tail_manifest_hash"],),
            )
            for row in rows
        )
        distribution = mapper.map_m1_distribution(m2_inputs, context)
        formal_count = sum(
            item.formal_estimand_value.value_cu is not None
            for item in distribution.consequences
        )
        attempts.append(
            {
                "decision_node_id": node_id,
                "scenario_count": len(rows),
                "formal_m2_scenarios": formal_count,
                "m2_status": "PASS" if formal_count == len(rows) else "PARTIAL",
            }
        )
        if formal_count != len(rows):
            continue
        baselines = tuple(
            M3BaselineConsequenceInput.model_validate(item.m3_baseline_payload())
            for item in distribution.consequences
        )
        eligibility = ActionEligibility.create(
            action_id="A00",
            action_family="null",
            decision_node_id=node_id,
            state=EligibilityState.ELIGIBLE,
            eligibility_conditions=("A00_IDENTITY_BASELINE",),
            fact_reference_ids=("M3_A00_IDENTITY_ONLY",),
            provenance=("DEVELOPMENT_SMOKE",),
        )
        response_rule = ActionResponseRule.create(
            response_rule_id="M3_A00_IDENTITY_V2",
            action_id="A00",
            action_family="null",
            affected_components=(),
            response_types=(ActionResponseType.IDENTITY,),
            response_rule="C_a_CU equals C_0_CU",
            parameter_source=ResponseSourceType.OPERATIONAL_RULE,
            support_state=ResponseSupportClass.SUPPORTED,
            source_references=("M3_A00_IDENTITY_ONLY",),
            parameter_version="M3-A00-V2",
            freeze_id="M3_A00_IDENTITY_FREEZE_V2",
            parameters=(),
            provenance=("A00_BASELINE_ONLY", "DEVELOPMENT_SMOKE"),
        )
        m3 = build_a00_identity_envelope(
            baselines,
            eligibility=eligibility,
            response_rule=response_rule,
        )
        m4 = M4ActionEnvelopeInput.model_validate(
            {**m3.m4_payload(), "comparison_scope": comparison_scope.model_dump()}
        )
        risk = evaluate_residual_risk(
            m4,
            monetary_mapping=rmb,
            risk_policy=risk_policy,
        )
        selected = {
            "decision_node_id": node_id,
            "scenario_count": len(rows),
            "m2_formal_scenarios": formal_count,
            "m3_action_id": m3.action_id,
            "m3_envelope_hash": m3.envelope_hash,
            "m4_numerical_state": risk.numerical_state.value,
            "m4_comparison_status": risk.comparison_status.value,
            "m4_support_state": risk.support_state.value,
            "m4_expected_monetary_loss": risk.expected_monetary_loss,
            "m4_cvar_0_90": risk.monetary_loss_cvar_alpha,
            "m4_residual_risk_objective": risk.residual_risk_objective,
            "a00_recommendation_authorized": False,
        }
        break
    payload = {
        "schema_version": "M1_POSITIVE_TAIL_E2E_SMOKE_V1",
        "artifact_id": "M1_POSITIVE_TAIL_E2E_SMOKE",
        "artifact_scope": "DEVELOPMENT_ONLY_SMOKE",
        "scenario_artifact_hash": scenario_payload["artifact_hash"],
        "attempts": attempts,
        "selected": selected,
        "pre": "PASS",
        "m1": "PASS",
        "m2": "PASS" if selected else "PARTIAL",
        "m3": "PASS" if selected else "NOT_REACHED",
        "m4": "PASS" if selected else "NOT_REACHED",
        "final_test_access_count": 0,
        "model_retrained": False,
        "parameter_reselected": False,
        "experiment_created": False,
    }
    payload["artifact_hash"] = content_id(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(materialize(), indent=2, sort_keys=True, default=str))

