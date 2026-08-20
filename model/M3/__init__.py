"""M3 action-template instantiation."""

from .contracts import ActionMaterialCoverageContract, CandidateAction
from .instantiate import instantiate_candidates
from .m2_action_interface import (
    ActionConditionedCUQuantity,
    M3ActionConditionedConsequence,
    M3BaselineConsequenceInput,
)
from .registry import ActionRegistry

__all__ = [
    "ActionMaterialCoverageContract",
    "ActionConditionedCUQuantity",
    "ActionRegistry",
    "CandidateAction",
    "M3ActionConditionedConsequence",
    "M3BaselineConsequenceInput",
    "instantiate_candidates",
]
