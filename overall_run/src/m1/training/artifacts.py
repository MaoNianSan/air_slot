from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..adapter.feature_schema import M1FeatureSchema
from ..distribution import DiscreteBins, EmpiricalTailArtifact
from ..model import SingleLightweightGRU


@dataclass(frozen=True)
class M1ModelArtifact:
    model: SingleLightweightGRU
    feature_schema: M1FeatureSchema
    bins: Mapping[str, DiscreteBins]
    model_version: str
    artifact_hash: str
    pre_manifest_hash: str
    architecture: Mapping[str, object]
    metadata: Mapping[str, object]
    tail_artifacts: Mapping[str, EmpiricalTailArtifact]

    def validate_for_runtime(
        self,
        *,
        pre_manifest_hash: str,
        feature_schema: M1FeatureSchema,
    ) -> None:
        if self.pre_manifest_hash != pre_manifest_hash:
            raise ValueError("M1_CHECKPOINT_PRE_MANIFEST_MISMATCH")
        if self.feature_schema.schema_hash != feature_schema.schema_hash:
            raise ValueError("M1_CHECKPOINT_FEATURE_SCHEMA_MISMATCH")
