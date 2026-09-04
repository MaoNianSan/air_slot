"""M4 V2 monetary interpretation and residual-risk aggregation."""

from .m3_action_interface import ConsequenceComparisonScope, M4ActionEnvelopeInput
from .residual_risk import (
    ResidualRiskPolicy,
    RiskEvaluationEnvelope,
    RiskRankingEnvelope,
    NumericalEvaluationState,
    SelectionState,
    evaluate_residual_risk,
    load_active_risk_policy,
    rank_risk_evaluations,
)
from .service import M4Service

RiskEvaluation = RiskEvaluationEnvelope

__all__ = [
    "M4ActionEnvelopeInput",
    "ConsequenceComparisonScope",
    "ResidualRiskPolicy",
    "RiskEvaluationEnvelope",
    "RiskEvaluation",
    "RiskRankingEnvelope",
    "NumericalEvaluationState",
    "SelectionState",
    "evaluate_residual_risk",
    "load_active_risk_policy",
    "rank_risk_evaluations",
    "M4Service",
]
