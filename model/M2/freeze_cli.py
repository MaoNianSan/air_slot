"""M2 Data2 formal freeze CLI (Development-only, deterministic)."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

from model.M2.freeze import (
    build_m2_data2_formal_registry,
    write_m2_registry,
)
from model.common.identity import content_id


def _write_status(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def build(*, root: Path, artifact_dir: Path) -> dict:
    registry_path = root / "registries" / "m2_data2_formal_cu_v1.json"
    manifest_path = artifact_dir / "M2_DATA2_FORMAL_CU_V1_MANIFEST.json"
    status_path = artifact_dir / "M2_FORMAL_FREEZE_STATUS.json"
    started = datetime.now(timezone.utc)
    _write_status(
        status_path,
        {
            "phase": "FITTING_REFERENCES_AND_SCALES",
            "started": started.isoformat(),
            "elapsed_seconds": 0,
            "rss_mb": int(psutil.Process().memory_info().rss / 1024 / 1024),
            "final_test_access_count": 0,
            "paper_full_run": False,
        },
    )
    registry, written = build_m2_data2_formal_registry(
        root=root, artifact_dir=artifact_dir
    )
    registry_path, manifest_path = write_m2_registry(
        registry,
        registry_path=registry_path,
        manifest_path=manifest_path,
        root=root,
    )
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    payload = {
        "schema_version": "M2_FORMAL_FREEZE_CLI_V1",
        "registry_id": registry.registry_id,
        "registry_path": str(registry_path),
        "registry_hash": registry.digest(),
        "manifest_path": str(manifest_path),
        "reference_artifacts": registry.reference_artifacts,
        "train_scales": registry.train_scale_artifact,
        "elapsed_seconds": elapsed,
        "rss_mb": int(psutil.Process().memory_info().rss / 1024 / 1024),
        "final_test_access_count": 0,
        "paper_full_run": False,
        "expensive_upstream_rerun_count": 0,
    }
    _write_status(artifact_dir / "M2_FORMAL_FREEZE_CLOSURE.json", payload)
    print(json.dumps(payload, sort_keys=True))
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build",))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("artifacts/diagnostics/v5_development_freeze"),
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    artifact_dir = (
        args.artifact_dir.resolve()
        if args.artifact_dir.is_absolute()
        else (root / args.artifact_dir)
    )
    return build(root=root, artifact_dir=artifact_dir)


if __name__ == "__main__":
    raise SystemExit(main())
