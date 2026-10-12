"""Development E2/E3 path using the exact weighted M1 marginal coupling.

This module is deliberately separate from the historical Section 5 runner.  It
keeps the old permutation output available under ``HISTORY_MARGINAL_LEGACY``
and routes only this experiment through ``ExactWeightedMarginalDistribution``.
All M2 consequence, M3 enumeration, and M4 evaluation calls remain the model
owned implementations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

from exp.jatm_section5.information_value import information_value_main
from exp.jatm_section5.recovery_value import (
    comparator_recovery,
    prepare_reference_recovery,
)
from exp.jatm_section5.run_development import (
    STAGES,
    _build_nodes,
    _canonical_selection,
    _canonicalize,
    _domain_vector,
    _reference_eligible,
    _abstaining_consequence_set,
)
from exp.jatm_section5.contracts import RepresentationNode
from model.M1.marginal_distribution import ExactWeightedMarginalDistribution
from model.M2.comparison_support import (
    DOMAIN_EMPHASIS_FLIGHT_VIEW,
    DOMAIN_EMPHASIS_PASSENGER_VIEW,
    DOMAIN_EMPHASIS_RESOURCE_VIEW,
    PRIMARY_AGGREGATION_VIEW,
    delay_priority_signal,
    phi_c,
)
from model.M3.stage2 import RecoveryPolicy, objective_by_grid
from model.M2.consequence_service import M2ConsequenceService
from model.common.decision_contracts import HeadroomSummary, StateScenarioSet
from model.common.enums import OperationalStage, SupportState
from model.common.identity import content_id
from model.PRE.decision_environment import action_stage_class
from validation.v2_phase5.common import (
    PHASE_DIR,
    consequence_set,
    expected_cu_for_support,
    load_authorities,
    load_development_bridge,
    load_tail_continuations,
    comparison_support_for as common_comparison_support_for,
)
from validation.v2_phase5.families import build_consequence_service
from exp.jatm_s34.annual_bridge import iter_annual_bridges


ROOT = Path(__file__).resolve().parents[2]
MAX_EXACT_SCENARIOS = 20_000
PROFILES = {
    "BALANCED": PRIMARY_AGGREGATION_VIEW,
    "FLIGHT": DOMAIN_EMPHASIS_FLIGHT_VIEW,
    "PASSENGER": DOMAIN_EMPHASIS_PASSENGER_VIEW,
    "RESOURCE": DOMAIN_EMPHASIS_RESOURCE_VIEW,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _headroom() -> HeadroomSummary:
    payload = json.loads(
        (PHASE_DIR / "TRAIN_TURNAROUND_HEADROOM_SUMMARY.json").read_text(
            encoding="utf-8"
        )
    )
    return HeadroomSummary.model_validate(payload["factual_headroom"]["headroom_summary"])


def _exact_projection(node: RepresentationNode, service) -> tuple[dict[str, Any], StateScenarioSet, Any, Any, dict[str, Any]]:
    source = node.state("HISTORY_JOINT")
    adapter = ExactWeightedMarginalDistribution.from_source(source)
    if adapter.scenario_count > MAX_EXACT_SCENARIOS:
        raise RuntimeError(
            f"E2_EXACT_MARGINAL_SCENARIO_LIMIT:{node.node_id}:{adapter.scenario_count}"
        )
    exact_state = adapter.materialize(max_scenarios=MAX_EXACT_SCENARIOS)
    if node.node_id in service.references:
        exact_consequence = consequence_set(service, exact_state)
    else:
        exact_consequence = _abstaining_consequence_set(
            exact_state,
            registry_id=service.registry_id,
            registry_hash=service.registry_hash,
        )
    support = common_comparison_support_for(exact_state, exact_consequence)
    audit = {
        "node_id": node.node_id,
        "product_scenario_count": adapter.scenario_count,
        "source_scenario_count": len(source.scenarios),
        "support_mass": float(support.supported_mass),
        "support_included": bool(support.included),
        "physical_feasibility": "NOT_ASSERTED_PRODUCT_COUPLING",
        "identity_note": adapter.identity_note,
    }
    if not support.included:
        values = {"delay": None, "consequence": None, "domain": None, "components": None}
    else:
        expected = expected_cu_for_support(exact_consequence, support)
        delay = delay_priority_signal(exact_state, support).score
        values = {
            "delay": None if delay is None else float(delay),
            "consequence": float(phi_c(expected)),
            "domain": _domain_vector(expected),
            "components": {key: float(value) for key, value in expected.items()},
        }
    audit["status"] = "PASS_EXACT_MARGINAL" if support.included else "ABSTAIN_COMMON_SUPPORT"
    audit["scores"] = values
    return values, exact_state, exact_consequence, support, audit


def _project_nodes(base_nodes, service, *, keep_exact_ids: set[str] | None = None):
    score_nodes: list[RepresentationNode] = []
    audits: list[dict[str, Any]] = []
    retained_exact: dict[str, tuple[StateScenarioSet, Any, Any, dict[str, Any]]] = {}
    for node in base_nodes:
        values, exact_state, exact_consequence, support, audit = _exact_projection(node, service)
        audits.append(audit)
        # Preserve the old permutation representation explicitly.  The alias
        # used by the E2/E3 adapters points to exact weighted marginal.
        state_sets = dict(node.state_sets)
        consequence_sets = dict(node.consequence_sets)
        supports = dict(node.supports)
        support_full = dict(node.support_full)
        delay_scores = dict(node.delay_scores)
        consequence_scores = dict(node.consequence_scores)
        domain_scores = dict(node.domain_scores)
        component_scores = dict(node.component_scores)
        state_sets["HISTORY_MARGINAL_EXACT"] = exact_state
        state_sets["HISTORY_MARGINAL"] = exact_state
        consequence_sets["HISTORY_MARGINAL_EXACT"] = exact_consequence
        consequence_sets["HISTORY_MARGINAL"] = exact_consequence
        supports["HISTORY_MARGINAL_EXACT"] = support
        supports["HISTORY_MARGINAL"] = support
        support_full["HISTORY_MARGINAL_EXACT"] = bool(
            support.included and abs(float(support.supported_mass) - 1.0) <= 1e-9
        )
        support_full["HISTORY_MARGINAL"] = support_full["HISTORY_MARGINAL_EXACT"]
        delay_scores["HISTORY_MARGINAL_EXACT"] = values["delay"]
        delay_scores["HISTORY_MARGINAL"] = values["delay"]
        consequence_scores["HISTORY_MARGINAL_EXACT"] = values["consequence"]
        consequence_scores["HISTORY_MARGINAL"] = values["consequence"]
        domain_scores["HISTORY_MARGINAL_EXACT"] = values["domain"]
        domain_scores["HISTORY_MARGINAL"] = values["domain"]
        component_scores["HISTORY_MARGINAL_EXACT"] = values["components"]
        component_scores["HISTORY_MARGINAL"] = values["components"]
        projected = replace(
            node,
            state_sets=state_sets,
            consequence_sets=consequence_sets,
            supports=supports,
            support_full=support_full,
            delay_scores=delay_scores,
            consequence_scores=consequence_scores,
            domain_scores=domain_scores,
            component_scores=component_scores,
        )
        score_nodes.append(projected)
        if keep_exact_ids is None or node.node_id in keep_exact_ids:
            retained_exact[node.node_id] = (
                exact_state,
                exact_consequence,
                support,
                values,
            )
    return tuple(score_nodes), audits, retained_exact


def _project_light_node(node: RepresentationNode, service):
    """Project one node and retain only score/support metadata for E2 Stage-I.

    Exact state/consequence scenario sets are intentionally released here;
    full objects are rebuilt only for the Stage-II shortlist in the second
    pass.  This is numerically the same `_exact_projection` operation.
    """
    values, _state, _consequence, support, audit = _exact_projection(node, service)
    state_sets = dict(node.state_sets); consequence_sets = dict(node.consequence_sets)
    supports = dict(node.supports); support_full = dict(node.support_full)
    delay_scores = dict(node.delay_scores); consequence_scores = dict(node.consequence_scores)
    domain_scores = dict(node.domain_scores); component_scores = dict(node.component_scores)
    supports["HISTORY_MARGINAL_EXACT"] = support; supports["HISTORY_MARGINAL"] = support
    support_full["HISTORY_MARGINAL_EXACT"] = bool(support.included and abs(float(support.supported_mass)-1.0) <= 1e-9)
    support_full["HISTORY_MARGINAL"] = support_full["HISTORY_MARGINAL_EXACT"]
    delay_scores["HISTORY_MARGINAL_EXACT"] = values["delay"]; delay_scores["HISTORY_MARGINAL"] = values["delay"]
    consequence_scores["HISTORY_MARGINAL_EXACT"] = values["consequence"]; consequence_scores["HISTORY_MARGINAL"] = values["consequence"]
    domain_scores["HISTORY_MARGINAL_EXACT"] = values["domain"]; domain_scores["HISTORY_MARGINAL"] = values["domain"]
    component_scores["HISTORY_MARGINAL_EXACT"] = values["components"]; component_scores["HISTORY_MARGINAL"] = values["components"]
    light = replace(node, state_sets={}, consequence_sets={}, supports=supports,
                    support_full=support_full, delay_scores=delay_scores,
                    consequence_scores=consequence_scores, domain_scores=domain_scores,
                    component_scores=component_scores)
    return light, audit


def _source_shortlists(nodes: tuple[RepresentationNode, ...], q: float) -> dict[OperationalStage, tuple[str, ...]]:
    canonical = _canonicalize(nodes, stages=STAGES)
    output: dict[OperationalStage, tuple[str, ...]] = {}
    for stage in (OperationalStage.PRE_IB, OperationalStage.POST_IB_PRE_OB):
        result = _canonical_selection(canonical.get(stage, ()), q=q)
        output[stage] = (
            tuple(result.evaluation.reference_shortlist) if result is not None else ()
        )
    return output


def _replace_with_exact(node: RepresentationNode, exact_payload) -> RepresentationNode:
    exact_state, exact_consequence, support, values = exact_payload
    state_sets = dict(node.state_sets)
    consequence_sets = dict(node.consequence_sets)
    supports = dict(node.supports)
    support_full = dict(node.support_full)
    state_sets["HISTORY_MARGINAL_EXACT"] = exact_state
    state_sets["HISTORY_MARGINAL"] = exact_state
    consequence_sets["HISTORY_MARGINAL_EXACT"] = exact_consequence
    consequence_sets["HISTORY_MARGINAL"] = exact_consequence
    supports["HISTORY_MARGINAL_EXACT"] = support
    supports["HISTORY_MARGINAL"] = support
    support_full["HISTORY_MARGINAL_EXACT"] = bool(support.included and abs(float(support.supported_mass) - 1.0) <= 1e-9)
    support_full["HISTORY_MARGINAL"] = support_full["HISTORY_MARGINAL_EXACT"]
    return replace(
        node,
        state_sets=state_sets,
        consequence_sets=consequence_sets,
        supports=supports,
        support_full=support_full,
    )


def _stage1_rows(nodes: tuple[RepresentationNode, ...], q: float):
    canonical = _canonicalize(nodes, stages=STAGES)
    rows = []
    for stage in (OperationalStage.PRE_IB, OperationalStage.POST_IB_PRE_OB):
        result = _canonical_selection(canonical.get(stage, ()), q=q)
        if result is None:
            continue
        rows.append({
            "stage": action_stage_class(stage),
            "q": float(q),
            "reference": "HISTORY_JOINT",
            "comparator": "HISTORY_MARGINAL_EXACT",
            "N": len(result.candidates),
            "K": len(result.evaluation.comparator_shortlist),
            "overlap": result.evaluation.overlap_count,
            "L_att": result.evaluation.L_att,
            "candidate_node_ids": list(result.evaluation.candidate_node_ids),
            "reference_shortlist": list(result.evaluation.reference_shortlist),
            "comparator_shortlist": list(result.evaluation.comparator_shortlist),
        })
    return rows


def _e3_rows(reference_cohort, service, headroom: HeadroomSummary):
    rows: list[dict[str, Any]] = []
    for profile, view in PROFILES.items():
        policy = RecoveryPolicy(lambda_policy=0.25, aggregation_view=view)
        for item in reference_cohort.nodes:
            node = item.node
            context = __import__("exp.jatm_section5.recovery_value", fromlist=["transition_context"]).transition_context(node, headroom)
            for representation in ("HISTORY_JOINT", "HISTORY_MARGINAL_EXACT"):
                state = node.state(representation)
                table = objective_by_grid(state, context=context, service=service, u_max=headroom.u_max, policy=policy, floor_to_minutes=headroom.floor_to_minutes)
                best_u, best_j = min(table, key=lambda pair: (pair[1], pair[0]))
                ordered = sorted(float(value) for _, value in table)
                margin = None if len(ordered) < 2 else ordered[1] - float(best_j)
                rows.append({
                    "profile": profile,
                    "aggregation_view": view,
                    "representation": representation,
                    "node_id": node.node_id,
                    "stage": action_stage_class(node.stage),
                    "u_star": float(best_u),
                    "J_zero": float(table[0][1]),
                    "J_star": float(best_j),
                    "recoverable_value": float(table[0][1] - best_j),
                    "decision_margin": float(margin) if margin is not None else None,
                    "headroom_u_max": float(headroom.u_max),
                    "action_grid_size": len(table),
                })
    return rows


def _mechanism_rows(nodes: tuple[RepresentationNode, ...], service, headroom):
    rows = []
    for node in nodes:
        state = node.state("HISTORY_MARGINAL_EXACT")
        consequence = node.consequences("HISTORY_MARGINAL_EXACT")
        nominal = common_comparison_support_for(state, consequence)
        full = common_comparison_support_for(state, consequence, threshold=1.0)
        rows.append({
            "node_id": node.node_id,
            "nominal_threshold": nominal.threshold,
            "nominal_support_mass": nominal.supported_mass,
            "full_support_mass": full.supported_mass,
            "threshold_ablation_status": "CHANGED" if nominal.included != full.included else "UNCHANGED",
            "headroom_u_max": headroom.u_max,
            "headroom_positive": bool(headroom.u_max > 0.0),
            "operator_change": "THRESHOLD_FULL_SUPPORT_DIAGNOSTIC_AND_HEADROOM_BOUNDARY_DIAGNOSTIC",
        })
    return rows


def run(*, output_root: Path, node_limit: int | None = None, annual_context=None) -> dict[str, Any]:
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if annual_context is None:
        authorities = load_authorities()
        bridge = load_development_bridge()
        tails = load_tail_continuations()
        model_kwargs = {}
    else:
        authorities = annual_context["authorities"]
        bridge = annual_context["bridge"]
        tails = annual_context["tails"]
        model_kwargs = {
            "history_checkpoint": annual_context["history_checkpoint"],
            "current_checkpoint": annual_context["current_checkpoint"],
        }
    layer = build_consequence_service(authorities=authorities, bridge=bridge, output_dir=output_root / "materialization")
    base_nodes = _build_nodes(authorities=authorities, bridge=bridge, tails=tails, layer=layer, **model_kwargs)
    if node_limit is not None:
        base_nodes = base_nodes[: int(node_limit)]
    projected, audits, exact_payloads = _project_nodes(base_nodes, layer.service)
    source_shortlists = _source_shortlists(projected, q=0.10)
    selected_ids = {node_id for values in source_shortlists.values() for node_id in values}
    exact_by_id = {node.node_id: _replace_with_exact(projected[index], exact_payloads[node.node_id]) for index, node in enumerate(projected) if node.node_id in exact_payloads}
    selected_nodes = tuple(exact_by_id[node.node_id] for node in projected if node.node_id in selected_ids)
    canonical = _canonicalize(projected, stages=STAGES)
    headroom = _headroom()
    reference_cohort = prepare_reference_recovery(selected_nodes, source_shortlists=source_shortlists, service=layer.service, headroom=headroom)
    information_nodes = tuple(
        node
        for node in projected
        if node.stage in (OperationalStage.PRE_IB, OperationalStage.POST_IB_PRE_OB)
        and all(
            node.support(rep).included
            and node.consequence_scores.get(rep) is not None
            for rep in (
                "HISTORY_JOINT",
                "CURRENT_JOINT",
                "HISTORY_POINT",
                "HISTORY_MARGINAL",
            )
        )
    )
    e2_information, e2_diagnostics, e2_bootstrap = information_value_main(
        information_nodes,
        q=0.10,
        reference_cohort=reference_cohort,
        service=layer.service,
        headroom=headroom,
        seed=20261011,
        replicates=2000,
    )
    for row in e2_information:
        if row.get("information_component") == "CROSS_STATE_DEPENDENCE":
            row["comparator"] = "HISTORY_MARGINAL_EXACT"
    recovery_rows = []
    for representation in ("CURRENT_JOINT", "HISTORY_POINT", "HISTORY_MARGINAL_EXACT"):
        result = comparator_recovery(reference_cohort, representation=("HISTORY_MARGINAL" if representation == "HISTORY_MARGINAL_EXACT" else representation), service=layer.service, headroom=headroom)
        recovery_rows.append({
            "representation": representation,
            "loss": result.evaluation.L_rec,
            "reference_recoverable_value": result.evaluation.reference_recoverable_value,
            "delta_recovery_objective": result.evaluation.delta_recovery_objective,
            "typed_fallbacks": dict(result.typed_fallbacks),
        })
    e3 = _e3_rows(reference_cohort, layer.service, headroom)
    mechanisms = _mechanism_rows(selected_nodes, layer.service, headroom)
    payload = {
        "schema_version": "JATM_S34_E2_E3_EXACT_DEVELOPMENT_V1",
        "status": "DEVELOPMENT_COMPLETE",
        "node_count": len(base_nodes),
        "exact_marginal": {
            "max_product_scenarios": max((row.get("product_scenario_count", 0) for row in audits), default=0),
            "audit_count": len(audits),
            "support_included_count": sum(bool(row.get("support_included")) for row in audits),
            "support_abstain_count": sum(not bool(row.get("support_included")) for row in audits),
            "product_scenario_count_min": min((row.get("product_scenario_count", 0) for row in audits), default=0),
            "product_scenario_count_total": sum(row.get("product_scenario_count", 0) for row in audits),
            "physical_feasibility": "NOT_ASSERTED_PRODUCT_COUPLING",
            "legacy_result_label": "HISTORY_MARGINAL_LEGACY",
            "exact_result_label": "HISTORY_MARGINAL_EXACT",
        },
        "e2": {
            "estimand": "CURRENT_JOINT_HISTORY_JOINT_HISTORY_POINT_HISTORY_MARGINAL_EXACT",
            "stage1_rows": _stage1_rows(projected, 0.10),
            "information_value": e2_information,
            "diagnostics": e2_diagnostics,
            "bootstrap": e2_bootstrap,
            "recovery_rows": recovery_rows,
            "reference_cohort_size": len(reference_cohort.nodes),
            "information_candidate_count": len(information_nodes),
        },
        "e3": {
            "profiles": list(PROFILES),
            "rows": e3,
            "mechanism_diagnostics": mechanisms,
            "joint_marginal_pair_count": len(e3),
        },
        "input_contract": {
            "git_head": subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
            ).stdout.strip(),
            "final_test_access_count": 0,
            "scientific_recomputation": True,
            "sealed_executor_called": False,
            "primary_headroom": str(PHASE_DIR / "TRAIN_TURNAROUND_HEADROOM_SUMMARY.json"),
        },
    }
    payload["artifact_hash"] = content_id(payload)
    (output_root / "E2_E3_SUMMARY.json").write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (output_root / "EXACT_MARGINAL_AUDIT.json").write_text(json.dumps(audits, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (output_root / "E2_INFORMATION.csv").write_text(json.dumps(e2_information, indent=2, default=str) + "\n", encoding="utf-8")
    (output_root / "E3_OBJECTIVE_ROWS.json").write_text(json.dumps(e3, indent=2, default=str) + "\n", encoding="utf-8")
    (output_root / "E3_MECHANISM_DIAGNOSTICS.json").write_text(json.dumps(mechanisms, indent=2, default=str) + "\n", encoding="utf-8")
    return payload


def run_bounded_annual(*, output_root: Path, year: int, n: int = 4096,
                       chunk_size: int = 64, node_limit: int | None = None,
                       bootstrap_replicates: int = 2000) -> dict[str, Any]:
    """Run E2/E3 with score-only first pass and shortlist-only Stage-II pass."""
    output_root = Path(output_root).resolve(); output_root.mkdir(parents=True, exist_ok=True)
    light_by_key = {}; audits = []; chunk_count = 0; last_authorities = None
    for context in iter_annual_bridges(year=year, n=n, chunk_size=chunk_size, node_limit=node_limit):
        chunk_count += 1; last_authorities = context["authorities"]
        layer = build_consequence_service(authorities=context["authorities"], bridge=context["bridge"],
                                           output_dir=output_root / "materialization" / f"first_{chunk_count:04d}")
        built = _build_nodes(authorities=context["authorities"], bridge=context["bridge"], tails=context["tails"],
                             layer=layer, history_checkpoint=context["history_checkpoint"], current_checkpoint=context["current_checkpoint"],
                             history_pipeline=context.get("history_pipeline"), current_pipeline=context.get("current_pipeline"))
        for node in built:
            if node.stage not in STAGES:
                continue
            light, audit = _project_light_node(node, layer.service); audits.append(audit)
            key = (light.episode_id, light.stage)
            previous = light_by_key.get(key)
            if previous is None or (light.decision_time, light.node_id) < (previous.decision_time, previous.node_id):
                light_by_key[key] = light
        (output_root / "E2_E3_FIRST_PASS_CHECKPOINT.json").write_text(
            json.dumps({"schema_version": "JATM_S34_E2_E3_BOUNDED_CHECKPOINT_V1",
                        "year": int(year), "pass": "score_only", "completed_chunks": chunk_count,
                        "canonical_records": len(light_by_key), "final_test_access_count": 0},
                       indent=2, sort_keys=True) + "\n", encoding="utf-8")
        del built, layer, context
    projected = tuple(light_by_key.values())
    source_shortlists = _source_shortlists(projected, q=0.10)
    selected_ids = {node_id for values in source_shortlists.values() for node_id in values}

    # Second pass: rebuild only Stage-II shortlist nodes and their exact states.
    full_by_id = {}; selected_bindings = {}; second_chunks = 0
    for context in iter_annual_bridges(year=year, n=n, chunk_size=chunk_size, node_limit=node_limit):
        second_chunks += 1
        layer = build_consequence_service(authorities=context["authorities"], bridge=context["bridge"],
                                           output_dir=output_root / "materialization" / f"second_{second_chunks:04d}")
        for node_id, binding in layer.bindings.items():
            if node_id in selected_ids:
                selected_bindings[node_id] = binding
        built = _build_nodes(authorities=context["authorities"], bridge=context["bridge"], tails=context["tails"], layer=layer,
                             history_checkpoint=context["history_checkpoint"], current_checkpoint=context["current_checkpoint"],
                             history_pipeline=context.get("history_pipeline"), current_pipeline=context.get("current_pipeline"))
        for node in built:
            if node.node_id not in selected_ids:
                continue
            values, exact_state, exact_consequence, support, _audit = _exact_projection(node, layer.service)
            full_by_id[node.node_id] = _replace_with_exact(node, (exact_state, exact_consequence, support, values))
        (output_root / "E2_E3_SECOND_PASS_CHECKPOINT.json").write_text(
            json.dumps({"schema_version": "JATM_S34_E2_E3_BOUNDED_CHECKPOINT_V1",
                        "year": int(year), "pass": "shortlist_stage_II", "completed_chunks": second_chunks,
                        "selected_full_nodes": len(full_by_id), "final_test_access_count": 0},
                       indent=2, sort_keys=True) + "\n", encoding="utf-8")
        del built, layer, context
    service = M2ConsequenceService(last_authorities.registry, selected_bindings)
    selected_nodes = tuple(full_by_id[node_id] for node_id in sorted(selected_ids) if node_id in full_by_id)
    headroom = _headroom()
    reference_cohort = prepare_reference_recovery(selected_nodes, source_shortlists=source_shortlists, service=service, headroom=headroom)
    information_nodes = tuple(node for node in projected if node.stage in STAGES and all(
        node.support(rep).included and node.consequence_scores.get(rep) is not None
        for rep in ("HISTORY_JOINT", "CURRENT_JOINT", "HISTORY_POINT", "HISTORY_MARGINAL_EXACT")))
    e2_information, e2_diagnostics, e2_bootstrap = information_value_main(
        information_nodes, q=0.10, reference_cohort=reference_cohort, service=service,
        headroom=headroom, seed=20261011, replicates=int(bootstrap_replicates))
    for row in e2_information:
        if row.get("information_component") == "CROSS_STATE_DEPENDENCE":
            row["comparator"] = "HISTORY_MARGINAL_EXACT"
    recovery_rows = []
    for representation in ("CURRENT_JOINT", "HISTORY_POINT", "HISTORY_MARGINAL_EXACT"):
        result = comparator_recovery(reference_cohort, representation=("HISTORY_MARGINAL" if representation == "HISTORY_MARGINAL_EXACT" else representation), service=service, headroom=headroom)
        recovery_rows.append({"representation": representation, "loss": result.evaluation.L_rec,
                              "reference_recoverable_value": result.evaluation.reference_recoverable_value,
                              "delta_recovery_objective": result.evaluation.delta_recovery_objective,
                              "typed_fallbacks": dict(result.typed_fallbacks)})
    e3 = _e3_rows(reference_cohort, service, headroom); mechanisms = _mechanism_rows(selected_nodes, service, headroom)
    payload = {
        "schema_version": "JATM_S34_E2_E3_EXACT_DEVELOPMENT_BOUNDED_V1", "status": "DEVELOPMENT_COMPLETE",
        "year": int(year), "chunk_size": int(chunk_size), "chunk_count": chunk_count,
        "second_pass_chunk_count": second_chunks, "node_count": len(projected),
        "exact_marginal": {"max_product_scenarios": max((row.get("product_scenario_count", 0) for row in audits), default=0),
                            "audit_count": len(audits), "support_included_count": sum(bool(row.get("support_included")) for row in audits),
                            "support_abstain_count": sum(not bool(row.get("support_included")) for row in audits),
                            "physical_feasibility": "NOT_ASSERTED_PRODUCT_COUPLING", "legacy_result_label": "HISTORY_MARGINAL_LEGACY",
                            "exact_result_label": "HISTORY_MARGINAL_EXACT"},
        "e2": {"estimand": "CURRENT_JOINT_HISTORY_JOINT_HISTORY_POINT_HISTORY_MARGINAL_EXACT", "stage1_rows": _stage1_rows(projected, 0.10),
               "information_value": e2_information, "diagnostics": e2_diagnostics, "bootstrap": e2_bootstrap,
               "recovery_rows": recovery_rows, "reference_cohort_size": len(reference_cohort.nodes), "information_candidate_count": len(information_nodes)},
        "e3": {"profiles": list(PROFILES), "rows": e3, "mechanism_diagnostics": mechanisms, "joint_marginal_pair_count": len(e3)},
        "input_contract": {"git_head": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip(),
                            "final_test_access_count": 0, "scientific_recomputation": True, "sealed_executor_called": False,
                            "bounded_memory": True, "two_pass": "score_only_then_shortlist_stage_II"},
    }
    payload["artifact_hash"] = content_id(payload)
    (output_root / "E2_E3_SUMMARY.json").write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (output_root / "EXACT_MARGINAL_AUDIT.json").write_text(json.dumps(audits, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (output_root / "E3_OBJECTIVE_ROWS.json").write_text(json.dumps(e3, indent=2, default=str) + "\n", encoding="utf-8")
    (output_root / "E3_MECHANISM_DIAGNOSTICS.json").write_text(json.dumps(mechanisms, indent=2, default=str) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--node-limit", type=int, default=None)
    args = parser.parse_args()
    result = run(output_root=args.output_root, node_limit=args.node_limit)
    print(json.dumps({"status": result["status"], "node_count": result["node_count"], "e3_rows": result["e3"]["joint_marginal_pair_count"]}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
