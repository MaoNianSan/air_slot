"""M3 action-template instantiation."""

from .contracts import ActionInstantiationRecord, ActionMaterialCoverageContract, CandidateAction, InstantiationState
from .action_response import (
    ActionEligibility,
    ActionEvaluationEnvelope,
    ActionResponseRule,
    ActionResponseType,
    EligibilityState,
    ResponseParameter,
    ResponseSourceType,
    ResponseSupportClass,
    build_a00_identity_envelope,
    build_conditional_scenario_envelope,
)
from .instantiate import (
    ActionInstantiationEvaluation,
    evaluate_action_instantiation,
    instantiate_action_records,
    instantiate_candidates,
)
from .m2_action_interface import (
    ActionConditionedCUQuantity,
    M3ActionConditionedConsequence,
    M3BaselineConsequenceInput,
    M3BaselineCUQuantity,
)
from .registry import ActionRegistry

__all__ = [
    "ActionMaterialCoverageContract",
    "ActionInstantiationRecord",
    "ActionInstantiationEvaluation",
    "ActionEligibility",
    "ActionEvaluationEnvelope",
    "ActionResponseRule",
    "ActionResponseType",
    "ActionConditionedCUQuantity",
    "ActionRegistry",
    "CandidateAction",
    "InstantiationState",
    "EligibilityState",
    "M3ActionConditionedConsequence",
    "M3BaselineConsequenceInput",
    "M3BaselineCUQuantity",
    "ResponseParameter",
    "ResponseSourceType",
    "ResponseSupportClass",
    "build_a00_identity_envelope",
    "build_conditional_scenario_envelope",
    "evaluate_action_instantiation",
    "instantiate_action_records",
    "instantiate_candidates",
]
