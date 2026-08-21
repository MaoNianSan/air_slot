from typing import Literal
from pydantic import Field, model_validator
from model.common.enums import DecisionTimeRole, EvidenceClass, FreezeState, weaker_or_equal
from model.common.value_objects import FrozenModel


Consumer = Literal["PRE", "M1", "M2", "M3", "EXP3", "EVALUATION_ONLY"]
SourceKind = Literal["RAW_SOURCE", "PROJECTION", "DERIVED_ARTIFACT"]
ColumnRole = Literal[
    "COVERED_ACTIVE",
    "RETAINED_IDENTITY",
    "OPTIONAL_PROJECTED_METADATA",
    "EXPLICITLY_UNUSED",
    "DIAGNOSTIC_ONLY",
    "REFERENCE_BUILD_ONLY",
    "SOURCE_SCHEMA_METADATA",
]


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
    source_kind: SourceKind = "RAW_SOURCE"
    source_rule_id: str | None = None
    projected_columns: tuple[str, ...] = ()
    raw_column_roles: dict[str, ColumnRole] = {}
    projected_column_roles: dict[str, ColumnRole] = {}
    projection_role: str | None = None
    declared_lag_minutes: int | None = Field(default=None, ge=0)
    observed_message_arrival_claim: bool | None = None
    production_availability_claim: bool | None = None
    source_outcome_role_preserved: bool | None = None
    derived_artifact_schema: str | None = None

    @model_validator(mode="after")
    def enforce_support_ceiling(self):
        if not weaker_or_equal(self.evidence_class, self.support_ceiling):
            raise ValueError("registry evidence exceeds support ceiling")
        if not set(self.raw_column_roles) <= set(self.raw_columns):
            raise ValueError("raw column role references undeclared column")
        if not set(self.projected_column_roles) <= set(self.projected_columns):
            raise ValueError("projected column role references undeclared column")
        if self.source_kind == "RAW_SOURCE":
            if self.source_rule_id or self.derived_artifact_schema:
                raise ValueError("raw source cannot declare projection/artifact ownership")
        elif self.source_kind == "PROJECTION":
            if not self.source_rule_id or not self.projection_role:
                raise ValueError("projection requires source_rule_id and projection_role")
            if self.raw_columns:
                raise ValueError("projection cannot own raw columns")
        elif self.source_kind == "DERIVED_ARTIFACT":
            if self.raw_columns or self.projected_columns:
                raise ValueError("derived artifact cannot own source columns")
            if not self.derived_artifact_schema:
                raise ValueError("derived artifact requires a schema id")
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
    # Tranche 3: realized outcomes may also act as FACTUAL_REPLAY_EVIDENCE in
    # a subsequent rolling state, but only under the Data2 factual-replay
    # availability policy gate (HUMAN_GATE / CONDITIONAL / SUPPORTED).
    factual_replay_support: str = "HUMAN_GATE"

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
