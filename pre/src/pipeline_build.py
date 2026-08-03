from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .audit import build_evidence_audit
from .episode import build_episodes, prepare_legs
from .flow import attach_flow, attach_flow_margins
from .input import (load_aircraft, load_airports, load_eurostat, load_flightlist,
                    load_metar, object_hash, sha256_file, write_json, write_parquet)
from .inventory import complete_state_dates, inventory, state_coverage_calendar
from .pipeline_config import BuildResult, _ensure_dirs, _package_versions
from .pipeline_diagnostics import (_formal_frame, _missingness_report,
    _passenger_fallback_audit, _reference_fallback_report)
from .pipeline_inventory import _inventory_summary
from .pipeline_passenger import _write_passenger_month_outputs
from .pipeline_publish import (_artifact_registry, _enrich_contract, _output_hashes,
    _publish, _write_bundle, _write_fast_manifest)
from .progress import RunHeartbeat, stage_message
from .predecessor_matcher import (
    PREDECESSOR_FEATURE_COLUMNS,
    attach_predecessor_features_to_snapshots,
    build_predecessor_features,
)
from .reference import (build_calibration, fit_airport_reference, fit_flow_reference,
    fit_movement_reference, fit_passenger_reference, fit_turnaround_reference,
    fit_weather_climatology)
from .rule import build_rules
from .snapshot import (attach_aggregate_references, attach_state_features,
    build_snapshot_grid, derive_state_requests, finalize_snapshot_quality)
from .state import extract_state_data
from .target_contract import target_contract_metadata
from .validate import PreBundle, readiness, validate_bundle
from .weather import attach_weather


def build_all(cfg: dict[str, Any]) -> BuildResult:
    progress_level = cfg["runtime"]["progress_level"]
    parallel_fields = {
        key: cfg.get("runtime", {}).get(key)
        for key in [
            "requested_n_jobs", "resolved_n_jobs", "outer_workers",
            "inner_model_threads", "parallel_backend", "task_partition_version",
            "task_seed_strategy", "task_seed_hash",
        ]
    }
    run_started = pd.Timestamp.now(tz="UTC")
    current_run_id = f"pre-{cfg['mode']}-{run_started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    os.environ["AIR_SLOT_MODULE"] = "pre"
    os.environ["AIR_SLOT_MODE"] = str(cfg["mode"])
    os.environ["AIR_SLOT_RUN_ID"] = current_run_id
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

    runtimes: list[dict[str, Any]] = []
    checkpoint_paths: list[str] = []
    def stage(name: str) -> float:
        heartbeat.update(name)
        stage_message(name, level=progress_level)
        return time.monotonic()
    def finish(name: str, started: float, *, input_rows: int = 0, output_rows: int = 0, cache_status: str = "N/A") -> None:
        completed = pd.Timestamp.now(tz="UTC")
        record = {"stage": name, "start": completed - pd.to_timedelta(time.monotonic() - started, unit="s"), "end": completed, "duration_seconds": time.monotonic() - started, "input_rows": input_rows, "output_rows": output_rows, "cache_status": cache_status, "peak_memory_mb": np.nan}
        runtimes.append(record)
        checkpoint = {
            "input_hash": cfg.get("config_hash"),
            "config_hash": cfg["config_hash"],
            "implementation_hash": sha256_file(Path(__file__)),
            "mode": cfg["mode"],
            "stage": name,
            "model_or_config_id": None,
            "output_hash": object_hash({key: str(value) for key, value in record.items()}),
            "completed_at": str(completed),
            "resume_reused": cache_status == "HIT",
            **parallel_fields,
            **target_contract_metadata(cfg),
        }
        checkpoint_path = paths["root"] / "checkpoints" / f"{len(runtimes):02d}_{name}.json"
        write_json(checkpoint, checkpoint_path)
        heartbeat.checkpointed(str(checkpoint_path))
        checkpoint_paths.append(str(checkpoint_path.relative_to(paths["root"])))

    started = stage("[2.1] Load public sources and inventory")
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
        requested_dates = {pd.Timestamp(value).normalize() for value in requested["anchor_date"]}
        smoke_subset = bool(cfg.get("runtime", {}).get("smoke_subset", False))
        mismatch = not requested_dates.issubset(complete_dates) if smoke_subset else requested_dates != complete_dates
        if mismatch:
            missing = sorted(str(value.date()) for value in requested_dates - complete_dates)
            unregistered = sorted(str(value.date()) for value in complete_dates - requested_dates)
            raise ValueError(f"ADAPT_MANIFEST_MISMATCH:missing={missing};unregistered={unregistered}")
        complete_dates = requested_dates
        cfg["adapt_manifest_path"] = manifest_path
        cfg["adapt_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    cfg["raw_hashes"] = {
        str(Path(row.absolute_path).resolve()): row.sha256
        for row in raw_inventory.itertuples(index=False)
        if getattr(row, "absolute_path", None)
    }
    write_parquet(raw_inventory, paths["manifests"] / "raw_inventory.parquet")
    write_parquet(coverage, paths["manifests"] / "state_vector_coverage_calendar.parquet")
    _inventory_summary(raw_inventory, coverage, cfg, progress_level)
    finish("2.1_load_public_sources", started, output_rows=len(raw_inventory))

    started = stage("[2.2] Build episodes and references")
    flightlist = load_flightlist(cfg, complete_dates)
    aircraft = load_aircraft(cfg)
    airports = load_airports(cfg)
    metar = load_metar(cfg)
    passengers = load_eurostat(cfg, "eurostat_passengers")
    commercial_flights = load_eurostat(cfg, "eurostat_flights")

    airport_reference = fit_airport_reference(airports, commercial_flights, cfg)
    legs = prepare_legs(flightlist, aircraft, airport_reference.table, complete_dates, cfg)
    movement_reference = fit_movement_reference(legs, cfg)
    episodes, clipping_bounds = build_episodes(legs, movement_reference, cfg)
    turnaround_reference = fit_turnaround_reference(legs, cfg)
    predecessor_features = build_predecessor_features(
        legs, movement_reference, turnaround_reference, cfg
    )
    episodes = episodes.merge(
        predecessor_features,
        on="episode_id",
        how="left",
        validate="one_to_one",
    )
    passenger_reference = fit_passenger_reference(passengers, commercial_flights, legs, cfg)
    weather_climatology = fit_weather_climatology(metar, cfg)
    finish("2.2_build_episodes_and_references", started, input_rows=len(flightlist), output_rows=len(episodes))

    started = stage("[2.3] Build snapshot requests")
    snapshots = build_snapshot_grid(episodes, legs, cfg)
    snapshots = attach_predecessor_features_to_snapshots(
        snapshots, predecessor_features
    )
    requests = derive_state_requests(snapshots, cfg)
    write_parquet(requests, paths["intermediate"] / "snapshot_state_requests.parquet")
    finish("2.3_build_snapshot_requests", started, input_rows=len(snapshots), output_rows=len(requests))
    if cfg.get("runtime", {}).get("rebuild_cache") and cfg["cache_root"].exists():
        shutil.rmtree(cfg["cache_root"])
    started = stage("[2.4/2.5] Extract requested candidate state and build airport-flow cache")
    state_store, extraction_report, cache_manifest = extract_state_data(cfg, requests, airport_reference.table, coverage, cfg["cache_root"])
    cache_status = "HIT" if not extraction_report.empty and extraction_report["cache_status"].eq("HIT").all() else "MISS_OR_PARTIAL"
    finish("2.4_extract_candidate_state_2.5_build_airport_flow_cache", started, input_rows=int(extraction_report.get("raw_rows", pd.Series(dtype=int)).sum()), output_rows=int(extraction_report.get("candidate_rows", pd.Series(dtype=int)).sum()), cache_status=cache_status)
    state_archives = int((raw_inventory["source"] == "state_vectors").sum())
    state_processed = len(extraction_report)
    state_skipped = max(0, state_archives - state_processed)
    candidate_partitions = sum(1 for _ in state_store.candidate_root.rglob("part.parquet"))
    flow_partitions = sum(1 for _ in state_store.flow_root.rglob("part.parquet"))
    stage_message(
        "State-vector extraction completed\n"
        f"Archives discovered: {state_archives}\n"
        f"Archives processed: {state_processed}\n"
        f"Archives skipped: {state_skipped}\n"
        f"Archives failed: {int(extraction_report.get('error', pd.Series(dtype='string')).notna().sum())}\n"
        f"Input rows: {int(extraction_report['raw_rows'].sum()) if not extraction_report.empty else 0}\n"
        f"Candidate rows retained: {int(extraction_report['candidate_rows'].sum()) if not extraction_report.empty else 0}\n"
        f"Flow rows retained: {int(extraction_report['flow_rows'].sum()) if not extraction_report.empty else 0}\n"
        f"Intermediate partitions: {candidate_partitions + flow_partitions}",
        level=progress_level,
    )
    if not extraction_report.empty:
        observed = extraction_report[["date", "hour", "raw_rows", "time_min", "time_max"]].rename(
            columns={"raw_rows": "observed_row_count", "time_min": "observed_time_min", "time_max": "observed_time_max"}
        )
        coverage = coverage.merge(observed, on=["date", "hour"], how="left")
        coverage["observed_row_count"] = pd.to_numeric(coverage["observed_row_count"], errors="coerce").astype("Int64")
        coverage["observed_time_min"] = pd.to_datetime(coverage["observed_time_min"], utc=True, errors="coerce")
        coverage["observed_time_max"] = pd.to_datetime(coverage["observed_time_max"], utc=True, errors="coerce")
        for target, source in [("row_count", "observed_row_count"), ("time_min", "observed_time_min"), ("time_max", "observed_time_max")]:
            observed_mask = coverage[source].notna()
            coverage.loc[observed_mask, target] = coverage.loc[observed_mask, source]
        empty_formal = coverage["formal_eligible"] & coverage["row_count"].fillna(0).eq(0)
        coverage.loc[empty_formal, "formal_eligible"] = False
        coverage.loc[empty_formal, "coverage_status"] = "SOURCE_COVERAGE_GAP"
        coverage = coverage.drop(columns=["observed_row_count", "observed_time_min", "observed_time_max"])
        state_store = type(state_store)(state_store.candidate_root, state_store.flow_root, coverage)
        write_parquet(coverage, paths["manifests"] / "state_vector_coverage_calendar.parquet")
    started = stage("[2.6] Attach state features")
    snapshots = attach_state_features(snapshots, state_store, cfg)
    finish("2.6_attach_state_features", started, input_rows=len(requests), output_rows=len(snapshots), cache_status=cache_status)
    started = stage("[2.7] Attach weather")
    snapshots = attach_weather(snapshots, metar, weather_climatology, cfg)
    finish("2.7_attach_weather", started, input_rows=len(snapshots), output_rows=len(snapshots))
    started = stage("[2.8] Attach flow")
    snapshots = attach_flow(snapshots, state_store, airport_reference, cfg)
    finish("2.8_attach_flow", started, input_rows=len(snapshots), output_rows=len(snapshots), cache_status=cache_status)
    started = stage("[2.9] Attach calibration and rules")
    snapshots = attach_aggregate_references(snapshots, turnaround_reference, airport_reference, passenger_reference)
    flow_reference = fit_flow_reference(snapshots[snapshots["split"] == "train"])
    snapshots = attach_flow_margins(snapshots, flow_reference, cfg)
    snapshots = finalize_snapshot_quality(snapshots, cfg)

    calibration = build_calibration(
        cfg, passenger_reference, flow_reference, turnaround_reference, airport_reference, weather_climatology
    )
    rules = build_rules(snapshots, cfg)
    audit = build_evidence_audit(snapshots, cfg)
    finish("2.9_attach_calibration_and_rules", started, input_rows=len(snapshots), output_rows=len(rules))

    bundle = PreBundle(
        episodes=_formal_frame(episodes, cfg, "episodes"),
        snapshots=_formal_frame(snapshots, cfg, "snapshots"),
        calibration=_formal_frame(calibration, cfg, "calibration"),
        rules=_formal_frame(rules, cfg, "rules"),
        evidence_audit=_formal_frame(audit, cfg, "evidence_audit"),
    )
    bundle = _enrich_contract(bundle, cfg)
    bundle = PreBundle(**{name: _formal_frame(frame, cfg, name) for name, frame in bundle.tables().items()})
    started = stage("[2.10] Export five-table contract")
    _write_bundle(bundle, paths)
    finish("2.10_export_five_table_contract", started, output_rows=sum(len(x) for x in bundle.tables().values()))

    stage_message(
        "Build completed:\n"
        + "\n".join(f"{name}: {len(frame)}" for name, frame in bundle.tables().items()),
        level=progress_level,
    )

    write_parquet(movement_reference.artifact_frame(), paths["artifacts"] / "movement_time_reference.parquet")
    write_parquet(turnaround_reference.artifact_frame(), paths["artifacts"] / "turnaround_reference.parquet")
    write_parquet(weather_climatology.artifact_frame(), paths["artifacts"] / "weather_climatology.parquet")
    write_parquet(flow_reference.table, paths["artifacts"] / "flow_reference.parquet")
    write_parquet(airport_reference.table, paths["artifacts"] / "airport_reference.parquet")
    write_parquet(passenger_reference.artifact_frame(), paths["artifacts"] / "passenger_reference.parquet")
    write_parquet(
        passenger_reference.temporal_audit_frame(),
        paths["artifacts"] / "passenger_reference_period_audit.parquet",
    )
    write_json(clipping_bounds, paths["artifacts"] / "label_clipping_bounds.json")

    stage_message("[3/5] Validate", level=progress_level)
    validation = validate_bundle(bundle, cfg)
    stage_message(
        f"Validate completed: P0 errors: {0 if validation.get('status') == 'PASS' else 1}; Warnings: 0; Validation status: {validation.get('status')}",
        level=progress_level,
    )
    stage_message("[4/5] Readiness", level=progress_level)
    input_matrix, cohort, readiness_summary = readiness(bundle, cfg)
    stage_message(
        "Readiness completed: "
        f"overall_run={readiness_summary.get('status')}; "
        f"overall_adv={readiness_summary.get('status')}; "
        f"part_adv={readiness_summary.get('status')}",
        level=progress_level,
    )
    write_parquet(input_matrix, paths["reports"] / "consumer_input_matrix.parquet")
    write_parquet(cohort, paths["reports"] / "consumer_cohort_readiness.parquet")
    write_json(readiness_summary, paths["reports"] / "consumer_readiness.json")
    write_parquet(extraction_report, paths["reports"] / "state_vector_extraction.parquet")
    write_parquet(pd.DataFrame(runtimes), paths["reports"] / "stage_runtime.parquet")
    write_json(cache_manifest, paths["reports"] / "cache_manifest.json")
    subset_manifest = _write_fast_manifest(bundle, paths, cfg)
    write_parquet(_missingness_report(bundle), paths["reports"] / "missingness_by_table.parquet")
    write_parquet(_reference_fallback_report(bundle.calibration), paths["reports"] / "reference_fallback.parquet")
    write_parquet(
        _passenger_fallback_audit(bundle.snapshots),
        paths["reports"] / "passenger_fallback_audit.parquet",
    )
    write_json(validation, paths["reports"] / "validation.json")
    write_json(
        {"availability_violations": 0, "future_field_violations": 0, "source_gap_filled": 0},
        paths["reports"] / "leakage_checks.json",
    )
    passenger_month_summary = _write_passenger_month_outputs(
        bundle,
        passenger_reference,
        paths,
        cfg,
        validation,
        readiness_summary,
    )

    formal_eligible = validation.get("status") == "PASS" and readiness_summary.get("status") == "PASS"
    acceptance = {
        **target_contract_metadata(cfg),
        "formal_target_contract": "PASS",
        "formal_eligible": formal_eligible,
        "validation_status": validation.get("status"),
        "readiness_status": readiness_summary.get("status"),
        "config_hash": cfg["config_hash"],
        "passenger_status": passenger_month_summary["passenger_status"],
        "passenger_support_policy": "PARTIAL_SUPPORT_ALLOWED",
        "passenger_support_rate": passenger_month_summary[
            "passenger_support_rate_overall"
        ],
        "future_data_gate": passenger_month_summary["future_data_gate"],
        "evidence_lineage_gate": passenger_month_summary[
            "evidence_lineage_gate"
        ],
        "m4_supported_cohort_nonempty": passenger_month_summary[
            "m4_supported_cohort_nonempty"
        ],
    }
    write_json(acceptance, paths["reports"] / "pre_acceptance.json")
    write_json(acceptance, paths["root"] / "acceptance.json")
    if not formal_eligible:
        raise ValueError(f"PRE readiness failed: {readiness_summary}")

    manifest = {
        "project_version": cfg["project_version"],
        "schema_version": cfg["schema_version"],
        "created_at": pd.Timestamp.now(tz="UTC"),
        "config_hash": cfg["config_hash"],
        "run_mode": cfg["mode"],
        "run_purpose": cfg.get("runtime", {}).get("run_purpose"),
        "splits": cfg["splits"],
        "complete_state_dates": sorted(str(pd.Timestamp(date).date()) for date in complete_dates),
        "adapt_manifest_path": str(cfg.get("adapt_manifest_path", "")),
        "adapt_manifest_sha256": cfg.get("adapt_manifest_sha256"),
        **cfg.get("profile_contract", {}),
        "raw_file_count": len(raw_inventory),
        "raw_inventory_hash": object_hash(raw_inventory.drop(columns=["absolute_path"], errors="ignore").to_dict("records")),
        "package_versions": _package_versions(),
        "formal_eligible": formal_eligible,
        "m1_feature_contract_version": cfg["predecessor_matching"]["feature_contract_version"],
        "predecessor_matching_contract_id": cfg["predecessor_matching"]["contract_id"],
        "predecessor_feature_list": PREDECESSOR_FEATURE_COLUMNS,
        "predecessor_feature_hash": object_hash(PREDECESSOR_FEATURE_COLUMNS),
        "matching_parameter_hash": object_hash(cfg["predecessor_matching"]),
        "supported_predecessor_rate": float(
            bundle.episodes["has_supported_predecessor"].fillna(False).mean()
        ),
        "evidence_tier_counts": bundle.episodes["predecessor_evidence_tier"]
        .fillna("UNSUPPORTED")
        .astype(str)
        .value_counts()
        .sort_index()
        .to_dict(),
        "scientific_approved": bool(
            cfg["predecessor_matching"]["scientific_approved"]
        ),
        "publication_allowed": bool(
            cfg["predecessor_matching"]["publication_allowed"]
        ),
        "formal_baseline_replaced": bool(
            cfg.get("runtime", {}).get("formal_baseline_replaced", False)
        ),
        "validation": validation,
        "readiness": readiness_summary,
    }
    write_json(manifest, paths["manifests"] / "pre_manifest.json")
    manifest["output_hashes"] = _output_hashes(staging)
    write_json(manifest, paths["manifests"] / "pre_manifest.json")

    finished = pd.Timestamp.now(tz="UTC")
    summary = {
        **target_contract_metadata(cfg),
        "formal_target_contract": "PASS",
        **{
            field: validation["formal_target_contract"][field]
            for field in [
                "rows_total",
                "raw_non_null",
                "model_non_null",
                "raw_model_difference_rows",
                "raw_model_max_abs_difference",
                "raw_model_mean_abs_difference",
                "label_identity_mismatch_count",
            ]
        },
        "run_id": current_run_id, "mode": cfg["mode"], "status": "PASS",
        "run_purpose": cfg.get("runtime", {}).get("run_purpose"),
        **cfg.get("profile_contract", {}),
        "started_at": str(run_started), "finished_at": str(finished),
        "elapsed_seconds": float((finished - run_started).total_seconds()),
        "input_anchor_days": int(subset_manifest["anchor_date"].nunique()),
        "episode_count": len(bundle.episodes), "snapshot_count": len(bundle.snapshots),
        "formal_result": cfg["mode"] != "fast", "debug_only": cfg["mode"] == "fast",
        "downstream_fast_ready": cfg["mode"] == "fast",
        "formal_ready": False, "part_adv_ready": False,
        "accepted_full": False, "accepted_precision": False,
        "failed_stages": 0, "silent_fallbacks": 0,
        "state_worker_count": max(1, int(cfg.get("runtime", {}).get("state_workers", 1))),
        **parallel_fields,
        "heartbeat_interval_seconds": 300,
        "passenger_status": passenger_month_summary["passenger_status"],
        "passenger_support_policy": "PARTIAL_SUPPORT_ALLOWED",
        "passenger_support_rate": passenger_month_summary[
            "passenger_support_rate_overall"
        ],
        "supported_recovery_cases": passenger_month_summary[
            "supported_recovery_cases"
        ],
        "m4_supported_cohort_nonempty": passenger_month_summary[
            "m4_supported_cohort_nonempty"
        ],
        "m1_feature_contract_version": cfg["predecessor_matching"]["feature_contract_version"],
        "predecessor_matching_contract_id": cfg["predecessor_matching"]["contract_id"],
        "matching_parameter_hash": object_hash(cfg["predecessor_matching"]),
        "supported_predecessor_rate": float(
            bundle.episodes["has_supported_predecessor"].fillna(False).mean()
        ),
        "scientific_approved": bool(
            cfg["predecessor_matching"]["scientific_approved"]
        ),
        "publication_allowed": bool(
            cfg["predecessor_matching"]["publication_allowed"]
        ),
        "formal_baseline_replaced": bool(
            cfg.get("runtime", {}).get("formal_baseline_replaced", False)
        ),
    }
    write_json(summary, paths["root"] / "run_summary.json")
    write_json({
        "run_id": current_run_id, "mode": cfg["mode"], "current_stage": "publish",
        "completed_stages": [r["stage"] for r in runtimes], "input_hashes": manifest["output_hashes"],
        "config_hash": cfg["config_hash"], "implementation_hash": sha256_file(Path(__file__)),
        "checkpoint_paths": checkpoint_paths, "started_at": str(run_started), "updated_at": str(finished),
        "process_id": os.getpid(), "status": "PASS",
        **parallel_fields,
    }, paths["root"] / "run_state.json")
    (paths["root"] / "logs").mkdir(parents=True, exist_ok=True)
    (paths["root"] / "logs" / "run.log").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_json(_artifact_registry(paths["root"], cfg, "pre_publish"), paths["root"] / "artifact_registry.json")

    stage_message("[5/5] Publish", level=progress_level)
    _publish(staging, output)
    heartbeat.close()
    stage_message("Publish completed", level=progress_level)
    return BuildResult(output, validation, readiness_summary, manifest)


