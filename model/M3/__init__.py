"""M3 action-template instantiation."""

from .contracts import ActionMaterialCoverageContract, CandidateAction
from .instantiate import instantiate_candidates
from .registry import ActionRegistry

__all__ = [
    "ActionMaterialCoverageContract",
    "ActionRegistry",
    "CandidateAction",
    "instantiate_candidates",
]
