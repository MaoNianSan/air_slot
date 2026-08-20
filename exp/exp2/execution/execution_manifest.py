"""Immutable manifest contracts for a future Exp2 scientific execution."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from model.common.identity import content_id

from ..variants import EXP2_VARIANT_IDS


SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"


class ExecutionReadinessStatus(str, Enum):
    READY = "READY"
    BLOCKED_MISSING_ARTIFACT = "BLOCKED_MISSING_ARTIFACT"
    BLOCKED_UNSUPPORTED_MAPPING = "BLOCKED_UNSUPPORTED_MAPPING"


class ArtifactKind(str, Enum):
    M1 = "M1"
    M2 = "M2"
    M3 = "M3"
    M4 = "M4"


class ArtifactReference(BaseModel):
    """One exact artifact identity; no path, version, or hash defaults."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_kind: ArtifactKind
    path: str = Field(min_length=1)
    artifact_version: str = Field(min_length=1)
    artifact_hash: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def explicit_identity(self):
        if self.path.strip().upper() == "UNSET":
            raise ValueError("EXP2_ARTIFACT_PATH_UNSET")
        if self.artifact_version.strip().upper() == "UNSET":
            raise ValueError("EXP2_ARTIFACT_VERSION_UNSET")
        return self


class Exp2ExecutionManifest(BaseModel):
    """All identities required before an Exp2 variant can be bound."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "AIR_SLOT_EXP2_EXECUTION_MANIFEST_V1"
    dataset_id: str = Field(min_length=1)
    split: str = Field(min_length=1)
    seed: int
    m1_artifact: ArtifactReference
    m2_artifact: ArtifactReference
    m3_artifact: ArtifactReference
    m4_artifact: ArtifactReference
    variant_id: str = Field(min_length=1)
    config_hash: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def exact_artifact_slots_and_variant(self):
        expected = (
            (self.m1_artifact, ArtifactKind.M1),
            (self.m2_artifact, ArtifactKind.M2),
            (self.m3_artifact, ArtifactKind.M3),
            (self.m4_artifact, ArtifactKind.M4),
        )
        if any(reference.artifact_kind is not kind for reference, kind in expected):
            raise ValueError("EXP2_EXECUTION_MANIFEST_ARTIFACT_SLOT_MISMATCH")
        if self.variant_id not in EXP2_VARIANT_IDS:
            raise ValueError(f"EXP2_EXECUTION_VARIANT_UNKNOWN:{self.variant_id}")
        if self.dataset_id.strip().upper() == "UNSET":
            raise ValueError("EXP2_EXECUTION_DATASET_UNSET")
        if self.split.strip().upper() == "UNSET":
            raise ValueError("EXP2_EXECUTION_SPLIT_UNSET")
        return self

    @property
    def manifest_hash(self) -> str:
        return content_id(
            self.model_dump(mode="json", exclude={"manifest_hash"})
        )

    @property
    def fixed_binding_identity(self) -> tuple:
        """Identity that must be identical for every representation variant."""

        return (
            self.dataset_id,
            self.split,
            self.seed,
            self.m1_artifact,
            self.m2_artifact,
            self.m3_artifact,
            self.m4_artifact,
            self.config_hash,
        )

    def assert_variant_compatible(self, other: "Exp2ExecutionManifest") -> None:
        if not isinstance(other, Exp2ExecutionManifest):
            raise TypeError("EXP2_EXECUTION_MANIFEST_REQUIRED")
        if self.fixed_binding_identity != other.fixed_binding_identity:
            raise ValueError("EXP2_VARIANT_FIXED_BINDING_IDENTITY_MISMATCH")


def validate_variant_manifests(
    manifests: tuple[Exp2ExecutionManifest, ...],
) -> tuple[Exp2ExecutionManifest, ...]:
    if not manifests:
        raise ValueError("EXP2_EXECUTION_MANIFEST_SET_EMPTY")
    variants = tuple(item.variant_id for item in manifests)
    if len(variants) != len(set(variants)):
        raise ValueError("EXP2_EXECUTION_MANIFEST_VARIANT_DUPLICATE")
    anchor = manifests[0]
    for manifest in manifests[1:]:
        anchor.assert_variant_compatible(manifest)
    return manifests


__all__ = [
    "ArtifactKind",
    "ArtifactReference",
    "ExecutionReadinessStatus",
    "Exp2ExecutionManifest",
    "SHA256_PATTERN",
    "validate_variant_manifests",
]
