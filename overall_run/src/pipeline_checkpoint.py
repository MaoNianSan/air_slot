from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from .artifacts import sha256_file
from .config import RunConfig
from .failures import FormalRunBlocked
from .input import FORMAL_TARGET_COLUMN, FORMAL_TARGET_CONTRACT_VERSION
from .utils import environment_manifest, git_commit, stable_hash, utc_now, write_json


def write_stage_checkpoint(
    staging: Path,
    *,
    stage: str,
    mode: str,
    cfg: RunConfig,
    input_hashes: dict[str, str],
    outputs: list[Path],
) -> Path:
    missing = [str(path) for path in outputs if not path.is_file()]
    if missing:
        raise FormalRunBlocked("CHECKPOINT_OUTPUT_MISSING:" + ",".join(missing))
    path = staging / "checkpoints" / f"{stage}.json"
    output_hashes = {
        output.relative_to(staging).as_posix(): sha256_file(output)
        for output in outputs
    }
    write_json(path, {
        "mode": mode,
        "stage": stage,
        "config_hash": cfg.config_hash,
        "implementation_hash": cfg.implementation_hash,
        "input_hashes": dict(input_hashes),
        "output_hashes": output_hashes,
        "output_hash": stable_hash(output_hashes),
        "formal_target_column": FORMAL_TARGET_COLUMN,
        "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
        "requested_n_jobs": cfg.compute.get("requested_n_jobs", 1),
        "resolved_n_jobs": cfg.compute.get("resolved_n_jobs", 1),
        "outer_workers": cfg.compute.get("outer_workers", 1),
        "inner_model_threads": cfg.compute.get("inner_model_threads", 1),
        "parallel_backend": cfg.compute.get("parallel_backend", "native"),
        "task_partition_version": cfg.compute.get("task_partition_version"),
        "task_seed_hash": cfg.compute.get("task_seed_hash"),
        "completed_at": pd.Timestamp.now(tz="UTC"),
    })
    return path


def validate_resume_checkpoints(
    staging: Path,
    *,
    mode: str,
    cfg: RunConfig,
    input_hashes: dict[str, str],
) -> None:
    expected_outputs = {
        "m1_fit": "m1.joblib",
        "m2_fit": "m2.joblib",
        "m3_contract": "m3.joblib",
        "m4_fit": "m4.joblib",
    }
    for stage, required_output in expected_outputs.items():
        path = staging / "checkpoints" / f"{stage}.json"
        if not path.is_file():
            raise FormalRunBlocked(f"RESUME_CHECKPOINT_MISSING:{path}")
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        expected = {
            "mode": mode,
            "stage": stage,
            "config_hash": cfg.config_hash,
            "implementation_hash": cfg.implementation_hash,
            "input_hashes": dict(input_hashes),
            "formal_target_column": FORMAL_TARGET_COLUMN,
            "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
        }
        for key, value in expected.items():
            if checkpoint.get(key) != value:
                raise FormalRunBlocked(
                    f"RESUME_CHECKPOINT_{key.upper()}_MISMATCH:{stage}"
                )
        output_hashes = checkpoint.get("output_hashes", {})
        if set(output_hashes) != {required_output}:
            raise FormalRunBlocked(f"RESUME_CHECKPOINT_OUTPUT_SET_MISMATCH:{stage}")
        for relative, expected_hash in output_hashes.items():
            output = (staging / relative).resolve()
            try:
                output.relative_to(staging.resolve())
            except ValueError as exc:
                raise FormalRunBlocked(
                    f"RESUME_CHECKPOINT_OUTPUT_OUTSIDE_STAGING:{relative}"
                ) from exc
            if not output.is_file() or sha256_file(output) != expected_hash:
                raise FormalRunBlocked(
                    f"RESUME_CHECKPOINT_OUTPUT_HASH_MISMATCH:{relative}"
                )


def mark_running_staging_incomplete(root: Path, error: BaseException) -> None:
    """Mark only staging owned by this process; never publish a failed run."""
    output_root = root / "output"
    state_paths = list((output_root / ".staging").glob("*/run_state.json"))
    state_paths.extend(
        path
        for path in output_root.glob("*/run_state.json")
        if path.parent.name != ".staging"
    )
    for state_path in state_paths:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if state.get("process_id") != os.getpid() or state.get("status") != "RUNNING":
            continue
        state.update({
            "status": "INCOMPLETE",
            "failed_at": str(pd.Timestamp.now(tz="UTC")),
            "failure_type": type(error).__name__,
            "failure_message": str(error),
        })
        write_json(state_path, state)
        summary_path = state_path.parent / "run_summary.json"
        if summary_path.is_file():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                summary.update({
                    "engineering_status": "INCOMPLETE",
                    "downstream_ready": False,
                    "failure_type": type(error).__name__,
                    "failure_message": str(error),
                })
                write_json(summary_path, summary)
            except (OSError, json.JSONDecodeError):
                pass


def artifact_dir(cfg: RunConfig, mode: str) -> Path:
    return cfg.root / "output" / mode


def manifest_artifact_root(cfg: RunConfig, manifest: dict[str, Any]) -> Path:
    raw = Path(str(manifest["artifact_root"]))
    return raw if raw.is_absolute() else (cfg.root / raw).resolve()


def build_manifest(
    cfg: RunConfig,
    mode: str,
    run_identifier: str,
    pre_hashes: dict[str, str],
) -> dict[str, Any]:
    return {
        "run_id": run_identifier,
        "mode": mode,
        "created_at": utc_now(),
        "config_hash": cfg.config_hash,
        "implementation_hash": cfg.implementation_hash,
        "project_version": cfg.project_version,
        "git_commit": git_commit(cfg.root),
        "pre_file_hashes": pre_hashes,
        "environment": environment_manifest(),
        "quantiles": cfg.scientific["m1"]["quantiles"],
    }


def save_registry_pre_hashes(artifact_root: Path, hashes: dict[str, str]) -> None:
    path = artifact_root / "artifact_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["pre_file_hashes"] = hashes
    write_json(path, registry)


def latest_run(cfg: RunConfig, mode: str) -> Path:
    pointer = cfg.root / "output" / f"latest_{mode}.txt"
    if not pointer.exists():
        raise FormalRunBlocked(f"LATEST_{mode.upper()}_RUN_MISSING")
    run_identifier = pointer.read_text(encoding="utf-8").strip()
    path = cfg.root / "output" / "runs" / run_identifier
    if not path.exists():
        raise FormalRunBlocked(f"RUN_DIRECTORY_MISSING:{path}")
    return path


class FullBlockedByFastAcceptance(FormalRunBlocked):
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("FULL_BLOCKED_BY_FAST_ACCEPTANCE:" + "|".join(reasons))


def hash_file_compat(path: Path) -> str:
    return sha256_file(path)


def assert_fast_acceptance(cfg_root: Path) -> None:
    fast_root = cfg_root / "output" / "fast"
    required = [
        fast_root / "run_summary.json",
        fast_root / "scientific_gate.json",
        fast_root / "artifact_registry.json",
    ]
    reasons = [f"MISSING:{path.name}" for path in required if not path.exists()]
    if reasons:
        raise FullBlockedByFastAcceptance(reasons)
    summary = json.loads(required[0].read_text(encoding="utf-8"))
    gates = json.loads(required[1].read_text(encoding="utf-8"))
    registry = json.loads(required[2].read_text(encoding="utf-8"))
    if summary.get("engineering_status") != "PASS":
        reasons.append(f"FAST_ENGINEERING_STATUS:{summary.get('engineering_status')}")
    if summary.get("scientific_status") != "PASS":
        reasons.append(f"FAST_SCIENTIFIC_STATUS:{summary.get('scientific_status')}")
    if summary.get("full_recommended") is not True:
        reasons.append("FAST_FULL_RECOMMENDED_FALSE")
    for name, gate in gates.items():
        if bool(gate.get("required")) and gate.get("status") != "PASS":
            reasons.append(f"FAST_REQUIRED_GATE:{name}:{gate.get('status')}")
    if registry.get("scientific_status") != "PASS":
        reasons.append(
            f"FAST_REGISTRY_SCIENTIFIC_STATUS:{registry.get('scientific_status')}"
        )
    for entry in registry.get("artifacts", []):
        path = Path(str(entry.get("absolute_path", "")))
        if not path.exists():
            reasons.append(f"FAST_ARTIFACT_MISSING:{entry.get('artifact_name')}")
        elif hash_file_compat(path) != entry.get("sha256"):
            reasons.append(
                f"FAST_ARTIFACT_HASH_MISMATCH:{entry.get('artifact_name')}"
            )
    if reasons:
        raise FullBlockedByFastAcceptance(sorted(set(reasons)))


def prepare_empty_publish_target(target: Path) -> None:
    """Consume the empty directory created by clean.py before atomic publish."""
    if not target.exists():
        return
    if target.is_symlink() or not target.is_dir() or any(target.iterdir()):
        raise FormalRunBlocked(f"OUTPUT_MODE_EXISTS_BACKUP_REQUIRED:{target}")
    target.rmdir()
