"""Current Section 3.6 downstream action-space interface.

The historical 23-action implementation remains available only through
explicit submodule imports such as ``model.M3.legacy_service``.
"""

from .action_interface import M2PostActionConsequenceAdapter, a00_baseline_action
from .interface_contracts import (
    ActionInterfaceRequest,
    CandidateActionProvider,
    CandidateActionRef,
    CandidateActionSet,
    CandidateActionSetState,
    MaterializationState,
    PostActionConsequence,
    PostActionConsequenceProvider,
    PostActionState,
    ResourceContext,
    ResourceContextState,
    StateTransitionProvider,
)
from .service import M3Service

__all__ = [
    "ActionInterfaceRequest",
    "CandidateActionProvider",
    "CandidateActionRef",
    "CandidateActionSet",
    "CandidateActionSetState",
    "M2PostActionConsequenceAdapter",
    "M3Service",
    "MaterializationState",
    "PostActionConsequence",
    "PostActionConsequenceProvider",
    "PostActionState",
    "ResourceContext",
    "ResourceContextState",
    "StateTransitionProvider",
    "a00_baseline_action",
]
