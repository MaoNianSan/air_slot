from __future__ import annotations

from model.common.errors import ContractError

from .action_interface import a00_baseline_action
from .interface_contracts import (
    ActionInterfaceRequest,
    CandidateActionProvider,
    CandidateActionRef,
    CandidateActionSet,
    CandidateActionSetState,
    PostActionConsequence,
    PostActionConsequenceProvider,
    PostActionState,
    ResourceContextState,
    StateTransitionProvider,
    MaterializationState,
)


class M3Service:
    def __init__(
        self,
        *,
        candidate_provider: CandidateActionProvider | None = None,
        transition_provider: StateTransitionProvider | None = None,
        consequence_provider: PostActionConsequenceProvider | None = None,
    ):
        self.candidate_provider = candidate_provider
        self.transition_provider = transition_provider
        self.consequence_provider = consequence_provider

    @staticmethod
    def _validate_request(request: ActionInterfaceRequest) -> None:
        if not isinstance(request, ActionInterfaceRequest):
            raise TypeError("M3_REQUEST_TYPE_INVALID")

    def candidate_actions(self, *, request: ActionInterfaceRequest) -> CandidateActionSet:
        self._validate_request(request)
        baseline = a00_baseline_action(request.node)
        if self.candidate_provider is None:
            return CandidateActionSet(
                request_digest=request.request_digest,
                node=request.node,
                baseline_action=baseline,
                state=CandidateActionSetState.NOT_MATERIALIZED,
                reason_codes=("M3_CANDIDATE_PROVIDER_MISSING",),
            )
        if request.resource_context.state is ResourceContextState.UNKNOWN:
            return CandidateActionSet(
                request_digest=request.request_digest,
                node=request.node,
                baseline_action=baseline,
                state=CandidateActionSetState.NOT_MATERIALIZED,
                reason_codes=("M3_RESOURCE_CONTEXT_UNKNOWN",),
            )
        if request.resource_context.state is ResourceContextState.UNAVAILABLE:
            return CandidateActionSet(
                request_digest=request.request_digest,
                node=request.node,
                baseline_action=baseline,
                state=CandidateActionSetState.UNSUPPORTED,
                reason_codes=("M3_RESOURCE_CONTEXT_UNAVAILABLE",),
            )
        result = self.candidate_provider.candidate_actions(request)
        if not isinstance(result, CandidateActionSet):
            raise ContractError("M3_PROVIDER_OUTPUT_INVALID")
        if result.state is CandidateActionSetState.MATERIALIZED and not result.provenance:
            raise ContractError("M3_PROVIDER_PROVENANCE_MISSING")
        if (
            result.request_digest != request.request_digest
            or (result.node.episode_id, result.node.decision_node_id)
            != (request.node.episode_id, request.node.decision_node_id)
        ):
            raise ContractError("M3_REQUEST_IDENTITY_MISMATCH")
        return result

    def transition_state(
        self,
        *,
        request: ActionInterfaceRequest,
        candidates: CandidateActionSet,
        action_id: str,
    ) -> PostActionState:
        self._validate_request(request)
        if (
            candidates.request_digest != request.request_digest
            or (candidates.node.episode_id, candidates.node.decision_node_id)
            != (request.node.episode_id, request.node.decision_node_id)
        ):
            raise ContractError("M3_REQUEST_IDENTITY_MISMATCH")
        if action_id == "A00":
            return PostActionState(
                request_digest=request.request_digest,
                node=request.node,
                action_id="A00",
                state=MaterializationState.MATERIALIZED,
                scenarios=request.baseline_scenarios,
                provider_id="M3_IDENTITY_BASELINE",
                provider_version="1.0.0",
                provenance=("A00_IDENTITY_STATE_TRANSITION",),
            )
        if candidates.state is not CandidateActionSetState.MATERIALIZED:
            return PostActionState(
                request_digest=request.request_digest,
                node=request.node,
                action_id=action_id,
                state=MaterializationState(candidates.state.value),
                reason_codes=candidates.reason_codes,
            )
        action = next((item for item in candidates.candidates if item.action_id == action_id), None)
        if action is None:
            raise ContractError("M3_ACTION_NOT_IN_CANDIDATE_SET")
        if request.resource_context.state is ResourceContextState.UNKNOWN:
            return PostActionState(
                request_digest=request.request_digest,
                node=request.node,
                action_id=action_id,
                state=MaterializationState.NOT_MATERIALIZED,
                reason_codes=("M3_RESOURCE_CONTEXT_UNKNOWN",),
            )
        if request.resource_context.state is ResourceContextState.UNAVAILABLE:
            return PostActionState(
                request_digest=request.request_digest,
                node=request.node,
                action_id=action_id,
                state=MaterializationState.UNSUPPORTED,
                reason_codes=("M3_RESOURCE_CONTEXT_UNAVAILABLE",),
            )
        if self.transition_provider is None:
            return PostActionState(
                request_digest=request.request_digest,
                node=request.node,
                action_id=action_id,
                state=MaterializationState.NOT_MATERIALIZED,
                reason_codes=("M3_TRANSITION_PROVIDER_MISSING",),
            )
        result = self.transition_provider.transition_state(request, action)
        if not isinstance(result, PostActionState):
            raise ContractError("M3_PROVIDER_OUTPUT_INVALID")
        if result.state is MaterializationState.MATERIALIZED:
            if not result.provenance:
                raise ContractError("M3_PROVIDER_PROVENANCE_MISSING")
            if not result.scenarios:
                raise ContractError("M3_PROVIDER_OUTPUT_INVALID")
            if any(
                (item.episode_id, item.decision_node_id)
                != (request.node.episode_id, request.node.decision_node_id)
                for item in result.scenarios
            ):
                raise ContractError("M3_PROVIDER_OUTPUT_INVALID")
        if (
            result.request_digest != request.request_digest
            or (result.node.episode_id, result.node.decision_node_id)
            != (request.node.episode_id, request.node.decision_node_id)
            or result.action_id != action_id
        ):
            raise ContractError("M3_REQUEST_IDENTITY_MISMATCH")
        return result

    def evaluate_post_action(
        self,
        *,
        request: ActionInterfaceRequest,
        state: PostActionState,
    ) -> PostActionConsequence:
        self._validate_request(request)
        if (
            state.request_digest != request.request_digest
            or (state.node.episode_id, state.node.decision_node_id)
            != (request.node.episode_id, request.node.decision_node_id)
        ):
            raise ContractError("M3_REQUEST_IDENTITY_MISMATCH")
        if state.state is not MaterializationState.MATERIALIZED:
            return PostActionConsequence(
                request_digest=request.request_digest,
                node=request.node,
                action_id=state.action_id,
                state=state.state,
                reason_codes=state.reason_codes,
            )
        if self.consequence_provider is None:
            return PostActionConsequence(
                request_digest=request.request_digest,
                node=request.node,
                action_id=state.action_id,
                state=MaterializationState.NOT_MATERIALIZED,
                reason_codes=("M3_CONSEQUENCE_PROVIDER_MISSING",),
            )
        result = self.consequence_provider.evaluate_post_action(
            state, request.consequence_context
        )
        if not isinstance(result, PostActionConsequence):
            raise ContractError("M3_PROVIDER_OUTPUT_INVALID")
        if result.state is MaterializationState.MATERIALIZED:
            if not result.provenance:
                raise ContractError("M3_PROVIDER_PROVENANCE_MISSING")
            if not result.consequences:
                raise ContractError("M3_PROVIDER_OUTPUT_INVALID")
            if any(
                (item.episode_id, item.decision_node_id)
                != (request.node.episode_id, request.node.decision_node_id)
                for item in result.consequences
            ):
                raise ContractError("M3_PROVIDER_OUTPUT_INVALID")
        if (
            result.request_digest != request.request_digest
            or (result.node.episode_id, result.node.decision_node_id)
            != (request.node.episode_id, request.node.decision_node_id)
            or result.action_id != state.action_id
        ):
            raise ContractError("M3_REQUEST_IDENTITY_MISMATCH")
        return result


__all__ = ["M3Service"]
