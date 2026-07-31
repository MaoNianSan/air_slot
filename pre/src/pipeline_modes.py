from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .input import sha256_file, write_json, write_parquet
from .pipeline_config import _ensure_dirs
from .pipeline_diagnostics import _formal_frame, _missingness_report
from .pipeline_publish import (
    _artifact_registry,
    _enrich_contract,
    _output_hashes,
    _validate_published_target_metadata,
    _write_bundle,
    _write_fast_manifest,
)
from .target_contract import target_contract_metadata
from .validate import PreBundle, load_bundle, readiness, validate_bundle


def validate_existing(cfg: dict[str, Any]) -> dict[str, Any]:
    bundle = load_bundle(cfg["output_root"])
    result = validate_bundle(bundle, cfg)
    _validate_published_target_metadata(cfg["output_root"], cfg)
    registry_path = cfg["output_root"] / "artifact_registry.json"
    if not registry_path.exists():
        raise FileNotFoundError(f"missing artifact registry: {registry_path}")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    stale = []
    for item in registry.get("artifacts", []):
        path = cfg["output_root"] / item["relative_path"]
        if not path.exists() or sha256_file(path) != item["sha256"]:
            stale.append(item["relative_path"])
    if stale:
        raise ValueError("STALE_ARTIFACT:" + ",".join(stale[:10]))
    result["artifact_registry"] = "PASS"
    result["stale_artifacts"] = 0
    return result


def repair_contract(cfg: dict[str, Any]) -> dict[str, Any]:
    """Reapply deterministic contract enrichment without rereading raw data."""
    output = cfg["output_root"]
    paths = _ensure_dirs(output)
    bundle = _enrich_contract(load_bundle(output), cfg)
    bundle = PreBundle(**{name: _formal_frame(frame, cfg, name) for name, frame in bundle.tables().items()})
    validation = validate_bundle(bundle, cfg)
    input_matrix, cohort, readiness_summary = readiness(bundle, cfg)
    if validation.get("status") != "PASS" or readiness_summary.get("status") != "PASS":
        raise ValueError("REPAIRED_CONTRACT_FAILED_GATES")
    _write_bundle(bundle, paths)
    write_parquet(input_matrix, paths["reports"] / "consumer_input_matrix.parquet")
    write_parquet(cohort, paths["reports"] / "consumer_cohort_readiness.parquet")
    write_json(readiness_summary, paths["reports"] / "consumer_readiness.json")
    write_parquet(_missingness_report(bundle), paths["reports"] / "missingness_by_table.parquet")
    write_json(validation, paths["reports"] / "validation.json")
    _write_fast_manifest(bundle, paths, cfg)
    repaired_acceptance = {
        **target_contract_metadata(cfg),
        "formal_target_contract": "PASS",
        "formal_eligible": True,
        "validation_status": "PASS",
        "readiness_status": "PASS",
        "config_hash": cfg["config_hash"],
    }
    write_json(repaired_acceptance, paths["reports"] / "pre_acceptance.json")
    write_json(repaired_acceptance, paths["root"] / "acceptance.json")
    manifest_path = paths["manifests"] / "pre_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest.update({"validation": validation, "readiness": readiness_summary, "formal_eligible": True})
    manifest["output_hashes"] = _output_hashes(output)
    write_json(manifest, manifest_path)
    repaired_at = str(pd.Timestamp.now(tz="UTC"))
    summary_path = output / "run_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    summary.update({
        **target_contract_metadata(cfg),
        "formal_target_contract": "PASS",
        "status": "PASS",
        "contract_repaired_at": repaired_at,
        "episode_count": len(bundle.episodes),
        "snapshot_count": len(bundle.snapshots),
    })
    write_json(summary, summary_path)
    state_path = output / "run_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    state.update({"status": "PASS", "current_stage": "contract_repair_complete", "updated_at": repaired_at, "implementation_hash": sha256_file(Path(__file__))})
    write_json(state, state_path)
    write_json(_artifact_registry(output, cfg, "contract_repair"), output / "artifact_registry.json")
    return {"status": "PASS", "validation": validation, "readiness": readiness_summary, "repaired_at": repaired_at}


def readiness_existing(cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    bundle = load_bundle(cfg["output_root"])
    matrix, cohort, summary = readiness(bundle, cfg)
    paths = _ensure_dirs(cfg["output_root"])
    write_parquet(matrix, paths["reports"] / "consumer_input_matrix.parquet")
    write_parquet(cohort, paths["reports"] / "consumer_cohort_readiness.parquet")
    write_json(summary, paths["reports"] / "consumer_readiness.json")
    return matrix, cohort, summary


