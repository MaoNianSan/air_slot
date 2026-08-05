from __future__ import annotations

import shutil

import pandas as pd

from ..input import write_parquet
from ..legacy_snapshot_grid import build_snapshot_grid, derive_state_requests
from ..predecessor_matcher import attach_predecessor_features_to_snapshots
from ..progress import stage_message
from ..state import extract_state_data
from ..state_feature_resolver import attach_state_features
from .context import PreBuildContext


def _reconcile_coverage(ctx: PreBuildContext) -> None:
    if ctx.extraction_report.empty:
        return
    observed = ctx.extraction_report[
        ["date", "hour", "raw_rows", "time_min", "time_max"]
    ].rename(
        columns={
            "raw_rows": "observed_row_count",
            "time_min": "observed_time_min",
            "time_max": "observed_time_max",
        }
    )
    coverage = ctx.coverage.merge(observed, on=["date", "hour"], how="left")
    coverage["observed_row_count"] = pd.to_numeric(
        coverage["observed_row_count"], errors="coerce"
    ).astype("Int64")
    coverage["observed_time_min"] = pd.to_datetime(
        coverage["observed_time_min"], utc=True, errors="coerce"
    )
    coverage["observed_time_max"] = pd.to_datetime(
        coverage["observed_time_max"], utc=True, errors="coerce"
    )
    for target, source in [
        ("row_count", "observed_row_count"),
        ("time_min", "observed_time_min"),
        ("time_max", "observed_time_max"),
    ]:
        observed_mask = coverage[source].notna()
        coverage.loc[observed_mask, target] = coverage.loc[observed_mask, source]
    empty_formal = coverage["formal_eligible"] & coverage["row_count"].fillna(0).eq(0)
    coverage.loc[empty_formal, "formal_eligible"] = False
    coverage.loc[empty_formal, "coverage_status"] = "SOURCE_COVERAGE_GAP"
    coverage = coverage.drop(
        columns=[
            "observed_row_count",
            "observed_time_min",
            "observed_time_max",
        ]
    )
    ctx.coverage = coverage
    ctx.state_store = type(ctx.state_store)(
        ctx.state_store.candidate_root, ctx.state_store.flow_root, coverage
    )
    write_parquet(
        coverage,
        ctx.paths["manifests"] / "state_vector_coverage_calendar.parquet",
    )


def _build_requests(ctx: PreBuildContext) -> None:
    cfg = ctx.cfg
    started = ctx.stage("[2.3] Build snapshot requests")
    snapshots = build_snapshot_grid(ctx.episodes, ctx.legs, cfg)
    snapshots = attach_predecessor_features_to_snapshots(
        snapshots, ctx.predecessor_features
    )
    requests = derive_state_requests(snapshots, cfg)
    write_parquet(
        requests, ctx.paths["intermediate"] / "snapshot_state_requests.parquet"
    )
    ctx.snapshots = snapshots
    ctx.requests = requests
    ctx.finish(
        "2.3_build_snapshot_requests",
        started,
        input_rows=len(snapshots),
        output_rows=len(requests),
    )


def _extract_state(ctx: PreBuildContext) -> None:
    cfg = ctx.cfg
    if cfg.get("runtime", {}).get("rebuild_cache") and cfg["cache_root"].exists():
        shutil.rmtree(cfg["cache_root"])
    started = ctx.stage(
        "[2.4/2.5] Extract requested candidate state and build airport-flow cache"
    )
    state_store, extraction_report, cache_manifest = extract_state_data(
        cfg,
        ctx.requests,
        ctx.airport_reference.table,
        ctx.coverage,
        cfg["cache_root"],
    )
    cache_status = (
        "HIT"
        if not extraction_report.empty
        and extraction_report["cache_status"].eq("HIT").all()
        else "MISS_OR_PARTIAL"
    )
    ctx.state_store = state_store
    ctx.extraction_report = extraction_report
    ctx.cache_manifest = cache_manifest
    ctx.cache_status = cache_status
    ctx.finish(
        "2.4_extract_candidate_state_2.5_build_airport_flow_cache",
        started,
        input_rows=int(
            extraction_report.get("raw_rows", pd.Series(dtype=int)).sum()
        ),
        output_rows=int(
            extraction_report.get("candidate_rows", pd.Series(dtype=int)).sum()
        ),
        cache_status=cache_status,
    )
    state_archives = int((ctx.raw_inventory["source"] == "state_vectors").sum())
    candidate_partitions = sum(
        1 for _ in state_store.candidate_root.rglob("part.parquet")
    )
    flow_partitions = sum(1 for _ in state_store.flow_root.rglob("part.parquet"))
    stage_message(
        "State-vector extraction completed\n"
        f"Archives discovered: {state_archives}\n"
        f"Archives processed: {len(extraction_report)}\n"
        f"Archives skipped: {max(0, state_archives - len(extraction_report))}\n"
        f"Archives failed: {int(extraction_report.get('error', pd.Series(dtype='string')).notna().sum())}\n"
        f"Input rows: {int(extraction_report['raw_rows'].sum()) if not extraction_report.empty else 0}\n"
        f"Candidate rows retained: {int(extraction_report['candidate_rows'].sum()) if not extraction_report.empty else 0}\n"
        f"Flow rows retained: {int(extraction_report['flow_rows'].sum()) if not extraction_report.empty else 0}\n"
        f"Intermediate partitions: {candidate_partitions + flow_partitions}",
        level=ctx.progress_level,
    )
    _reconcile_coverage(ctx)


def _attach_state(ctx: PreBuildContext) -> None:
    started = ctx.stage("[2.6] Attach state features")
    ctx.snapshots = attach_state_features(ctx.snapshots, ctx.state_store, ctx.cfg)
    ctx.finish(
        "2.6_attach_state_features",
        started,
        input_rows=len(ctx.requests),
        output_rows=len(ctx.snapshots),
        cache_status=ctx.cache_status,
    )


def run_state_stage(ctx: PreBuildContext) -> None:
    ctx.require(
        "episodes",
        "legs",
        "predecessor_features",
        "airport_reference",
        "coverage",
        "raw_inventory",
    )
    _build_requests(ctx)
    _extract_state(ctx)
    _attach_state(ctx)
