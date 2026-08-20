"""Strict artifact loading for the future Exp2 execution binding."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from model.M4.residual_risk import RiskPolicyStatus
from model.common.errors import ContractError
from model.common.identity import content_id
from model.common.monetary_system import MonetaryMappingStatus

from ..representation import (
    ConsequenceRepresentationAdapter,
    ScenarioRepresentationAdapter,
)
from ..variants import EXP2A_JOINT, EXP2B_COMPONENT
from .execution_manifest import (
    ArtifactKind,
    ArtifactReference,
    ExecutionReadinessStatus,
    Exp2ExecutionManifest,
    SHA256_PATTERN,
)


ARTIFACT_SCHEMA_VERSION = "AIR_SLOT_EXP2_EXECUTION_ARTIFACT_V1"


class ArtifactScope(str, Enum):
    SCIENTIFIC = "SCIENTIFIC"
    TEST_ONLY_SMOKE = "TEST_ONLY_SMOKE"


class Exp2ExecutionBlocked(RuntimeError):
    """A non-recovering readiness failure with an explicit allowed status."""

    def __init__(
        self,
        status: ExecutionReadinessStatus,
        *,
        artifact_kind: ArtifactKind,
        reason: str,
    ):
        if status is ExecutionReadinessStatus.READY:
            raise ValueError("EXP2_BLOCKED_EXCEPTION_CANNOT_BE_READY")
        self.status = status
        self.artifact_kind = artifact_kind
        self.reason = reason
        super().__init__(f"{status.value}:{artifact_kind.value}:{reason}")


class ArtifactEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    artifact_kind: ArtifactKind
    artifact_version: str = Field(min_length=1)
    artifact_hash: str = Field(pattern=SHA256_PATTERN)
    artifact_scope: ArtifactScope = ArtifactScope.SCIENTIFIC
    payload: dict[str, Any]

    @model_validator(mode="after")
    def valid_envelope(self):
        if self.schema_version != ARTIFACT_SCHEMA_VERSION:
            raise ValueError("EXP2_ARTIFACT_SCHEMA_VERSION_MISMATCH")
        if not self.payload:
            raise ValueError("EXP2_ARTIFACT_PAYLOAD_EMPTY")
        if content_id(self.payload) != self.artifact_hash:
            raise ValueError("EXP2_ARTIFACT_PAYLOAD_HASH_MISMATCH")
        return self


class CutoffProvenance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_node_id: str = Field(min_length=1)
    decision_time_utc: datetime
    information_cutoff_utc: datetime
    availability_rule: str = Field(min_length=1)
    source_manifest_hash: str = Field(pattern=SHA256_PATTERN)

    @field_validator("decision_time_utc", "information_cutoff_utc")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("EXP2_CUTOFF_TIMESTAMP_TIMEZONE_REQUIRED")
        return value

    @model_validator(mode="after")
    def no_future_cutoff(self):
        if self.information_cutoff_utc > self.decision_time_utc:
            raise ValueError("EXP2_M1_FUTURE_INFORMATION_CUTOFF")
        return self


class CULineage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    registry_id: str = Field(min_length=1)
    registry_hash: str = Field(pattern=SHA256_PATTERN)
    freeze_id: str = Field(min_length=1)
    reference_period: str = Field(min_length=1)

    @model_validator(mode="after")
    def no_unset_lineage(self):
        values = (self.registry_id, self.freeze_id, self.reference_period)
        if any(value.strip().upper() == "UNSET" for value in values):
            raise ValueError("EXP2_M2_CU_LINEAGE_UNSET")
        return self


class M1ArtifactPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scenarios: tuple[dict[str, Any], ...] = Field(min_length=1)
    cutoff_provenance: CutoffProvenance


class M2ArtifactPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    consequences: tuple[dict[str, Any], ...] = Field(min_length=1)
    cu_lineage: CULineage


class M3ArtifactPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action_ids: tuple[str, ...] = Field(min_length=1)
    action_registry_hash: str = Field(pattern=SHA256_PATTERN)
    response_registry_hash: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def unique_actions(self):
        if len(self.action_ids) != len(set(self.action_ids)):
            raise ValueError("EXP2_M3_ACTION_SET_DUPLICATE")
        if any(not item.strip() or item.strip().upper() == "UNSET" for item in self.action_ids):
            raise ValueError("EXP2_M3_ACTION_ID_UNSET")
        return self


class M4ArtifactPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    monetary_mapping_hash: str = Field(pattern=SHA256_PATTERN)
    monetary_mapping_status: MonetaryMappingStatus
    risk_policy_hash: str = Field(pattern=SHA256_PATTERN)
    risk_policy_status: RiskPolicyStatus


class LoadedM1Artifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: ArtifactReference
    scenarios: tuple[dict[str, Any], ...]
    cutoff_provenance: CutoffProvenance
    scenario_hash: str = Field(pattern=SHA256_PATTERN)


class LoadedM2Artifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: ArtifactReference
    consequences: tuple[dict[str, Any], ...]
    cu_lineage: CULineage
    consequence_hash: str = Field(pattern=SHA256_PATTERN)


class LoadedM3Artifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: ArtifactReference
    action_ids: tuple[str, ...]
    action_registry_hash: str = Field(pattern=SHA256_PATTERN)
    response_registry_hash: str = Field(pattern=SHA256_PATTERN)


class LoadedM4Artifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: ArtifactReference
    monetary_mapping_hash: str = Field(pattern=SHA256_PATTERN)
    monetary_mapping_status: MonetaryMappingStatus
    risk_policy_hash: str = Field(pattern=SHA256_PATTERN)
    risk_policy_status: RiskPolicyStatus


class Exp2LoadedArtifacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ExecutionReadinessStatus
    m1: LoadedM1Artifact
    m2: LoadedM2Artifact
    m3: LoadedM3Artifact
    m4: LoadedM4Artifact

    @model_validator(mode="after")
    def ready_only(self):
        if self.status is not ExecutionReadinessStatus.READY:
            raise ValueError("EXP2_LOADED_ARTIFACT_SET_MUST_BE_READY")
        return self


class Exp2ArtifactLoader:
    """Load only identity-matching artifacts; never synthesize a default."""

    def __init__(
        self,
        *,
        artifact_root: Path,
        execution_scope: ArtifactScope = ArtifactScope.SCIENTIFIC,
    ):
        self.artifact_root = Path(artifact_root).resolve()
        self.execution_scope = ArtifactScope(execution_scope)

    def _path(self, reference: ArtifactReference) -> Path:
        path = Path(reference.path)
        return path.resolve() if path.is_absolute() else (self.artifact_root / path).resolve()

    def _read_envelope(self, reference: ArtifactReference) -> ArtifactEnvelope:
        path = self._path(reference)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            envelope = ArtifactEnvelope.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise Exp2ExecutionBlocked(
                ExecutionReadinessStatus.BLOCKED_MISSING_ARTIFACT,
                artifact_kind=reference.artifact_kind,
                reason=f"ARTIFACT_UNAVAILABLE_OR_INVALID:{type(exc).__name__}",
            ) from exc
        if envelope.artifact_kind is not reference.artifact_kind:
            self._missing(reference, "ARTIFACT_KIND_MISMATCH")
        if envelope.artifact_version != reference.artifact_version:
            self._missing(reference, "ARTIFACT_VERSION_MISMATCH")
        if envelope.artifact_hash != reference.artifact_hash:
            self._missing(reference, "ARTIFACT_HASH_MISMATCH")
        if (
            self.execution_scope is ArtifactScope.SCIENTIFIC
            and envelope.artifact_scope is ArtifactScope.TEST_ONLY_SMOKE
        ):
            status = (
                ExecutionReadinessStatus.BLOCKED_UNSUPPORTED_MAPPING
                if reference.artifact_kind is ArtifactKind.M4
                else ExecutionReadinessStatus.BLOCKED_MISSING_ARTIFACT
            )
            raise Exp2ExecutionBlocked(
                status,
                artifact_kind=reference.artifact_kind,
                reason="TEST_ONLY_SMOKE_ARTIFACT_REJECTED_BY_PRODUCTION",
            )
        if (
            self.execution_scope is ArtifactScope.TEST_ONLY_SMOKE
            and envelope.artifact_scope is not ArtifactScope.TEST_ONLY_SMOKE
        ):
            raise Exp2ExecutionBlocked(
                ExecutionReadinessStatus.BLOCKED_MISSING_ARTIFACT,
                artifact_kind=reference.artifact_kind,
                reason="SMOKE_REQUIRES_TEST_ONLY_SMOKE_ARTIFACT",
            )
        return envelope

    @staticmethod
    def _missing(reference: ArtifactReference, reason: str):
        raise Exp2ExecutionBlocked(
            ExecutionReadinessStatus.BLOCKED_MISSING_ARTIFACT,
            artifact_kind=reference.artifact_kind,
            reason=reason,
        )

    def load_m1(self, reference: ArtifactReference) -> LoadedM1Artifact:
        envelope = self._read_envelope(reference)
        try:
            payload = M1ArtifactPayload.model_validate(envelope.payload)
            adapter = ScenarioRepresentationAdapter(
                payload.scenarios,
                artifact_version=reference.artifact_version,
            )
            joint = adapter.transform(EXP2A_JOINT)
        except (ContractError, TypeError, ValueError) as exc:
            self._missing(reference, f"M1_CONTRACT_INVALID:{type(exc).__name__}")
        return LoadedM1Artifact(
            reference=reference,
            scenarios=payload.scenarios,
            cutoff_provenance=payload.cutoff_provenance,
            scenario_hash=joint.source_scenario_hash,
        )

    def load_m2(self, reference: ArtifactReference) -> LoadedM2Artifact:
        envelope = self._read_envelope(reference)
        try:
            payload = M2ArtifactPayload.model_validate(envelope.payload)
            adapter = ConsequenceRepresentationAdapter(
                payload.consequences,
                artifact_version=reference.artifact_version,
            )
            component = adapter.transform(EXP2B_COMPONENT)
        except (ContractError, TypeError, ValueError) as exc:
            self._missing(reference, f"M2_CONTRACT_INVALID:{type(exc).__name__}")
        return LoadedM2Artifact(
            reference=reference,
            consequences=payload.consequences,
            cu_lineage=payload.cu_lineage,
            consequence_hash=component.source_artifact_hash,
        )

    def load_m3(self, reference: ArtifactReference) -> LoadedM3Artifact:
        envelope = self._read_envelope(reference)
        try:
            payload = M3ArtifactPayload.model_validate(envelope.payload)
        except ValueError as exc:
            self._missing(reference, f"M3_CONTRACT_INVALID:{type(exc).__name__}")
        return LoadedM3Artifact(reference=reference, **payload.model_dump())

    def load_m4(self, reference: ArtifactReference) -> LoadedM4Artifact:
        envelope = self._read_envelope(reference)
        try:
            payload = M4ArtifactPayload.model_validate(envelope.payload)
        except ValueError as exc:
            self._missing(reference, f"M4_CONTRACT_INVALID:{type(exc).__name__}")
        required_mapping_status = (
            MonetaryMappingStatus.TEST_ONLY
            if self.execution_scope is ArtifactScope.TEST_ONLY_SMOKE
            else MonetaryMappingStatus.FROZEN
        )
        required_policy_status = (
            RiskPolicyStatus.TEST_ONLY
            if self.execution_scope is ArtifactScope.TEST_ONLY_SMOKE
            else RiskPolicyStatus.FROZEN
        )
        if (
            payload.monetary_mapping_status is not required_mapping_status
            or payload.risk_policy_status is not required_policy_status
        ):
            raise Exp2ExecutionBlocked(
                ExecutionReadinessStatus.BLOCKED_UNSUPPORTED_MAPPING,
                artifact_kind=ArtifactKind.M4,
                reason=(
                    "M4_MAPPING_OR_POLICY_STATUS_INVALID_FOR_EXECUTION_SCOPE:"
                    f"{self.execution_scope.value}:"
                    f"{payload.monetary_mapping_status.value}:"
                    f"{payload.risk_policy_status.value}"
                ),
            )
        return LoadedM4Artifact(reference=reference, **payload.model_dump())

    def load_all(self, manifest: Exp2ExecutionManifest) -> Exp2LoadedArtifacts:
        if not isinstance(manifest, Exp2ExecutionManifest):
            raise TypeError("EXP2_EXECUTION_MANIFEST_REQUIRED")
        return Exp2LoadedArtifacts(
            status=ExecutionReadinessStatus.READY,
            m1=self.load_m1(manifest.m1_artifact),
            m2=self.load_m2(manifest.m2_artifact),
            m3=self.load_m3(manifest.m3_artifact),
            m4=self.load_m4(manifest.m4_artifact),
        )


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "ArtifactScope",
    "ArtifactEnvelope",
    "CULineage",
    "CutoffProvenance",
    "Exp2ArtifactLoader",
    "Exp2ExecutionBlocked",
    "Exp2LoadedArtifacts",
    "LoadedM1Artifact",
    "LoadedM2Artifact",
    "LoadedM3Artifact",
    "LoadedM4Artifact",
    "M1ArtifactPayload",
    "M2ArtifactPayload",
    "M3ArtifactPayload",
    "M4ArtifactPayload",
]
