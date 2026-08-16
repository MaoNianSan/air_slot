from __future__ import annotations

from model.M3.contracts import ResponseParameterStatus, ResponseProvenance
from model.M4.coverage import (
    A00BaselineComparatorGate,
    MaterialCoverageEvaluation,
    evaluate_a00_baseline_gate,
    evaluate_material_coverage,
)
from model.M4.eligibility import scenario_opportunities
from model.M4.lanes import assign_lane
from model.M4.response import response_value
from model.M4.results import ActionEvaluation
from model.M4.risk import weighted_mean, weighted_var_cvar
from model.common.estimand import FormalEstimandStatus


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
                       material_coverage_contract, baseline_gate, lambda_risk, alpha, seed):
    by_scenario = {row.scenario_id: row for row in m2_consequences}
    weights = [float(scenario["scenario_weight"]) for scenario in m1_scenarios]
    opportunities = scenario_opportunities(candidate, m1_scenarios)
    opportunity = weighted_mean(opportunities, weights)
    coverage = _aggregate_candidate_coverage(candidate, m2_consequences, material_coverage_contract)
    lane = assign_lane(candidate, opportunity, baseline_valid=baseline_gate.valid,
                       material_coverage_valid=coverage.formal_coverage_valid)
    formal_status = FormalEstimandStatus.FORMAL_AVAILABLE
    post = []
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
        response = 0.0
        if candidate.template_id != "A00" and open_:
            if candidate.response_parameter_status is ResponseParameterStatus.FROZEN:
                response = response_value(candidate, seed=seed, episode=episode_id,
                                          scenario=scenario["scenario_id"])
            elif candidate.response_provenance in {
                ResponseProvenance.PURE_SCENARIO,
                ResponseProvenance.STRUCTURAL_BOUNDED_SCENARIO,
                ResponseProvenance.UNSUPPORTED,
            }:
                formal_status = FormalEstimandStatus.FORMAL_AGGREGATE_UNRESOLVED
                continue
        total = 0.0
        for component, pre in values.items():
            if candidate.template_id == "A00" or not open_:
                value = float(pre)
            else:
                reduction = float(candidate.mitigation.get(component, 0)) * response
                induced = float(candidate.induced.get(component, 0)) + response * float(
                    candidate.induced_response.get(component, 0))
                value = (1 - reduction) * float(pre) + induced
            total += value
        post.append(total)
    if len(post) != len(m1_scenarios):
        mean = var = cvar = risk = None
        if lane == "FORMAL":
            lane = "SCENARIO"
    else:
        mean = weighted_mean(post, weights)
        var, cvar = weighted_var_cvar(post, weights, alpha)
        risk = (1 - lambda_risk) * mean + lambda_risk * cvar
    scope = m2_consequences[0].consequence_scope
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
        valuation_registry_id=scope.valuation_registry_id,
        formal_aggregate_status=formal_status,
        expected_residual=mean,
        var=var,
        cvar=cvar,
        residual_risk_j=risk,
        post_totals=tuple(post),
        quality_flags=coverage.quality_flags,
        coverage_explanation=tuple(sorted(set(coverage.coverage_explanation + baseline_gate.explanation))),
    )
