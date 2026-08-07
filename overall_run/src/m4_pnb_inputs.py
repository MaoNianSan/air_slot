from __future__ import annotations

LEGACY_M4_NOT_FORMAL = True

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .m4_pnb_contract import (
    CHANNELS,
    FLOAT32_RECONSTRUCTION_ATOL_RMB,
    FLOAT32_RATIO_ATOL,
    NON_NULL_ACTIONS,
    FrozenInputs,
    _json,
    validate_sample_ids,
    verify_baseline,
)


def _infer_positive_multiplier(
    response: np.ndarray,
    target_raw_mean: np.ndarray,
) -> np.ndarray:
    """Recover the published row scalar without reading PRE anchors.

    M2 publishes the raw float32 row mean but not the passenger anchor scalar.
    Iterating against that exact mean recovers a scalar within the float32
    quantization interval. The resulting PNB indicator is checked exactly.
    """
    response_mean = response.astype(float).mean(axis=1)
    multiplier = np.divide(
        target_raw_mean,
        response_mean,
        out=np.zeros_like(target_raw_mean, dtype=float),
        where=response_mean > 0,
    )
    for _ in range(32):
        reconstructed_mean = (
            (multiplier[:, None] * response).astype(np.float32).astype(float).mean(axis=1)
        )
        multiplier += np.divide(
            target_raw_mean - reconstructed_mean,
            response_mean,
            out=np.zeros_like(multiplier),
            where=response_mean > 0,
        )
    return multiplier


def _reconstruct_m2_costs(
    run_dir: Path,
    summary: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[dict[str, np.ndarray], np.ndarray, dict[str, Any]]:
    samples_long = pd.read_parquet(run_dir / "m1_predictive_samples" / "part.parquet")
    counts = samples_long.groupby("snapshot_id", observed=True)["sample_id"].nunique()
    if counts.nunique() != 1:
        raise RuntimeError("PNB_M1_SAMPLE_COUNT_INCONSISTENT")
    n_samples = int(counts.iloc[0])
    sample_ids = validate_sample_ids(
        sorted(samples_long["sample_id"].unique()), n_samples
    )
    pivot = samples_long.pivot(
        index="snapshot_id", columns="sample_id", values="sample_value"
    ).reindex(summary["snapshot_id"].astype(str))
    if pivot.isna().any().any():
        raise RuntimeError("PNB_M1_SAMPLE_KEY_COVERAGE_FAILURE")
    samples = pivot.to_numpy(dtype=float)

    costs: dict[str, np.ndarray] = {}
    exposure_f = summary["exposure_F"].to_numpy(float)
    threshold_f = summary["threshold_F"].to_numpy(float)
    raw_f = (
        (1.0 + exposure_f[:, None])
        * np.maximum(samples - threshold_f[:, None], 0.0)
    ).astype(np.float32)
    unit_f = (
        raw_f.astype(float)
        / summary["common_unit_scale_F"].to_numpy(float)[:, None]
    ).astype(np.float32)
    costs["F"] = (
        unit_f * summary["unit_cost_rmb_F"].to_numpy(float)[:, None]
    ).astype(np.float32)

    passenger = config["m2"]["passenger"]
    p_excess = np.maximum(samples - float(passenger["threshold"]), 0.0)
    p_response = p_excess / (float(passenger["saturation"]) + p_excess)
    p_multiplier = _infer_positive_multiplier(
        p_response, summary["raw_quantity_mean_P"].to_numpy(float)
    )
    raw_p = (p_multiplier[:, None] * p_response).astype(np.float32)
    unit_p = (
        raw_p.astype(float)
        / summary["common_unit_scale_P"].to_numpy(float)[:, None]
    ).astype(np.float32)
    costs["P"] = (
        unit_p * summary["unit_cost_rmb_P"].to_numpy(float)[:, None]
    ).astype(np.float32)

    resource = config["m2"]["resource"]
    r_excess = np.maximum(samples - float(resource["threshold"]), 0.0)
    r_response = r_excess / (float(resource["saturation"]) + r_excess)
    r_shape = (0.25 + summary["exposure_R"].to_numpy(float)[:, None]) * r_response
    r_multiplier = _infer_positive_multiplier(
        r_shape, summary["raw_quantity_mean_R"].to_numpy(float)
    )
    raw_r = (r_multiplier[:, None] * r_shape).astype(np.float32)
    unit_r = (
        raw_r.astype(float)
        / summary["common_unit_scale_R"].to_numpy(float)[:, None]
    ).astype(np.float32)
    costs["R"] = (
        unit_r * summary["unit_cost_rmb_R"].to_numpy(float)[:, None]
    ).astype(np.float32)

    diagnostics: dict[str, Any] = {
        "method": "F_FROM_PUBLISHED_FORMULA;P_R_SCALAR_FROM_PUBLISHED_FLOAT32_RAW_MEAN",
        "dtype": "float32 formal arrays reconstructed through published float32 summaries",
        "rmb_atol": FLOAT32_RECONSTRUCTION_ATOL_RMB,
        "channel_mean_max_abs_error_rmb": {},
    }
    for channel in CHANNELS:
        actual_mean = costs[channel].astype(float).mean(axis=1)
        published = summary[f"cost_rmb_mean_{channel}"].to_numpy(float)
        diagnostics["channel_mean_max_abs_error_rmb"][channel] = float(
            np.max(np.abs(actual_mean - published))
        )
    total = np.zeros_like(costs["F"], dtype=np.float32)
    for channel in CHANNELS:
        total += costs[channel]
    diagnostics["total_mean_max_abs_error_rmb"] = float(
        np.max(
            np.abs(
                total.astype(float).mean(axis=1)
                - summary["total_pre_action_cost_rmb_mean"].to_numpy(float)
            )
        )
    )
    return costs, sample_ids, diagnostics


def _load_m3_arrays(
    run_dir: Path,
    sample_ids: np.ndarray,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, np.ndarray]]:
    frame = pd.read_parquet(run_dir / "m3_response_samples.parquet")
    recovery: dict[str, np.ndarray] = {}
    implementation: dict[str, np.ndarray] = {}
    success: dict[str, np.ndarray] = {}
    for action_id, group in frame.groupby("action_id", sort=True, observed=True):
        ordered = group.sort_values("sample_id", kind="mergesort")
        validate_sample_ids(ordered["sample_id"], len(sample_ids))
        recovery[str(action_id)] = ordered[
            [f"recovery_rate_{channel}" for channel in CHANNELS]
        ].to_numpy(float)
        implementation[str(action_id)] = ordered[
            [f"implementation_cost_rmb_{channel}" for channel in CHANNELS]
        ].to_numpy(float)
        success[str(action_id)] = ordered["implementation_success"].to_numpy(bool)
    expected = {"A00", *NON_NULL_ACTIONS}
    if set(recovery) != expected:
        raise RuntimeError("PNB_M3_ACTION_COVERAGE_FAILURE")
    return recovery, implementation, success


def load_frozen_inputs(run_dir: Path) -> FrozenInputs:
    verify_baseline(run_dir)
    config = _json(run_dir / "merged_config.json")
    summary = pd.read_parquet(run_dir / "metrics" / "m2_summary.parquet").copy()
    summary["snapshot_id"] = summary["snapshot_id"].astype(str)
    costs, sample_ids, reconstruction = _reconstruct_m2_costs(
        run_dir, summary, config
    )
    recovery, implementation, success = _load_m3_arrays(run_dir, sample_ids)
    return FrozenInputs(
        summary=summary,
        costs_rmb=costs,
        sample_ids=sample_ids,
        m3_recovery=recovery,
        m3_implementation=implementation,
        m3_success=success,
        m3_parameters=pd.read_parquet(run_dir / "m3_response_parameters.parquet"),
        candidates=pd.read_parquet(run_dir / "m4_candidate_screen.parquet"),
        rankings=pd.read_parquet(run_dir / "m4_rankings.parquet"),
        recommendations=pd.read_parquet(run_dir / "m4_recommendations.parquet"),
        actions=pd.read_parquet(run_dir / "action_metadata.parquet"),
        config=config,
        reconstruction_diagnostics=reconstruction,
    )


