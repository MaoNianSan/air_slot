from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pre.src.core.contracts import (
    CONTRACT_ID,
    RESEARCH_CODE_REVISION,
    SCHEMA_VERSION,
)
from pre.src.input import sha256_file

from ..contracts import PreBundleIdentity


class PreBundleValidationError(RuntimeError):
    pass


DIRECT_ARTIFACTS = {
    "episodes": "episodes.parquet",
    "events": "events.parquet",
    "calibration": "calibration.parquet",
    "evidence_audit": "evidence_audit.parquet",
    "column_registry": "column_registry.yaml",
    "observation_partition_manifest": (
        "observations/observation_partition_manifest.json"
    ),
    "membership_partition_manifest": (
        "observation_membership/observation_membership_partition_manifest.json"
    ),
}


@dataclass(frozen=True)
class ValidatedManifest:
    root: Path
    payload: dict[str, Any]
    identity: PreBundleIdentity


def _fail(code: str, detail: object = "") -> None:
    suffix = f":{detail}" if detail != "" else ""
    raise PreBundleValidationError(code + suffix)


def _published_root(root: Path) -> Path:
    resolved = root.resolve()
    publication_parent = resolved.parents[2].name.lower()
    if publication_parent in {"raw", "cache", "staging"} or any(
        ".staging" in part.lower() for part in resolved.parts
    ):
        _fail("PRE_UNPUBLISHED_BUNDLE", resolved)
    if resolved.name != CONTRACT_ID or resolved.parent.parent.name != "output_core":
        _fail("PRE_UNPUBLISHED_BUNDLE", resolved)
    return resolved


def _read_manifest(root: Path) -> tuple[Path, dict[str, Any]]:
    path = root / "pre_manifest.json"
    if not path.is_file():
        _fail("PRE_REQUIRED_ARTIFACT_MISSING", "pre_manifest")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("PRE_MANIFEST_HASH_MISMATCH", type(exc).__name__)
    if not isinstance(payload, dict):
        _fail("PRE_MANIFEST_HASH_MISMATCH", "NOT_MAPPING")
    return path, payload


def _identity(payload: dict[str, Any], manifest_hash: str, mode: str) -> PreBundleIdentity:
    if payload.get("contract_id") != CONTRACT_ID:
        _fail("PRE_CONTRACT_MISMATCH", payload.get("contract_id"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        _fail("PRE_SCHEMA_MISMATCH", payload.get("schema_version"))
    if payload.get("research_code_revision") != RESEARCH_CODE_REVISION:
        _fail("PRE_RESEARCH_REVISION_MISMATCH", payload.get("research_code_revision"))
    if payload.get("mode") != mode:
        _fail("PRE_UNPUBLISHED_BUNDLE", "MODE_PATH_MISMATCH")
    declared = payload.get("pre_manifest_hash")
    if declared and declared != manifest_hash:
        _fail("PRE_MANIFEST_HASH_MISMATCH")
    required = ("source_manifest_hash", "frozen_config_hash", "git_commit")
    missing = [key for key in required if not payload.get(key)]
    if missing:
        _fail("PRE_REQUIRED_ARTIFACT_MISSING", ",".join(missing))
    return PreBundleIdentity(
        contract_id=CONTRACT_ID,
        schema_version=SCHEMA_VERSION,
        research_code_revision=RESEARCH_CODE_REVISION,
        pre_manifest_hash=manifest_hash,
        source_manifest_hash=str(payload["source_manifest_hash"]),
        frozen_config_hash=str(payload["frozen_config_hash"]),
        git_commit=str(payload["git_commit"]),
        mode=mode,
    )


def _validate_direct_artifacts(root: Path, payload: dict[str, Any]) -> None:
    recorded = payload.get("file_hashes", {})
    for name, relative in DIRECT_ARTIFACTS.items():
        path = root / relative
        if not path.is_file():
            _fail("PRE_REQUIRED_ARTIFACT_MISSING", name)
        expected = recorded.get(name)
        if not expected or sha256_file(path) != expected:
            _fail("PRE_MANIFEST_HASH_MISMATCH", name)


def validate_manifest(root: str | Path) -> ValidatedManifest:
    published = _published_root(Path(root))
    manifest_path, payload = _read_manifest(published)
    manifest_hash = sha256_file(manifest_path)
    identity = _identity(payload, manifest_hash, published.parent.name)
    _validate_direct_artifacts(published, payload)
    return ValidatedManifest(published, payload, identity)
