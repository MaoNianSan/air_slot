from __future__ import annotations

from ..audit import build_evidence_audit
from ..bundle_writer import write_bundle
from ..contract_enrichment import enrich_contract
from ..flow import attach_flow, attach_flow_margins
from ..input import write_json, write_parquet
from ..pipeline_diagnostics import _formal_frame
from ..progress import stage_message
from ..reference import build_calibration, fit_flow_reference
from ..rule import build_rules
from ..snapshot_reference_enrichment import attach_aggregate_references
from ..state_quality import finalize_snapshot_quality
from ..validate import PreBundle
from ..weather import attach_weather
from .context import PreBuildContext


def _attach_sources(ctx: PreBuildContext) -> None:
    cfg = ctx.cfg
    started = ctx.stage("[2.7] Attach weather")
    ctx.snapshots = attach_weather(
        ctx.snapshots, ctx.metar, ctx.weather_climatology, cfg
    )
    ctx.finish(
        "2.7_attach_weather",
        started,
        input_rows=len(ctx.snapshots),
        output_rows=len(ctx.snapshots),
    )
    started = ctx.stage("[2.8] Attach flow")
    ctx.snapshots = attach_flow(
        ctx.snapshots, ctx.state_store, ctx.airport_reference, cfg
    )
    ctx.finish(
        "2.8_attach_flow",
        started,
        input_rows=len(ctx.snapshots),
        output_rows=len(ctx.snapshots),
        cache_status=ctx.cache_status,
    )


def _build_legacy_bundle(ctx: PreBuildContext) -> None:
    cfg = ctx.cfg
    started = ctx.stage("[2.9] Attach calibration and rules")
    ctx.snapshots = attach_aggregate_references(
        ctx.snapshots,
        ctx.turnaround_reference,
        ctx.airport_reference,
        ctx.passenger_reference,
    )
    ctx.flow_reference = fit_flow_reference(
        ctx.snapshots[ctx.snapshots["split"] == "train"]
    )
    ctx.snapshots = attach_flow_margins(ctx.snapshots, ctx.flow_reference, cfg)
    ctx.snapshots = finalize_snapshot_quality(ctx.snapshots, cfg)
    ctx.calibration = build_calibration(
        cfg,
        ctx.passenger_reference,
        ctx.flow_reference,
        ctx.turnaround_reference,
        ctx.airport_reference,
        ctx.weather_climatology,
    )
    ctx.rules = build_rules(ctx.snapshots, cfg)
    ctx.audit = build_evidence_audit(ctx.snapshots, cfg)
    ctx.finish(
        "2.9_attach_calibration_and_rules",
        started,
        input_rows=len(ctx.snapshots),
        output_rows=len(ctx.rules),
    )
    bundle = PreBundle(
        episodes=_formal_frame(ctx.episodes, cfg, "episodes"),
        snapshots=_formal_frame(ctx.snapshots, cfg, "snapshots"),
        calibration=_formal_frame(ctx.calibration, cfg, "calibration"),
        rules=_formal_frame(ctx.rules, cfg, "rules"),
        evidence_audit=_formal_frame(ctx.audit, cfg, "evidence_audit"),
    )
    bundle = enrich_contract(bundle, cfg)
    ctx.bundle = PreBundle(
        **{
            name: _formal_frame(frame, cfg, name)
            for name, frame in bundle.tables().items()
        }
    )
    started = ctx.stage("[2.10] Export five-table contract")
    write_bundle(ctx.bundle, ctx.paths)
    ctx.finish(
        "2.10_export_five_table_contract",
        started,
        output_rows=sum(len(frame) for frame in ctx.bundle.tables().values()),
    )
    stage_message(
        "Build completed:\n"
        + "\n".join(
            f"{name}: {len(frame)}" for name, frame in ctx.bundle.tables().items()
        ),
        level=ctx.progress_level,
    )


def _write_reference_artifacts(ctx: PreBuildContext) -> None:
    write_parquet(
        ctx.movement_reference.artifact_frame(),
        ctx.paths["artifacts"] / "movement_time_reference.parquet",
    )
    write_parquet(
        ctx.turnaround_reference.artifact_frame(),
        ctx.paths["artifacts"] / "turnaround_reference.parquet",
    )
    write_parquet(
        ctx.weather_climatology.artifact_frame(),
        ctx.paths["artifacts"] / "weather_climatology.parquet",
    )
    write_parquet(
        ctx.flow_reference.table, ctx.paths["artifacts"] / "flow_reference.parquet"
    )
    write_parquet(
        ctx.airport_reference.table,
        ctx.paths["artifacts"] / "airport_reference.parquet",
    )
    write_parquet(
        ctx.passenger_reference.artifact_frame(),
        ctx.paths["artifacts"] / "passenger_reference.parquet",
    )
    write_parquet(
        ctx.passenger_reference.temporal_audit_frame(),
        ctx.paths["artifacts"] / "passenger_reference_period_audit.parquet",
    )
    write_json(
        ctx.clipping_bounds, ctx.paths["artifacts"] / "label_clipping_bounds.json"
    )


def run_enrichment_stage(ctx: PreBuildContext) -> None:
    ctx.require(
        "snapshots",
        "state_store",
        "metar",
        "weather_climatology",
        "airport_reference",
        "turnaround_reference",
        "passenger_reference",
        "episodes",
        "movement_reference",
        "clipping_bounds",
    )
    _attach_sources(ctx)
    _build_legacy_bundle(ctx)
    _write_reference_artifacts(ctx)
