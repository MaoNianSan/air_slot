"""Frozen scientific contracts for shared recovery-priority scores."""

from __future__ import annotations

from math import isfinite
from typing import Literal

from pydantic import Field, computed_field, model_validator

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id
from model.common.value_objects import FrozenModel

PRIORITY_CONTRACT_VERSION = "AIR_SLOT_SHARED_PRIORITY_CONTRACT_V1_20260906"
PRIORITY_CONTRACT_PAYLOAD = {
    "version": PRIORITY_CONTRACT_VERSION,
    "authority": "HUMAN_APPROVED",
    "status": "FROZEN_FOR_EXP2_EXP3_EXP4",
    "components": CONSEQUENCE_COMPONENTS,
    "delay": "sum(scenario_weight * authoritative_d_to_minutes)",
    "component_summary": "sum(scenario_weight * authoritative_component_value)",
    "flight": "mean(F_continuity,F_execution,F_propagation)",
    "passenger": "mean(P_time,P_itinerary,P_service)",
    "operating": "R_operating",
    "aggregate": "mean(score_F,score_P,score_R)",
    "no_f_execution": "mean(mean(F_continuity,F_propagation),score_P,score_R)",
    "equal_component": "mean(all_seven_CU_components)",
    "support": "FAIL_CLOSED_NO_DROP_NO_RENORMALIZATION_NO_ZERO_FILL",
    "ranking": "EXPERIMENT_SPECIFIC_NOT_SHARED",
}
PRIORITY_CONTRACT_HASH = content_id(PRIORITY_CONTRACT_PAYLOAD)

# Interface identity is descriptive only and cannot replace the scientific contract.
PRIORITY_INTERFACE_VERSION = "AIR_SLOT_SHARED_PRIORITY_INTERFACE_V1_20260906"
PRIORITY_INTERFACE_PAYLOAD = {
    "version": PRIORITY_INTERFACE_VERSION,
    "scientific_contract_version": PRIORITY_CONTRACT_VERSION,
    "scientific_contract_hash": PRIORITY_CONTRACT_HASH,
    "namespace": "exp.shared",
}
PRIORITY_INTERFACE_HASH = content_id(PRIORITY_INTERFACE_PAYLOAD)

ScientificContractStatus = Literal["FROZEN_FOR_EXP2_EXP3_EXP4"]
ArtifactStage = Literal["DEVELOPMENT_ONLY_PHASE0_VALIDATION"]
SupportState = Literal["SUPPORTED", "UNSUPPORTED"]


class SharedPriorityAuthority(FrozenModel):
    version: Literal["AIR_SLOT_SHARED_PRIORITY_CONTRACT_V1_20260906"] = (
        PRIORITY_CONTRACT_VERSION
    )
    contract_hash: str = Field(
        default=PRIORITY_CONTRACT_HASH, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    authority: Literal["HUMAN_APPROVED"] = "HUMAN_APPROVED"
    status: ScientificContractStatus = "FROZEN_FOR_EXP2_EXP3_EXP4"
    interface_version: Literal["AIR_SLOT_SHARED_PRIORITY_INTERFACE_V1_20260906"] = (
        PRIORITY_INTERFACE_VERSION
    )
    final_test_authorized: Literal[False] = False
    paper_result: Literal[False] = False

    @model_validator(mode="after")
    def exact_authority(self):
        if self.contract_hash != PRIORITY_CONTRACT_HASH:
            raise ValueError("PRIORITY_CONTRACT_HASH_MISMATCH")
        return self


SHARED_PRIORITY_AUTHORITY = SharedPriorityAuthority()


class SupportedScore(FrozenModel):
    value: float | None
    support: SupportState
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def explicit_support(self):
        if self.support == "SUPPORTED":
            if self.value is None or not isfinite(self.value) or self.value < 0:
                raise ValueError(
                    "PRIORITY_SUPPORTED_SCORE_REQUIRES_FINITE_NONNEGATIVE_VALUE"
                )
            if self.reason_codes:
                raise ValueError("PRIORITY_SUPPORTED_SCORE_CANNOT_HAVE_REASONS")
        elif self.value is not None or not self.reason_codes:
            raise ValueError("PRIORITY_UNSUPPORTED_SCORE_REQUIRES_NULL_AND_REASON")
        return self


class ComponentSupportRecord(FrozenModel):
    component_id: str
    support: SupportState
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def explicit_reason(self):
        if self.support == "SUPPORTED" and self.reason_codes:
            raise ValueError("PRIORITY_SUPPORTED_COMPONENT_CANNOT_HAVE_REASONS")
        if self.support == "UNSUPPORTED" and not self.reason_codes:
            raise ValueError("PRIORITY_UNSUPPORTED_COMPONENT_REQUIRES_REASON")
        return self


class NamedSupportRecord(FrozenModel):
    object_id: str
    support: SupportState
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def explicit_reason(self):
        if self.support == "SUPPORTED" and self.reason_codes:
            raise ValueError("PRIORITY_SUPPORTED_OBJECT_CANNOT_HAVE_REASONS")
        if self.support == "UNSUPPORTED" and not self.reason_codes:
            raise ValueError("PRIORITY_UNSUPPORTED_OBJECT_REQUIRES_REASON")
        return self


class RecoveryPriorityScoreRecord(FrozenModel):
    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    decision_time: str | None = None
    operational_stage: str | None = None
    delay_score: float | None

    native_F_continuity: float | None
    native_F_execution: float | None
    native_F_propagation: float | None
    native_P_time: float | None
    native_P_itinerary: float | None
    native_P_service: float | None
    native_R_operating: float | None

    cu_F_continuity: float | None
    cu_F_execution: float | None
    cu_F_propagation: float | None
    cu_P_time: float | None
    cu_P_itinerary: float | None
    cu_P_service: float | None
    cu_R_operating: float | None

    score_F: float | None
    score_P: float | None
    score_R: float | None
    score_C: float | None
    score_C_no_F_execution: float | None
    score_equal_component: float | None

    delay_support: SupportState
    native_component_support: tuple[ComponentSupportRecord, ...]
    cu_component_support: tuple[ComponentSupportRecord, ...]
    domain_support: tuple[NamedSupportRecord, ...]
    aggregate_support: tuple[NamedSupportRecord, ...]
    reason_codes: tuple[str, ...]

    repository_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    m1_lineage: tuple[str, ...] = Field(min_length=1)
    m2_scope_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    m2_registry_id: str = Field(min_length=1)
    m2_registry_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    m2_cu_normalization_registry_hash: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$"
    )
    priority_contract_version: Literal[
        "AIR_SLOT_SHARED_PRIORITY_CONTRACT_V1_20260906"
    ] = PRIORITY_CONTRACT_VERSION
    priority_contract_hash: str = Field(
        default=PRIORITY_CONTRACT_HASH, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    priority_interface_version: Literal[
        "AIR_SLOT_SHARED_PRIORITY_INTERFACE_V1_20260906"
    ] = PRIORITY_INTERFACE_VERSION
    priority_interface_hash: str = Field(
        default=PRIORITY_INTERFACE_HASH, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    scientific_contract_authority: Literal["HUMAN_APPROVED"] = "HUMAN_APPROVED"
    scientific_contract_status: ScientificContractStatus = (
        "FROZEN_FOR_EXP2_EXP3_EXP4"
    )
    artifact_stage: ArtifactStage = "DEVELOPMENT_ONLY_PHASE0_VALIDATION"
    final_test_authorized: Literal[False] = False
    paper_result: Literal[False] = False

    object_type: Literal["RESEARCH_PRIORITY_SCORE"] = "RESEARCH_PRIORITY_SCORE"
    model_object: Literal[False] = False
    ground_truth: Literal[False] = False
    optimal_priority: Literal[False] = False

    @model_validator(mode="after")
    def exact_component_support(self):
        expected = tuple(CONSEQUENCE_COMPONENTS)
        if tuple(item.component_id for item in self.native_component_support) != expected:
            raise ValueError("PRIORITY_NATIVE_SUPPORT_REQUIRES_EXACT_ONTOLOGY")
        if tuple(item.component_id for item in self.cu_component_support) != expected:
            raise ValueError("PRIORITY_CU_SUPPORT_REQUIRES_EXACT_ONTOLOGY")
        if self.priority_contract_hash != PRIORITY_CONTRACT_HASH:
            raise ValueError("PRIORITY_CONTRACT_HASH_MISMATCH")
        if self.priority_interface_hash != PRIORITY_INTERFACE_HASH:
            raise ValueError("PRIORITY_INTERFACE_HASH_MISMATCH")
        return self

    @computed_field
    @property
    def artifact_id(self) -> str:
        return content_id(self.model_dump(mode="json", exclude_computed_fields=True))


__all__ = [
    "ArtifactStage",
    "ComponentSupportRecord",
    "NamedSupportRecord",
    "PRIORITY_CONTRACT_HASH",
    "PRIORITY_CONTRACT_PAYLOAD",
    "PRIORITY_CONTRACT_VERSION",
    "PRIORITY_INTERFACE_HASH",
    "PRIORITY_INTERFACE_PAYLOAD",
    "PRIORITY_INTERFACE_VERSION",
    "RecoveryPriorityScoreRecord",
    "SHARED_PRIORITY_AUTHORITY",
    "ScientificContractStatus",
    "SharedPriorityAuthority",
    "SupportedScore",
]
