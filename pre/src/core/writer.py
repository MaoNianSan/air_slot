from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ..input import object_hash, write_json, write_parquet
from .contracts import ResumeContract
from .resume_contract import select_compatible_staging, write_resume_manifest


def dataframe_hash(frame: pd.DataFrame, key: list[str] | None = None) -> str:
    ordered = frame.copy()
    if key and all(column in ordered for column in key):
        ordered = ordered.sort_values(key, kind="mergesort")
    ordered = ordered.reset_index(drop=True)
    digest = hashlib.sha256()
    digest.update(object_hash({"columns": list(ordered.columns)}).encode("ascii"))
    if len(ordered):
        normalized = ordered.astype("string").fillna("<CORE_NULL>")
        hashes = pd.util.hash_pandas_object(normalized, index=False).values
        digest.update(hashes.tobytes())
    return digest.hexdigest()


def begin_staging(
    output_root: Path,
    *,
    resume: bool = False,
    resume_contract: ResumeContract | None = None,
    audit_root: Path | None = None,
) -> Path:
    output_root.parent.mkdir(parents=True, exist_ok=True)
    if resume and resume_contract is not None:
        selected, audit = select_compatible_staging(
            output_root, resume_contract, audit_root=audit_root
        )
        if selected is not None:
            reports = selected / "reports"
            reports.mkdir(parents=True, exist_ok=True)
            write_json(audit, reports / "staging_resume_audit.json")
            return selected
    staging = output_root.parent / f".{output_root.name}.staging-{uuid.uuid4().hex[:12]}"
    staging.mkdir(parents=True, exist_ok=False)
    if resume_contract is not None:
        write_resume_manifest(staging, resume_contract)
        if resume:
            _, audit = select_compatible_staging(
                output_root, resume_contract, audit_root=audit_root
            )
            audit["created_staging"] = str(staging)
            reports = staging / "reports"
            reports.mkdir(parents=True, exist_ok=True)
            write_json(audit, reports / "staging_resume_audit.json")
    return staging


def write_core_tables(
    staging: Path,
    tables: dict[str, pd.DataFrame],
    registry: list[dict[str, Any]],
    schema: dict[str, Any],
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name, frame in tables.items():
        persisted = frame.copy()
        persisted.attrs = {}
        write_parquet(persisted, staging / f"{name}.parquet")
        spec = schema["tables"].get(name, {})
        key = list(spec.get("key", []))
        hashes[name] = dataframe_hash(persisted, key)
    registry_path = staging / "column_registry.yaml"
    registry_path.write_text(
        yaml.safe_dump({"columns": registry}, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    hashes["column_registry"] = object_hash(registry)
    return hashes


def write_core_metadata(
    staging: Path,
    manifest: dict[str, Any],
    validation: dict[str, Any],
    readiness: dict[str, Any],
    cache_manifest: dict[str, Any],
    extraction_report: pd.DataFrame,
    report_markdown: str,
) -> None:
    write_json(manifest, staging / "pre_manifest.json")
    reports = staging / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    write_json(validation, reports / "core_validation.json")
    write_json(readiness, reports / "core_readiness.json")
    write_json(cache_manifest, reports / "core_cache_manifest.json")
    if not extraction_report.empty:
        write_parquet(extraction_report, reports / "state_vector_extraction.parquet")
    (reports / "PRE_CORE_RUN_REPORT.md").write_text(report_markdown, encoding="utf-8")
    write_json(
        {
            "status": "PASS" if validation.get("status") == "PASS" else "FAIL",
            "mode": manifest["mode"],
            "contract_id": manifest["contract_id"],
            "core_data_hash": manifest["core_data_hash"],
            "validation_status": validation.get("status"),
            "readiness_status": readiness.get("status"),
            "created_at": manifest["created_at"],
        },
        staging / "run_state.json",
    )


def publish_staging(staging: Path, output_root: Path, core_data_hash: str) -> str:
    if output_root.exists():
        manifest_path = output_root / "pre_manifest.json"
        existing = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        shutil.rmtree(staging)
        if existing.get("core_data_hash") == core_data_hash:
            return "REUSED_IDENTICAL_EXISTING"
        raise FileExistsError(f"CORE_OUTPUT_EXISTS_WITH_DIFFERENT_HASH={output_root}")
    os.replace(staging, output_root)
    return "PUBLISHED_NEW"
