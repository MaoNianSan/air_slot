"""Frozen, value-explicit artifact schemas for Exp2 execution preparation."""

from __future__ import annotations

from enum import Enum
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id


EXP2_ARTIFACT_SCHEMA_VERSION = "AIR_SLOT_EXP2_SCIENTIFIC_ARTIFACT_V1"
SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
REQUIRED_RISK_PARAMETERS = (
    "alpha",
    "expected_loss_coefficient",
    "cvar_coefficient",
)


class Exp2ResponseSupport(str, Enum):
    SUPPORTED = "SUPPORTED"
    REFERENCE_BASED = "REFERENCE_BASED"
    SCENARIO_ASSUMPTION = "SCENARIO_ASSUMPTION"
    ABSTAIN = "ABSTAIN"


class Exp2ResponseSource(str, Enum):
    LITERATURE = "LITERATURE"
    OPERATIONAL_RULE = "OPERATIONAL_RULE"
    SCENARIO_ASSUMPTION = "SCENARIO_ASSUMPTION"
    EXPERT_JUDGEMENT = "EXPERT_JUDGEMENT"
    HYBRID = "HYBRID"


class ArtifactSupportStatus(str, Enum):
    FROZEN = "FROZEN"
    NOT_FROZEN = "NOT_FROZEN"
    ABSTAIN = "ABSTAIN"
    TEST_ONLY = "TEST_ONLY"


class _FrozenArtifactModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def reject_unset_strings(cls, value):
        if isinstance(value, str) and value.strip().upper() in {"", "UNSET"}:
            raise ValueError("EXP2_ARTIFACT_EXPLICIT_VALUE_REQUIRED")
        return value


class Exp2ActionManifest(_FrozenArtifactModel):
    """One cohort-level ordered action set shared by every Exp2 variant."""

    manifest_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    split: str = Field(min_length=1)
    cohort_hash: str = Field(pattern=SHA256_PATTERN)
    action_ids: tuple[str, ...] = Field(min_length=2)
    action_registry_id: str = Field(min_length=1)
    action_registry_hash: str = Field(pattern=SHA256_PATTERN)
    response_registry_id: str = Field(min_length=1)
    response_registry_hash: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def frozen_action_order(self):
        if len(self.action_ids) != len(set(self.action_ids)):
            raise ValueError("EXP2_ACTION_MANIFEST_DUPLICATE_ACTION")
        if "A00" not in self.action_ids:
            raise ValueError("EXP2_ACTION_MANIFEST_A00_REQUIRED")
        if len(self.action_ids) < 2 or not any(action_id != "A00" for action_id in self.action_ids):
            raise ValueError("EXP2_ACTION_MANIFEST_NON_A00_REQUIRED")
        if self.action_ids[0] != "A00":
            raise ValueError("EXP2_ACTION_MANIFEST_A00_MUST_BE_FIRST")
        if self.action_ids[1:] != tuple(sorted(self.action_ids[1:])):
            raise ValueError("EXP2_ACTION_MANIFEST_ORDER_NOT_DETERMINISTIC")
        return self

    @property
    def manifest_hash(self) -> str:
        return content_id(self.model_dump(mode="json"))


class Exp2ResponseBundle(_FrozenArtifactModel):
    """One exact M3 response rule; support is recorded, never inferred."""

    action_id: str = Field(min_length=1)
    response_rule_id: str = Field(min_length=1)
    support_class: Exp2ResponseSupport
    source_type: Exp2ResponseSource
    source_reference: str = Field(min_length=1)
    parameter_version: str = Field(min_length=1)
    freeze_id: str = Field(min_length=1)
    rule_hash: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def support_source_and_hash(self):
        if (
            self.support_class is Exp2ResponseSupport.SCENARIO_ASSUMPTION
            and self.source_type is not Exp2ResponseSource.SCENARIO_ASSUMPTION
        ):
            raise ValueError("EXP2_SCENARIO_RESPONSE_SOURCE_MISMATCH")
        if (
            self.support_class is Exp2ResponseSupport.SUPPORTED
            and self.source_type
            in {
                Exp2ResponseSource.SCENARIO_ASSUMPTION,
                Exp2ResponseSource.EXPERT_JUDGEMENT,
            }
        ):
            raise ValueError("EXP2_RESPONSE_SUPPORT_CANNOT_BE_UPGRADED")
        expected = content_id(self.model_dump(mode="json", exclude={"rule_hash"}))
        if self.rule_hash != expected:
            raise ValueError("EXP2_RESPONSE_RULE_HASH_MISMATCH")
        return self


class Exp2MonetaryMappingBundle(_FrozenArtifactModel):
    """Complete seven-component internal-loss mapping identity."""

    mapping_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    component_ids: tuple[str, ...] = Field(min_length=1)
    mapping_function_reference: dict[str, str] = Field(min_length=1)
    source_reference: dict[str, tuple[str, ...]] = Field(min_length=1)
    version: str = Field(min_length=1)
    hash: str = Field(pattern=SHA256_PATTERN)
    support_status: ArtifactSupportStatus
    interpretation: Literal["CONSTRUCTED_INTERNAL_LOSS_UNIT"]

    @model_validator(mode="after")
    def complete_nonfallback_mapping(self):
        required = tuple(CONSEQUENCE_COMPONENTS)
        if self.component_ids != required:
            raise ValueError("EXP2_M4_EXACT_COMPONENT_COVERAGE_REQUIRED")
        if set(self.mapping_function_reference) != set(required):
            raise ValueError("EXP2_M4_MAPPING_FUNCTION_COVERAGE_INCOMPLETE")
        if set(self.source_reference) != set(required) or any(
            not references for references in self.source_reference.values()
        ):
            raise ValueError("EXP2_M4_MAPPING_SOURCE_COVERAGE_INCOMPLETE")
        all_references = tuple(self.mapping_function_reference.values()) + tuple(
            reference
            for references in self.source_reference.values()
            for reference in references
        )
        if any("FALLBACK" in reference.upper() for reference in all_references):
            raise ValueError("EXP2_M4_FALLBACK_MAPPING_FORBIDDEN")
        if self.support_status is ArtifactSupportStatus.TEST_ONLY:
            raise ValueError("EXP2_M4_TEST_ONLY_MAPPING_FORBIDDEN")
        expected = content_id(self.model_dump(mode="json", exclude={"hash"}))
        if self.hash != expected:
            raise ValueError("EXP2_M4_MAPPING_HASH_MISMATCH")
        return self


class Exp2RiskPolicyBundle(_FrozenArtifactModel):
    """Explicit M4 residual-risk/CVaR policy with no parameter defaults."""

    policy_id: str = Field(min_length=1)
    tail_policy: str = Field(min_length=1)
    CVaR_policy: str = Field(min_length=1)
    parameters: dict[str, float] = Field(min_length=1)
    version: str = Field(min_length=1)
    hash: str = Field(pattern=SHA256_PATTERN)
    support_status: ArtifactSupportStatus

    @model_validator(mode="after")
    def explicit_policy_and_hash(self):
        if any(
            token in value.upper()
            for value in (self.tail_policy, self.CVaR_policy)
            for token in ("DEFAULT", "FALLBACK", "UNSET")
        ):
            raise ValueError("EXP2_M4_IMPLICIT_RISK_POLICY_FORBIDDEN")
        missing = set(REQUIRED_RISK_PARAMETERS) - set(self.parameters)
        if missing:
            raise ValueError("EXP2_M4_RISK_PARAMETERS_INCOMPLETE")
        if any(not math.isfinite(value) for value in self.parameters.values()):
            raise ValueError("EXP2_M4_RISK_PARAMETER_NONFINITE")
        alpha = self.parameters["alpha"]
        expected_coefficient = self.parameters["expected_loss_coefficient"]
        cvar_coefficient = self.parameters["cvar_coefficient"]
        if not 0 < alpha < 1:
            raise ValueError("EXP2_M4_CVAR_ALPHA_OUT_OF_RANGE")
        if expected_coefficient < 0 or cvar_coefficient < 0:
            raise ValueError("EXP2_M4_RISK_COEFFICIENT_NEGATIVE")
        if abs(expected_coefficient + cvar_coefficient - 1.0) > 1e-12:
            raise ValueError("EXP2_M4_RISK_COEFFICIENTS_MUST_SUM_TO_ONE")
        if self.support_status is ArtifactSupportStatus.TEST_ONLY:
            raise ValueError("EXP2_M4_TEST_ONLY_RISK_POLICY_FORBIDDEN")
        expected = content_id(self.model_dump(mode="json", exclude={"hash"}))
        if self.hash != expected:
            raise ValueError("EXP2_M4_RISK_POLICY_HASH_MISMATCH")
        return self


__all__ = [
    "EXP2_ARTIFACT_SCHEMA_VERSION",
    "REQUIRED_RISK_PARAMETERS",
    "SHA256_PATTERN",
    "ArtifactSupportStatus",
    "Exp2ActionManifest",
    "Exp2MonetaryMappingBundle",
    "Exp2ResponseBundle",
    "Exp2ResponseSource",
    "Exp2ResponseSupport",
    "Exp2RiskPolicyBundle",
]
