from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from ..input import write_parquet
from ..inventory import complete_state_dates, inventory, state_coverage_calendar
from ..pipeline_inventory import _inventory_summary
from .context import PreBuildContext


def run_inventory_stage(ctx: PreBuildContext) -> None:
    cfg = ctx.cfg
    started = ctx.stage("[2.1] Load public sources and inventory")
    raw_inventory = inventory(cfg)
    coverage = state_coverage_calendar(raw_inventory, cfg)
    complete_dates = complete_state_dates(coverage, cfg)
    if not complete_dates:
        raise ValueError("no complete state-vector observation day")
    adapt_manifest_path = cfg.get("runtime", {}).get("adapt_manifest_path")
    if adapt_manifest_path:
        manifest_path = Path(adapt_manifest_path)
        if not manifest_path.is_absolute():
            manifest_path = (cfg["project_root"] / manifest_path).resolve()
        requested = pd.read_csv(manifest_path)
        requested_dates = {
            pd.Timestamp(value).normalize() for value in requested["anchor_date"]
        }
        smoke_subset = bool(cfg.get("runtime", {}).get("smoke_subset", False))
        mismatch = (
            not requested_dates.issubset(complete_dates)
            if smoke_subset
            else requested_dates != complete_dates
        )
        if mismatch:
            missing = sorted(
                str(value.date()) for value in requested_dates - complete_dates
            )
            unregistered = sorted(
                str(value.date()) for value in complete_dates - requested_dates
            )
            raise ValueError(
                f"ADAPT_MANIFEST_MISMATCH:missing={missing};"
                f"unregistered={unregistered}"
            )
        complete_dates = requested_dates
        cfg["adapt_manifest_path"] = manifest_path
        cfg["adapt_manifest_sha256"] = hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest()
    cfg["raw_hashes"] = {
        str(Path(row.absolute_path).resolve()): row.sha256
        for row in raw_inventory.itertuples(index=False)
        if getattr(row, "absolute_path", None)
    }
    write_parquet(raw_inventory, ctx.paths["manifests"] / "raw_inventory.parquet")
    write_parquet(
        coverage,
        ctx.paths["manifests"] / "state_vector_coverage_calendar.parquet",
    )
    _inventory_summary(raw_inventory, coverage, cfg, ctx.progress_level)
    ctx.raw_inventory = raw_inventory
    ctx.coverage = coverage
    ctx.complete_dates = complete_dates
    ctx.finish("2.1_load_public_sources", started, output_rows=len(raw_inventory))
