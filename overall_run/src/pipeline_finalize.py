from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .artifacts import CORE_REQUIRED_ARTIFACT_IDS, write_artifact_registry
from .audit import build_scientific_gate
from .config import RunConfig, dump_config_snapshot
from .input import (
    FORMAL_TARGET_COLUMN,
    FORMAL_TARGET_CONTRACT_VERSION,
    SENSITIVITY_TARGET_COLUMN,
)
from .pipeline_data import passenger_support, role_mask, write_frame
from .progress import Progress
from .ranking_contract import RANKING_CONTRACT_VERSION, RANKING_DEPTHS
from .scientific_transition import transition_id
from .utils import stable_hash, write_json


@dataclass
class FinalizationInputs:
    cfg: RunConfig
    mode: str
    published_mode: str
    target: Path
    staging: Path
    run_identifier: str
    started_wall: pd.Timestamp
    started_clock: float
    parallel_fields: dict[str, Any]
    bundle: Any
    input_audit: dict[str, Any]
    model_frame: pd.DataFrame
    formal: pd.DataFrame
    prediction: dict[str, Any]
    m1: Any
    m2: Any
    m3: Any
    m4: Any
    m2_summary: pd.DataFrame
    m4_available: bool
    m4_support: np.ndarray
    label_identity_mismatch_count: int
    progress: Progress
    override_fast_gate: bool


def _pinball_loss(y: np.ndarray, q: np.ndarray, tau: float) -> np.ndarray:
    residual = np.asarray(y, dtype=float) - np.asarray(q, dtype=float)
    return np.maximum(tau * residual, (tau - 1.0) * residual)


def _quantile_crps(
    y: np.ndarray, qmat: np.ndarray, quantiles: np.ndarray
) -> np.ndarray:
    losses = np.column_stack(
        [_pinball_loss(y, qmat[:, i], float(tau)) for i, tau in enumerate(quantiles)]
    )
    return 2.0 * np.trapezoid(losses, quantiles, axis=1)


def finalize_experiment(inputs: FinalizationInputs) -> Path:
    """Compute acceptance metadata and atomically publish the completed run."""
    cfg = inputs.cfg
    staging = inputs.staging
    inputs.progress.stage(9, 10, "Compute scientific acceptance gates")
    quantiles = np.asarray(inputs.m1.quantiles, dtype=float)
    q05 = int(np.argmin(np.abs(quantiles - 0.05)))
    q95 = int(np.argmin(np.abs(quantiles - 0.95)))
    target_values = inputs.formal["target"].to_numpy(float)
    coverage90 = float(
        (
            (target_values >= inputs.prediction["quantiles"][:, q05])
            & (target_values <= inputs.prediction["quantiles"][:, q95])
        ).mean()
    )
    roles = cfg.scientific["cohort"]["roles"]
    train = inputs.model_frame[
        role_mask(inputs.model_frame["split"], roles["train"])
        & inputs.model_frame["target"].notna()
    ]
    train_q95 = float(train["target"].quantile(0.95))
    tail_mask = target_values > train_q95
    tail_coverage = (
        float(
            (
                (
                    target_values[tail_mask]
                    >= inputs.prediction["quantiles"][tail_mask, q05]
                )
                & (
                    target_values[tail_mask]
                    <= inputs.prediction["quantiles"][tail_mask, q95]
                )
            ).mean()
        )
        if tail_mask.any()
        else np.nan
    )
    crossing_rate = float(
        (np.diff(inputs.prediction["quantiles"], axis=1) < 0).any(axis=1).mean()
    )
    # ---- D6 formal distributional metrics (M1_V2_20260724 contract) ----
    # twcrps: weighted mean of row CRPS with weight 5 at/above validation q95.
    # q95/q99 pinball: mean pinball loss at tau=0.95/0.99.
    # upper_shortfall: mean max(y - Q(.99), 0).
    # upper_quantile_calibration: max(|q95 exceedance - .05|, |q99 exceedance - .01|).
    q99 = int(np.argmin(np.abs(quantiles - 0.99)))
    qmat = inputs.prediction["quantiles"]
    validation = inputs.model_frame[
        role_mask(inputs.model_frame["split"], roles["validation"])
        & inputs.model_frame["target"].notna()
    ]
    validation_q95 = (
        float(validation["target"].quantile(0.95))
        if len(validation)
        else float(train_q95)
    )
    crps_rows = _quantile_crps(target_values, qmat, quantiles)
    tail_weights = np.where(target_values >= validation_q95, 5.0, 1.0)
    twcrps = float(np.average(crps_rows, weights=tail_weights))
    q95_pinball = float(_pinball_loss(target_values, qmat[:, q95], 0.95).mean())
    q99_pinball = float(_pinball_loss(target_values, qmat[:, q99], 0.99).mean())
    upper_shortfall = float(np.maximum(target_values - qmat[:, q99], 0.0).mean())
    q95_exceedance = float((target_values > qmat[:, q95]).mean())
    q99_exceedance = float((target_values > qmat[:, q99]).mean())
    upper_quantile_calibration = float(
        max(abs(q95_exceedance - 0.05), abs(q99_exceedance - 0.01))
    )
    channel_means = {
        channel: float(
            pd.to_numeric(
                inputs.m2_summary[f"loss_mean_{channel}"], errors="coerce"
            ).mean()
        )
        for channel in ("F", "P", "R")
    }
    finite_means = {
        key: value
        for key, value in channel_means.items()
        if np.isfinite(value) and value >= 0
    }
    total_mean = sum(finite_means.values())
    dominance = (
        max(finite_means.values()) / total_mean
        if finite_means and total_mean > 0
        else np.nan
    )
    correlation = inputs.m2_summary[
        [f"loss_mean_{channel}" for channel in ("F", "P", "R")]
    ].corr()
    off_diagonal = [
        abs(float(correlation.iloc[row, column]))
        for row in range(len(correlation))
        for column in range(row + 1, len(correlation))
        if np.isfinite(correlation.iloc[row, column])
    ]
    maximum_correlation = max(off_diagonal) if off_diagonal else np.nan
    passenger_support_rate = float(passenger_support(inputs.formal).mean())
    write_frame(
        pd.DataFrame(
            [
                {
                    "metric": "coverage_90",
                    "value": coverage90,
                    "support": len(inputs.formal),
                },
                {
                    "metric": "tail_coverage_90",
                    "value": tail_coverage,
                    "support": int(tail_mask.sum()),
                },
                {
                    "metric": "quantile_crossing_rate",
                    "value": crossing_rate,
                    "support": len(inputs.formal),
                },
                {"metric": "twcrps", "value": twcrps, "support": len(inputs.formal)},
                {
                    "metric": "upper_quantile_calibration",
                    "value": upper_quantile_calibration,
                    "support": len(inputs.formal),
                },
                {
                    "metric": "q95_pinball",
                    "value": q95_pinball,
                    "support": len(inputs.formal),
                },
                {
                    "metric": "q99_pinball",
                    "value": q99_pinball,
                    "support": len(inputs.formal),
                },
                {
                    "metric": "upper_shortfall",
                    "value": upper_shortfall,
                    "support": len(inputs.formal),
                },
            ]
        ),
        staging / "metrics" / "m1_summary_evaluation.parquet",
    )
    write_frame(
        correlation.rename_axis("channel").reset_index(),
        staging / "metrics" / "m2_channel_correlation.parquet",
    )
    write_frame(
        pd.DataFrame(
            [
                {
                    "channel": channel,
                    "mean_loss": channel_means[channel],
                    "supported": bool(np.isfinite(channel_means[channel])),
                    "raw_share": (
                        channel_means[channel] / total_mean
                        if channel in finite_means and total_mean > 0
                        else np.nan
                    ),
                }
                for channel in ("F", "P", "R")
            ]
        ),
        staging / "metrics" / "m2_channel_summary.parquet",
    )
    gate_metrics = {
        "coverage_90": coverage90,
        "tail_coverage_90": tail_coverage,
        "quantile_crossing_rate": crossing_rate,
        "twcrps": twcrps,
        "upper_quantile_calibration": upper_quantile_calibration,
        "q95_pinball": q95_pinball,
        "q99_pinball": q99_pinball,
        "upper_shortfall": upper_shortfall,
        "pairwise_channel_corr": maximum_correlation,
        "channel_dominance_share": dominance,
        "passenger_proxy_support": passenger_support_rate,
        "artifact_contract": all(
            (staging / name).exists()
            for name in ("m1.joblib", "m2.joblib", "m3.joblib", "m4.joblib")
        ),
        "config_contract": True,
    }
    gates, scientific_status, blocking, warnings = build_scientific_gate(
        gate_metrics, cfg.acceptance
    )
    if not inputs.m4_available:
        blocking.append("M4_UNAVAILABLE_UNSUPPORTED_PASSENGER_INPUT")
        scientific_status = "STOP_AND_REVIEW"
    full_recommended = bool(scientific_status == "PASS" and not blocking)
    engineering_status = "PASS"
    downstream_ready = bool(
        inputs.mode in {"acceptance_23d", "middle", "full"}
        and scientific_status == "PASS"
        and engineering_status == "PASS"
    )
    write_json(staging / "scientific_gate.json", gates)
    write_frame(
        pd.DataFrame([{"gate_name": name, **value} for name, value in gates.items()]),
        staging / "audit.parquet",
    )
    failures = pd.DataFrame(
        (
            []
            if inputs.m4_available
            else [
                {
                    "stage": "M2_M4_CONTRACT",
                    "failure_code": "UNSUPPORTED_PASSENGER_PROXY_INPUT",
                    "severity": "SCIENTIFIC_BLOCKER",
                    "message": "Passenger proxy is missing; no passenger-cost fallback or M4 evaluation was used.",
                }
            ]
        ),
        columns=["stage", "failure_code", "severity", "message"],
    )
    write_frame(failures, staging / "failure_records.parquet")
    dump_config_snapshot(cfg, staging)
    write_json(staging / "input_audit.json", inputs.input_audit)

    completed = pd.Timestamp.now(tz="UTC")
    pre_summary = json.loads(
        (inputs.bundle.pre_output / "run_summary.json").read_text(encoding="utf-8")
    )
    scientific_transition_id = transition_id(cfg.root)
    manifest = {
        "run_id": inputs.run_identifier,
        "mode": inputs.published_mode,
        "compute_mode": inputs.mode,
        "started_at": inputs.started_wall,
        "completed_at": completed,
        "config_hash": cfg.config_hash,
        "implementation_hash": cfg.implementation_hash,
        "scientific_transition_id": scientific_transition_id,
        "run_purpose": cfg.scientific.get("run_purpose"),
        **cfg.profile_contract,
        "contract_version": cfg.contract_version,
        "config_sources": cfg.config_sources,
        "pre_file_hashes": inputs.bundle.file_hashes,
        "pre_run_id": pre_summary.get("run_id"),
        "fast_gate_overridden": bool(inputs.override_fast_gate),
        "interface_smoke_gate_exempt": bool(
            cfg.profile_contract.get("smoke_subset", False)
        ),
        "authoritative_chain": [
            "src.config",
            "src.pipeline",
            "src.m1",
            "src.m2",
            "src.m3",
            "src.m4",
            "src.audit",
            "src.artifacts",
        ],
        "formal_target_column": FORMAL_TARGET_COLUMN,
        "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
        "formal_target_definition_hash": inputs.m1.formal_target_definition_hash,
    }
    write_json(staging / "run_manifest.json", manifest)
    summary = {
        "run_id": inputs.run_identifier,
        "mode": inputs.published_mode,
        "compute_mode": inputs.mode,
        "started_at": inputs.started_wall,
        "completed_at": completed,
        "elapsed_seconds": float(time.monotonic() - inputs.started_clock),
        "engineering_status": engineering_status,
        "scientific_status": scientific_status,
        "full_recommended": full_recommended,
        "downstream_ready": downstream_ready,
        "blocking_reasons": sorted(set(blocking)),
        "warning_reasons": sorted(set(warnings)),
        "config_hash": cfg.config_hash,
        "implementation_hash": cfg.implementation_hash,
        "scientific_transition_id": scientific_transition_id,
        "run_purpose": cfg.scientific.get("run_purpose"),
        **cfg.profile_contract,
        "interface_smoke_gate_exempt": bool(
            cfg.profile_contract.get("smoke_subset", False)
        ),
        "contract_version": cfg.contract_version,
        "passenger_proxy_support_rate": passenger_support_rate,
        "m2_unit_scales": dict(inputs.m2.unit_scales),
        "m2_unit_scale_support": dict(inputs.m2.unit_scale_support),
        "m2_unit_costs_rmb": dict(inputs.m2.unit_costs_rmb),
        "m3_parameter_hash": inputs.m3.parameter_hash,
        "m3_sample_hash": inputs.m3.sample_hash,
        "m3_sample_count": inputs.m3.n_samples,
        "m3_action_library_version": cfg.scientific["m3"]["action_library_version"],
        "m3_formal_action_count": len(cfg.scientific["m3"]["actions"]),
        "m3_parameter_status": "PROVISIONAL",
        "ranking_depths": list(RANKING_DEPTHS),
        "ranking_contract_version": RANKING_CONTRACT_VERSION,
        "m4_available": inputs.m4_available,
        "m4_common_support_rows": int(inputs.m4_support.sum()),
        "m4_common_support_rate": float(inputs.m4_support.mean()),
        "formal_target_column": FORMAL_TARGET_COLUMN,
        "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
        "formal_target_definition_hash": inputs.m1.formal_target_definition_hash,
        "sensitivity_target_column": SENSITIVITY_TARGET_COLUMN,
        "training_target_column": FORMAL_TARGET_COLUMN,
        "calibration_target_column": FORMAL_TARGET_COLUMN,
        "evaluation_target_column": FORMAL_TARGET_COLUMN,
        "label_identity_mismatch_count": inputs.label_identity_mismatch_count,
        "observed_outcome_source": FORMAL_TARGET_COLUMN,
        "training_label_hash": inputs.m1.training_label_hash,
        "validation_label_hash": inputs.m1.validation_label_hash,
        "test_label_hash": inputs.m1.test_label_hash,
        "model_parameter_hash": inputs.m1.model_parameter_hash,
        "feature_schema_hash": inputs.m1.feature_schema_hash,
        "m1_feature_contract_version": inputs.m1.feature_contract_version,
        "scientific_parameter_approval_status": "PENDING",
        "publication_allowed": bool(cfg.scientific.get("publication_allowed", False)),
        "formal_baseline_replaced": bool(
            cfg.scientific.get("formal_baseline_replaced", False)
        ),
        "quantile_grid_hash": stable_hash(inputs.m1.quantiles),
        "worker_count": max(1, int(cfg.compute.get("outer_workers", 1))),
        "lightgbm_n_jobs": max(1, int(cfg.compute.get("inner_model_threads", 1))),
        **inputs.parallel_fields,
        "heartbeat_interval_seconds": 300,
    }
    write_json(staging / "run_summary.json", summary)
    write_json(
        staging / "run_state.json",
        {
            "run_id": inputs.run_identifier,
            "mode": inputs.published_mode,
            "compute_mode": inputs.mode,
            "status": "RUNNING",
            "current_stage": "publish",
            "process_id": os.getpid(),
            "started_at": inputs.started_wall,
            "completed_at": completed,
            "config_hash": cfg.config_hash,
            "implementation_hash": cfg.implementation_hash,
            "input_hashes": inputs.bundle.file_hashes,
            "checkpoint_paths": sorted(
                path.relative_to(staging).as_posix()
                for path in (staging / "checkpoints").glob("*.json")
            ),
            **inputs.parallel_fields,
        },
    )

    inputs.progress.stage(10, 10, "Publish unified mode directory")
    inputs.target.parent.mkdir(parents=True, exist_ok=True)
    staging.replace(inputs.target)
    write_artifact_registry(
        inputs.target,
        mode=inputs.published_mode,
        run_id=inputs.run_identifier,
        config_hash=cfg.config_hash,
        implementation_hash=cfg.implementation_hash,
        contract_version=cfg.contract_version,
        upstream_artifact_hashes=inputs.bundle.file_hashes,
        scientific_status=scientific_status,
        artifact_names=list(CORE_REQUIRED_ARTIFACT_IDS),
        registry_kind="core",
        required_artifact_ids=CORE_REQUIRED_ARTIFACT_IDS,
        metadata={
            "formal_target_column": FORMAL_TARGET_COLUMN,
            "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
            "formal_target_definition_hash": inputs.m1.formal_target_definition_hash,
            "sensitivity_target_column": SENSITIVITY_TARGET_COLUMN,
            "training_label_hash": inputs.m1.training_label_hash,
            "validation_label_hash": inputs.m1.validation_label_hash,
            "test_label_hash": inputs.m1.test_label_hash,
            "model_parameter_hash": inputs.m1.model_parameter_hash,
            "feature_schema_hash": inputs.m1.feature_schema_hash,
            "m1_feature_contract_version": inputs.m1.feature_contract_version,
            "quantile_grid_hash": stable_hash(inputs.m1.quantiles),
            "m2_unit_scales": dict(inputs.m2.unit_scales),
            "m3_parameter_hash": inputs.m3.parameter_hash,
            "m3_sample_hash": inputs.m3.sample_hash,
            "m3_action_library_version": cfg.scientific["m3"]["action_library_version"],
            "m3_formal_action_count": len(cfg.scientific["m3"]["actions"]),
            "ranking_depths": list(RANKING_DEPTHS),
            "ranking_contract_version": RANKING_CONTRACT_VERSION,
            "scientific_parameter_approval_status": "PENDING",
            "publication_allowed": False,
            "formal_baseline_replaced": False,
            "label_identity_mismatch_count": inputs.label_identity_mismatch_count,
            "observed_outcome_source": FORMAL_TARGET_COLUMN,
            "scientific_transition_id": scientific_transition_id,
        },
    )
    write_json(
        inputs.target / "run_state.json",
        {
            "run_id": inputs.run_identifier,
            "mode": inputs.published_mode,
            "compute_mode": inputs.mode,
            "status": "COMPLETE",
            "process_id": os.getpid(),
            "started_at": inputs.started_wall,
            "completed_at": completed,
            "config_hash": cfg.config_hash,
            "implementation_hash": cfg.implementation_hash,
            "input_hashes": inputs.bundle.file_hashes,
            "checkpoint_paths": sorted(
                path.relative_to(inputs.target).as_posix()
                for path in (inputs.target / "checkpoints").glob("*.json")
            ),
            **inputs.parallel_fields,
        },
    )
    inputs.progress.summary(
        f"{engineering_status}/{scientific_status}: {inputs.target}"
    )
    inputs.progress.stop_heartbeat()
    return inputs.target
