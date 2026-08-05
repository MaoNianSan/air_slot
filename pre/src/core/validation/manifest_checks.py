from __future__ import annotations

from pathlib import Path
from typing import Any

from ...input import object_hash, sha256_file
from ..contracts import (
    CONTRACT_ID,
    RESEARCH_CODE_REVISION,
    SCHEMA_VERSION,
    contract_hashes,
    frozen_config_hash,
    git_metadata,
    implementation_hash,
    schema_hash,
)
from ..membership import MEMBERSHIP_PARTITION_MANIFEST_NAME


def check_manifest(
    manifest: dict[str, Any], cfg: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    missing = sorted(
        set(cfg["core_schema"].get("manifest_required", [])) - set(manifest)
    )
    identity_failures = [
        field
        for field, expected in {
            "contract_id": CONTRACT_ID,
            "schema_version": SCHEMA_VERSION,
            "research_code_revision": RESEARCH_CODE_REVISION,
        }.items()
        if manifest.get(field) != expected
    ]
    expected_hashes = {
        **contract_hashes(cfg),
        "core_schema_hash": schema_hash(cfg),
        "frozen_config_hash": frozen_config_hash(cfg),
        "source_schema_hash": object_hash(cfg.get("sources", {})),
    }
    hash_failures = [
        name for name, expected in expected_hashes.items() if manifest.get(name) != expected
    ]
    implementation = implementation_hash(cfg.get("project_root"))
    git = git_metadata(cfg.get("project_root"))
    warnings = []
    if manifest.get("implementation_hash") != implementation.get("hash"):
        warnings.append("IMPLEMENTATION_HASH_CHANGED_WARNING")
    if manifest.get("git_commit") != git.get("git_commit"):
        warnings.append("GIT_COMMIT_CHANGED_WARNING")
    if bool(manifest.get("git_dirty")) != bool(git.get("git_dirty")):
        warnings.append("GIT_DIRTY_STATUS_CHANGED_WARNING")
    return {
        "manifest_required_fields": {
            "status": "PASS" if not missing else "FAIL",
            "missing": missing,
        },
        "contract_identity": {
            "status": "PASS" if not identity_failures else "FAIL",
            "failures": identity_failures,
        },
        "contract_hashes": {
            "status": "PASS" if not hash_failures else "FAIL",
            "failures": sorted(set(hash_failures)),
            "provenance_warnings": warnings,
        },
    }


def check_file_hashes(
    root: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    failures = []
    special = {
        "column_registry": root / "column_registry.yaml",
        "observation_partition_manifest": root
        / "observations"
        / "observation_partition_manifest.json",
        "membership_partition_manifest": root
        / "observation_membership"
        / MEMBERSHIP_PARTITION_MANIFEST_NAME,
    }
    for name, expected in manifest.get("file_hashes", {}).items():
        path = special.get(name, root / f"{name}.parquet")
        if not path.exists() or sha256_file(path) != expected:
            failures.append(name)
    return {"status": "PASS" if not failures else "FAIL", "failures": failures}
