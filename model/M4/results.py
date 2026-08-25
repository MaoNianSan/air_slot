from __future__ import annotations

from pydantic import model_validator

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
    cu_normalization_registry_id: str
    monetary_system: str
    monetary_mapping_registry_id: str
    monetary_mapping_registry_hash: str
    formal_aggregate_status: FormalEstimandStatus
    expected_residual: float | None
    var: float | None
    cvar: float | None
    residual_risk_j: float | None
    post_totals: tuple[float, ...]
    scenario_conditioned: bool = False
    post_total_status: str = "NOT_COMPUTED"
    interpretation_class: str = "NOT_DECLARED"
    quality_flags: tuple[str, ...]
    coverage_explanation: tuple[str, ...]
    ranking_position: int | None = None

    @model_validator(mode="after")
    def post_total_label_contract(self):
        if self.post_total_status not in {
            "FORMAL_ESTIMAND",
            "SCENARIO_CONDITIONED",
            "NOT_COMPUTED",
        }:
            raise ValueError("UNKNOWN_POST_TOTAL_STATUS")
        if self.scenario_conditioned and self.post_total_status == "FORMAL_ESTIMAND":
            raise ValueError("SCENARIO_CONDITIONED_MISLABELED_FORMAL")
        if not self.monetary_system or not self.monetary_mapping_registry_id:
            raise ValueError("MONETARY_MAPPING_LINEAGE_REQUIRED")
        return self


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
