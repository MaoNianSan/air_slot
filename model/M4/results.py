from __future__ import annotations

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
