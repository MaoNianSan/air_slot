from __future__ import annotations

from model.M2.contracts import M2ScientificContext
from model.M2.service import M2Service
from model.common.errors import ContractError

from .interface_contracts import (
    ActionInterfaceRequest,
    CandidateActionRef,
    CandidateActionSet,
    CandidateActionSetState,
    MaterializationState,
    PostActionConsequence,
    PostActionState,
    ResourceContextState,
)


class M2PostActionConsequenceAdapter:
    """Delegate post-action consequence mapping to the existing M2 service."""

    provider_id = "M2_POST_ACTION_CONSEQUENCE_ADAPTER"
    provider_version = "1.0.0"

    def __init__(self, m2_service: M2Service):
        self.m2_service = m2_service

    def evaluate_post_action(self, state: PostActionState, context: M2ScientificContext):
        if state.state is not MaterializationState.MATERIALIZED:
            return PostActionConsequence(
                request_digest=state.request_digest,
                node=state.node,
                action_id=state.action_id,
                state=state.state,
                provider_id=self.provider_id,
                provider_version=self.provider_version,
                reason_codes=state.reason_codes,
            )
        consequences = tuple(self.m2_service.map_scenarios(state.scenarios, context))
        return PostActionConsequence(
            request_digest=state.request_digest,
            node=state.node,
            action_id=state.action_id,
            state=MaterializationState.MATERIALIZED,
            consequences=consequences,
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            evidence_class="M2_DELEGATED_CONSEQUENCE_MAPPING",
            provenance=("M2Service.map_scenarios", "action_conditioned_lineage_preserved"),
        )


def a00_baseline_action(node) -> CandidateActionRef:
    return CandidateActionRef(
        action_id="A00",
        action_family="null",
        provider_id="M3_IDENTITY_BASELINE",
        provenance=("A00_NO_ADDITIONAL_RECOVERY_ACTION",),
        eligibility_lineage=(node.decision_node_id,),
    )


__all__ = ["M2PostActionConsequenceAdapter", "a00_baseline_action"]
