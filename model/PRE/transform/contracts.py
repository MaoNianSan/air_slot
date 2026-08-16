from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from model.common.enums import (
    AvailabilityBasis,
    DecisionTimeRole,
    EvidenceClass,
    SupportState,
    weaker_or_equal,
)
from model.common.errors import RegistryError
from model.common.value_objects import FrozenModel

class ConstructionType(str, Enum):
    DIRECT_OBSERVATION = "DIRECT_OBSERVATION"
    DETERMINISTIC_DERIVATION = "DETERMINISTIC_DERIVATION"
    EVENT_STATE_INFERENCE = "EVENT_STATE_INFERENCE"
    RELATIONAL_DERIVATION = "RELATIONAL_DERIVATION"
    TRAIN_FROZEN_REFERENCE = "TRAIN_FROZEN_REFERENCE"
    EXTERNAL_OR_POLICY_REFERENCE = "EXTERNAL_OR_POLICY_REFERENCE"
    SCENARIO_ASSUMPTION = "SCENARIO_ASSUMPTION"
    UNSUPPORTED = "UNSUPPORTED"


class TransformationStatus(str, Enum):
    FROZEN = "FROZEN"
    DEVELOPMENT_FROZEN = "DEVELOPMENT_FROZEN"
    DEVELOPMENT_CANDIDATE = "DEVELOPMENT_CANDIDATE"
    UNSUPPORTED = "UNSUPPORTED"


class TransformationRule(FrozenModel):
    transformation_rule_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    construction_type: ConstructionType
    input_object_types: tuple[str, ...]
    input_fields: tuple[str, ...]
    relation_keys: tuple[str, ...] = ()
    group_by_keys: tuple[str, ...] = ()
    order_by_keys: tuple[str, ...] = ()
    join_on_keys: tuple[str, ...] = ()
    window_rule: str | None = None
    adjacency_rule: str | None = None
    tie_break_rule: str | None = None
    duplicate_rule: str = "REJECT_EXACT_DUPLICATE_SCIENTIFIC_KEY"
    missing_key_rule: str = "ABSTAIN_OR_REJECT"
    temporal_rule: str = Field(min_length=1)
    formula_or_algorithm: str = Field(min_length=1)
    output_variable: str = Field(min_length=1)
    output_unit: str = Field(min_length=1)
    evidence_rule: str = Field(min_length=1)
    support_rule: str = Field(min_length=1)
    consumer_roles: tuple[DecisionTimeRole, ...]
    availability_basis: AvailabilityBasis
    evidence_class: EvidenceClass
    support_ceiling: EvidenceClass
    status: TransformationStatus
    reason_code: str | None = None

    @model_validator(mode="after")
    def explicit_unfrozen_state(self):
        if not weaker_or_equal(self.evidence_class, self.support_ceiling):
            raise ValueError("TRANSFORMATION_EVIDENCE_EXCEEDS_SUPPORT_CEILING")
        if self.status in {
            TransformationStatus.DEVELOPMENT_CANDIDATE,
            TransformationStatus.UNSUPPORTED,
        } and not self.reason_code:
            raise ValueError("UNFROZEN_TRANSFORMATION_REQUIRES_REASON")
        if self.status is TransformationStatus.UNSUPPORTED and (
            self.construction_type is not ConstructionType.UNSUPPORTED
            or self.evidence_class is not EvidenceClass.UNSUPPORTED
        ):
            raise ValueError("UNSUPPORTED_TRANSFORMATION_STATE_MISMATCH")
        return self

    @property
    def formal_executable(self) -> bool:
        return self.status is TransformationStatus.FROZEN


class TransformationRegistry(FrozenModel):
    registry_version: str
    rules: tuple[TransformationRule, ...]

    @model_validator(mode="after")
    def unique_rules(self):
        identities = tuple(
            (rule.transformation_rule_id, rule.version) for rule in self.rules
        )
        if len(identities) != len(set(identities)):
            raise ValueError("DUPLICATE_TRANSFORMATION_RULE")
        return self

    def get(self, rule_id: str, version: str) -> TransformationRule:
        matches = [
            rule
            for rule in self.rules
            if rule.transformation_rule_id == rule_id and rule.version == version
        ]
        if not matches:
            raise RegistryError("TRANSFORMATION_RULE_NOT_REGISTERED")
        return matches[0]


class ScientificObjectValue(FrozenModel):
    scientific_variable_id: str
    value: Any | None
    unit: str
    construction_type: ConstructionType
    transformation_rule_id: str
    transformation_version: str
    evidence_class: EvidenceClass
    support_state: SupportState
    support_ceiling: EvidenceClass
    reason_code: str | None = None
    parent_object_ids: tuple[str, ...]
    source_object_types: tuple[str, ...]
    source_fields: tuple[str, ...]
    relation_keys: tuple[str, ...] = ()
    temporal_rule: str
    evidence_rule: str
    support_rule: str
    consumer_roles: tuple[DecisionTimeRole, ...]
    transformation_status: TransformationStatus
    decision_time_role: DecisionTimeRole
    availability_basis: AvailabilityBasis
    provenance: tuple[str, ...]

    @model_validator(mode="after")
    def preserve_abstention(self):
        if self.support_state is SupportState.ABSTAIN:
            if self.value is not None or not self.reason_code:
                raise ValueError("DERIVED_ABSTAIN_REQUIRES_NULL_AND_REASON")
        elif self.value is None:
            raise ValueError("DERIVED_NULL_REQUIRES_ABSTAIN")
        return self



class ReferenceFitManifest(FrozenModel):
    transformation_rule_id: str
    transformation_version: str
    fit_partition: str
    fit_period: str
    grouping_keys: tuple[str, ...]
    statistic_id: str
    minimum_support_rule: str
    fallback_hierarchy: tuple[str, ...]
    applicability_scope: str
    evidence_class: EvidenceClass
    support_ceiling: EvidenceClass
    availability_basis: AvailabilityBasis
    consumer_roles: tuple[DecisionTimeRole, ...]
    rule_status: TransformationStatus
    training_record_ids: tuple[str, ...]
    training_source_fingerprints: tuple[str, ...]
    sample_count: int
    freeze_id: str
