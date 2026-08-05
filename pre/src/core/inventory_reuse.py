from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..input_sources import discover_files, resolve_source_root
from ..inventory import inventory


def _discovered_paths(cfg: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for source, spec in cfg["sources"].items():
        if source == "ourairports":
            root = resolve_source_root(
                cfg["project_root"], cfg["data_root"], spec["root"]
            )
            files = [root / spec["airports_file"], root / spec["runways_file"]]
        else:
            files = discover_files(cfg["project_root"], cfg["data_root"], spec)
        paths.update(str(path.resolve()) for path in files if path.exists())
    return paths


def _candidate_paths(cfg: dict[str, Any]) -> list[Path]:
    roots = [cfg["project_root"] / "output" / cfg["mode"]]
    if cfg["mode"] == "full":
        roots.append(cfg["project_root"] / "output" / "middle")
    return [root / "manifests" / "raw_inventory.parquet" for root in roots]


def _unchanged(frame: pd.DataFrame, discovered: set[str]) -> bool:
    recorded = set(frame["absolute_path"].astype(str))
    if recorded != discovered:
        return False
    for row in frame.itertuples(index=False):
        path = Path(row.absolute_path)
        if not path.exists() or path.stat().st_size != int(row.size_bytes):
            return False
        current = pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC")
        recorded_time = pd.Timestamp(row.modified_time)
        if recorded_time.tzinfo is None:
            recorded_time = recorded_time.tz_localize("UTC")
        else:
            recorded_time = recorded_time.tz_convert("UTC")
        if abs((current - recorded_time).total_seconds()) > 1e-6:
            return False
    return True


def load_verified_inventory(cfg: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    discovered = _discovered_paths(cfg)
    for candidate in _candidate_paths(cfg):
        if not candidate.exists():
            continue
        frame = pd.read_parquet(candidate)
        if _unchanged(frame, discovered):
            return frame, f"VERIFIED_REUSE:{candidate}"
    return inventory(cfg), "REFRESHED"
