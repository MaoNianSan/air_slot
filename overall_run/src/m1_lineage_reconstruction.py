from __future__ import annotations

import sys
from typing import Any

import numpy as np
import pandas as pd

from .m1_lineage_contract import (
    AuditStop,
    FAST_ROOT,
    FORMAL_TARGET,
    MODULE_ROOT,
    PART_ROOT,
    PRE_ROOT,
    PROJECT_ROOT,
    QUANTILES,
    _json,
    cohort_hash,
    pinball_loss,
    quantile_crps,
)


def _q_column(tau: float, *, raw: bool = False, part: bool = False) -> str:
    if part:
        return f"q_{tau:g}"
    prefix = "raw_q" if raw else "q"
    return f"{prefix}_{str(float(tau)).replace('.', '_')}"


def _limited_result(estimate: float, event_clusters: int, *, comparative: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "estimate": float(estimate),
        "event_clusters": int(event_clusters),
        "bootstrap_primary_cluster": "trigger_event_group_id",
        "ci_lower": None,
        "ci_upper": None,
        "support": "METRIC_SUPPORT_LIMITED",
    }
    if comparative:
        result.update(status="METRIC_SUPPORT_LIMITED", delta="PROP_MINUS_HIST")
    else:
        result.update(alpha=0.05, certification="METRIC_SUPPORT_LIMITED")
    return result


def _build_q95_audit(
    values: dict[str, float | int],
    evaluation: pd.DataFrame,
    validation_q95: float,
) -> dict[str, Any]:
    event_clusters = int(evaluation["trigger_event_group_id"].nunique())
    return {
        "audit_scope": "CORRECTED_Q95_FAST_SUPPORT_AUDIT",
        "lineage_gate": "PASS",
        "formal_target_column": FORMAL_TARGET,
        "metric_definition": {
            "crps": "twice trapezoidal integral of quantile pinball loss",
            "twcrps": "same row CRPS with weight 5 for rows at/above validation raw-label q95 and 1 otherwise",
            "upper_shortfall": "max(y - projected q0.99, 0); STRESS_DIAGNOSTIC",
            "bootstrap": "paired recovery-event cluster bootstrap; snapshots are never independent clusters",
        },
        "support": {
            "rows": int(len(evaluation)),
            "flights": int(evaluation["flight_id"].nunique()),
            "events": event_clusters,
            "days": int(evaluation["anchor_date"].nunique()),
            "airports": int(evaluation["airport_id"].nunique()),
            "stages": int(
                evaluation[
                    "snapshot_stage_x" if "snapshot_stage_x" in evaluation else "snapshot_stage"
                ].nunique()
            ),
        },
        "metrics": {
            "rows": int(len(evaluation)),
            "q95_empirical_exceedance": float(values["q95_exceedance"]),
            "q99_empirical_exceedance": float(values["q99_exceedance"]),
            "coverage90": float(values["coverage90"]),
            "q95_pinball": float(values["q95_pinball"]),
            "q99_pinball": float(values["q99_pinball"]),
            "crps": float(values["crps"]),
            "twcrps": float(values["twcrps"]),
            "upper_shortfall": float(values["upper_shortfall"]),
        },
        "q95_calibration": _limited_result(values["q95_exceedance"], event_clusters),
        "q99_calibration": _limited_result(values["q99_exceedance"], event_clusters),
        "comparative": {
            "twcrps": _limited_result(values["twcrps_prop_minus_hist"], event_clusters, comparative=True),
            "q95_pinball": _limited_result(values["q95_pinball_prop_minus_hist"], event_clusters, comparative=True),
            "q99_pinball": _limited_result(values["q99_pinball_prop_minus_hist"], event_clusters, comparative=True),
        },
        "crossing": {
            "raw_crossing_rows": int(values["raw_crossing_rows"]),
            "projected_crossing_rows": int(values["projected_crossing_rows"]),
            "projected_crossing_gate": "PASS" if int(values["projected_crossing_rows"]) == 0 else "FAIL",
        },
        "tail_stress_diagnostic": {
            "role": "STRESS_DIAGNOSTIC",
            "validation_q95_threshold": float(validation_q95),
            "upper_shortfall": float(values["upper_shortfall"]),
        },
        "absolute_test_derived_thresholds_used": False,
    }


def _reconstruct_formal_cohort(snapshots: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    if str(MODULE_ROOT) not in sys.path:
        sys.path.insert(0, str(MODULE_ROOT))
    from src.cohort import build_cohorts

    frame = snapshots.copy()
    frame["decision_time"] = pd.to_datetime(frame["decision_time_utc"], utc=True)
    frame["split"] = frame["split"].astype(str).str.lower()
    frame["airport"] = frame["airport"].astype(str).str.upper()
    cohorts = build_cohorts(
        frame,
        config,
        config["modes"]["fast"],
        int(config["random_seed"]),
    )
    return cohorts.formal_core.sort_values("snapshot_id", kind="mergesort").reset_index(drop=True)


def reconstruct_current_metrics() -> dict[str, Any]:
    prediction_path = FAST_ROOT / "metrics" / "m1_predictions_evaluation.parquet"
    predictions = pd.read_parquet(prediction_path).sort_values("snapshot_id", kind="mergesort").reset_index(drop=True)
    config = _json(FAST_ROOT / "merged_config.json")
    qcols = [_q_column(tau) for tau in QUANTILES]
    raw_qcols = [_q_column(tau, raw=True) for tau in QUANTILES]
    required = ["snapshot_id", "episode_id", "flight_id", "target", "trigger", *qcols, *raw_qcols]
    missing = sorted(set(required).difference(predictions.columns))
    if missing:
        raise AuditStop("CURRENT_PREDICTION_COLUMNS_MISSING:" + ",".join(missing))

    snapshot_columns = [
        "episode_id", "snapshot_id", "flight_id", "split", "snapshot_valid",
        "snapshot_stage", "airport", "airport_id", "anchor_date", "decision_time_utc",
        "balanced_primary_cohort", "trajectory_coverage", "trigger_event_group_id",
        "m4_passenger_input_supported",
    ]
    snapshots = pd.read_parquet(PRE_ROOT / "snapshots.parquet", columns=snapshot_columns)
    episodes = pd.read_parquet(
        PRE_ROOT / "episodes.parquet",
        columns=["episode_id", "flight_id", "y_movement_raw", "split", "anchor_date"],
    )
    formal_reconstructed = _reconstruct_formal_cohort(snapshots, config)
    artifact_key_hash = cohort_hash(predictions["snapshot_id"])
    reconstructed_key_hash = cohort_hash(formal_reconstructed["snapshot_id"])
    existing_key_hash = _json(
        PROJECT_ROOT / "overall_adv" / "output" / "fast" / "common_support_cohort.json"
    )["common_support_cohort_hash"]
    if set(predictions["snapshot_id"]) != set(formal_reconstructed["snapshot_id"]):
        raise AuditStop("CURRENT_FORMAL_COHORT_KEY_MISMATCH")
    if artifact_key_hash != reconstructed_key_hash or artifact_key_hash != existing_key_hash:
        raise AuditStop("CURRENT_FORMAL_COHORT_HASH_MISMATCH")

    metadata = snapshots[
        [
            "snapshot_id", "trigger_event_group_id", "anchor_date", "airport_id",
            "snapshot_stage", "m4_passenger_input_supported",
        ]
    ].drop_duplicates("snapshot_id")
    evaluation = predictions.merge(metadata, on="snapshot_id", how="left", validate="one_to_one")
    if evaluation["trigger_event_group_id"].isna().any():
        raise AuditStop("CURRENT_EVENT_LINEAGE_MISSING")

    target = predictions["target"].to_numpy(float)
    qmat = predictions[qcols].to_numpy(float)
    raw_qmat = predictions[raw_qcols].to_numpy(float)
    crps = quantile_crps(target, qmat)
    indices = {float(tau): int(np.flatnonzero(np.isclose(QUANTILES, tau))[0]) for tau in QUANTILES}

    part = pd.read_parquet(PART_ROOT / "m1" / "m1_predictions.parquet")
    prop = part.loc[part["model_id"].eq("PROP")].sort_values("snapshot_id", kind="mergesort").reset_index(drop=True)
    hist = part.loc[part["model_id"].eq("HIST")].sort_values("snapshot_id", kind="mergesort").reset_index(drop=True)
    if list(prop["snapshot_id"].astype(str)) != list(predictions["snapshot_id"].astype(str)):
        raise AuditStop("CURRENT_PROP_COHORT_MISMATCH")
    part_qcols = [_q_column(tau, part=True) for tau in QUANTILES]
    part_qmat = prop[part_qcols].to_numpy(float)
    hist_qmat = hist[part_qcols].to_numpy(float)
    prediction_layer_max_abs_delta = float(np.max(np.abs(qmat - part_qmat)))
    target_layer_max_abs_delta = float(
        np.max(np.abs(target - prop["observed_outcome"].to_numpy(float)))
    )
    if prediction_layer_max_abs_delta != 0.0 or target_layer_max_abs_delta != 0.0:
        raise AuditStop("CURRENT_PROP_PREDICTION_LAYER_MISMATCH")

    adapter = pd.read_parquet(
        PART_ROOT / "input_adapter" / "m1_model_frame.parquet",
        columns=["split", "observed_outcome"],
    )
    validation_y = pd.to_numeric(
        adapter.loc[adapter["split"].eq("validation"), "observed_outcome"], errors="coerce"
    ).dropna()
    validation_q95 = float(validation_y.quantile(0.95))

    model_frame_targets = snapshots[["episode_id", "split"]].merge(
        episodes[["episode_id", "y_movement_raw"]], on="episode_id", validate="many_to_one"
    )
    train_y = pd.to_numeric(
        model_frame_targets.loc[
            model_frame_targets["split"].astype(str).str.lower().isin({"train", "model"}),
            "y_movement_raw",
        ],
        errors="coerce",
    ).dropna()
    train_q95 = float(train_y.quantile(0.95))

    i01, i05, i50, i95, i99 = (indices[level] for level in (0.01, 0.05, 0.50, 0.95, 0.99))
    coverage = (target >= qmat[:, i05]) & (target <= qmat[:, i95])
    tail_mask = target > train_q95
    q95_exceed = target > qmat[:, i95]
    q99_exceed = target > qmat[:, i99]
    hist_crps = quantile_crps(target, hist_qmat)
    tail_weights = np.where(target >= validation_q95, 5.0, 1.0)
    brier15 = (predictions["p_exceed_15"].to_numpy(float) - (target > 15.0)) ** 2

    values = {
        "crps": float(crps.mean()),
        "twcrps": float(np.average(crps, weights=tail_weights)),
        "q01_pinball": float(pinball_loss(target, qmat[:, i01], 0.01).mean()),
        "q05_pinball": float(pinball_loss(target, qmat[:, i05], 0.05).mean()),
        "q50_pinball": float(pinball_loss(target, qmat[:, i50], 0.50).mean()),
        "q95_pinball": float(pinball_loss(target, qmat[:, i95], 0.95).mean()),
        "q99_pinball": float(pinball_loss(target, qmat[:, i99], 0.99).mean()),
        "coverage90": float(coverage.mean()),
        "q95_exceedance": float(q95_exceed.mean()),
        "q99_exceedance": float(q99_exceed.mean()),
        "q95_empirical_cdf": float((target <= qmat[:, i95]).mean()),
        "q99_empirical_cdf": float((target <= qmat[:, i99]).mean()),
        "q95_calibration_signed": float((target <= qmat[:, i95]).mean() - 0.95),
        "q99_calibration_signed": float((target <= qmat[:, i99]).mean() - 0.99),
        "q95_calibration_absolute": float(abs((target <= qmat[:, i95]).mean() - 0.95)),
        "q99_calibration_absolute": float(abs((target <= qmat[:, i99]).mean() - 0.99)),
        "tail_coverage90": float(coverage[tail_mask].mean()),
        "upper_shortfall": float(np.maximum(target - qmat[:, i99], 0.0).mean()),
        "raw_crossing_rows": int(np.any(np.diff(raw_qmat, axis=1) < 0.0, axis=1).sum()),
        "raw_crossing_rate": float(np.any(np.diff(raw_qmat, axis=1) < 0.0, axis=1).mean()),
        "projected_crossing_rows": int(np.any(np.diff(qmat, axis=1) < 0.0, axis=1).sum()),
        "projected_crossing_rate": float(np.any(np.diff(qmat, axis=1) < 0.0, axis=1).mean()),
        "brier15": float(brier15.mean()),
        "trigger_rate": float(predictions["trigger"].mean()),
        "twcrps_prop_minus_hist": float(np.average(crps - hist_crps, weights=tail_weights)),
        "q95_pinball_prop_minus_hist": float(
            (
                pinball_loss(target, qmat[:, i95], 0.95)
                - pinball_loss(target, hist_qmat[:, i95], 0.95)
            ).mean()
        ),
        "q99_pinball_prop_minus_hist": float(
            (
                pinball_loss(target, qmat[:, i99], 0.99)
                - pinball_loss(target, hist_qmat[:, i99], 0.99)
            ).mean()
        ),
    }

    samples = pd.read_parquet(FAST_ROOT / "m1_predictive_samples" / "part.parquet")
    samples = samples.sort_values(["snapshot_id", "sample_id"], kind="mergesort").reset_index(drop=True)
    if str(MODULE_ROOT) not in sys.path:
        sys.path.insert(0, str(MODULE_ROOT))
    from src.utils import stable_seed

    expected_samples = np.empty((len(predictions), 256), dtype=np.float32)
    for row_index, row in enumerate(predictions[["flight_id", "snapshot_id"]].itertuples(index=False)):
        rng = np.random.default_rng(stable_seed(int(config["random_seed"]), row.flight_id, row.snapshot_id, "m1_samples"))
        uniforms = rng.uniform(0.0, 1.0, size=256)
        expected_samples[row_index] = np.interp(
            uniforms,
            QUANTILES,
            qmat[row_index],
            left=float(qmat[row_index, 0]),
            right=float(qmat[row_index, -1]),
        ).astype(np.float32)
    expected_sample_frame = pd.DataFrame(
        {
            "snapshot_id": np.repeat(predictions["snapshot_id"].to_numpy(), 256),
            "sample_id": np.tile(np.arange(256, dtype=np.int32), len(predictions)),
            "expected": expected_samples.reshape(-1),
        }
    ).sort_values(["snapshot_id", "sample_id"], kind="mergesort").reset_index(drop=True)
    sample_key_match = bool(
        samples[["snapshot_id", "sample_id"]].equals(
            expected_sample_frame[["snapshot_id", "sample_id"]]
        )
    )
    sample_max_abs_delta = float(
        np.max(np.abs(samples["sample_value"].to_numpy(float) - expected_sample_frame["expected"].to_numpy(float)))
    )
    if not sample_key_match or sample_max_abs_delta != 0.0:
        raise AuditStop("CURRENT_PREDICTIVE_SAMPLE_LAYER_MISMATCH")

    summary_table = pd.read_parquet(FAST_ROOT / "metrics" / "m1_summary_evaluation.parquet")
    summary_values = summary_table.set_index("metric")["value"].to_dict()
    summary_support = summary_table.set_index("metric")["support"].to_dict()
    q95_audit = _build_q95_audit(values, evaluation, validation_q95)
    reported_values: dict[str, float] = {
        "crps": float(q95_audit["metrics"]["crps"]),
        "twcrps": float(q95_audit["metrics"]["twcrps"]),
        "q95_pinball": float(q95_audit["metrics"]["q95_pinball"]),
        "q99_pinball": float(q95_audit["metrics"]["q99_pinball"]),
        "coverage90": float(summary_values["coverage_90"]),
        "q95_exceedance": float(q95_audit["metrics"]["q95_empirical_exceedance"]),
        "q99_exceedance": float(q95_audit["metrics"]["q99_empirical_exceedance"]),
        "tail_coverage90": float(summary_values["tail_coverage_90"]),
        "upper_shortfall": float(q95_audit["metrics"]["upper_shortfall"]),
        "raw_crossing_rows": int(q95_audit["crossing"]["raw_crossing_rows"]),
        "projected_crossing_rows": int(q95_audit["crossing"]["projected_crossing_rows"]),
        "projected_crossing_rate": float(summary_values["quantile_crossing_rate"]),
        "twcrps_prop_minus_hist": float(q95_audit["comparative"]["twcrps"]["estimate"]),
        "q95_pinball_prop_minus_hist": float(q95_audit["comparative"]["q95_pinball"]["estimate"]),
        "q99_pinball_prop_minus_hist": float(q95_audit["comparative"]["q99_pinball"]["estimate"]),
    }
    reported_support = {
        key: int(q95_audit["metrics"]["rows"])
        for key in reported_values
    }
    reported_support["coverage90"] = int(summary_support["coverage_90"])
    reported_support["tail_coverage90"] = int(summary_support["tail_coverage_90"])
    reported_support["projected_crossing_rate"] = int(summary_support["quantile_crossing_rate"])
    reported_support["raw_crossing_rows"] = len(predictions)
    reported_support["projected_crossing_rows"] = len(predictions)

    artifact_tail_hash = cohort_hash(predictions.loc[tail_mask, "snapshot_id"])
    reconstructed_tail_mask = predictions["target"].to_numpy(float) > train_q95
    reconstructed_tail_hash = cohort_hash(predictions.loc[reconstructed_tail_mask, "snapshot_id"])
    if artifact_tail_hash != reconstructed_tail_hash:
        raise AuditStop("CURRENT_TAIL_COHORT_HASH_MISMATCH")

    return {
        "run_id": _json(FAST_ROOT / "artifact_registry.json")["run_id"],
        "config": config,
        "predictions": predictions,
        "evaluation": evaluation,
        "snapshots": snapshots,
        "episodes": episodes,
        "formal_reconstructed": formal_reconstructed,
        "qmat": qmat,
        "raw_qmat": raw_qmat,
        "target": target,
        "coverage": coverage,
        "tail_mask": tail_mask,
        "q95_exceed": q95_exceed,
        "q99_exceed": q99_exceed,
        "tail_weights": tail_weights,
        "crps_rows": crps,
        "hist_crps_rows": hist_crps,
        "values": values,
        "reported_values": reported_values,
        "reported_support": reported_support,
        "q95_audit": q95_audit,
        "formal_cohort_hash": artifact_key_hash,
        "reconstructed_formal_cohort_hash": reconstructed_key_hash,
        "tail_cohort_hash": artifact_tail_hash,
        "reconstructed_tail_cohort_hash": reconstructed_tail_hash,
        "train_q95": train_q95,
        "validation_q95": validation_q95,
        "base_rows": int(
            (
                snapshots["snapshot_valid"].fillna(False).astype(bool)
                & snapshots["split"].astype(str).str.lower().isin({"test", "final_test"})
                & snapshots["snapshot_stage"].isin({"t1", "t2", "t3"})
            ).sum()
        ),
        "prediction_layer_max_abs_delta": prediction_layer_max_abs_delta,
        "target_layer_max_abs_delta": target_layer_max_abs_delta,
        "predictive_sample_max_abs_delta": sample_max_abs_delta,
        "predictive_sample_key_match": sample_key_match,
    }


