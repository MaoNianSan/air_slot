from __future__ import annotations

import json
import os
import shutil
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd

from .input import object_hash, sha256_file, write_json
from .pipeline_config import load_config
from .pipeline_publish import _artifact_registry, _output_hashes
from .target_contract import target_contract_metadata


SCIENTIFIC_TABLES = (
    "episodes.parquet",
    "snapshots.parquet",
    "calibration.parquet",
    "rules.parquet",
    "evidence_audit.parquet",
)


def _profile_scientific_payload(cfg: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(cfg)
    for key in (
        "mode", "project_root", "data_root", "output_root", "intermediate_root",
        "cache_root", "config_hash", "raw_hashes", "profile_contract",
    ):
        payload.pop(key, None)
    paths = payload.get("paths", {})
    paths.pop("output_root", None)
    paths.pop("intermediate_root", None)
    runtime = payload.get("runtime", {})
    for key in (
        "state_workers", "rebuild_cache", "requested_n_jobs", "resolved_n_jobs",
        "outer_workers", "inner_model_threads", "parallel_backend",
        "task_partition_version", "task_seed_strategy", "task_seed_hash",
    ):
        runtime.pop(key, None)
    for key in (
        "requested_n_jobs", "resolved_n_jobs", "outer_workers", "inner_model_threads",
        "parallel_backend", "task_partition_version", "task_seed_strategy", "task_seed_hash",
    ):
        payload.pop(key, None)
    return payload


def _verify_registry(root: Path) -> dict[str, Any]:
    registry_path = root / "artifact_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    stale: list[str] = []
    for entry in registry.get("artifacts", []):
        path = root / str(entry["relative_path"])
        if not path.is_file() or sha256_file(path) != entry.get("sha256"):
            stale.append(str(entry["relative_path"]))
    if stale:
        raise ValueError("PROFILE_MIGRATION_SOURCE_REGISTRY_STALE:" + ",".join(stale[:20]))
    return registry


def _copy_file(source: str, target: str) -> str:
    source_path = Path(source)
    target_path = Path(target)
    if source_path.stat().st_size >= 1 << 20:
        os.link(source_path, target_path)
        return str(target_path)
    return shutil.copy2(source_path, target_path)


def migrate_legacy_profile(
    cfg: dict[str, Any],
    *,
    source_mode: str = "adapt_full",
) -> dict[str, Any]:
    if source_mode != "adapt_full" or cfg.get("mode") != "acceptance_23d":
        raise ValueError("PROFILE_MIGRATION_ONLY_ADAPT_FULL_TO_ACCEPTANCE_23D")
    started = time.monotonic()
    project_root = Path(cfg["project_root"])
    source = project_root / "output" / source_mode
    target = Path(cfg["output_root"])
    if not source.is_dir():
        raise FileNotFoundError(f"PROFILE_MIGRATION_SOURCE_MISSING:{source}")
    if target.exists() and any(target.iterdir()):
        raise ValueError(f"PROFILE_MIGRATION_TARGET_NOT_EMPTY:{target}")

    source_cfg = load_config(mode=source_mode)
    source_registry = _verify_registry(source)
    source_registry_hash = sha256_file(source / "artifact_registry.json")
    if object_hash(_profile_scientific_payload(source_cfg)) != object_hash(
        _profile_scientific_payload(cfg)
    ):
        raise ValueError("PROFILE_MIGRATION_SCIENTIFIC_PAYLOAD_MISMATCH")

    source_summary = json.loads((source / "run_summary.json").read_text(encoding="utf-8"))
    source_manifest = json.loads(
        (source / "manifests" / "pre_manifest.json").read_text(encoding="utf-8")
    )
    expected_manifest = pd.read_csv(
        project_root.parent / "data" / "manifests" / "current_data_adapt_full_manifest.csv"
    )
    expected_dates = sorted(pd.to_datetime(expected_manifest["anchor_date"]).dt.strftime("%Y-%m-%d"))
    if source_summary.get("status") != "PASS" or source_summary.get("input_anchor_days") != 23:
        raise ValueError("PROFILE_MIGRATION_SOURCE_NOT_ACCEPTED_23D")
    if sorted(source_manifest.get("complete_state_dates", [])) != expected_dates:
        raise ValueError("PROFILE_MIGRATION_SOURCE_CALENDAR_MISMATCH")

    source_hashes = {name: sha256_file(source / name) for name in SCIENTIFIC_TABLES}
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True, copy_function=_copy_file)

    raw_inventory = pd.read_parquet(target / "manifests" / "raw_inventory.parquet")
    cfg["raw_hashes"] = {
        str(Path(row.absolute_path).resolve()): str(row.sha256)
        for row in raw_inventory.itertuples(index=False)
        if getattr(row, "absolute_path", None)
    }
    now = pd.Timestamp.now(tz="UTC")
    run_id = f"pre-acceptance_23d-migrated-{now.strftime('%Y%m%dT%H%M%SZ')}-{cfg['config_hash'][:8]}"
    profile = dict(cfg.get("profile_contract", {}))
    provenance = {
        "profile_migration_status": "PASS",
        "profile_migration_contract": "ADAPT_FULL_TO_ACCEPTANCE_23D_V1_20260731",
        "legacy_source_mode": source_mode,
        "legacy_source_run_id": source_summary.get("run_id"),
        "legacy_source_registry_sha256": source_registry_hash,
        "scientific_tables_recomputed": False,
        **profile,
    }

    summary_path = target / "run_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update({
        "run_id": run_id,
        "mode": "acceptance_23d",
        "config_hash": cfg["config_hash"],
        "status": "PASS",
        "scientific_compute_elapsed_seconds": source_summary.get("elapsed_seconds"),
        "migration_elapsed_seconds": float(time.monotonic() - started),
        "finished_at": now,
        **provenance,
    })
    write_json(summary, summary_path)

    manifest_path = target / "manifests" / "pre_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({
        "run_mode": "acceptance_23d",
        "config_hash": cfg["config_hash"],
        "created_at": now,
        **provenance,
    })
    manifest["output_hashes"] = _output_hashes(target)
    write_json(manifest, manifest_path)

    acceptance_path = target / "acceptance.json"
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    acceptance.update({
        **target_contract_metadata(cfg),
        "formal_target_contract": "PASS",
        "config_hash": cfg["config_hash"],
        **provenance,
    })
    write_json(acceptance, acceptance_path)

    state = {
        "run_id": run_id,
        "mode": "acceptance_23d",
        "status": "PASS",
        "current_stage": "profile_migration_complete",
        "config_hash": cfg["config_hash"],
        "updated_at": now,
        **provenance,
    }
    write_json(state, target / "run_state.json")

    target_hashes = {name: sha256_file(target / name) for name in SCIENTIFIC_TABLES}
    if target_hashes != source_hashes:
        raise ValueError("PROFILE_MIGRATION_SCIENTIFIC_TABLE_HASH_MISMATCH")
    if sha256_file(source / "artifact_registry.json") != source_registry_hash:
        raise ValueError("PROFILE_MIGRATION_SOURCE_REGISTRY_MODIFIED")

    audit = {
        "status": "PASS",
        "contract": provenance["profile_migration_contract"],
        "source": str(source.resolve()),
        "target": str(target.resolve()),
        "source_registry_sha256": source_registry_hash,
        "source_registered_artifact_count": len(source_registry.get("artifacts", [])),
        "scientific_table_hashes": source_hashes,
        "scientific_tables_recomputed": False,
        "migration_elapsed_seconds": float(time.monotonic() - started),
    }
    write_json(audit, target / "reports" / "profile_migration_audit.json")
    write_json(_artifact_registry(target, cfg, "profile_migration"), target / "artifact_registry.json")
    _verify_registry(target)
    return {**audit, "run_id": run_id, "validation": "PASS"}
