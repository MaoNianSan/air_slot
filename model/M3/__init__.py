"""M3 action-template instantiation."""

from .contracts import (
    ActionInstantiationRecord,
    ActionMaterialCoverageContract,
    CandidateAction,
    FootprintRole,
    InstantiationState,
    ResponseParameterStatus,
    ResponseProvenance,
)
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
from .instantiation_layer.builder import (
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
from .registry_layer.actions import ActionRegistry
from .readiness import (
    ActionNumericalReadiness,
    NumericalParameterState,
    build_action_numerical_readiness,
    readiness_for_template,
    readiness_for_action,
)
from .service import M3Service

ActionEnvelope = ActionEvaluationEnvelope

__all__ = [
    "ActionMaterialCoverageContract",
    "ActionInstantiationRecord",
    "ActionInstantiationEvaluation",
    "ActionEligibility",
    "ActionEvaluationEnvelope",
    "ActionEnvelope",
    "ActionResponseRule",
    "ActionResponseType",
    "ActionConditionedCUQuantity",
    "ActionRegistry",
    "ActionNumericalReadiness",
    "CandidateAction",
    "FootprintRole",
    "InstantiationState",
    "NumericalParameterState",
    "EligibilityState",
    "M3ActionConditionedConsequence",
    "M3BaselineConsequenceInput",
    "M3BaselineCUQuantity",
    "M3Service",
    "ResponseParameter",
    "ResponseParameterStatus",
    "ResponseProvenance",
    "ResponseSourceType",
    "ResponseSupportClass",
    "build_a00_identity_envelope",
    "build_conditional_scenario_envelope",
    "evaluate_action_instantiation",
    "instantiate_action_records",
    "instantiate_candidates",
    "build_action_numerical_readiness",
    "readiness_for_action",
    "readiness_for_template",
]
