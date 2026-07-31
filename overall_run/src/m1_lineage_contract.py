from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

MODULE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = MODULE_ROOT.parent
FAST_ROOT = MODULE_ROOT / "output" / "fast"
AUDIT_ROOT = FAST_ROOT / "audits"
FIGURE_ROOT = AUDIT_ROOT / "m1_d6_figures"
PRE_ROOT = PROJECT_ROOT / "pre" / "output" / "fast"
PART_ROOT = PROJECT_ROOT / "part_adv" / "output" / "fast"
LOG_ROOT = PROJECT_ROOT / "output_logs"

EXPECTED_RUN_ID = "20260727_214650_fast_df2c1ae3_unknown"
EXPECTED_CONFIG_HASH = "df2c1ae3147c2279cd6cc419213906df28fc1b5a251f36a50ce70ceec4327922"
EXPECTED_SCIENTIFIC_IMPLEMENTATION_HASH = (
    "9079c6d66a6559eb26f731e0db157a9a2233821e5874a803ac378c1e69016d98"
)
EXPECTED_REGISTRY_HASH = "4bb821d83c117fe8c6ba942d1b925e8515ac161f4a9a9eeda744ca15405da7a5"
EXPECTED_M4_REGISTRY_HASH = "7f42bf5a28c866636fe08a12b3a39c74f54650cf206b5047949db270624b9212"
EXPECTED_PRE_RUN_ID = "pre-fast-20260727T151907Z-6b6957da"
FORMAL_TARGET = "y_movement_raw"
QUANTILES = np.asarray(
    [0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.975, 0.99],
    dtype=float,
)
BOOTSTRAP_SEED = 20260725
BOOTSTRAP_DRAWS = 2000
MIN_EVENT_CLUSTERS = 20
DEPRECATION_DATE = "2026-07-27"


class AuditStop(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cohort_hash(values: pd.Series | list[str] | np.ndarray) -> str:
    ordered = sorted(str(value) for value in list(values))
    return stable_hash(ordered)


def pinball_loss(y: np.ndarray, q: np.ndarray, tau: float) -> np.ndarray:
    residual = np.asarray(y, dtype=float) - np.asarray(q, dtype=float)
    return np.maximum(tau * residual, (tau - 1.0) * residual)


def quantile_crps(y: np.ndarray, qmat: np.ndarray, quantiles: np.ndarray = QUANTILES) -> np.ndarray:
    losses = np.column_stack(
        [pinball_loss(y, qmat[:, index], float(tau)) for index, tau in enumerate(quantiles)]
    )
    integrate = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
    return 2.0 * integrate(losses, quantiles, axis=1)


def twcrps_value(crps: np.ndarray, y: np.ndarray, validation_q95: float) -> float:
    weights = np.where(np.asarray(y, dtype=float) >= float(validation_q95), 5.0, 1.0)
    return float(np.average(crps, weights=weights))


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    temporary.replace(path)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def registered_artifact_snapshot() -> dict[str, str]:
    registry = _json(FAST_ROOT / "artifact_registry.json")
    return {
        str(row["artifact_name"]): sha256_file(Path(row["absolute_path"]))
        for row in registry["artifacts"]
    }


def verify_frozen_baseline(*, deep_inputs: bool = True) -> dict[str, Any]:
    registry_path = FAST_ROOT / "artifact_registry.json"
    registry = _json(registry_path)
    run_manifest = _json(FAST_ROOT / "run_manifest.json")
    registry_hash = sha256_file(registry_path)
    pre_refactor_run = registry.get("run_id") == EXPECTED_RUN_ID
    if pre_refactor_run:
        expected_implementation_hash = EXPECTED_SCIENTIFIC_IMPLEMENTATION_HASH
    else:
        from .config import load_config

        expected_implementation_hash = load_config(MODULE_ROOT, "fast").implementation_hash
    m4_registry_path = AUDIT_ROOT / "m4_pnb_audit_registry.json"
    m4_registry = _json(m4_registry_path) if m4_registry_path.is_file() else {}
    m4_artifacts_valid = all(
        (FAST_ROOT / row["relative_path"]).is_file()
        and sha256_file(FAST_ROOT / row["relative_path"]) == row["sha256"]
        for row in m4_registry.get("artifacts", [])
    )
    checks = {
        "run_id": registry.get("run_id") == run_manifest.get("run_id"),
        "config_hash": registry.get("config_hash") == EXPECTED_CONFIG_HASH,
        "scientific_implementation_hash": (
            registry.get("implementation_hash") == expected_implementation_hash
            and run_manifest.get("implementation_hash") == expected_implementation_hash
        ),
        "formal_registry_hash": (
            registry_hash == EXPECTED_REGISTRY_HASH if pre_refactor_run else True
        ),
        "registered_artifact_count": len(registry.get("artifacts", [])) == 24,
        "m4_registry_hash": (
            m4_registry.get("baseline_registry_hash") == registry_hash
            and m4_registry.get("formal_artifacts_modified") is False
            and bool(m4_registry.get("artifacts"))
            and m4_artifacts_valid
        ),
    }
    artifact_mismatches: list[str] = []
    for row in registry.get("artifacts", []):
        path = Path(row["absolute_path"])
        if not path.is_file() or sha256_file(path) != row["sha256"]:
            artifact_mismatches.append(str(row["artifact_name"]))
    checks["registered_artifact_hashes"] = not artifact_mismatches

    pre_summary = _json(PRE_ROOT / "run_summary.json")
    pre_hashes: dict[str, str] = {}
    pre_mismatches: list[str] = []
    for name, expected in run_manifest["pre_file_hashes"].items():
        path = PRE_ROOT / f"{name}.parquet"
        actual = sha256_file(path) if path.is_file() else "MISSING"
        pre_hashes[name] = actual
        if actual != expected:
            pre_mismatches.append(name)
    checks["pre_run_id"] = pre_summary.get("run_id") == EXPECTED_PRE_RUN_ID
    checks["pre_five_table_hashes"] = not pre_mismatches and len(pre_hashes) == 5

    inventory = pd.read_parquet(PRE_ROOT / "manifests" / "raw_inventory.parquet")
    formal_input_mismatches: list[str] = []
    formal_input_missing: list[str] = []
    if deep_inputs:
        for row in inventory.itertuples(index=False):
            path = Path(row.absolute_path)
            if not path.is_file():
                formal_input_missing.append(str(path))
            elif sha256_file(path) != row.sha256:
                formal_input_mismatches.append(str(path))
    data_files = [path for path in (PROJECT_ROOT / "data").rglob("*") if path.is_file()]
    data_bytes = sum(path.stat().st_size for path in data_files)
    checks["formal_input_count"] = len(inventory) == 167
    checks["formal_input_hashes"] = not formal_input_missing and not formal_input_mismatches
    checks["data_file_count"] = len(data_files) == 687
    checks["data_total_bytes"] = data_bytes == 85406288136
    if not all(checks.values()):
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise AuditStop("FROZEN_BASELINE_MISMATCH:" + ",".join(failed))
    return {
        "checks": checks,
        "artifact_mismatch_count": len(artifact_mismatches),
        "pre_mismatch_count": len(pre_mismatches),
        "formal_input_count": int(len(inventory)),
        "formal_input_total_bytes": int(inventory["size_bytes"].sum()),
        "formal_input_missing_count": len(formal_input_missing),
        "formal_input_mismatch_count": len(formal_input_mismatches),
        "data_file_count": len(data_files),
        "data_total_bytes": data_bytes,
        "run_id": registry.get("run_id"),
        "formal_registry_hash": registry_hash,
        "scientific_implementation_hash": expected_implementation_hash,
        "m4_audit_registry_hash": sha256_file(m4_registry_path),
    }


