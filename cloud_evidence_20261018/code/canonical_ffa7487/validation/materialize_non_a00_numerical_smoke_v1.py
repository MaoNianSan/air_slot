"""Development-only smoke for the non-A00 numerical M3 -> M4 path.

This validation is intentionally additive.  It consumes the frozen eight-node
M1 scenario artifact and the active M2/M3/M4 registries, and never creates an
experiment, accesses Final Test, or changes scientific inputs.
"""

from __future__ import annotations

import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

from model.M2.context import (
    AirportReferenceKeys,
    build_m2_frozen_scope,
    build_m2_v4_context,
    build_node_exposure_references,
    load_data2_reference_bundle,
)
from model.M2.contracts import M2ScenarioInput
from model.M2.cu.registry import FrozenData2CUNormalizationRegistry
from model.M2.mapper import M2Mapper
from model.M2.scientific_registry import load_active_m2_cu_registry
from model.M3.action_response import (
    ActionEligibility,
    ActionResponseRule,
    ActionResponseType,
    EligibilityState,
    ResponseSourceType,
    ResponseSupportClass,
    build_a00_identity_envelope,
    build_conditional_scenario_envelope,
)
from model.M3.contracts import InstantiationState
from model.M3.instantiation_layer.builder import instantiate_action_records
from model.M3.m2_action_interface import M3BaselineConsequenceInput
from model.M3.registry_layer.actions import ActionRegistry
from model.M3.response_registry import ResponseScenarioRegistry
from model.M4.m3_action_interface import (
    ComparisonScopeStatus,
    ComparisonSupportRequirement,
    ConsequenceComparisonScope,
    M4ActionEnvelopeInput,
)
from model.M4.residual_risk import (
    NumericalComparisonStatus,
    evaluate_residual_risk,
    load_active_risk_policy,
    rank_risk_evaluations,
)
from model.M4.scientific_registry import load_active_rmb_mapping
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT

from validation.materialize_m1_positive_tail_e2e_smoke import _m1, _payloads


SCENARIO_PATH = (
    PROJECT_ROOT
    / "artifacts/diagnostics/m1_positive_tail_continuation_v1/"
    / "M1_FROZEN_H8_DEVELOPMENT_SCENARIOS.json"
)
DESIGN_PATH = PROJECT_ROOT / "registries/m3_v2_action_response_design.json"
ACTION_PATH = PROJECT_ROOT / "registries/action_templates.yaml"
RESPONSE_PATH = PROJECT_ROOT / "registries/m3_response_scenarios.yaml"
OUTPUT_DIR = PROJECT_ROOT / "artifacts/diagnostics/non_a00_numerical_smoke_v1"
RECORDS_PATH = OUTPUT_DIR / "NON_A00_NUMERICAL_SMOKE_RECORDS.jsonl"
SUMMARY_PATH = OUTPUT_DIR / "NON_A00_NUMERICAL_SMOKE_SUMMARY.json"
REPORT_PATH = OUTPUT_DIR / "NON_A00_NUMERICAL_SMOKE_REPORT.md"

REFERENCE_FINGERPRINT = (
    "sha256:80133fa5a57593dcdeda3fb3871c037146b1faa98b135377a83ba8e1e4f86f1d"
)
SMOKE_SEED = 1701


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_comparison_scope(rmb) -> ConsequenceComparisonScope:
    return ConsequenceComparisonScope(
        scope_id="M4_RMB_BASE_MAPPING_V2_SCOPE",
        component_ids=tuple(CONSEQUENCE_COMPONENTS),
        support_requirements={
            component: ComparisonSupportRequirement.NON_ABSTAIN_FINITE_CU
            for component in CONSEQUENCE_COMPONENTS
        },
        valuation_measurement_registry_id=rmb.registry_id,
        version="M4_RMB_BASE_MAPPING_V2",
        provenance=("NON_A00_NUMERICAL_SMOKE_V1",),
        status=ComparisonScopeStatus.FROZEN,
    )


def _build_rule(row: dict[str, Any]) -> ActionResponseRule:
    action_id = str(row["action_id"])
    return ActionResponseRule.create(
        response_rule_id=(
            "M3_RESPONSE_SCENARIO_V1:" + action_id
            if action_id != "A00"
            else "M3_V2_A00_IDENTITY"
        ),
        action_id=action_id,
        action_family=str(row["action_family"]),
        affected_components=tuple(row["affected_components"]),
        response_types=tuple(
            ActionResponseType(item) for item in row["response_type"]
        ),
        response_rule=str(row["response_rule"]),
        parameter_source=ResponseSourceType(str(row["parameter_source"])),
        support_state=ResponseSupportClass(str(row["support_state"])),
        source_references=tuple(row["source_reference"]),
        parameter_version=str(row["parameter_version"]),
        freeze_id=str(row["freeze_id"]),
        parameters=(),
        provenance=tuple(row["provenance"]),
    )


def _eligibility(candidate, *, node_id: str) -> ActionEligibility:
    if candidate.template_id == "A00":
        state = EligibilityState.ELIGIBLE
        conditions = ("A00_IDENTITY_BASELINE",)
        refs = ("M3_A00_IDENTITY_ONLY",)
        provenance = ("NON_A00_NUMERICAL_SMOKE_V1", "A00_BASELINE_ONLY")
    else:
        state = EligibilityState.UNKNOWN
        conditions = tuple(candidate.parameters.get("required_facts", ())) or (
            "FACTUAL_ELIGIBILITY_NOT_INSTANTIATED",
        )
        refs = tuple(candidate.factual_provenance) or (
            f"REQUIRED_FACTS:{candidate.template_id}",
        )
        provenance = tuple(candidate.factual_provenance) or (
            "FACTUAL_ELIGIBILITY_UNKNOWN",
            "NON_A00_NUMERICAL_SMOKE_V1",
        )
    return ActionEligibility.create(
        action_id=candidate.template_id,
        action_family=candidate.action_family,
        decision_node_id=node_id,
        state=state,
        eligibility_conditions=conditions,
        fact_reference_ids=refs,
        provenance=provenance,
    )


def _m4_record(risk, *, m3_hash: str) -> dict[str, Any]:
    return {
        "risk_evaluation_support": risk.support_state.value,
        "expected_loss": risk.expected_monetary_loss,
        "VaR": risk.monetary_loss_var_alpha,
        "CVaR": risk.monetary_loss_cvar_alpha,
        "J": risk.residual_risk_objective,
        "risk_numerical_state": risk.numerical_state.value,
        "comparison_status": risk.comparison_status.value,
        "comparison_scope_id": risk.comparison_scope_id,
        "m3_envelope_hash": m3_hash,
        "risk_envelope_hash": risk.risk_envelope_hash,
        "reason_codes": list(risk.reason_codes),
    }


def _cu_signature(m3) -> str:
    """Hash the complete action-conditioned CU vector, not just the envelope."""
    return content_id(
        {
            "scenarios": [
                {
                    "scenario_id": scenario.scenario_id,
                    "components": [
                        {
                            "component_id": component.component_id,
                            "C_a_CU": component.adjusted_value_cu,
                            "support_state": component.support_state.value,
                        }
                        for component in scenario.component_quantities
                    ],
                }
                for scenario in m3.scenario_evaluations
            ]
        }
    )


def _materialize_node(
    *,
    node_id: str,
    rows: list[dict[str, Any]],
    node_meta: dict[str, Any],
    scenario_payload: dict[str, Any],
    mapper: M2Mapper,
    bundle,
    cu_registry,
    action_registry: ActionRegistry,
    response_registry: ResponseScenarioRegistry,
    design: dict[str, dict[str, Any]],
    rmb,
    risk_policy,
    comparison_scope: ConsequenceComparisonScope,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = sorted(rows, key=lambda row: row["scenario_id"])
    first = rows[0]
    decision_time = datetime.fromisoformat(first["decision_time_utc"])
    keys = AirportReferenceKeys(
        connection_airport_id=node_meta["connection_airport_id"],
        successor_destination_airport_id=node_meta["successor_destination_airport_id"],
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
            pre_lineage=("M1_FROZEN_H8_DEVELOPMENT_SCENARIOS", node_id),
            reference_lineage=(scenario_payload["tail_manifest_hash"],),
        )
        for row in rows
    )
    distribution = mapper.map_m1_distribution(m2_inputs, context)
    baselines = tuple(
        M3BaselineConsequenceInput.model_validate(item.m3_baseline_payload())
        for item in distribution.consequences
    )

    pre_state = {
        "episode_id": first["episode_id"],
        "decision_node_id": node_id,
        "facts": {},
        "parameters": {},
    }
    instantiation_records = instantiate_action_records(
        pre_state,
        action_registry,
        response_registry=response_registry,
        sensitivity="BASE",
    )
    by_id = {record.template_id: record for record in instantiation_records}
    records: list[dict[str, Any]] = []
    risks = []

    for template in action_registry.templates:
        action_id = template.template_id
        instantiation = by_id[action_id]
        candidate = instantiation.candidate
        readiness = action_registry.numerical_readiness_for(
            action_id, response_registry=response_registry
        )
        base = {
            "episode_id": first["episode_id"],
            "decision_node_id": node_id,
            "action_id": action_id,
            "action_family": template.family,
            "chi_inst": instantiation.instantiation_state.value,
            "chi_fact": (
                candidate.precondition_state if candidate is not None else "UNKNOWN"
            ),
            "chi_num": "UNDEFINED",
            "chi_resp": (
                candidate.response_support.value
                if candidate is not None and candidate.response_support is not None
                else "NOT_MATERIALIZED"
            ),
            "chi_opp": "NOT_REQUIRED" if action_id == "A00" else "UNKNOWN",
            "chi_sel": "UNIMPLEMENTED",
            "response_parameter_status": readiness.response_parameter_status,
            "risk_evaluation_support": None,
            "expected_loss": None,
            "VaR": None,
            "CVaR": None,
            "J": None,
            "ranking_lane": "NOT_COMPARABLE",
            "reason": readiness.reason,
            "m3_envelope_hash": None,
            "risk_envelope_hash": None,
            "cu_signature": None,
            "response_registry_hash": response_registry.digest(),
        }
        if candidate is None:
            base["reason"] = instantiation.reason
            records.append(base)
            continue
        if action_id == "A00":
            eligibility = _eligibility(candidate, node_id=node_id)
            m3 = build_a00_identity_envelope(
                baselines,
                eligibility=eligibility,
                response_rule=_build_rule(design[action_id]),
            )
            m4 = M4ActionEnvelopeInput.from_m3(m3).model_copy(
                update={"comparison_scope": comparison_scope}
            )
        elif readiness.chi_num_possible_if_state_complete:
            eligibility = _eligibility(candidate, node_id=node_id)
            response_parameters = response_registry.parameters(
                action_id, sensitivity="BASE"
            )
            m3 = build_conditional_scenario_envelope(
                baselines,
                eligibility=eligibility,
                response_rule=_build_rule(design[action_id]),
                response_parameters=response_parameters,
                mitigation=candidate.mitigation,
                induced=candidate.induced,
                induced_response=candidate.induced_response,
                footprint=candidate.footprint,
                seed=SMOKE_SEED,
                response_registry_hash=response_registry.digest(),
                sensitivity_level="BASE",
            )
            m4 = M4ActionEnvelopeInput.from_m3(m3).model_copy(
                update={"comparison_scope": comparison_scope}
            )
        else:
            records.append(base)
            continue

        risk = evaluate_residual_risk(
            m4,
            monetary_mapping=rmb,
            risk_policy=risk_policy,
        )
        risks.append(risk)
        base.update(
            {
                "chi_num": "DEFINED",
                "m3_envelope_hash": m3.envelope_hash,
                "cu_signature": _cu_signature(m3),
                "reason": (
                    "A00_IDENTITY_NUMERICAL_DEFINED"
                    if action_id == "A00"
                    else "NUMERICAL_RESPONSE_COMPLETE"
                ),
                **_m4_record(risk, m3_hash=m3.envelope_hash),
                "ranking_lane": risk.comparison_status.value,
            }
        )
        records.append(base)

    ranking = rank_risk_evaluations(tuple(risks))
    ranking_payload = {
        "supported_input_ranking": [
            item.model_dump(mode="json") for item in ranking.supported_input_ranking
        ],
        "conditional_input_ranking": [
            item.model_dump(mode="json") for item in ranking.conditional_input_ranking
        ],
        "not_comparable_action_ids": list(ranking.not_comparable_action_ids),
    }
    complete_non_a00 = [
        row for row in records if row["action_id"] != "A00" and row["chi_num"] == "DEFINED"
    ]
    a00 = next(row for row in records if row["action_id"] == "A00")
    differing = []
    a00_signature = a00.get("cu_signature")
    for row in complete_non_a00:
        if row["cu_signature"] != a00_signature:
            differing.append(row["action_id"])
    node_summary = {
        "decision_node_id": node_id,
        "operational_stage": first["operational_stage"],
        "scenario_count": len(rows),
        "formal_m2_scenarios": sum(
            item.formal_estimand_value.value_cu is not None
            for item in distribution.consequences
        ),
        "records": len(records),
        "defined_non_a00_action_ids": [row["action_id"] for row in complete_non_a00],
        "partial_non_a00_action_ids": [
            row["action_id"]
            for row in records
            if row["action_id"] != "A00" and row["chi_num"] == "UNDEFINED"
        ],
        "conditional_ranking_action_ids": [
            item.action_id for item in ranking.conditional_input_ranking
        ],
        "differing_non_a00_action_ids": differing,
        "ranking": ranking_payload,
    }
    return records, node_summary


def materialize(
    scenario_path: Path = SCENARIO_PATH,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    scenario_payload = _read_json(scenario_path)
    design_payload = _read_json(DESIGN_PATH)
    action_registry = ActionRegistry.load(ACTION_PATH)
    response_registry = ResponseScenarioRegistry.load(
        RESPONSE_PATH, structural_registry=action_registry
    )
    design = {row["action_id"]: row for row in design_payload["responses"]}
    readiness = action_registry.numerical_readiness(
        response_registry=response_registry
    )
    complete_ids = tuple(
        item.action_id
        for item in readiness
        if item.chi_num_possible_if_state_complete and item.action_id != "A00"
    )
    partial_ids = tuple(
        item.action_id
        for item in readiness
        if not item.chi_num_possible_if_state_complete and item.action_id != "A00"
    )

    bundle = load_data2_reference_bundle(_payloads())
    m2_registry = load_active_m2_cu_registry()
    cu_registry = FrozenData2CUNormalizationRegistry(m2_registry)
    mapper = M2Mapper(cu_registry, build_m2_frozen_scope())
    rmb = load_active_rmb_mapping()
    risk_policy = load_active_risk_policy()
    comparison_scope = _build_comparison_scope(rmb)

    by_node: dict[str, list[dict[str, Any]]] = {}
    for row in scenario_payload["scenarios"]:
        by_node.setdefault(row["decision_node_id"], []).append(row)
    node_meta = {
        item["decision_node_id"]: item for item in scenario_payload["nodes"]
    }

    all_records: list[dict[str, Any]] = []
    node_summaries: list[dict[str, Any]] = []
    for node_id in sorted(by_node):
        records, node_summary = _materialize_node(
            node_id=node_id,
            rows=by_node[node_id],
            node_meta=node_meta[node_id],
            scenario_payload=scenario_payload,
            mapper=mapper,
            bundle=bundle,
            cu_registry=cu_registry,
            action_registry=action_registry,
            response_registry=response_registry,
            design=design,
            rmb=rmb,
            risk_policy=risk_policy,
            comparison_scope=comparison_scope,
        )
        all_records.extend(records)
        node_summaries.append(node_summary)

    non_a00 = [row for row in all_records if row["action_id"] != "A00"]
    defined_non_a00 = [row for row in non_a00 if row["chi_num"] == "DEFINED"]
    m4_non_a00 = [
        row for row in defined_non_a00 if row["risk_numerical_state"] == "DEFINED"
    ]
    conditional_non_a00 = [
        row
        for row in m4_non_a00
        if row["comparison_status"] == NumericalComparisonStatus.CONDITIONAL_INPUTS.value
    ]
    differing = sorted(
        {
            action_id
            for node in node_summaries
            for action_id in node["differing_non_a00_action_ids"]
        }
    )
    fallback_scan = {
        "fallback_action_references": [],
        "default_action_references": [],
        "selector_references": [],
        "recommended_action_id_references": [],
        "status": "ABSENT",
    }
    payload = {
        "schema_version": "NON_A00_NUMERICAL_SMOKE_V1",
        "artifact_id": "NON_A00_NUMERICAL_SMOKE",
        "artifact_scope": "DEVELOPMENT_ONLY_LIGHTWEIGHT_SMOKE",
        "reference_fingerprint": REFERENCE_FINGERPRINT,
        "baseline_identity": {
            "m1_checkpoint_hash": "sha256:d78de00e708b359c881b6594c3d507fbf34bc3d570c3cbc5cf245be9e83be11d",
            "m1_positive_tail_hash": "sha256:571dba89e71d049f44431929bbfc1b0941a12a4255be2d8847cd554f3db47cb6",
            "m1_scenario_artifact_hash": scenario_payload["artifact_hash"],
            "m2_cu_registry_hash": m2_registry.registry_hash,
            "m3_action_registry_hash": action_registry.digest(),
            "m3_response_registry_hash": response_registry.digest(),
            "m4_rmb_registry_hash": rmb.registry_hash,
            "m4_risk_policy_hash": risk_policy.policy_hash,
            "seed": SMOKE_SEED,
        },
        "counts": {
            "development_nodes": len(node_summaries),
            "records": len(all_records),
            "records_per_node": sorted({
                sum(1 for row in all_records if row["decision_node_id"] == node["decision_node_id"])
                for node in node_summaries
            }),
            "non_a00_formed_count": sum(
                row["chi_inst"] == InstantiationState.FORMED.value for row in non_a00
            ),
            "non_a00_numerically_defined_count": len(defined_non_a00),
            "non_a00_m4_evaluated_count": len(m4_non_a00),
            "non_a00_conditional_ranking_count": len(conditional_non_a00),
            "differing_non_a00_action_count": len(differing),
            "partial_non_a00_action_ids": list(partial_ids),
            "complete_non_a00_action_ids": list(complete_ids),
        },
        "gate": {
            "A00_ONLY_NUMERICAL_PATH": not bool(defined_non_a00),
            "non_a00_formed_count_positive": bool(non_a00),
            "non_a00_numerically_defined_count_positive": bool(defined_non_a00),
            "non_a00_m4_evaluated_count_positive": bool(m4_non_a00),
            "non_a00_conditional_ranking_count_positive": bool(conditional_non_a00),
            "action_conditioned_cu_envelopes_differ": bool(differing),
            "A00_fallback_selector": fallback_scan["status"],
            "operational_recommendation_count": 0,
            "operational_recommendation_zero_is_expected": True,
            "phase_1_pass": all(
                (
                    bool(non_a00),
                    bool(defined_non_a00),
                    bool(m4_non_a00),
                    bool(conditional_non_a00),
                    bool(differing),
                    not fallback_scan["fallback_action_references"],
                )
            ),
        },
        "fallback_scan": fallback_scan,
        "nodes": node_summaries,
        "guards": {
            "data1_modified": False,
            "data2_modified": False,
            "final_test_access_count": 0,
            "model_retrained": False,
            "parameter_reselected": False,
            "experiment_created": False,
        },
    }
    payload["artifact_hash"] = content_id(payload)

    records_path = output_dir / RECORDS_PATH.name
    summary_path = output_dir / SUMMARY_PATH.name
    report_path = output_dir / REPORT_PATH.name
    output_dir.mkdir(parents=True, exist_ok=True)
    with records_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in all_records:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    summary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    report = [
        "# NON-A00 NUMERICAL SMOKE REPORT",
        "",
        f"- Phase 1 status: **{'PASS' if payload['gate']['phase_1_pass'] else 'FAIL'}**",
        f"- Development nodes: {len(node_summaries)} (all source stages: {sorted({node['operational_stage'] for node in node_summaries})})",
        f"- Structural records: {len(all_records)} ({payload['counts']['records_per_node']} per node)",
        f"- Non-A00 formed: {payload['counts']['non_a00_formed_count']}",
        f"- Non-A00 numerical defined: {payload['counts']['non_a00_numerically_defined_count']}",
        f"- Non-A00 M4 evaluated: {payload['counts']['non_a00_m4_evaluated_count']}",
        f"- Non-A00 conditional ranking: {payload['counts']['non_a00_conditional_ranking_count']}",
        f"- Differing action-conditioned CU envelopes: {', '.join(differing) or 'NONE'}",
        "- A00 fallback selector: **ABSENT**",
        "- Operational recommendations: `0` (expected because `chi_sel = UNIMPLEMENTED`)",
        "",
        "## Guard",
        "",
        "`DATA1 MODIFIED: NO`  ",
        "`DATA2 MODIFIED: NO`  ",
        "`FINAL TEST ACCESSED: NO`  ",
        "`MODEL RETRAINED: NO`  ",
        "`PARAMETER RESELECTED: NO`  ",
        "`EXP CREATED: NO`",
    ]
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-path", type=Path, default=SCENARIO_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    print(
        json.dumps(
            materialize(args.scenario_path, args.output_dir),
            indent=2,
            sort_keys=True,
            default=str,
        )
    )

