from __future__ import annotations

from model.M3.contracts import ResponseParameterStatus, ResponseProvenance
from model.M4.contracts import M4DecisionRequest
from model.M4.coverage import (
    A00BaselineComparatorGate,
    MaterialCoverageEvaluation,
    evaluate_a00_baseline_gate,
    evaluate_material_coverage,
)
from model.M4.lanes import assign_lane
from model.M4.response import response_value
from model.M4.risk import weighted_mean, weighted_var_cvar
from model.common.errors import ContractError
from model.common.estimand import FormalEstimandStatus
from model.common.value_objects import FrozenModel


class ActionEvaluation(FrozenModel):
    candidate_action_id: str
    template_id: str
    action_index: int
    candidate_index: int
    lane: str
    opportunity_probability: float
    estimand_id: str
    estimand_version: str
    scope_hash: str
    valuation_registry_id: str
    formal_aggregate_status: FormalEstimandStatus
    expected_residual: float | None
    var: float | None
    cvar: float | None
    residual_risk_j: float | None
    post_totals: tuple[float, ...]
    quality_flags: tuple[str, ...]
    coverage_explanation: tuple[str, ...]
    ranking_position: int | None = None


class EpisodeDecision(FrozenModel):
    episode_id: str
    actions: tuple[ActionEvaluation, ...]
    decision_outcome: str
    authoritative_decision_available: bool
    authoritative_ranking: tuple[str, ...]
    ranking_at_1: str | None
    ranking_at_2: tuple[str, ...] | None
    ranking_at_3: tuple[str, ...] | None
    ranking_at_5: tuple[str, ...] | None


def _opportunities(candidate, m1_scenarios):
    if candidate.precondition_state == "FALSE":
        return [0.0 for _ in m1_scenarios]
    if candidate.template_id == "A00":
        return [1.0 for _ in m1_scenarios]
    scalar = candidate.parameters.get("deadline_minutes")
    by_scenario = candidate.parameters.get("deadline_minutes_by_scenario", {})
    deadlines = [
        scenario.get(
            "deadline_minutes",
            by_scenario.get(
                str(scenario["scenario_id"]),
                by_scenario.get(scenario["scenario_id"], scalar),
            ),
        )
        for scenario in m1_scenarios
    ]
    if candidate.precondition_state == "UNKNOWN" and any(
        value is None for value in deadlines
    ):
        return [1.0 for _ in m1_scenarios]
    if any(value is None for value in deadlines):
        raise ContractError("ACTION_DEADLINE_UNRESOLVED")
    return [
        1.0 if float(value) > candidate.preparation_time_minutes else 0.0
        for value in deadlines
    ]


def _compatible_formal_ranking(evaluations):
    formal = [item for item in evaluations if item.lane == "FORMAL"]
    identities = {
        (
            item.estimand_id,
            item.estimand_version,
            item.scope_hash,
            item.valuation_registry_id,
        )
        for item in formal
    }
    if len(identities) > 1:
        raise ContractError("FORMAL_RANKING_ESTIMAND_SCOPE_MISMATCH")
    if any(
        item.formal_aggregate_status is not FormalEstimandStatus.FORMAL_AVAILABLE
        or item.residual_risk_j is None
        for item in formal
    ):
        raise ContractError("FORMAL_RANKING_AGGREGATE_INVALID")
    return sorted(
        formal,
        key=lambda item: (
            item.residual_risk_j,
            item.action_index,
            item.candidate_index,
            item.candidate_action_id,
        ),
    )


def evaluate_decision(
    episode_id,
    m1_scenarios,
    m2_consequences,
    candidates,
    *,
    material_coverage_contract,
    lambda_risk=0.25,
    alpha=0.9,
    seed=0,
):
    by_s = {row.scenario_id: row for row in m2_consequences}
    weights = [float(scenario["scenario_weight"]) for scenario in m1_scenarios]
    baseline_gates = tuple(
        evaluate_a00_baseline_gate(
            consequence.component_vector.rows, material_coverage_contract
        )
        for consequence in m2_consequences
    )
    baseline_gate = A00BaselineComparatorGate(
        valid=all(item.valid for item in baseline_gates),
        missing_components=tuple(
            sorted(
                {
                    component
                    for item in baseline_gates
                    for component in item.missing_components
                }
            )
        ),
        explanation=tuple(
            sorted(
                {
                    explanation
                    for item in baseline_gates
                    for explanation in item.explanation
                }
            )
        ),
    )
    evaluations = []
    for candidate in candidates:
        opportunities = _opportunities(candidate, m1_scenarios)
        opportunity = weighted_mean(opportunities, weights)
        scenario_coverages = tuple(
            evaluate_material_coverage(
                candidate,
                consequence.component_vector.rows,
                material_coverage_contract,
            )
            for consequence in m2_consequences
        )
        coverage = MaterialCoverageEvaluation(
            candidate_action_id=candidate.candidate_action_id,
            material_benefit_coverage=all(
                item.material_benefit_coverage for item in scenario_coverages
            ),
            material_burden_coverage=all(
                item.material_burden_coverage for item in scenario_coverages
            ),
            baseline_coverage=all(
                item.baseline_coverage for item in scenario_coverages
            ),
            nonmaterial_missingness=tuple(
                sorted(
                    {
                        component
                        for item in scenario_coverages
                        for component in item.nonmaterial_missingness
                    }
                )
            ),
            coverage_explanation=tuple(
                sorted(
                    {
                        explanation
                        for item in scenario_coverages
                        for explanation in item.coverage_explanation
                    }
                )
            ),
            quality_flags=tuple(
                sorted(
                    {
                        flag
                        for item in scenario_coverages
                        for flag in item.quality_flags
                    }
                )
            ),
        )
        lane = assign_lane(
            candidate,
            opportunity,
            baseline_valid=baseline_gate.valid,
            material_coverage_valid=coverage.formal_coverage_valid,
        )
        formal_status = FormalEstimandStatus.FORMAL_AVAILABLE
        post = []
        for scenario, open_ in zip(m1_scenarios, opportunities):
            consequence = by_s[scenario["scenario_id"]]
            formal = consequence.formal_estimand_value
            if formal.status is not FormalEstimandStatus.FORMAL_AVAILABLE:
                formal_status = formal.status
                continue
            values = {
                row.component_id: row.constructed_value_cu
                for row in consequence.component_vector.rows
                if row.component_id in formal.included_components
            }
            if any(value is None for value in values.values()) or len(values) != len(
                formal.included_components
            ):
                formal_status = FormalEstimandStatus.FORMAL_AGGREGATE_UNRESOLVED
                continue
            total = 0.0
            response = 0.0
            if candidate.template_id != "A00" and open_:
                if (
                    candidate.response_parameter_status
                    is ResponseParameterStatus.FROZEN
                ):
                    response = response_value(
                        candidate,
                        seed=seed,
                        episode=episode_id,
                        scenario=scenario["scenario_id"],
                    )
                elif candidate.response_provenance in {
                    ResponseProvenance.PURE_SCENARIO,
                    ResponseProvenance.STRUCTURAL_BOUNDED_SCENARIO,
                    ResponseProvenance.UNSUPPORTED,
                }:
                    formal_status = FormalEstimandStatus.FORMAL_AGGREGATE_UNRESOLVED
                    continue
            for component, pre in values.items():
                if candidate.template_id == "A00" or not open_:
                    value = float(pre)
                else:
                    reduction = float(candidate.mitigation.get(component, 0)) * response
                    induced = float(candidate.induced.get(component, 0)) + response * float(
                        candidate.induced_response.get(component, 0)
                    )
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
        explanations = tuple(
            sorted(set(coverage.coverage_explanation + baseline_gate.explanation))
        )
        evaluations.append(
            ActionEvaluation(
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
                coverage_explanation=explanations,
            )
        )
    if not baseline_gate.valid:
        ranking = ()
        outcome = "AUTHORITATIVE_DECISION_UNAVAILABLE"
        authoritative = False
    else:
        formal = _compatible_formal_ranking(evaluations)
        ranks = {
            item.candidate_action_id: index + 1
            for index, item in enumerate(formal)
        }
        evaluations = [
            item.model_copy(
                update={"ranking_position": ranks.get(item.candidate_action_id)}
            )
            for item in evaluations
        ]
        ranking = tuple(item.candidate_action_id for item in formal)
        a00 = next((item for item in formal if item.template_id == "A00"), None)
        if not formal:
            outcome = "AUTHORITATIVE_DECISION_UNAVAILABLE"
            authoritative = False
        elif len(formal) == 1 and a00:
            outcome = "NO_OTHER_ACTION_CURRENTLY_FORMALLY_COMPARABLE"
            authoritative = True
        elif formal[0].template_id == "A00":
            outcome = "FORMAL_A00_PREFERRED_WITHIN_DECLARED_ESTIMAND"
            authoritative = True
        else:
            outcome = "FORMAL_ACTION_PREFERRED_WITHIN_DECLARED_ESTIMAND"
            authoritative = True
    return EpisodeDecision(
        episode_id=episode_id,
        actions=tuple(evaluations),
        decision_outcome=outcome,
        authoritative_decision_available=authoritative,
        authoritative_ranking=ranking,
        ranking_at_1=ranking[0] if ranking else None,
        ranking_at_2=ranking[:2] if len(ranking) >= 2 else None,
        ranking_at_3=ranking[:3] if len(ranking) >= 3 else None,
        ranking_at_5=ranking[:5] if len(ranking) >= 5 else None,
    )


def evaluate_request(request: M4DecisionRequest) -> EpisodeDecision:
    scenarios = [row.model_dump(mode="json") for row in request.m1_scenarios]
    return evaluate_decision(
        request.pre_state.decision_node.episode_id,
        scenarios,
        request.m2_consequences,
        request.candidates,
        material_coverage_contract=request.material_coverage_contract,
        lambda_risk=request.lambda_risk,
        alpha=request.alpha,
        seed=request.seed,
    )
