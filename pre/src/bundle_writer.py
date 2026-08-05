from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from .input import write_parquet
from .validate import PreBundle


def write_fast_manifest(
    bundle: PreBundle, paths: dict[str, Path], cfg: dict[str, Any]
) -> pd.DataFrame:
    ep = bundle.episodes
    manifest = ep.groupby(
        ["anchor_date", "split", "subset_role"], as_index=False, observed=True
    ).agg(episode_count=("episode_id", "count"), formal_eligible=("formal_eligible", "all"))
    manifest["debug_only"] = cfg["mode"] == "fast"
    manifest["formal_result"] = False if cfg["mode"] == "fast" else True
    manifest["selection_reason"] = (
        "DATE_SOURCE_COMPLETENESS_FROZEN_FAST"
        if cfg["mode"] == "fast"
        else "FROZEN_FORMAL_MANIFEST"
    )
    manifest["selection_seed"] = int(cfg["base_seed"])
    name = "fast_subset_manifest" if cfg["mode"] == "fast" else "model_subset"
    write_parquet(manifest, paths["manifests"] / f"{name}.parquet")
    manifest.to_csv(paths["manifests"] / f"{name}.csv", index=False)
    return manifest


def write_bundle(bundle: PreBundle, paths: dict[str, Path]) -> None:
    for name, frame in bundle.tables().items():
        write_parquet(frame, paths["root"] / f"{name}.parquet")


def publish_bundle(staging: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    backup = output / f".backup-{uuid.uuid4().hex[:8]}"
    backup.mkdir(parents=True, exist_ok=True)
    targets = [
        "episodes.parquet",
        "snapshots.parquet",
        "calibration.parquet",
        "rules.parquet",
        "evidence_audit.parquet",
        "intermediate",
        "artifacts",
        "manifests",
        "reports",
        "checkpoints",
        "artifact_registry.json",
        "run_state.json",
        "run_summary.json",
        "acceptance.json",
        "passenger_support_by_split.parquet",
        "passenger_support_by_airport.parquet",
        "passenger_support_by_source_period.parquet",
        "passenger_fallback_distribution.parquet",
        "fast_month_selection_audit.csv",
        "PASSENGER_MONTH_FAST_REPORT.md",
        "PASSENGER_MONTH_FAST_SUMMARY.json",
    ]
    moved_old: list[str] = []
    moved_new: list[str] = []
    try:
        for name in targets:
            old = output / name
            if old.exists():
                old.rename(backup / name)
                moved_old.append(name)
        for name in targets:
            new = staging / name
            if new.exists():
                new.rename(output / name)
                moved_new.append(name)
        new_logs = staging / "logs"
        if new_logs.exists():
            destination_logs = output / "logs"
            destination_logs.mkdir(parents=True, exist_ok=True)
            for source in new_logs.iterdir():
                destination = destination_logs / source.name
                if destination.exists():
                    try:
                        destination.unlink()
                    except PermissionError:
                        if source.name == "run.log":
                            continue
                        raise
                source.rename(destination)
        shutil.rmtree(backup, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)
    except Exception:
        for name in reversed(moved_new):
            current = output / name
            if current.exists():
                destination = staging / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                current.rename(destination)
        for name in reversed(moved_old):
            saved = backup / name
            if saved.exists():
                saved.rename(output / name)
        raise


_publish = publish_bundle
_write_bundle = write_bundle
_write_fast_manifest = write_fast_manifest
