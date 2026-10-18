from typing import Literal
from pydantic import Field, model_validator
from model.common.enums import DecisionTimeRole, EvidenceClass, FreezeState, weaker_or_equal
from model.common.value_objects import FrozenModel


Consumer = Literal["PRE", "M1", "M2", "M3", "EVALUATION_ONLY"]


class DataUsageRule(FrozenModel):
    rule_id: str; rule_version: str; freeze_state: FreezeState; dataset_id: str
    logical_source: str; raw_columns: tuple[str, ...]; raw_semantics: str
    raw_unit: str | None; canonical_object: str; canonical_variable: str
    canonical_unit: str; transformation_rule: str; event_time_source: str | None
    availability_rule: str; decision_time_role: DecisionTimeRole
    evidence_class: EvidenceClass; support_ceiling: EvidenceClass
    missing_rule: str; stale_rule: str; fallback_rule: str; pre_family: str
    downstream_consumers: tuple[Consumer, ...]; scientific_purpose: str
    semantic_status: str; confidence: Literal["HIGH", "MEDIUM", "LOW"]
    external_evidence_rule_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def enforce_support_ceiling(self):
        if not weaker_or_equal(self.evidence_class, self.support_ceiling):
            raise ValueError("registry evidence exceeds support ceiling")
        return self


class DatasetSupport(FrozenModel):
    formal_input_support: EvidenceClass
    realized_outcome_support: EvidenceClass
    reason_code: str | None = None


class ScientificVariableDefinition(FrozenModel):
    scientific_variable: str; registry_version: str; freeze_state: FreezeState
    pre_family: str; canonical_inputs: tuple[str, ...]; transformation_rule: str
    unit: str; time_semantics: str; availability_rule: str
    evidence_class: EvidenceClass; support_ceiling: EvidenceClass
    missing_rule: str; fallback_rule: str; consumers: tuple[Consumer, ...]
    development_frozen_dependencies: tuple[str, ...] = ()
    upstream_variables: tuple[str, ...] = ()
    dataset_support: dict[str, DatasetSupport]
    notes: str = ""

    @model_validator(mode="after")
    def enforce_support_ceiling(self):
        if not weaker_or_equal(self.evidence_class, self.support_ceiling):
            raise ValueError("scientific variable exceeds support ceiling")
        return self


class DatasetCapability(FrozenModel):
    scientific_object: str; decision_time_role: DecisionTimeRole
    max_evidence_class: EvidenceClass; formal_input_support: EvidenceClass
    realized_outcome_support: EvidenceClass; freeze_state: FreezeState
    reason_code: str | None = None; source_families: tuple[str, ...] = ()

    @model_validator(mode="after")
    def explicit_unsupported(self):
        states = (self.max_evidence_class, self.formal_input_support,
                  self.realized_outcome_support, self.freeze_state)
        if any(value.value == "UNSUPPORTED" for value in states) and not self.reason_code:
            raise ValueError("unsupported capability requires reason_code")
        return self


class DatasetCapabilityProfile(FrozenModel):
    dataset_instance_id: str; dataset_profile: str
    cross_dataset_reference_overlay: bool = False
    capabilities: tuple[DatasetCapability, ...]

    @model_validator(mode="after")
    def overlay_disabled(self):
        if self.cross_dataset_reference_overlay:
            raise ValueError("cross-dataset overlay requires a separate specification")
        return self


class SourcePriorityEntry(FrozenModel):
    scientific_object: str; dataset_instance_id: str
    rule_ids: tuple[str, ...]; priority: int; condition: str; version: str


class RegistryFileIdentity(FrozenModel):
    path: str; sha256: str


class RegistryManifest(FrozenModel):
    manifest_version: str
    registries: tuple[RegistryFileIdentity, ...]
    combined_sha256: str
    validation_status: Literal["PASS"]
