from __future__ import annotations

import json
import os

import pandas as pd

from ..artifact_registry import build_artifact_registry, output_hashes
from ..bundle_writer import publish_bundle
from ..input import write_json
from ..pipeline_config import BuildResult
from ..progress import stage_message
from ..run_metadata import build_manifest, build_summary
from .context import PreBuildContext


def run_finalization_stage(ctx: PreBuildContext) -> BuildResult:
    ctx.require(
        "bundle",
        "validation",
        "readiness_summary",
        "subset_manifest",
        "passenger_month_summary",
        "raw_inventory",
        "complete_dates",
    )
    manifest = build_manifest(ctx, output_hashes(ctx.staging))
    finished = pd.Timestamp.now(tz="UTC")
    summary = build_summary(ctx, finished)
    write_json(summary, ctx.paths["root"] / "run_summary.json")
    write_json(
        {
            "run_id": ctx.current_run_id,
            "mode": ctx.cfg["mode"],
            "current_stage": "publish",
            "completed_stages": [record["stage"] for record in ctx.runtimes],
            "input_hashes": manifest["output_hashes"],
            "config_hash": ctx.cfg["config_hash"],
            "implementation_hash": ctx.implementation_hash,
            "checkpoint_paths": ctx.checkpoint_paths,
            "started_at": str(ctx.run_started),
            "updated_at": str(finished),
            "process_id": os.getpid(),
            "status": "PASS",
            **ctx.parallel_fields,
        },
        ctx.paths["root"] / "run_state.json",
    )
    (ctx.paths["root"] / "logs").mkdir(parents=True, exist_ok=True)
    (ctx.paths["root"] / "logs" / "run.log").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    write_json(
        build_artifact_registry(ctx.paths["root"], ctx.cfg, "pre_publish"),
        ctx.paths["root"] / "artifact_registry.json",
    )
    stage_message("[5/5] Publish", level=ctx.progress_level)
    publish_bundle(ctx.staging, ctx.output)
    ctx.heartbeat.close()
    stage_message("Publish completed", level=ctx.progress_level)
    ctx.manifest = manifest
    return BuildResult(ctx.output, ctx.validation, ctx.readiness_summary, manifest)
