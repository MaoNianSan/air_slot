from __future__ import annotations

from enum import Enum
from hashlib import sha256
import json
from typing import Any

from pydantic import Field, field_validator, model_validator

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import EvidenceClass, SupportState
from model.common.value_objects import FrozenModel


ACTION_FAMILIES = {
    "null",
    "timing_passenger_coordination",
    "flight_execution",
    "timing",
    "capacity_coordination",
    "passenger_recovery",
    "passenger_service",
    "ground_recovery",
    "aircraft_recovery",
    "crew_recovery",
    "extreme_local_network",
}
RESPONSE_MODELS = {
    "DETERMINISTIC",
    "BERNOULLI_BETA",
    "DISCRETE_SCENARIO",
    "EMPIRICAL",
}


class ResponseProvenance(str, Enum):
    EMPIRICAL_ACTION_LOG = "EMPIRICAL_ACTION_LOG"
    OPERATOR_INDUSTRY = "OPERATOR_INDUSTRY"
    STRUCTURAL_BOUNDED_SCENARIO = "STRUCTURAL_BOUNDED_SCENARIO"
    PURE_SCENARIO = "PURE_SCENARIO"
    UNSUPPORTED = "UNSUPPORTED"


class ResponseParameterStatus(str, Enum):
    FROZEN = "FROZEN"
    NOT_FROZEN = "NOT_FROZEN"
    NOT_REQUIRED = "NOT_REQUIRED"


class MechanismRole(str, Enum):
    PRINCIPAL_BENEFIT = "PRINCIPAL_BENEFIT"
    PRINCIPAL_BURDEN = "PRINCIPAL_BURDEN"
    BASELINE_COMPARATOR = "BASELINE_COMPARATOR"
    NONMATERIAL_CONTEXT = "NONMATERIAL_CONTEXT"


class MaterialCriticality(str, Enum):
    MATERIAL_REQUIRED = "MATERIAL_REQUIRED"
    MATERIAL_DEGRADABLE = "MATERIAL_DEGRADABLE"
    NONMATERIAL = "NONMATERIAL"


class CoverageRequirement(str, Enum):
    VALUED_COMPONENT = "VALUED_COMPONENT"
    NATIVE_QUANTITY = "NATIVE_QUANTITY"
    SUPPORT_ONLY = "SUPPORT_ONLY"


class BenefitOrBurden(str, Enum):
    BENEFIT = "BENEFIT"
    BURDEN = "BURDEN"
    BASELINE = "BASELINE"
    CONTEXT = "CONTEXT"


class ActionTemplate(FrozenModel):
    template_id: str
    name: str
    family: str
    required_facts: tuple[str, ...] = ()
    required_parameters: tuple[str, ...] = ()
    authority_capabilities: tuple[str, ...] = ()
    mitigation: dict[str, float] = {}
    induced: dict[str, float] = {}
    induced_response: dict[str, float] = {}
    response_model: str = "BERNOULLI_BETA"
    response_parameters: dict[str, Any] = {}
    response_provenance: ResponseProvenance = ResponseProvenance.PURE_SCENARIO
    response_parameter_status: ResponseParameterStatus = ResponseParameterStatus.NOT_FROZEN
    coverage: str = "PARTIAL"
    preparation_time_minutes: float = Field(default=0, ge=0)
    deadline_semantics: str = "scenario_deadline"

    @field_validator("template_id")
    @classmethod
    def action_id(cls, value):
        if len(value) != 3 or value[0] != "A" or not value[1:].isdigit():
            raise ValueError("INVALID_ACTION_ID")
        return value

    @model_validator(mode="after")
    def strict_contract(self):
        unknown = (
            set(self.mitigation) | set(self.induced) | set(self.induced_response)
        ) - set(CONSEQUENCE_COMPONENTS)
        if unknown:
            raise ValueError(f"UNKNOWN_M2_CONSEQUENCE_COMPONENT:{sorted(unknown)}")
        if self.family not in ACTION_FAMILIES:
            raise ValueError("UNKNOWN_ACTION_FAMILY")
        if self.response_model not in RESPONSE_MODELS:
            raise ValueError("UNKNOWN_RESPONSE_MODEL")
        if self.coverage not in {"FULL", "HIGH", "PARTIAL", "INSUFFICIENT"}:
            raise ValueError("UNKNOWN_COVERAGE")
        if len(set(self.required_parameters)) != len(self.required_parameters):
            raise ValueError("DUPLICATE_REQUIRED_PARAMETER")
        if not self.deadline_semantics:
            raise ValueError("DEADLINE_SEMANTICS_REQUIRED")
        if self.template_id == "A00":
            if self.response_parameter_status is not ResponseParameterStatus.NOT_REQUIRED:
                raise ValueError("A00_RESPONSE_PARAMETERS_NOT_REQUIRED")
        elif (
            self.response_parameter_status is ResponseParameterStatus.FROZEN
            and not self.response_parameters
        ):
            raise ValueError("FROZEN_RESPONSE_PARAMETERS_REQUIRED")
        return self


class CandidateAction(FrozenModel):
    candidate_action_id: str
    template_id: str
    action_family: str
    action_index: int = Field(ge=0)
    candidate_index: int = Field(ge=0)
    parameters: dict[str, Any]
    precondition_state: str
    authority_capabilities: tuple[str, ...]
    mitigation: dict[str, float]
    induced: dict[str, float]
    induced_response: dict[str, float] = {}
    response_model: str
    response_parameters: dict[str, Any]
    response_provenance: ResponseProvenance
    response_parameter_status: ResponseParameterStatus
    coverage: str
    preparation_time_minutes: float
    deadline_semantics: str

    @model_validator(mode="after")
    def typed_boundaries(self):
        if self.precondition_state not in {"TRUE", "FALSE", "UNKNOWN"}:
            raise ValueError("UNKNOWN_PRECONDITION_STATE")
        if self.template_id != "A00" and (
            self.response_parameter_status is ResponseParameterStatus.FROZEN
            and not self.response_parameters
        ):
            raise ValueError("FROZEN_RESPONSE_PARAMETERS_REQUIRED")
        return self


class ActionMaterialCoverageEntry(FrozenModel):
    template_id: str
    component_id: str
    mechanism_role: MechanismRole
    criticality: MaterialCriticality
    coverage_requirement: CoverageRequirement
    benefit_or_burden: BenefitOrBurden
    required_evidence_class: EvidenceClass
    required_support: SupportState
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def semantic_roles(self):
        if self.component_id not in CONSEQUENCE_COMPONENTS:
            raise ValueError("UNKNOWN_CONSEQUENCE_COMPONENT")
        if (
            self.mechanism_role is MechanismRole.NONMATERIAL_CONTEXT
            and self.criticality is not MaterialCriticality.NONMATERIAL
        ):
            raise ValueError("NONMATERIAL_ROLE_REQUIRES_NONMATERIAL_CRITICALITY")
        if (
            self.mechanism_role is MechanismRole.BASELINE_COMPARATOR
            and self.benefit_or_burden is not BenefitOrBurden.BASELINE
        ):
            raise ValueError("BASELINE_ROLE_REQUIRES_BASELINE_CLASS")
        return self


class ActionMaterialCoverageContract(FrozenModel):
    contract_id: str
    contract_version: str
    entries: tuple[ActionMaterialCoverageEntry, ...]
    contract_hash: str

    @classmethod
    def create(
        cls,
        *,
        contract_id: str,
        contract_version: str,
        entries: tuple[ActionMaterialCoverageEntry, ...],
    ) -> "ActionMaterialCoverageContract":
        payload = {
            "contract_id": contract_id,
            "contract_version": contract_version,
            "entries": [item.model_dump(mode="json") for item in entries],
        }
        digest = _coverage_contract_digest(payload)
        return cls(**payload, contract_hash=f"sha256:{digest}")

    @model_validator(mode="after")
    def unique_and_hashed(self):
        keys = tuple(
            (item.template_id, item.component_id, item.mechanism_role)
            for item in self.entries
        )
        if len(keys) != len(set(keys)):
            raise ValueError("DUPLICATE_ACTION_MATERIAL_COVERAGE_ENTRY")
        payload = {
            "contract_id": self.contract_id,
            "contract_version": self.contract_version,
            "entries": [item.model_dump(mode="json") for item in self.entries],
        }
        if self.contract_hash != f"sha256:{_coverage_contract_digest(payload)}":
            raise ValueError("ACTION_MATERIAL_COVERAGE_HASH_MISMATCH")
        return self

    def for_template(self, template_id: str) -> tuple[ActionMaterialCoverageEntry, ...]:
        return tuple(item for item in self.entries if item.template_id == template_id)


def _coverage_contract_digest(payload: dict) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
