from __future__ import annotations

from enum import Enum
from hashlib import sha256
import json
from typing import Any

from pydantic import Field, computed_field, field_validator, model_validator

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
    """Legacy single-label provenance (deprecated for new Pi_a contracts)."""

    EMPIRICAL_ACTION_LOG = "EMPIRICAL_ACTION_LOG"
    OPERATOR_INDUSTRY = "OPERATOR_INDUSTRY"
    STRUCTURAL_BOUNDED_SCENARIO = "STRUCTURAL_BOUNDED_SCENARIO"
    PURE_SCENARIO = "PURE_SCENARIO"
    ASSUMPTION_GROUNDED = "ASSUMPTION_GROUNDED"
    UNSUPPORTED = "UNSUPPORTED"


class EvidenceBasis(str, Enum):
    """Structured evidence bases for an action-response provenance (Pi_a)."""

    PUBLISHED_EVIDENCE = "PUBLISHED_EVIDENCE"
    OPERATIONAL_RULE = "OPERATIONAL_RULE"
    EXPERT_ENGINEERING_JUDGEMENT = "EXPERT_ENGINEERING_JUDGEMENT"
    SCENARIO_ASSUMPTION = "SCENARIO_ASSUMPTION"
    EMPIRICAL_ACTION_EVIDENCE = "EMPIRICAL_ACTION_EVIDENCE"
    DECLARED_HYBRID = "DECLARED_HYBRID"
    UNSUPPORTED = "UNSUPPORTED"


class ActionResponseSupportState(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONDITIONAL = "CONDITIONAL"
    UNSUPPORTED = "UNSUPPORTED"


class ActionResponseSupport(FrozenModel):
    """Structured response provenance ``Pi_a`` with full source lineage.

    A hybrid support declares multiple evidence bases and keeps every source
    reference; scenario assumptions are never relabeled as empirical evidence
    and expert judgement is never relabeled as published evidence.
    """

    evidence_bases: tuple[EvidenceBasis, ...] = Field(min_length=1)
    source_refs: tuple[str, ...] = ()
    support_state: ActionResponseSupportState
    freeze_id: str | None = None
    parameter_version: str | None = None
    interpretation_scope: str | None = None
    hybrid: bool = False
    provenance: tuple[str, ...] = ()

    @model_validator(mode="after")
    def hybrid_contract(self):
        bases = set(self.evidence_bases)
        if self.hybrid != (len(bases) >= 2):
            raise ValueError("HYBRID_FLAG_MUST_MATCH_MULTI_BASE_EVIDENCE")
        if EvidenceBasis.UNSUPPORTED in bases and len(bases) > 1:
            raise ValueError("UNSUPPORTED_EVIDENCE_CANNOT_BE_HYBRID")
        if self.support_state is ActionResponseSupportState.SUPPORTED and bases == {
            EvidenceBasis.SCENARIO_ASSUMPTION
        }:
            raise ValueError("SCENARIO_ONLY_SUPPORT_CANNOT_BE_UNCONDITIONAL")
        if self.support_state is ActionResponseSupportState.UNSUPPORTED and bases != {
            EvidenceBasis.UNSUPPORTED
        }:
            raise ValueError("UNSUPPORTED_SUPPORT_REQUIRES_UNSUPPORTED_BASIS_ONLY")
        if EvidenceBasis.DECLARED_HYBRID in bases:
            if not self.hybrid or not self.source_refs:
                raise ValueError("DECLARED_HYBRID_REQUIRES_FLAG_AND_SOURCES")
        return self

    @classmethod
    def from_legacy_provenance(
        cls, provenance: ResponseProvenance | str
    ) -> "ActionResponseSupport":
        value = ResponseProvenance(provenance)
        mapping = {
            ResponseProvenance.EMPIRICAL_ACTION_LOG: (
                EvidenceBasis.EMPIRICAL_ACTION_EVIDENCE,
            ),
            ResponseProvenance.OPERATOR_INDUSTRY: (EvidenceBasis.OPERATIONAL_RULE,),
            ResponseProvenance.STRUCTURAL_BOUNDED_SCENARIO: (
                EvidenceBasis.SCENARIO_ASSUMPTION,
            ),
            ResponseProvenance.PURE_SCENARIO: (EvidenceBasis.SCENARIO_ASSUMPTION,),
            ResponseProvenance.ASSUMPTION_GROUNDED: (
                EvidenceBasis.SCENARIO_ASSUMPTION,
            ),
            ResponseProvenance.UNSUPPORTED: (EvidenceBasis.UNSUPPORTED,),
        }
        bases = mapping[value]
        state = (
            ActionResponseSupportState.UNSUPPORTED
            if value is ResponseProvenance.UNSUPPORTED
            else ActionResponseSupportState.CONDITIONAL
        )
        return cls(
            evidence_bases=bases,
            support_state=state,
            hybrid=False,
            provenance=(f"legacy:{value.value}",),
        )


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


class InstantiationState(str, Enum):
    """χ_inst: whether the declared mathematical action instance was formed."""

    FORMED = "FORMED"
    NOT_FORMED = "NOT_FORMED"


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
    response_support: ActionResponseSupport | None = None
    response_parameter_status: ResponseParameterStatus = (
        ResponseParameterStatus.NOT_FROZEN
    )
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
            if (
                self.response_parameter_status
                is not ResponseParameterStatus.NOT_REQUIRED
            ):
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
    instantiation_state: InstantiationState = InstantiationState.FORMED
    authority_capabilities: tuple[str, ...]
    mitigation: dict[str, float]
    induced: dict[str, float]
    induced_response: dict[str, float] = {}
    response_model: str
    response_parameters: dict[str, Any]
    response_provenance: ResponseProvenance
    response_support: ActionResponseSupport | None = None
    response_parameter_status: ResponseParameterStatus
    response_registry_id: str | None = None
    response_registry_hash: str | None = None
    response_sensitivity_level: str = "BASE"
    coverage: str
    preparation_time_minutes: float
    deadline_semantics: str
    precondition_reason: str = "REQUIRED_FACTS_TRUE"
    factual_provenance: tuple[str, ...] = ()

    @model_validator(mode="after")
    def typed_boundaries(self):
        if self.precondition_state not in {"TRUE", "FALSE", "UNKNOWN"}:
            raise ValueError("UNKNOWN_PRECONDITION_STATE")
        if self.instantiation_state is not InstantiationState.FORMED:
            raise ValueError("NON_INSTANTIABLE_CANDIDATE_MUST_NOT_ENTER_A")
        if self.template_id != "A00" and (
            self.response_parameter_status is ResponseParameterStatus.FROZEN
            and not self.response_parameters
        ):
            raise ValueError("FROZEN_RESPONSE_PARAMETERS_REQUIRED")
        return self

    @computed_field
    @property
    def instantiable(self) -> bool:
        """Compatibility projection of χ_inst; not an independent state."""
        return self.instantiation_state is InstantiationState.FORMED


class ActionInstantiationRecord(FrozenModel):
    """Auditable template-level record for ``chi_inst``.

    A record exists for every action template at every decision node.  Only a
    formed mathematical instance carries a ``CandidateAction``; a missing
    required parameter is therefore visible in the audit trail without being
    admitted to the candidate set consumed by downstream layers.
    """

    template_id: str = Field(min_length=1)
    instantiation_state: InstantiationState
    reason: str = Field(min_length=1)
    missing_required_parameters: tuple[str, ...] = ()
    source: tuple[str, ...] = Field(min_length=1)
    lineage: tuple[str, ...] = Field(min_length=1)
    candidate: CandidateAction | None = None

    @model_validator(mode="after")
    def candidate_boundary(self):
        if self.instantiation_state is InstantiationState.FORMED:
            if self.candidate is None:
                raise ValueError("FORMED_INSTANTIATION_REQUIRES_CANDIDATE")
            if self.candidate.template_id != self.template_id:
                raise ValueError("INSTANTIATION_CANDIDATE_TEMPLATE_MISMATCH")
            if self.candidate.instantiation_state is not InstantiationState.FORMED:
                raise ValueError("FORMED_RECORD_REQUIRES_FORMED_CANDIDATE")
            if self.missing_required_parameters:
                raise ValueError("FORMED_INSTANTIATION_CANNOT_HAVE_MISSING_PARAMETERS")
        else:
            if self.candidate is not None:
                raise ValueError("NOT_FORMED_INSTANTIATION_CANNOT_HAVE_CANDIDATE")
            if not self.missing_required_parameters:
                raise ValueError("NOT_FORMED_INSTANTIATION_REQUIRES_MISSING_PARAMETERS")
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
