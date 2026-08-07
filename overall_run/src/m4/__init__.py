from __future__ import annotations

from ..failures import M4ContractMismatch
from .compatibility import formal_m2_blockers, validate_m2_inputs, validate_m3_artifact
from .contracts import *  # noqa: F401,F403
from .draw_pairing import response_draw_index
from .evaluation import evaluate_frozen_artifact, run_optional_evaluation
from .evidence import REQUIRED_EVIDENCE_BY_ACTION, build_evidence_context
from .input_adapter import adapt_m4_inputs
from .lane_assignment import assign_decision_lane
from .opportunity import OpportunityResult, evaluate_opportunity
from .output import episode_decisions_frame, write_formal_artifact
from .pipeline import run_m4, run_m4_formal_stage, run_m4_synthetic_integration
from .post_loss import PostLossSamples, calculate_post_loss
from .ranking import action_evaluations_frame, build_authoritative_ranking
from .risk import (
    normalize_weights,
    risk_score,
    validate_risk_config,
    weighted_cvar,
    weighted_mean,
    weighted_positive_probability,
    weighted_var,
)
from .rolling import compare_rolling_rankings
from .stage_adapter import StageCompatibility, evaluate_stage


def _legacy_retired(*args: object, **kwargs: object):
    del args, kwargs
    raise M4ContractMismatch(
        "M4_LEGACY_CONTRACT_RETIRED: use M2InputBundle, M2SampleLoss, and M3Artifact"
    )


fit_m4 = _legacy_retired
evaluate_m4 = _legacy_retired
screen_physical_actions = _legacy_retired


__all__ = [
    "OpportunityResult",
    "PostLossSamples",
    "REQUIRED_EVIDENCE_BY_ACTION",
    "StageCompatibility",
    "action_evaluations_frame",
    "adapt_m4_inputs",
    "assign_decision_lane",
    "build_authoritative_ranking",
    "build_evidence_context",
    "calculate_post_loss",
    "compare_rolling_rankings",
    "episode_decisions_frame",
    "evaluate_frozen_artifact",
    "evaluate_m4",
    "evaluate_opportunity",
    "evaluate_stage",
    "fit_m4",
    "formal_m2_blockers",
    "normalize_weights",
    "response_draw_index",
    "risk_score",
    "run_m4",
    "run_m4_formal_stage",
    "run_m4_synthetic_integration",
    "run_optional_evaluation",
    "screen_physical_actions",
    "validate_m2_inputs",
    "validate_m3_artifact",
    "validate_risk_config",
    "weighted_cvar",
    "weighted_mean",
    "weighted_positive_probability",
    "weighted_var",
    "write_formal_artifact",
]
