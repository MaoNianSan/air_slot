from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from .ranking_contract import build_ranking_prefixes

from .cohort import build_cohorts
from .config import RunConfig
from .failures import FormalRunBlocked
from .input import (
    FORMAL_TARGET_COLUMN,
    load_pre_bundle,
    normalize_bundle,
)
from .m1 import prepare_model_frame
from .m3 import load_actions
from .m4 import evaluate_m4, screen_physical_actions
from .progress import Progress
from .pipeline_checkpoint import (
    FullBlockedByFastAcceptance,
    assert_fast_acceptance,
    mark_running_staging_incomplete,
    prepare_empty_publish_target,
    requires_fast_acceptance,
    validate_resume_checkpoints as _validate_resume_checkpoints,
    write_stage_checkpoint as _write_stage_checkpoint,
)
from .pipeline_data import (
    attach_rule_context as _attach_rule_context,
    authoritative_m2_summary as _authoritative_m2_summary,
    enrich_snapshots as _enrich_snapshots,
    passenger_support as _passenger_support,
    prediction_table as _prediction_table,
    resolve_pre_output as _resolve_pre_output,
    set_model_attrs as _set_model_attrs,
    subset_rules as _subset_rules,
    trigger as _trigger,
    validate_action_library as _validate_action_library,
    validate_bundle_with_rule_anchors as _validate_bundle_with_rule_anchors,
    write_frame as _write_df,
)
from .pipeline_parameters import parameter_manifest as _parameter_manifest
from .pipeline_fit import fit_artifacts as _fit_artifacts
from .pipeline_modes import report_mode, rerun_report, validate_mode
from .pipeline_precision import run_precision
from .pipeline_finalize import FinalizationInputs, finalize_experiment
from .utils import run_id, stable_hash, write_json


def run_experiment(
    cfg: RunConfig,
    mode: str,
    progress_level: str = "normal",
    pre_output: Path | None = None,
    refit: bool = True,
    *,
    override_fast_gate: bool = False,
    output_name: str | None = None,
    resume_staging: Path | None = None,
) -> Path:
    """Authoritative modular M1-M4 runner with one fixed per-mode artifact root."""

    parallel_fields = {
        key: cfg.compute.get(key)
        for key in [
            "requested_n_jobs", "resolved_n_jobs", "outer_workers",
            "inner_model_threads", "parallel_backend", "task_partition_version",
            "task_seed_strategy", "task_seed_hash",
        ]
    }

    if mode not in {"fast", "diagnostic", "acceptance_23d", "middle", "full"}:
        raise ValueError("mode must be fast, diagnostic, acceptance_23d, middle, or full")
    if requires_fast_acceptance(
        mode, cfg.profile_contract, override_fast_gate=override_fast_gate
    ):
        assert_fast_acceptance(cfg.root)
    published_mode = output_name or mode
    target = cfg.root / "output" / published_mode
    prepare_empty_publish_target(target)
    started_wall = pd.Timestamp.now(tz="UTC")
    started_clock = time.monotonic()
    rid = run_id(published_mode, cfg.config_hash, cfg.root)
    os.environ["AIR_SLOT_MODULE"] = "overall_run"
    os.environ["AIR_SLOT_MODE"] = published_mode
    os.environ["AIR_SLOT_RUN_ID"] = rid
    if resume_staging is not None:
        staging = resume_staging.resolve()
        expected_parent = (cfg.root / "output" / ".staging").resolve()
        try:
            staging.relative_to(expected_parent)
        except ValueError as exc:
            raise FormalRunBlocked(f"RESUME_STAGING_OUTSIDE_OUTPUT:{staging}") from exc
        if not staging.is_dir() or not all((staging / name).exists() for name in ("m1.joblib", "m2.joblib", "m4.joblib")):
            raise FormalRunBlocked(f"RESUME_STAGING_MODEL_SET_INCOMPLETE:{staging}")
        rid = staging.name
    else:
        staging = cfg.root / "output" / ".staging" / rid
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=False)
        for name in ("metrics", "logs", "m1_predictive_samples", "checkpoints"):
            (staging / name).mkdir()
        write_json(staging / "run_state.json", {
            "run_id": rid,
            "mode": published_mode,
            "compute_mode": mode,
            "status": "RUNNING",
            "process_id": os.getpid(),
            "started_at": started_wall,
            "config_hash": cfg.config_hash,
            "implementation_hash": cfg.implementation_hash,
            "checkpoint_paths": [],
        })
    progress = Progress(progress_level)
    progress.start_heartbeat(
        module="overall_run",
        mode=published_mode,
        interval_seconds=300,
        runtime=parallel_fields,
    )

    progress.stage(1, 10, "Validate PRE outputs")
    bundle = load_pre_bundle(_resolve_pre_output(cfg, pre_output), cfg.scientific, require_acceptance=True)
    input_audit = _validate_bundle_with_rule_anchors(bundle, cfg.scientific)
    tables = normalize_bundle(bundle)
    tables["snapshots"] = _enrich_snapshots(tables["snapshots"], tables["calibration"])
    tables["snapshots"] = _attach_rule_context(tables["snapshots"], tables["rules"])
    if resume_staging is not None:
        previous_state_path = staging / "run_state.json"
        previous_state = (
            json.loads(previous_state_path.read_text(encoding="utf-8"))
            if previous_state_path.is_file()
            else {}
        )
        write_json(previous_state_path, {
            "run_id": rid,
            "mode": published_mode,
            "compute_mode": mode,
            "status": "RUNNING",
            "current_stage": "resume_validation",
            "process_id": os.getpid(),
            "started_at": started_wall,
            "previous_status": previous_state.get("status"),
            "config_hash": cfg.config_hash,
            "implementation_hash": cfg.implementation_hash,
        })
        _validate_resume_checkpoints(
            staging, mode=published_mode, cfg=cfg, input_hashes=bundle.file_hashes
        )
        write_json(staging / "run_state.json", {
            "run_id": rid,
            "mode": published_mode,
            "compute_mode": mode,
            "status": "RUNNING",
            "process_id": os.getpid(),
            "started_at": started_wall,
            "config_hash": cfg.config_hash,
            "implementation_hash": cfg.implementation_hash,
            "input_hashes": bundle.file_hashes,
            "resume_reused": True,
            "checkpoint_paths": sorted(
                path.relative_to(staging).as_posix()
                for path in (staging / "checkpoints").glob("*.json")
            ),
        })

    progress.stage(2, 10, "Build model frame")
    model_frame, features, numeric, categorical = prepare_model_frame(tables["snapshots"], tables["episodes"], cfg.scientific)
    model_frame = _set_model_attrs(model_frame, features, numeric, categorical)
    progress.stage(3, 10, "Build cohorts")
    mode_cfg = cfg.mode(mode)
    cohorts = build_cohorts(tables["snapshots"], cfg.scientific, mode_cfg, int(cfg.compute["random_seed"]))
    if cohorts.formal_core.empty:
        raise FormalRunBlocked("FORMAL_CORE_EMPTY")

    if resume_staging is not None:
        import joblib

        progress.stage(4, 10, "Reuse frozen staging models")
        m1 = joblib.load(staging / "m1.joblib")
        m2 = joblib.load(staging / "m2.joblib")
        m3 = joblib.load(staging / "m3.joblib")
        m4 = joblib.load(staging / "m4.joblib")
        tuning_path = staging / "metrics" / "m1_tuning.parquet"
        feature_path = staging / "metrics" / "m1_feature_audit.parquet"
        tuning = pd.read_parquet(tuning_path) if tuning_path.exists() else pd.DataFrame()
        feature_audit = pd.read_parquet(feature_path) if feature_path.exists() else pd.DataFrame()
    else:
        m1, m2, m3, m4, tuning, feature_audit = _fit_artifacts(
            cfg, tables, model_frame, features, numeric, categorical, staging, progress, mode=mode,
            formal_target_definition_hash=json.loads(
                (bundle.pre_output / "run_summary.json").read_text(encoding="utf-8")
            )["formal_target_definition_hash"],
            test_label_hash=stable_hash(
                model_frame.merge(
                    cohorts.formal_core[["episode_id", "snapshot_id"]].drop_duplicates(),
                    on=["episode_id", "snapshot_id"], how="inner", validate="one_to_one",
                )[["snapshot_id", "target"]].sort_values("snapshot_id").to_dict("records")
            ),
        )
        for checkpoint_stage, artifact_name in (
            ("m1_fit", "m1.joblib"),
            ("m2_fit", "m2.joblib"),
            ("m3_contract", "m3.joblib"),
            ("m4_fit", "m4.joblib"),
        ):
            checkpoint_path = _write_stage_checkpoint(
                staging,
                stage=checkpoint_stage,
                mode=published_mode,
                cfg=cfg,
                input_hashes=bundle.file_hashes,
                outputs=[staging / artifact_name],
            )
            progress.checkpoint(
                checkpoint_path.relative_to(staging).as_posix(),
                rows_processed=len(model_frame),
            )
    active_features = list(m1.feature_columns)
    active_numeric = list(m1.numeric_columns)
    active_categorical = list(m1.categorical_columns)

    progress.stage(7, 10, "Run M1 distribution")
    formal_keys = cohorts.formal_core[["episode_id", "snapshot_id"]].drop_duplicates()
    formal = model_frame.merge(formal_keys, on=["episode_id", "snapshot_id"], how="inner", validate="one_to_one").reset_index(drop=True)
    formal = _set_model_attrs(formal, active_features, active_numeric, active_categorical)
    raw = pd.to_numeric(formal[FORMAL_TARGET_COLUMN], errors="coerce")
    alias = pd.to_numeric(formal["target"], errors="coerce")
    label_identity_mismatch_count = int((~(alias.eq(raw) | (alias.isna() & raw.isna()))).sum())
    if label_identity_mismatch_count:
        raise FormalRunBlocked("OVERALL_RUN_FORMAL_TARGET_IDENTITY_MISMATCH")
    m1.test_label_hash = stable_hash(
        formal[["snapshot_id", "target"]].sort_values("snapshot_id").to_dict("records")
    )
    model_contract_path = staging / "model_contract.json"
    model_contract = json.loads(model_contract_path.read_text(encoding="utf-8"))
    model_contract["test_label_hash"] = m1.test_label_hash
    model_contract["label_identity_mismatch_count"] = label_identity_mismatch_count
    write_json(model_contract_path, model_contract)
    pred = m1.predict_distribution(formal, int(mode_cfg["formal_samples"]), int(cfg.compute["random_seed"]))
    trigger = _trigger(pred, cfg.scientific)
    prediction_table = _prediction_table(formal, pred, m1.quantiles)
    prediction_table["trigger"] = trigger
    _write_df(prediction_table, staging / "metrics" / "m1_predictions_evaluation.parquet")
    if not tuning.empty:
        _write_df(tuning, staging / "metrics" / "m1_tuning.parquet")
    _write_df(feature_audit, staging / "metrics" / "m1_feature_audit.parquet")
    sample_count = pred["samples"].shape[1]
    sample_frame = pd.DataFrame({
        "episode_id": np.repeat(formal.episode_id.to_numpy(), sample_count),
        "flight_id": np.repeat(formal.flight_id.to_numpy(), sample_count),
        "snapshot_id": np.repeat(formal.snapshot_id.to_numpy(), sample_count),
        "sample_id": np.tile(pred["sample_ids"], len(formal)),
        "sample_value": pred["samples"].reshape(-1),
    })
    _write_df(sample_frame, staging / "m1_predictive_samples" / "part.parquet")
    checkpoint_path = _write_stage_checkpoint(
        staging, stage="m1_evaluation", mode=published_mode, cfg=cfg,
        input_hashes=bundle.file_hashes,
        outputs=[
            staging / "metrics" / "m1_predictions_evaluation.parquet",
            staging / "m1_predictive_samples" / "part.parquet",
        ],
    )
    progress.checkpoint(checkpoint_path.relative_to(staging).as_posix(), rows_processed=len(formal))

    progress.stage(8, 10, "Run M2 quantities, M3 responses, and M4 screening")
    m2_result = m2.reconstruct(formal, pred["samples"])
    m2_summary = _authoritative_m2_summary(formal, m2_result)
    _write_df(m2_summary, staging / "metrics" / "m2_summary.parquet")
    checkpoint_path = _write_stage_checkpoint(
        staging, stage="m2_evaluation", mode=published_mode, cfg=cfg,
        input_hashes=bundle.file_hashes,
        outputs=[staging / "metrics" / "m2_summary.parquet"],
    )
    progress.checkpoint(checkpoint_path.relative_to(staging).as_posix(), rows_processed=len(m2_summary))

    actions = load_actions(cfg.scientific)
    action_library = pd.DataFrame([asdict(action) for action in actions.values()])
    _write_df(action_library, staging / "action_metadata.parquet")
    _write_df(action_library, staging / "m3_action_library.parquet")  # legacy alias
    if m3.n_samples != pred["samples"].shape[1]:
        raise FormalRunBlocked(
            f"M3_SAMPLE_COUNT_MISMATCH:{m3.n_samples}!={pred['samples'].shape[1]}"
        )
    _write_df(m3.parameter_table, staging / "m3_response_parameters.parquet")
    _write_df(m3.response_samples_frame(), staging / "m3_response_samples.parquet")
    _write_df(m3.response_audit, staging / "m3_response_audit.parquet")

    rules = _subset_rules(tables["rules"], formal)
    _validate_action_library(rules, actions)
    physical_result = screen_physical_actions(
        rules,
        formal,
        actions,
        trigger,
        cfg.scientific["m3"]["resource_profiles"],
    )
    _write_df(physical_result.audit, staging / "metrics" / "m4_physical_screening.parquet")
    _write_df(physical_result.audit, staging / "metrics" / "m3_audit.parquet")  # legacy alias
    checkpoint_path = _write_stage_checkpoint(
        staging, stage="m3_evaluation", mode=published_mode, cfg=cfg,
        input_hashes=bundle.file_hashes,
        outputs=[
            staging / "m3_response_parameters.parquet",
            staging / "m3_response_samples.parquet",
            staging / "m3_response_audit.parquet",
            staging / "metrics" / "m4_physical_screening.parquet",
        ],
    )
    progress.checkpoint(checkpoint_path.relative_to(staging).as_posix(), rows_processed=len(physical_result.audit))

    m4_available = bool(getattr(m4, "available", True))
    m4_support = _passenger_support(formal).to_numpy(bool) & np.asarray(
        m2_result["passenger_proxy_used"], dtype=bool
    )
    action_scores, rankings, candidates = evaluate_m4(
        formal,
        m2_result["costs_rmb"],
        physical_result.audit,
        actions,
        m3,
        m4,
    )
    ranking_all_k, ranking_views = build_ranking_prefixes(
        formal[
            [
                "episode_id",
                "snapshot_id",
                "flight_id",
                "airport",
                "snapshot_stage",
            ]
        ].drop_duplicates(),
        rankings,
        action_library_version=str(
            cfg.scientific["m3"]["action_library_version"]
        ),
    )
    recommendations = ranking_views[1].copy()
    recommendations["recommended"] = ~recommendations["is_padding"].fillna(False).astype(bool)
    recommendations["recommendation_status"] = np.where(
        recommendations["recommended"],
        "AVAILABLE",
        "NO_REAL_CANDIDATE",
    )
    recommendations["deprecated_alias_of"] = "Ranking@1"
    _write_df(action_scores, staging / "m4_action_scores.parquet")
    _write_df(candidates, staging / "m4_candidate_screen.parquet")
    _write_df(rankings, staging / "m4_rankings.parquet")
    _write_df(ranking_all_k, staging / "m4_ranking_all_k.parquet")
    for depth, view in ranking_views.items():
        _write_df(view, staging / f"m4_ranking_k{depth}.parquet")
    _write_df(recommendations, staging / "m4_recommendations.parquet")
    _write_df(action_scores, staging / "metrics" / "m4_action_scores.parquet")
    _write_df(rankings, staging / "metrics" / "m4_rankings.parquet")
    parameter_manifest = _parameter_manifest(cfg, m1, m2, m3, m4)
    _write_df(parameter_manifest, staging / "parameter_manifest.parquet")
    write_json(staging / "parameter_manifest.json", parameter_manifest.to_dict("records"))
    checkpoint_path = _write_stage_checkpoint(
        staging, stage="m4_evaluation", mode=published_mode, cfg=cfg,
        input_hashes=bundle.file_hashes,
        outputs=[
            staging / "m4_action_scores.parquet",
            staging / "m4_candidate_screen.parquet",
            staging / "m4_rankings.parquet",
            staging / "m4_ranking_all_k.parquet",
            staging / "m4_ranking_k1.parquet",
            staging / "m4_ranking_k2.parquet",
            staging / "m4_ranking_k3.parquet",
            staging / "m4_ranking_k5.parquet",
            staging / "m4_recommendations.parquet",
        ],
    )
    progress.checkpoint(checkpoint_path.relative_to(staging).as_posix(), rows_processed=len(formal))

    return finalize_experiment(FinalizationInputs(
        cfg=cfg,
        mode=mode,
        published_mode=published_mode,
        target=target,
        staging=staging,
        run_identifier=rid,
        started_wall=started_wall,
        started_clock=started_clock,
        parallel_fields=parallel_fields,
        bundle=bundle,
        input_audit=input_audit,
        model_frame=model_frame,
        formal=formal,
        prediction=pred,
        m1=m1,
        m2=m2,
        m3=m3,
        m4=m4,
        m2_summary=m2_summary,
        m4_available=m4_available,
        m4_support=m4_support,
        label_identity_mismatch_count=label_identity_mismatch_count,
        progress=progress,
        override_fast_gate=override_fast_gate,
    ))
