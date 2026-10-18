from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import Field, model_validator
from math import isclose, isfinite

from model.M2.contracts import M2ScenarioInput, M2ScientificContext, ScenarioConsequence
from model.PRE.contracts.pre_state import DecisionNodeRecord
from model.common.identity import content_id
from model.common.value_objects import FrozenModel


class CandidateActionSetState(str, Enum):
    MATERIALIZED = "MATERIALIZED"
    NOT_MATERIALIZED = "NOT_MATERIALIZED"
    UNSUPPORTED = "UNSUPPORTED"


class ResourceContextState(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class MaterializationState(str, Enum):
    MATERIALIZED = "MATERIALIZED"
    NOT_MATERIALIZED = "NOT_MATERIALIZED"
    UNSUPPORTED = "UNSUPPORTED"


class ResourceContext(FrozenModel):
    state: ResourceContextState
    provider_id: str | None = None
    provenance: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @model_validator(mode="after")
    def source_contract(self):
        if self.state is ResourceContextState.AVAILABLE and (
            not self.provider_id or not self.provenance
        ):
            raise ValueError("M3_RESOURCE_PROVENANCE_REQUIRED")
        return self


class ActionInterfaceRequest(FrozenModel):
    node: DecisionNodeRecord
    baseline_scenarios: tuple[M2ScenarioInput, ...] = Field(min_length=1)
    consequence_context: M2ScientificContext
    resource_context: ResourceContext
    request_digest: str = Field(min_length=1)

    @model_validator(mode="after")
    def request_contract(self):
        if any(
            (item.episode_id, item.decision_node_id)
            != (self.node.episode_id, self.node.decision_node_id)
            for item in self.baseline_scenarios
        ):
            raise ValueError("M3_REQUEST_NODE_IDENTITY_MISMATCH")
        scenario_ids = tuple(item.scenario_id for item in self.baseline_scenarios)
        weights = tuple(float(item.scenario_weight) for item in self.baseline_scenarios)
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("M3_BASELINE_SCENARIO_ID_INVALID")
        if any(not isfinite(value) or value <= 0 for value in weights) or not isclose(
            sum(weights), 1.0, rel_tol=1e-9, abs_tol=1e-6
        ):
            raise ValueError("M3_BASELINE_SCENARIO_WEIGHTS_INVALID")
        payload = self.model_dump(mode="json", exclude={"request_digest"})
        if self.request_digest != content_id(payload):
            raise ValueError("M3_REQUEST_DIGEST_MISMATCH")
        return self


class CandidateActionRef(FrozenModel):
    action_id: str = Field(min_length=1)
    action_family: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    provenance: tuple[str, ...] = Field(min_length=1)
    eligibility_lineage: tuple[str, ...] = Field(min_length=1)


class CandidateActionSet(FrozenModel):
    request_digest: str
    node: DecisionNodeRecord
    baseline_action: CandidateActionRef
    candidates: tuple[CandidateActionRef, ...] = ()
    state: CandidateActionSetState
    provider_id: str | None = None
    provenance: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def candidate_contract(self):
        if self.baseline_action.action_id != "A00":
            raise ValueError("M3_BASELINE_ACTION_MUST_BE_A00")
        ids = tuple(item.action_id for item in self.candidates)
        if "A00" in ids or len(ids) != len(set(ids)):
            raise ValueError("M3_CANDIDATE_ACTION_ID_INVALID")
        if self.state is CandidateActionSetState.MATERIALIZED and not self.provenance:
            raise ValueError("M3_PROVIDER_PROVENANCE_MISSING")
        if self.state is CandidateActionSetState.MATERIALIZED and not self.provider_id:
            raise ValueError("M3_PROVIDER_OUTPUT_INVALID")
        if self.state is not CandidateActionSetState.MATERIALIZED and self.candidates:
            raise ValueError("M3_NONMATERIALIZED_CANDIDATES_FORBIDDEN")
        if any(
            item.eligibility_lineage[0] != self.node.decision_node_id
            for item in self.candidates
        ):
            raise ValueError("M3_PROVIDER_OUTPUT_INVALID")
        return self


class PostActionState(FrozenModel):
    request_digest: str
    node: DecisionNodeRecord
    action_id: str
    state: MaterializationState
    scenarios: tuple[M2ScenarioInput, ...] | None = None
    provider_id: str | None = None
    provider_version: str | None = None
    provenance: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def state_contract(self):
        if self.state is MaterializationState.MATERIALIZED:
            if not self.provenance:
                raise ValueError("M3_PROVIDER_PROVENANCE_MISSING")
            if not self.provider_id or not self.provider_version:
                raise ValueError("M3_PROVIDER_OUTPUT_INVALID")
            if not self.scenarios:
                raise ValueError("M3_PROVIDER_OUTPUT_INVALID")
            if any(
                (item.episode_id, item.decision_node_id)
                != (self.node.episode_id, self.node.decision_node_id)
                for item in self.scenarios
            ):
                raise ValueError("M3_PROVIDER_OUTPUT_INVALID")
        elif self.scenarios is not None:
            raise ValueError("M3_NONMATERIALIZED_STATE_PAYLOAD_FORBIDDEN")
        return self


class PostActionConsequence(FrozenModel):
    request_digest: str
    node: DecisionNodeRecord
    action_id: str
    state: MaterializationState
    consequences: tuple[ScenarioConsequence, ...] | None = Field(default=None, min_length=1)
    provider_id: str | None = None
    provider_version: str | None = None
    evidence_class: str | None = None
    provenance: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def consequence_contract(self):
        if self.state is MaterializationState.MATERIALIZED:
            if not self.provenance:
                raise ValueError("M3_PROVIDER_PROVENANCE_MISSING")
            if not self.provider_id or not self.provider_version:
                raise ValueError("M3_PROVIDER_OUTPUT_INVALID")
            if not self.consequences:
                raise ValueError("M3_PROVIDER_OUTPUT_INVALID")
            if any(
                (item.episode_id, item.decision_node_id)
                != (self.node.episode_id, self.node.decision_node_id)
                for item in self.consequences
            ):
                raise ValueError("M3_PROVIDER_OUTPUT_INVALID")
        elif self.consequences is not None:
            raise ValueError("M3_NONMATERIALIZED_CONSEQUENCE_PAYLOAD_FORBIDDEN")
        return self


class CandidateActionProvider(Protocol):
    def candidate_actions(self, request: ActionInterfaceRequest) -> CandidateActionSet: ...


class StateTransitionProvider(Protocol):
    def transition_state(
        self, request: ActionInterfaceRequest, action: CandidateActionRef
    ) -> PostActionState: ...


class PostActionConsequenceProvider(Protocol):
    def evaluate_post_action(
        self, state: PostActionState, context: M2ScientificContext
    ) -> PostActionConsequence: ...


__all__ = [
    "ActionInterfaceRequest",
    "CandidateActionProvider",
    "CandidateActionRef",
    "CandidateActionSet",
    "CandidateActionSetState",
    "MaterializationState",
    "PostActionConsequence",
    "PostActionConsequenceProvider",
    "PostActionState",
    "ResourceContext",
    "ResourceContextState",
    "StateTransitionProvider",
]
