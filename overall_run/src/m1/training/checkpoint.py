from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

import torch

from ..adapter.feature_schema import M1FeatureSchema
from ..distribution import DiscreteBins, EmpiricalTailArtifact
from ..model import SingleLightweightGRU
from .artifacts import M1ModelArtifact


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bin_payload(bins: Mapping[str, DiscreteBins]) -> dict[str, object]:
    return {
        name: {
            "lower_minutes": list(value.lower_minutes),
            "upper_minutes": list(value.upper_minutes),
        }
        for name, value in sorted(bins.items())
    }


def _schema(payload: Mapping[str, object]) -> M1FeatureSchema:
    return M1FeatureSchema(
        schema_version=str(payload["schema_version"]),
        value_features=tuple(payload["value_features"]),
        mask_features=tuple(payload["mask_features"]),
        age_features=tuple(payload["age_features"]),
        stale_features=tuple(payload["stale_features"]),
        fallback_features=tuple(payload["fallback_features"]),
        stage_features=tuple(payload["stage_features"]),
        static_features=tuple(payload["static_features"]),
        final_feature_order=tuple(payload["final_feature_order"]),
        schema_hash=str(payload["schema_hash"]),
    )


def save_checkpoint(
    path: str | Path,
    *,
    state_dict: Mapping[str, torch.Tensor],
    model_architecture: Mapping[str, object],
    feature_schema: M1FeatureSchema,
    bins: Mapping[str, DiscreteBins],
    pre_manifest_hash: str,
    split_definition: Mapping[str, object],
    training_config: Mapping[str, object],
    random_seed: int,
    best_epoch: int,
    validation_metrics: Mapping[str, float],
    source_commit: str,
    artifact_version: str,
    tail_artifacts: Mapping[str, EmpiricalTailArtifact] | None = None,
) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    torch.save(dict(state_dict), target)
    metadata = {
        "model_architecture": dict(model_architecture),
        "feature_schema": feature_schema.as_dict(),
        "feature_schema_hash": feature_schema.schema_hash,
        "bin_definitions": _bin_payload(bins),
        "pre_manifest_hash": pre_manifest_hash,
        "split_definition": dict(split_definition),
        "training_config": dict(training_config),
        "random_seed": int(random_seed),
        "best_epoch": int(best_epoch),
        "validation_metrics": dict(validation_metrics),
        "source_commit": source_commit,
        "artifact_version": artifact_version,
        "state_dict_hash": _sha256(target),
        "tail_artifacts": {
            name: {
                "target_name": artifact.target_name,
                "overflow_lower_bound": artifact.overflow_lower_bound,
                "training_tail_values": list(artifact.training_tail_values),
                "tail_sample_count": artifact.tail_sample_count,
                "artifact_version": artifact.artifact_version,
                "source_split": artifact.source_split,
                "minimum_tail_count": artifact.minimum_tail_count,
            }
            for name, artifact in sorted((tail_artifacts or {}).items())
        },
    }
    encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8")
    metadata["artifact_hash"] = hashlib.sha256(encoded).hexdigest()
    target.with_suffix(target.suffix + ".manifest.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return str(metadata["artifact_hash"])


def load_checkpoint(
    path: str | Path,
    *,
    expected_pre_manifest_hash: str,
    expected_feature_schema: M1FeatureSchema,
    expected_bins: Mapping[str, DiscreteBins] | None = None,
) -> M1ModelArtifact:
    target = Path(path)
    manifest_path = target.with_suffix(target.suffix + ".manifest.json")
    if not target.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("M1_MODEL_ARTIFACT_MISSING")
    metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _sha256(target) != metadata.get("state_dict_hash"):
        raise ValueError("M1_CHECKPOINT_ARTIFACT_HASH_MISMATCH")
    declared_hash = metadata.get("artifact_hash")
    hash_payload = {key: value for key, value in metadata.items() if key != "artifact_hash"}
    encoded = json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if declared_hash != hashlib.sha256(encoded).hexdigest():
        raise ValueError("M1_CHECKPOINT_ARTIFACT_HASH_MISMATCH")
    if metadata.get("pre_manifest_hash") != expected_pre_manifest_hash:
        raise ValueError("M1_CHECKPOINT_PRE_MANIFEST_MISMATCH")
    if metadata.get("feature_schema_hash") != expected_feature_schema.schema_hash:
        raise ValueError("M1_CHECKPOINT_FEATURE_SCHEMA_MISMATCH")
    if expected_bins is not None and metadata.get("bin_definitions") != _bin_payload(expected_bins):
        raise ValueError("M1_CHECKPOINT_BIN_MISMATCH")
    architecture = dict(metadata.get("model_architecture", {}))
    if architecture.get("type") != "single_lightweight_gru" or int(architecture.get("layers", 0)) != 1:
        raise ValueError("M1_CHECKPOINT_ARCHITECTURE_MISMATCH")
    schema = _schema(metadata["feature_schema"])
    bins = {
        name: DiscreteBins(
            tuple(value["lower_minutes"]),
            tuple(value["upper_minutes"]),
        )
        for name, value in metadata["bin_definitions"].items()
    }
    model = SingleLightweightGRU(
        len(schema.final_feature_order),
        {name: value.count for name, value in bins.items()},
        hidden_size=int(architecture["hidden_size"]),
    )
    model.load_state_dict(torch.load(target, map_location="cpu", weights_only=True))
    tail_artifacts = {
        name: EmpiricalTailArtifact(
            target_name=str(value["target_name"]),
            overflow_lower_bound=float(value["overflow_lower_bound"]),
            training_tail_values=tuple(float(item) for item in value["training_tail_values"]),
            tail_sample_count=int(value["tail_sample_count"]),
            artifact_version=str(value["artifact_version"]),
            source_split=str(value["source_split"]),
            minimum_tail_count=int(value["minimum_tail_count"]),
        )
        for name, value in metadata.get("tail_artifacts", {}).items()
    }
    return M1ModelArtifact(
        model=model,
        feature_schema=schema,
        bins=bins,
        model_version=str(metadata["artifact_version"]),
        artifact_hash=str(declared_hash),
        pre_manifest_hash=str(metadata["pre_manifest_hash"]),
        architecture=architecture,
        metadata=metadata,
        tail_artifacts=tail_artifacts,
    )
