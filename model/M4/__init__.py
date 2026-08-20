"""M4 V2 monetary interpretation and residual-risk aggregation."""

from .m3_action_interface import M4ActionEnvelopeInput
from .residual_risk import (
    ResidualRiskPolicy,
    RiskEvaluationEnvelope,
    RiskRankingEnvelope,
    evaluate_residual_risk,
    rank_risk_evaluations,
)

__all__ = [
    "M4ActionEnvelopeInput",
    "ResidualRiskPolicy",
    "RiskEvaluationEnvelope",
    "RiskRankingEnvelope",
    "evaluate_residual_risk",
    "rank_risk_evaluations",
]


def __getattr__(name):
    """Lazy compatibility access for pre-V2 callers; not part of V2 `__all__`."""
    if name == "M4DecisionRequest":
        from .contracts import M4DecisionRequest

        return M4DecisionRequest
    if name in {"EpisodeDecision", "evaluate_decision", "evaluate_request"}:
        from .decision import EpisodeDecision, evaluate_decision, evaluate_request

        return {
            "EpisodeDecision": EpisodeDecision,
            "evaluate_decision": evaluate_decision,
            "evaluate_request": evaluate_request,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
