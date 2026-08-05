from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from pre.src.input import sha256_file

from ..contracts import PreBundleIdentity
from .manifest_validator import PreBundleValidationError, validate_manifest


@dataclass(frozen=True)
class PublishedPreBundle:
    root: Path
    identity: PreBundleIdentity
    manifest: dict[str, Any]
    episodes: pd.DataFrame
    events: pd.DataFrame
    observations: pd.DataFrame
    observation_membership: pd.DataFrame
    calibration: pd.DataFrame
    evidence_audit: pd.DataFrame
    column_registry: tuple[dict[str, Any], ...]


def _partition_frame(root: Path, manifest_name: str) -> pd.DataFrame:
    manifest_path = root / manifest_name
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    pieces: list[pd.DataFrame] = []
    for key, record in sorted(payload.get("partitions", {}).items()):
        status = record.get("status")
        if status == "PASS_EMPTY":
            continue
        if status != "PASS" or not record.get("relative_path"):
            raise PreBundleValidationError(f"PRE_UNPUBLISHED_BUNDLE:{key}:{status}")
        path = (root / str(record["relative_path"])).resolve()
        if root.resolve() not in path.parents:
            raise PreBundleValidationError(f"PRE_UNPUBLISHED_BUNDLE:{key}:PATH_ESCAPE")
        if not path.is_file():
            raise PreBundleValidationError(f"PRE_REQUIRED_ARTIFACT_MISSING:{key}")
        if sha256_file(path) != record.get("file_hash"):
            raise PreBundleValidationError(f"PRE_MANIFEST_HASH_MISMATCH:{key}")
        pieces.append(pd.read_parquet(path))
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def _registry(path: Path) -> tuple[dict[str, Any], ...]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = payload.get("columns", [])
    if not isinstance(rows, list):
        raise PreBundleValidationError("PRE_REQUIRED_ARTIFACT_MISSING:column_registry")
    return tuple(dict(row) for row in rows)


def load_published_bundle(root: str | Path) -> PublishedPreBundle:
    validated = validate_manifest(root)
    base = validated.root
    return PublishedPreBundle(
        root=base,
        identity=validated.identity,
        manifest=validated.payload,
        episodes=pd.read_parquet(base / "episodes.parquet"),
        events=pd.read_parquet(base / "events.parquet"),
        observations=_partition_frame(
            base / "observations", "observation_partition_manifest.json"
        ),
        observation_membership=_partition_frame(
            base / "observation_membership",
            "observation_membership_partition_manifest.json",
        ),
        calibration=pd.read_parquet(base / "calibration.parquet"),
        evidence_audit=pd.read_parquet(base / "evidence_audit.parquet"),
        column_registry=_registry(base / "column_registry.yaml"),
    )
