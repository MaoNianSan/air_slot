from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import pyarrow.parquet as pq
except ModuleNotFoundError:
    pq = None

from .input import object_hash, sha256_file
from .target_contract import target_contract_metadata


def output_hashes(root: Path) -> dict[str, str]:
    names = ["episodes", "snapshots", "calibration", "rules", "evidence_audit"]
    return {name: sha256_file(root / f"{name}.parquet") for name in names}


def build_artifact_registry(
    root: Path, cfg: dict[str, Any], stage: str
) -> dict[str, Any]:
    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {
            "artifact_registry.json",
            "run_state.json",
        }:
            continue
        rows = None
        if path.suffix == ".parquet":
            rows = int(pq.ParquetFile(path).metadata.num_rows) if pq else None
        entries.append(
            {
                "artifact_name": path.stem,
                "relative_path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "row_count": rows,
                "schema_version": cfg["schema_version"],
                "contract_version": "pre-contract-v3",
                "parameter_version": cfg["project_version"],
                "input_hash": object_hash(cfg.get("raw_hashes", {})),
                "config_hash": cfg["config_hash"],
                "implementation_hash": sha256_file(Path(__file__)),
                "mode": cfg["mode"],
                "created_by_stage": stage,
                "created_at": str(pd.Timestamp.now(tz="UTC")),
            }
        )
    return {
        "mode": cfg["mode"],
        **target_contract_metadata(cfg),
        "formal_target_contract": "PASS",
        "artifacts": entries,
        "stale_artifacts": 0,
    }


def validate_published_target_metadata(root: Path, cfg: dict[str, Any]) -> None:
    expected = target_contract_metadata(cfg)
    metadata_paths = {
        "run_summary": root / "run_summary.json",
        "acceptance": root / "acceptance.json",
        "artifact_registry": root / "artifact_registry.json",
    }
    for name, path in metadata_paths.items():
        if not path.exists():
            raise FileNotFoundError(
                f"FORMAL_TARGET_CONTRACT_BLOCKED: missing {name}: {path}"
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        for field, value in expected.items():
            if payload.get(field) != value:
                raise ValueError(
                    f"FORMAL_TARGET_CONTRACT_BLOCKED: {name}.{field}="
                    f"{payload.get(field)!r}, expected {value!r}"
                )
        if payload.get("formal_target_contract") != "PASS":
            raise ValueError(
                f"FORMAL_TARGET_CONTRACT_BLOCKED: {name} does not declare PASS"
            )


_artifact_registry = build_artifact_registry
_output_hashes = output_hashes
_validate_published_target_metadata = validate_published_target_metadata
