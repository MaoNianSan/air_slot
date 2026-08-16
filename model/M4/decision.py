"""Public M4 decision orchestration facade."""

from __future__ import annotations

from model.M4.contracts import M4DecisionRequest
from model.M4.post_action import aggregate_a00_baseline_gate, evaluate_candidate
from model.M4.ranking import compatible_formal_ranking, finalize_ranking
from model.M4.results import ActionEvaluation, EpisodeDecision


_compatible_formal_ranking = compatible_formal_ranking


def evaluate_decision(episode_id, m1_scenarios, m2_consequences, candidates, *,
                      material_coverage_contract, lambda_risk=0.25, alpha=0.9, seed=0):
    baseline_gate = aggregate_a00_baseline_gate(m2_consequences, material_coverage_contract)
    evaluations = tuple(evaluate_candidate(
        candidate,
        episode_id=episode_id,
        m1_scenarios=m1_scenarios,
        m2_consequences=m2_consequences,
        material_coverage_contract=material_coverage_contract,
        baseline_gate=baseline_gate,
        lambda_risk=lambda_risk,
        alpha=alpha,
        seed=seed,
    ) for candidate in candidates)
    actions, ranking, outcome, authoritative = finalize_ranking(
        evaluations, baseline_valid=baseline_gate.valid)
    return EpisodeDecision(
        episode_id=episode_id,
        actions=actions,
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


__all__ = [
    "ActionEvaluation",
    "EpisodeDecision",
    "evaluate_decision",
    "evaluate_request",
]
