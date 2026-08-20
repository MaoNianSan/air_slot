"""Fail-closed preparation validation for an Exp2 scientific artifact freeze.

The validator verifies only declared artifact identities and registry lineage.
It never reads an experimental dataset, constructs a model artifact, selects an
action, or turns a missing scientific decision into a default.
"""

from __future__ import annotations

from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from model.M2.freeze import load_m2_registry
from model.M3.registry import ActionRegistry
from model.M3.response_registry import ResponseScenarioRegistry
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id
from model.common.monetary_system import MonetaryMappingStatus
from model.M4.residual_risk import RiskPolicyStatus


SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
REQUIRED_PREFIX = "REQUIRED_"
SCIENTIFIC_MANIFEST_SCHEMA_VERSION = "AIR_SLOT_EXP2_SCIENTIFIC_MANIFEST_V1"
M2_COMPONENT_SCHEMA_ID = "M2_SEVEN_COMPONENT_CONSEQUENCE_V1"


class ScientificManifestStatus(str, Enum):
    READY = "READY"
    BLOCKED_MISSING_ARTIFACT = "BLOCKED_MISSING_ARTIFACT"
    BLOCKED_INCOMPATIBLE_SCHEMA = "BLOCKED_INCOMPATIBLE_SCHEMA"
    BLOCKED_LINEAGE_MISMATCH = "BLOCKED_LINEAGE_MISMATCH"
    BLOCKED_UNSUPPORTED_MAPPING = "BLOCKED_UNSUPPORTED_MAPPING"


class M4ScientificGateStatus(str, Enum):
    READY = "READY"
    BLOCKED_UNSUPPORTED_MAPPING = "BLOCKED_UNSUPPORTED_MAPPING"


def _required(value: str) -> bool:
    return value.strip().upper().startswith(REQUIRED_PREFIX)


def _hash_or_required(value: str) -> str:
    if _required(value):
        return value
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError("EXP2_SCIENTIFIC_MANIFEST_HASH_OR_REQUIRED_EXPECTED")
    return value


class DatasetBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str = Field(min_length=1)
    source_dataset_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    data_source_identifier: str = Field(min_length=1)
    split: str = Field(min_length=1)
    episode_selector: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    capabilities_registry: str = Field(min_length=1)
    capabilities_registry_hash: str = Field(pattern=SHA256_PATTERN)
    required_capabilities: tuple[dict[str, str], ...] = Field(min_length=1)
    cohort_artifact: str = Field(min_length=1)
    cohort_hash: str = Field(pattern=SHA256_PATTERN)
    cohort_artifact_hash: str = Field(pattern=SHA256_PATTERN)
    final_test_access_count: int = Field(ge=0)
    paper_full_run: bool


class M1ScientificBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    checkpoint: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    hash: str = Field(min_length=1)
    lineage_registry_hash: str = Field(pattern=SHA256_PATTERN)

    @field_validator("hash")
    @classmethod
    def hash_is_explicit_or_required(cls, value: str) -> str:
        return _hash_or_required(value)


class M2ComponentSchema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_id: str = Field(min_length=1)
    component_ids: tuple[str, ...] = Field(min_length=1)
    hash: str = Field(pattern=SHA256_PATTERN)


class RegistryReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    registry_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)


class M2ScientificBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    cu_registry: RegistryReference
    component_schema: M2ComponentSchema
    hash: str = Field(min_length=1)
    lineage_m1_artifact_id: str = Field(min_length=1)

    @field_validator("hash")
    @classmethod
    def hash_is_explicit_or_required(cls, value: str) -> str:
        return _hash_or_required(value)


class M3ScientificBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str = Field(min_length=1)
    action_manifest: RegistryReference
    response_bundle: RegistryReference
    artifact_path: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    hash: str = Field(min_length=1)
    status: str = Field(min_length=1)

    @field_validator("hash")
    @classmethod
    def hash_is_explicit_or_required(cls, value: str) -> str:
        return _hash_or_required(value)


class M4ScientificBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str = Field(min_length=1)
    mapping_registry: RegistryReference
    risk_policy: str = Field(min_length=1)
    risk_policy_hash: str = Field(pattern=SHA256_PATTERN)
    artifact_id: str = Field(min_length=1)
    hash: str = Field(min_length=1)
    mapping_status: MonetaryMappingStatus
    risk_policy_status: RiskPolicyStatus
    support_status: str = Field(min_length=1)
    mapping_resolved: bool
    mapping_provenance: tuple[str, ...] = ()
    risk_policy_provenance: tuple[str, ...] = ()

    @field_validator("hash")
    @classmethod
    def hash_is_explicit_or_required(cls, value: str) -> str:
        return _hash_or_required(value)


class ScientificArtifactManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_version: str = SCIENTIFIC_MANIFEST_SCHEMA_VERSION
    execution_intent: str = "ARTIFACT_FREEZE_PREPARATION_ONLY"
    scientific_run: bool = False
    paper_result: bool = False
    dataset: DatasetBinding
    m1: M1ScientificBinding = Field(alias="M1")
    m2: M2ScientificBinding = Field(alias="M2")
    m3: M3ScientificBinding = Field(alias="M3")
    m4: M4ScientificBinding = Field(alias="M4")


class M4ScientificGateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: M4ScientificGateStatus
    reason_codes: tuple[str, ...]


class M4ScientificGate:
    """Validate a complete M4 scientific declaration without choosing values."""

    def validate(self, binding: M4ScientificBinding) -> M4ScientificGateResult:
        if not isinstance(binding, M4ScientificBinding):
            raise TypeError("EXP2_M4_SCIENTIFIC_BINDING_REQUIRED")

        reasons: list[str] = []
        if binding.mapping_status is MonetaryMappingStatus.TEST_ONLY:
            reasons.append("TEST_ONLY_MAPPING_REJECTED")
        elif binding.mapping_status is not MonetaryMappingStatus.FROZEN:
            reasons.append(f"MAPPING_STATUS_NOT_FROZEN:{binding.mapping_status.value}")
        if binding.risk_policy_status is RiskPolicyStatus.TEST_ONLY:
            reasons.append("TEST_ONLY_RISK_POLICY_REJECTED")
        elif binding.risk_policy_status is not RiskPolicyStatus.FROZEN:
            reasons.append(
                f"RISK_POLICY_STATUS_NOT_FROZEN:{binding.risk_policy_status.value}"
            )
        if binding.support_status != "SUPPORTED":
            reasons.append(f"M4_SUPPORT_STATUS_NOT_SUPPORTED:{binding.support_status}")
        if not binding.mapping_resolved:
            reasons.append("MAPPING_UNRESOLVED")
        if not binding.mapping_provenance:
            reasons.append("MAPPING_PROVENANCE_MISSING")
        if not binding.risk_policy_provenance:
            reasons.append("RISK_POLICY_PROVENANCE_MISSING")
        if _required(binding.risk_policy):
            reasons.append("RISK_POLICY_ARTIFACT_REQUIRED")
        if _required(binding.artifact_id) or _required(binding.hash):
            reasons.append("M4_FROZEN_ARTIFACT_REQUIRED")
        return M4ScientificGateResult(
            status=(
                M4ScientificGateStatus.READY
                if not reasons
                else M4ScientificGateStatus.BLOCKED_UNSUPPORTED_MAPPING
            ),
            reason_codes=tuple(reasons) or ("M4_SCIENTIFIC_GATE_PASS",),
        )


class ScientificManifestValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ScientificManifestStatus
    reason_codes: tuple[str, ...]
    dataset_binding_valid: bool
    lineage_valid: bool
    m4_gate: M4ScientificGateResult


class ScientificManifestValidator:
    """Validate registry binding and unresolved-artifact state without fallback."""

    def __init__(self, *, repository_root: Path | None = None):
        self.repository_root = (
            Path(repository_root).resolve()
            if repository_root is not None
            else Path(__file__).resolve().parents[3]
        )

    def load(self, path: Path) -> ScientificArtifactManifest:
        try:
            raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
            return ScientificArtifactManifest.model_validate(raw)
        except (OSError, TypeError, ValidationError, yaml.YAMLError) as exc:
            raise ValueError(
                f"EXP2_SCIENTIFIC_MANIFEST_INVALID:{type(exc).__name__}"
            ) from exc

    def validate_path(self, path: Path) -> ScientificManifestValidationResult:
        return self.validate(self.load(path))

    def validate(
        self, manifest: ScientificArtifactManifest
    ) -> ScientificManifestValidationResult:
        if not isinstance(manifest, ScientificArtifactManifest):
            raise TypeError("EXP2_SCIENTIFIC_MANIFEST_REQUIRED")
        if manifest.schema_version != SCIENTIFIC_MANIFEST_SCHEMA_VERSION:
            raise ValueError("EXP2_SCIENTIFIC_MANIFEST_SCHEMA_VERSION_MISMATCH")
        if manifest.execution_intent != "ARTIFACT_FREEZE_PREPARATION_ONLY":
            raise ValueError("EXP2_SCIENTIFIC_MANIFEST_EXECUTION_INTENT_INVALID")
        if manifest.scientific_run or manifest.paper_result:
            raise ValueError("EXP2_SCIENTIFIC_MANIFEST_RUN_OR_PAPER_FORBIDDEN")

        reasons: list[str] = []
        dataset_valid = self._validate_dataset(manifest.dataset, reasons)
        dataset_valid = self._validate_materialized_dataset_binding(
            manifest.dataset, reasons
        ) and dataset_valid
        lineage_valid = self._validate_lineage(manifest, reasons)
        self._validate_registry_hashes(manifest, reasons)
        self._validate_materialized_m3_binding(manifest.m3, reasons)
        self._validate_materialized_m4_binding(manifest.m4, reasons)
        self._validate_unresolved_artifacts(manifest, reasons)
        m4_gate = M4ScientificGate().validate(manifest.m4)
        reasons.extend(m4_gate.reason_codes if m4_gate.status is not M4ScientificGateStatus.READY else ())

        dataset_incompatibility = any(
            code in {
                "DATASET_CAPABILITIES_REGISTRY_UNAVAILABLE",
                "DATASET_SCHEMA_VERSION_MISMATCH",
                "DATASET_CAPABILITIES_HASH_MISMATCH",
                "DATASET_NOT_REGISTERED",
            }
            or code.startswith("DATASET_CAPABILITY_UNAVAILABLE:")
            for code in reasons
        )
        if dataset_incompatibility:
            status = ScientificManifestStatus.BLOCKED_INCOMPATIBLE_SCHEMA
        elif any("HASH_MISMATCH" in code or "LINEAGE" in code for code in reasons):
            status = ScientificManifestStatus.BLOCKED_LINEAGE_MISMATCH
        elif (
            m4_gate.status is M4ScientificGateStatus.BLOCKED_UNSUPPORTED_MAPPING
            and not any(code.endswith("_REQUIRED") for code in reasons)
        ):
            status = ScientificManifestStatus.BLOCKED_UNSUPPORTED_MAPPING
        elif reasons:
            status = ScientificManifestStatus.BLOCKED_MISSING_ARTIFACT
        else:
            status = ScientificManifestStatus.READY
        return ScientificManifestValidationResult(
            status=status,
            reason_codes=tuple(dict.fromkeys(reasons)) or ("MANIFEST_READY",),
            dataset_binding_valid=dataset_valid,
            lineage_valid=lineage_valid,
            m4_gate=m4_gate,
        )

    def _path(self, relative_path: str) -> Path:
        candidate = (self.repository_root / relative_path).resolve()
        if self.repository_root not in candidate.parents:
            raise ValueError("EXP2_SCIENTIFIC_MANIFEST_PATH_OUTSIDE_REPOSITORY")
        return candidate

    @staticmethod
    def _source_hash(path: Path) -> str:
        return f"sha256:{sha256(path.read_bytes()).hexdigest()}"

    def _validate_dataset(self, dataset: DatasetBinding, reasons: list[str]) -> bool:
        try:
            registry_path = self._path(dataset.capabilities_registry)
            raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, yaml.YAMLError):
            reasons.append("DATASET_CAPABILITIES_REGISTRY_UNAVAILABLE")
            return False
        compatible = True
        if raw.get("schema_version") != dataset.schema_version:
            reasons.append("DATASET_SCHEMA_VERSION_MISMATCH")
            compatible = False
        registry_hash = self._source_hash(registry_path)
        if registry_hash != dataset.capabilities_registry_hash:
            reasons.append("DATASET_CAPABILITIES_HASH_MISMATCH")
            compatible = False
        profiles = {
            item.get("dataset_instance_id"): item
            for item in raw.get("profiles", ())
        }
        # ``dataset_id`` is the Exp2 scientific binding label (for example,
        # ``DATA2``).  Registry profiles retain their source-instance name
        # (currently ``data2_2019``).  Keeping both identities explicit avoids
        # silently treating a logical experiment label as a raw-data version.
        profile = profiles.get(dataset.source_dataset_id)
        if profile is None:
            reasons.append("DATASET_NOT_REGISTERED")
            return False
        capabilities = {
            item.get("scientific_object"): item for item in profile.get("capabilities", ())
        }
        for requirement in dataset.required_capabilities:
            entry = capabilities.get(requirement["scientific_object"])
            if entry is None or entry.get("decision_time_role") != requirement["decision_time_role"]:
                reasons.append(
                    "DATASET_CAPABILITY_UNAVAILABLE:"
                    f"{requirement['scientific_object']}:"
                    f"{requirement['decision_time_role']}"
                )
                compatible = False
        if _required(dataset.version):
            reasons.append("DATASET_VERSION_REQUIRED")
        elif dataset.version == "DATA2_VERSION_PENDING":
            reasons.append("DATA2_VERSION_PENDING")
        if dataset.data_source_identifier.endswith("_PENDING"):
            reasons.append("DATA2_SOURCE_IDENTIFIER_PENDING")
        if _required(dataset.split):
            reasons.append("DATASET_SPLIT_REQUIRED")
        if _required(dataset.episode_selector):
            reasons.append("DATASET_EPISODE_SELECTOR_REQUIRED")
        return compatible

    def _validate_materialized_dataset_binding(
        self, dataset: DatasetBinding, reasons: list[str]
    ) -> bool:
        try:
            cohort_path = self._path(dataset.cohort_artifact)
            payload = json.loads(cohort_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError):
            reasons.append("DATASET_COHORT_ARTIFACT_UNAVAILABLE")
            return False
        artifact_hash = payload.pop("artifact_hash", None)
        if artifact_hash != content_id(payload) or artifact_hash != dataset.cohort_artifact_hash:
            reasons.append("DATASET_COHORT_CONTENT_HASH_MISMATCH")
        if payload.get("cohort_hash") != dataset.cohort_hash:
            reasons.append("DATASET_COHORT_HASH_MISMATCH")
        if (
            payload.get("dataset_id") != dataset.dataset_id
            or payload.get("source_dataset_id") != dataset.source_dataset_id
            or payload.get("dataset_version") != dataset.version
            or payload.get("split") != dataset.split
        ):
            reasons.append("DATASET_COHORT_IDENTITY_MISMATCH")
        if (
            payload.get("FINAL_TEST_ACCESS_COUNT") != dataset.final_test_access_count
            or payload.get("PAPER_FULL_RUN") != dataset.paper_full_run
            or payload.get("FINAL_TEST_ACCESS_COUNT") != 0
            or payload.get("PAPER_FULL_RUN") is not False
        ):
            reasons.append("DATASET_COHORT_FINAL_TEST_OR_PAPER_VIOLATION")
        return not any(code.startswith("DATASET_COHORT_") for code in reasons)

    def _validate_lineage(
        self, manifest: ScientificArtifactManifest, reasons: list[str]
    ) -> bool:
        dataset_id = manifest.dataset.dataset_id
        bindings = (manifest.m1, manifest.m2, manifest.m3, manifest.m4)
        if any(item.dataset_id != dataset_id for item in bindings):
            reasons.append("ARTIFACT_DATASET_LINEAGE_MISMATCH")
        if manifest.m1.lineage_registry_hash != manifest.dataset.capabilities_registry_hash:
            reasons.append("M1_DATASET_REGISTRY_LINEAGE_MISMATCH")
        if manifest.m2.lineage_m1_artifact_id != manifest.m1.artifact_id:
            reasons.append("M2_M1_ARTIFACT_LINEAGE_MISMATCH")
        component_payload = {
            "schema_id": manifest.m2.component_schema.schema_id,
            "component_ids": manifest.m2.component_schema.component_ids,
        }
        if manifest.m2.component_schema.schema_id != M2_COMPONENT_SCHEMA_ID:
            reasons.append("M2_COMPONENT_SCHEMA_ID_MISMATCH")
        if manifest.m2.component_schema.component_ids != CONSEQUENCE_COMPONENTS:
            reasons.append("M2_COMPONENT_SCHEMA_COVERAGE_MISMATCH")
        if content_id(component_payload) != manifest.m2.component_schema.hash:
            reasons.append("M2_COMPONENT_SCHEMA_HASH_MISMATCH")
        return not any("LINEAGE_MISMATCH" in code for code in reasons)

    def _validate_registry_hashes(
        self, manifest: ScientificArtifactManifest, reasons: list[str]
    ) -> None:
        try:
            m2_path = self._path(manifest.m2.cu_registry.path)
            m2_registry = load_m2_registry(m2_path)
            if self._source_hash(m2_path) != manifest.m2.cu_registry.source_sha256:
                reasons.append("M2_CU_REGISTRY_SOURCE_HASH_MISMATCH")
            if m2_registry.registry_hash != manifest.m2.cu_registry.registry_hash:
                reasons.append("M2_CU_REGISTRY_HASH_MISMATCH")
        except (OSError, TypeError, ValueError):
            reasons.append("M2_CU_REGISTRY_UNAVAILABLE")
        try:
            action_path = self._path(manifest.m3.action_manifest.path)
            action_registry = ActionRegistry.load(action_path)
            if action_registry.source_sha256 != manifest.m3.action_manifest.source_sha256:
                reasons.append("M3_ACTION_REGISTRY_SOURCE_HASH_MISMATCH")
            if action_registry.registry_hash != manifest.m3.action_manifest.registry_hash:
                reasons.append("M3_ACTION_REGISTRY_HASH_MISMATCH")
            response_path = self._path(manifest.m3.response_bundle.path)
            response_registry = ResponseScenarioRegistry.load(
                response_path, structural_registry=action_registry
            )
            if response_registry.source_sha256 != manifest.m3.response_bundle.source_sha256:
                reasons.append("M3_RESPONSE_REGISTRY_SOURCE_HASH_MISMATCH")
            if response_registry.registry_hash != manifest.m3.response_bundle.registry_hash:
                reasons.append("M3_RESPONSE_REGISTRY_HASH_MISMATCH")
        except (OSError, TypeError, ValueError):
            reasons.append("M3_REGISTRY_UNAVAILABLE")
        try:
            m4_path = self._path(manifest.m4.mapping_registry.path)
            if self._source_hash(m4_path) != manifest.m4.mapping_registry.source_sha256:
                reasons.append("M4_MAPPING_DESIGN_SOURCE_HASH_MISMATCH")
            m4_design = json.loads(m4_path.read_text(encoding="utf-8"))
            if not m4_design.get("production_mapping_enabled", False):
                reasons.append("M4_MAPPING_DESIGN_UNRESOLVED")
        except (OSError, json.JSONDecodeError, TypeError):
            reasons.append("M4_MAPPING_DESIGN_REGISTRY_UNAVAILABLE")

    def _validate_materialized_m3_binding(
        self, binding: M3ScientificBinding, reasons: list[str]
    ) -> None:
        try:
            from exp.exp2.artifacts.m3_scenario_bundle import M3ScenarioBundle

            path = self._path(binding.artifact_path)
            bundle = M3ScenarioBundle.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            reasons.append("M3_TYPED_SCENARIO_BUNDLE_UNAVAILABLE")
            return
        if bundle.bundle_id != binding.artifact_id or bundle.bundle_hash != binding.hash:
            reasons.append("M3_TYPED_SCENARIO_BUNDLE_IDENTITY_MISMATCH")
        if (
            bundle.action_registry_hash != binding.action_manifest.registry_hash
            or bundle.response_registry_hash != binding.response_bundle.registry_hash
        ):
            reasons.append("M3_TYPED_SCENARIO_BUNDLE_REGISTRY_LINEAGE_MISMATCH")
        if any(rule.formal_support_upgrade for rule in bundle.rules):
            reasons.append("M3_TYPED_SCENARIO_BUNDLE_SUPPORT_UPGRADE_FORBIDDEN")
        if any(
            rule.action_id != "A00" and rule.support_state != "SCENARIO_ASSUMPTION"
            for rule in bundle.rules
        ):
            reasons.append("M3_TYPED_SCENARIO_BUNDLE_SUPPORT_STATE_INVALID")
        if bundle.FINAL_TEST_ACCESS_COUNT != 0 or bundle.PAPER_FULL_RUN:
            reasons.append("M3_TYPED_SCENARIO_BUNDLE_FINAL_TEST_OR_PAPER_VIOLATION")

    def _validate_materialized_m4_binding(
        self, binding: M4ScientificBinding, reasons: list[str]
    ) -> None:
        try:
            from model.M4.residual_risk import ResidualRiskPolicy

            path = self._path(binding.risk_policy)
            payload = json.loads(path.read_text(encoding="utf-8"))
            artifact_hash = payload.pop("artifact_hash", None)
            policy = ResidualRiskPolicy.model_validate(payload["policy"])
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
            reasons.append("M4_TYPED_RISK_POLICY_ARTIFACT_UNAVAILABLE")
            return
        if artifact_hash != content_id(payload) or artifact_hash != binding.hash:
            reasons.append("M4_TYPED_RISK_POLICY_ARTIFACT_HASH_MISMATCH")
        if policy.policy_hash != binding.risk_policy_hash:
            reasons.append("M4_TYPED_RISK_POLICY_HASH_MISMATCH")
        if policy.policy_status is not binding.risk_policy_status:
            reasons.append("M4_TYPED_RISK_POLICY_STATUS_MISMATCH")
        if payload.get("FINAL_TEST_ACCESS_COUNT") != 0 or payload.get("PAPER_FULL_RUN"):
            reasons.append("M4_TYPED_RISK_POLICY_FINAL_TEST_OR_PAPER_VIOLATION")

    @staticmethod
    def _validate_unresolved_artifacts(
        manifest: ScientificArtifactManifest, reasons: list[str]
    ) -> None:
        for field_name, value in (
            ("M1_ARTIFACT", manifest.m1.artifact_id),
            ("M1_CHECKPOINT", manifest.m1.checkpoint),
            ("M1_SCHEMA", manifest.m1.schema_version),
            ("M1_HASH", manifest.m1.hash),
            ("M2_ARTIFACT", manifest.m2.artifact_id),
            ("M2_HASH", manifest.m2.hash),
            ("M3_ACTION_RESPONSE_ARTIFACT", manifest.m3.artifact_id),
            ("M3_HASH", manifest.m3.hash),
        ):
            if _required(value):
                reasons.append(f"{field_name}_REQUIRED")


__all__ = [
    "M2_COMPONENT_SCHEMA_ID",
    "M4ScientificGate",
    "M4ScientificGateResult",
    "M4ScientificGateStatus",
    "M4ScientificBinding",
    "ScientificArtifactManifest",
    "ScientificManifestStatus",
    "ScientificManifestValidationResult",
    "ScientificManifestValidator",
]
