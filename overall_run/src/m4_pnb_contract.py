from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CHANNELS = ("F", "P", "R")
NON_NULL_ACTIONS = (
    "A11", "A12", "A13", "A21", "A22", "A23", "A31", "A32", "A33",
    "A41", "A42", "A43", "A51", "A52", "A53", "A54", "A55", "A61",
    "A62", "A71", "A72", "A73", "A81", "A82", "A83",
)
AUDIT_SEED_NAMESPACE = "M4_PNB_AUDIT_V1"
FORMAL_Q_TOLERANCE = 1e-12
FLOAT32_RECONSTRUCTION_ATOL_RMB = 2e-6
FLOAT32_RATIO_ATOL = 2e-7
NEAR_Q_TOLERANCE = 0.02
EXPECTED_RUN_ID = "20260727_214650_fast_df2c1ae3_unknown"
EXPECTED_CONFIG_HASH = "df2c1ae3147c2279cd6cc419213906df28fc1b5a251f36a50ce70ceec4327922"
EXPECTED_IMPLEMENTATION_HASH = "9079c6d66a6559eb26f731e0db157a9a2233821e5874a803ac378c1e69016d98"
EXPECTED_REGISTRY_HASH = "b6ec527341117ac23309eaa5d5503fe676970f34bdc5403aed431dc32b27a46b"


@dataclass
class FrozenInputs:
    summary: pd.DataFrame
    costs_rmb: dict[str, np.ndarray]
    sample_ids: np.ndarray
    m3_recovery: dict[str, np.ndarray]
    m3_implementation: dict[str, np.ndarray]
    m3_success: dict[str, np.ndarray]
    m3_parameters: pd.DataFrame
    candidates: pd.DataFrame
    rankings: pd.DataFrame
    recommendations: pd.DataFrame
    actions: pd.DataFrame
    config: dict[str, Any]
    reconstruction_diagnostics: dict[str, Any]


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def capture_registered_hashes(run_dir: Path) -> dict[str, str]:
    registry = _json(run_dir / "artifact_registry.json")
    hashes: dict[str, str] = {}
    for entry in registry["artifacts"]:
        relative = str(entry.get("relative_path") or entry["artifact_name"])
        path = run_dir / relative
        if not path.is_file():
            raise RuntimeError(f"REGISTERED_ARTIFACT_MISSING:{relative}")
        actual = sha256_file(path)
        if actual != entry["sha256"]:
            raise RuntimeError(f"REGISTERED_ARTIFACT_HASH_MISMATCH:{relative}")
        hashes[relative] = actual
    return hashes


def verify_baseline(run_dir: Path) -> dict[str, Any]:
    summary = _json(run_dir / "run_summary.json")
    registry = _json(run_dir / "artifact_registry.json")
    registry_hash = sha256_file(run_dir / "artifact_registry.json")
    pre_refactor_run = summary.get("run_id") == EXPECTED_RUN_ID
    if pre_refactor_run:
        expected_implementation_hash = EXPECTED_IMPLEMENTATION_HASH
    else:
        from .config import load_config

        expected_implementation_hash = load_config(run_dir.parents[1], "fast").implementation_hash
    checks = {
        "run_id": summary.get("run_id") == registry.get("run_id"),
        "config_hash": summary.get("config_hash") == EXPECTED_CONFIG_HASH,
        "scientific_implementation_hash": (
            summary.get("implementation_hash") == expected_implementation_hash
            and registry.get("implementation_hash")
            == expected_implementation_hash
        ),
        "artifact_registry_hash": (
            registry_hash == EXPECTED_REGISTRY_HASH if pre_refactor_run else True
        ),
        "scientific_status": summary.get("scientific_status") == "STOP_AND_REVIEW",
        "full_recommended": summary.get("full_recommended") is False,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("FROZEN_BASELINE_MISMATCH:" + ",".join(failed))
    registered = capture_registered_hashes(run_dir)
    return {
        "checks": checks,
        "run_id": summary["run_id"],
        "config_hash": summary["config_hash"],
        "scientific_implementation_hash": summary["implementation_hash"],
        "artifact_registry_hash": registry_hash,
        "registered_artifact_count": len(registered),
    }


def validate_sample_ids(sample_ids: Iterable[int], expected_count: int) -> np.ndarray:
    values = np.asarray(list(sample_ids), dtype=np.int64)
    expected = np.arange(expected_count, dtype=np.int64)
    if values.shape != expected.shape or not np.array_equal(values, expected):
        raise RuntimeError("PNB_SAMPLE_ID_ALIGNMENT_FAILURE")
    return values.astype(np.int32)


