from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ..column_registry import validate_column_registry
from ..writer import dataframe_hash


def dataset_file_audit(
    dataset_root: Path, partition_manifest: dict[str, Any]
) -> dict[str, list[str]]:
    partitions = partition_manifest.get("partitions", {})
    registered = {
        str(record["relative_path"])
        for record in partitions.values()
        if isinstance(record, dict)
        and record.get("status") == "PASS"
        and record.get("relative_path")
    }
    actual = (
        {
            path.relative_to(dataset_root).as_posix()
            for path in dataset_root.rglob("*.parquet")
        }
        if dataset_root.exists()
        else set()
    )
    grouped: dict[str, list[str]] = {}
    for relative in sorted(actual):
        grouped.setdefault(str(Path(relative).parent).replace("\\", "/"), []).append(relative)
    return {
        "extra_unregistered_files": sorted(actual - registered),
        "missing_registered_files": sorted(registered - actual),
        "duplicate_partition_files": sorted(
            key for key, files in grouped.items() if len(files) > 1
        ),
        "pass_empty_file_conflicts": sorted(
            key
            for key, record in partitions.items()
            if isinstance(record, dict)
            and record.get("status") == "PASS_EMPTY"
            and grouped.get(key)
        ),
    }


def load_tables(
    root: Path, cfg: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    failures: dict[str, Any] = {}
    tables: dict[str, pd.DataFrame] = {}
    for name, spec in cfg["core_schema"]["tables"].items():
        if name in {"observations", "observation_membership"}:
            continue
        path = root / f"{name}.parquet"
        if not path.exists():
            failures[name] = {"missing_file": True}
            continue
        frame = pd.read_parquet(path)
        tables[name] = frame
        missing = sorted(set(spec.get("required", [])) - set(frame.columns))
        duplicate = int(frame.duplicated(spec.get("key", [])).sum()) if not missing else -1
        if missing or duplicate:
            failures[name] = {"missing_columns": missing, "duplicate_keys": duplicate}
    return failures, tables


def check_registry(
    root: Path, cfg: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    path = root / "column_registry.yaml"
    if not path.exists():
        return {"status": "FAIL", "reason": "FILE_MISSING"}, []
    registry = yaml.safe_load(path.read_text(encoding="utf-8")).get("columns", [])
    return validate_column_registry(registry, cfg), registry


def check_logical_hashes(
    manifest: dict[str, Any],
    tables: dict[str, pd.DataFrame],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    failures = []
    for name, expected in manifest.get("artifact_hashes", {}).items():
        if name in {"observations", "observation_membership"}:
            continue
        if name in tables and dataframe_hash(
            tables[name], list(cfg["core_schema"]["tables"][name].get("key", []))
        ) != expected:
            failures.append(name)
    return {"status": "PASS" if not failures else "FAIL", "failures": failures}
