"""Legacy pre-V2 evaluator; retained for compatibility tests only.

M4 V2 uses `residual_risk.evaluate_residual_risk` and never reconstructs an
M3 response or consumes PRE/M1/M2 operational objects.
"""

from __future__ import annotations

from model.M3.contracts import ResponseParameterStatus, ResponseProvenance
from model.common.errors import ContractError
from model.M4.coverage import (
    A00BaselineComparatorGate,
    MaterialCoverageEvaluation,
    evaluate_a00_baseline_gate,
    evaluate_material_coverage,
)
from model.M4.eligibility import scenario_opportunities
from model.M4.lanes import assign_lane
from model.M3.response import action_post_consequences, response_draw
from model.M4.results import ActionEvaluation
from model.M4.risk import weighted_mean, weighted_var_cvar
from model.common.estimand import FormalEstimandStatus
from model.common.monetary_system import MonetaryMappingRegistry, MonetaryMappingStatus


def _interpretation_class(candidate) -> str:
    """Carry the Pi_a evidence interpretation class separately from eligibility.

    Structured response_support evidence bases win; legacy single-label
    provenance maps to the declared interpretation category.
    """
    support = getattr(candidate, "response_support", None)
    if support is not None and getattr(support, "evidence_bases", ()):
        return "+".join(sorted(item.value for item in support.evidence_bases))
    mapping = {
        ResponseProvenance.PURE_SCENARIO: "SCENARIO_BASED",
        ResponseProvenance.STRUCTURAL_BOUNDED_SCENARIO: "STRUCTURAL_SCENARIO",
        ResponseProvenance.OPERATOR_INDUSTRY: "OPERATIONAL_RULE",
        ResponseProvenance.EMPIRICAL_ACTION_LOG: "EMPIRICALLY_ANCHORED",
        ResponseProvenance.UNSUPPORTED: "UNSUPPORTED",
    }
    return mapping.get(getattr(candidate, "response_provenance", None), "NOT_DECLARED")


def aggregate_a00_baseline_gate(m2_consequences, material_coverage_contract):
    gates = tuple(evaluate_a00_baseline_gate(
        consequence.component_vector.rows, material_coverage_contract)
        for consequence in m2_consequences)
    return A00BaselineComparatorGate(
        valid=all(item.valid for item in gates),
        missing_components=tuple(sorted({component for item in gates for component in item.missing_components})),
        explanation=tuple(sorted({explanation for item in gates for explanation in item.explanation})),
    )


def _aggregate_candidate_coverage(candidate, m2_consequences, material_coverage_contract):
    rows = tuple(evaluate_material_coverage(
        candidate, consequence.component_vector.rows, material_coverage_contract)
        for consequence in m2_consequences)
    return MaterialCoverageEvaluation(
        candidate_action_id=candidate.candidate_action_id,
        material_benefit_coverage=all(item.material_benefit_coverage for item in rows),
        material_burden_coverage=all(item.material_burden_coverage for item in rows),
        baseline_coverage=all(item.baseline_coverage for item in rows),
        nonmaterial_missingness=tuple(sorted({component for item in rows for component in item.nonmaterial_missingness})),
        coverage_explanation=tuple(sorted({explanation for item in rows for explanation in item.coverage_explanation})),
        quality_flags=tuple(sorted({flag for item in rows for flag in item.quality_flags})),
    )


def evaluate_candidate(candidate, *, episode_id, m1_scenarios, m2_consequences,
                       material_coverage_contract, baseline_gate, monetary_mapping,
                       lambda_risk, alpha, seed):
    if not isinstance(monetary_mapping, MonetaryMappingRegistry):
        monetary_mapping = MonetaryMappingRegistry.model_validate(monetary_mapping)
    by_scenario = {row.scenario_id: row for row in m2_consequences}
    weights = [float(scenario["scenario_weight"]) for scenario in m1_scenarios]
    opportunities = scenario_opportunities(candidate, m1_scenarios)
    opportunity = weighted_mean(opportunities, weights)
    coverage = _aggregate_candidate_coverage(candidate, m2_consequences, material_coverage_contract)
    monetary_frozen = monetary_mapping.frozen
    lane = assign_lane(candidate, opportunity, baseline_valid=baseline_gate.valid,
                       material_coverage_valid=coverage.formal_coverage_valid,
                       monetary_mapping_frozen=monetary_frozen)
    formal_status = FormalEstimandStatus.FORMAL_AVAILABLE
    post = []
    any_scenario_conditioned = False
    monetary_blocker = False
    for scenario, open_ in zip(m1_scenarios, opportunities):
        consequence = by_scenario[scenario["scenario_id"]]
        formal = consequence.formal_estimand_value
        if formal.status is not FormalEstimandStatus.FORMAL_AVAILABLE:
            formal_status = formal.status
            continue
        values = {row.component_id: row.constructed_value_cu
                  for row in consequence.component_vector.rows
                  if row.component_id in formal.included_components}
        if any(value is None for value in values.values()) or len(values) != len(formal.included_components):
            formal_status = FormalEstimandStatus.FORMAL_AGGREGATE_UNRESOLVED
            continue
        if not monetary_frozen:
            formal_status = FormalEstimandStatus.MONETARY_MAPPING_NOT_FROZEN
            monetary_blocker = True
            continue
        response = 0.0
        if candidate.template_id != "A00" and open_:
            if candidate.response_parameter_status is ResponseParameterStatus.FROZEN:
                draw_parameters = dict(candidate.response_parameters)
                draw_parameters.setdefault("response_model", candidate.response_model)
                response = response_draw(
                    seed=seed,
                    episode_id=episode_id,
                    decision_node_id=str(scenario.get("decision_node_id", "")),
                    scenario_id=scenario["scenario_id"],
                    action_template_id=candidate.template_id,
                    parameters=draw_parameters,
                    response_registry_hash=candidate.response_registry_hash or "UNSET",
                    sensitivity_level=candidate.response_sensitivity_level or "BASE",
                )
                any_scenario_conditioned = True
            else:
                formal_status = FormalEstimandStatus.FORMAL_AGGREGATE_UNRESOLVED
                continue
        if candidate.template_id == "A00" or not open_:
            post_cu = dict(values)
        else:
            gamma = candidate.response_parameters.get("induced_score_to_cu")
            if gamma is None:
                raise ContractError("M4_INDUCED_SCORE_TO_CU_SOURCE_MISSING")
            post_cu = action_post_consequences(
                pre_by_component=values,
                mitigation=candidate.mitigation,
                induced=candidate.induced,
                rho=response,
                induced_score_to_cu=float(gamma),
                included_components=formal.included_components,
            )
        # Monetary conversion happens per scenario: L_a^m = sum_k omega_k^m * C_a,k^CU.
        total_money = monetary_mapping.to_money(post_cu)
        if total_money is None:
            formal_status = FormalEstimandStatus.MONETARY_MAPPING_NOT_FROZEN
            monetary_blocker = True
            continue
        post.append(total_money)
    scenario_conditioned = any_scenario_conditioned
    if len(post) != len(m1_scenarios):
        mean = var = cvar = risk = None
        post_total_status = "NOT_COMPUTED"
        scenario_conditioned = False
        if lane == "FORMAL":
            lane = "SCENARIO"
    else:
        mean = weighted_mean(post, weights)
        var, cvar = weighted_var_cvar(post, weights, alpha)
        risk = (1 - lambda_risk) * mean + lambda_risk * cvar
        post_total_status = (
            "SCENARIO_CONDITIONED" if scenario_conditioned else "FORMAL_ESTIMAND"
        )
    scope = m2_consequences[0].consequence_scope
    if monetary_blocker and formal_status is FormalEstimandStatus.FORMAL_AVAILABLE:
        formal_status = FormalEstimandStatus.MONETARY_MAPPING_NOT_FROZEN
    return ActionEvaluation(
        candidate_action_id=candidate.candidate_action_id,
        template_id=candidate.template_id,
        action_index=candidate.action_index,
        candidate_index=candidate.candidate_index,
        lane=lane,
        opportunity_probability=opportunity,
        estimand_id=scope.estimand_id,
        estimand_version=scope.estimand_version,
        scope_hash=scope.scope_hash,
        cu_normalization_registry_id=scope.cu_normalization_registry_id,
        monetary_system=monetary_mapping.monetary_system_id,
        monetary_mapping_registry_id=monetary_mapping.registry_id,
        monetary_mapping_registry_hash=monetary_mapping.registry_hash or monetary_mapping.digest(),
        formal_aggregate_status=formal_status,
        expected_residual=mean,
        var=var,
        cvar=cvar,
        residual_risk_j=risk,
        post_totals=tuple(post),
        scenario_conditioned=scenario_conditioned,
        post_total_status=post_total_status,
        interpretation_class=_interpretation_class(candidate),
        quality_flags=coverage.quality_flags,
        coverage_explanation=tuple(sorted(set(coverage.coverage_explanation + baseline_gate.explanation))),
    )
