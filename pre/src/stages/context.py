from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..input import sha256_file, write_json
from ..pipeline_config import _ensure_dirs
from ..progress import RunHeartbeat, stage_message


@dataclass
class PreBuildContext:
    cfg: dict[str, Any]
    progress_level: str
    parallel_fields: dict[str, Any]
    run_started: pd.Timestamp
    current_run_id: str
    output: Path
    staging: Path
    paths: dict[str, Path]
    heartbeat: RunHeartbeat
    implementation_hash: str
    runtimes: list[dict[str, Any]] = field(default_factory=list)
    checkpoint_paths: list[str] = field(default_factory=list)
    raw_inventory: Any = None
    coverage: Any = None
    complete_dates: Any = None
    flightlist: Any = None
    aircraft: Any = None
    airports: Any = None
    metar: Any = None
    passengers: Any = None
    commercial_flights: Any = None
    airport_reference: Any = None
    legs: Any = None
    movement_reference: Any = None
    episodes: Any = None
    clipping_bounds: Any = None
    turnaround_reference: Any = None
    predecessor_features: Any = None
    passenger_reference: Any = None
    weather_climatology: Any = None
    snapshots: Any = None
    requests: Any = None
    state_store: Any = None
    extraction_report: Any = None
    cache_manifest: Any = None
    cache_status: str = "N/A"
    flow_reference: Any = None
    calibration: Any = None
    rules: Any = None
    audit: Any = None
    bundle: Any = None
    validation: Any = None
    readiness_summary: Any = None
    subset_manifest: Any = None
    passenger_month_summary: Any = None
    manifest: Any = None

    def require(self, *names: str) -> None:
        missing = [name for name in names if getattr(self, name) is None]
        if missing:
            raise RuntimeError("PRE_STAGE_CONTEXT_MISSING:" + ",".join(missing))

    def stage(self, message: str) -> float:
        self.heartbeat.update(message)
        stage_message(message, level=self.progress_level)
        return time.monotonic()

    def finish(
        self,
        name: str,
        started: float,
        *,
        input_rows: int = 0,
        output_rows: int = 0,
        cache_status: str = "N/A",
    ) -> None:
        completed = pd.Timestamp.now(tz="UTC")
        duration = time.monotonic() - started
        record = {
            "stage": name,
            "start": completed - pd.to_timedelta(duration, unit="s"),
            "end": completed,
            "duration_seconds": duration,
            "input_rows": input_rows,
            "output_rows": output_rows,
            "cache_status": cache_status,
            "peak_memory_mb": np.nan,
        }
        self.runtimes.append(record)
        checkpoint = {
            "input_hash": self.cfg.get("config_hash"),
            "config_hash": self.cfg["config_hash"],
            "implementation_hash": self.implementation_hash,
            "mode": self.cfg["mode"],
            "stage": name,
            "model_or_config_id": None,
            "output_hash": self._record_hash(record),
            "completed_at": str(completed),
            "resume_reused": cache_status == "HIT",
            **self.parallel_fields,
            **self._target_metadata(),
        }
        path = self.paths["root"] / "checkpoints" / (
            f"{len(self.runtimes):02d}_{name}.json"
        )
        write_json(checkpoint, path)
        self.heartbeat.checkpointed(str(path))
        self.checkpoint_paths.append(str(path.relative_to(self.paths["root"])))

    @staticmethod
    def _record_hash(record: dict[str, Any]) -> str:
        from ..input import object_hash

        return object_hash({key: str(value) for key, value in record.items()})

    def _target_metadata(self) -> dict[str, Any]:
        from ..target_contract import target_contract_metadata

        return target_contract_metadata(self.cfg)


def create_build_context(cfg: dict[str, Any]) -> PreBuildContext:
    progress_level = cfg["runtime"]["progress_level"]
    parallel_fields = {
        key: cfg.get("runtime", {}).get(key)
        for key in [
            "requested_n_jobs",
            "resolved_n_jobs",
            "outer_workers",
            "inner_model_threads",
            "parallel_backend",
            "task_partition_version",
            "task_seed_strategy",
            "task_seed_hash",
        ]
    }
    run_started = pd.Timestamp.now(tz="UTC")
    run_id = (
        f"pre-{cfg['mode']}-{run_started.strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid.uuid4().hex[:8]}"
    )
    os.environ["AIR_SLOT_MODULE"] = "pre"
    os.environ["AIR_SLOT_MODE"] = str(cfg["mode"])
    os.environ["AIR_SLOT_RUN_ID"] = run_id
    output = cfg["output_root"]
    staging_parent = output / ".staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = staging_parent / f"run-{uuid.uuid4().hex}"
    paths = _ensure_dirs(staging)
    heartbeat = RunHeartbeat(
        mode=cfg["mode"],
        config_id=cfg["config_hash"],
        level=progress_level,
        runtime=parallel_fields,
    )
    heartbeat.start()
    implementation_path = Path(__file__).resolve().parents[1] / "pipeline_build.py"
    return PreBuildContext(
        cfg=cfg,
        progress_level=progress_level,
        parallel_fields=parallel_fields,
        run_started=run_started,
        current_run_id=run_id,
        output=output,
        staging=staging,
        paths=paths,
        heartbeat=heartbeat,
        implementation_hash=sha256_file(implementation_path),
    )
