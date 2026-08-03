from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from scipy.stats import norm
from sklearn.isotonic import IsotonicRegression

from .shared_contracts import strict_deep_merge

from .pipeline_common import (
    FORMAL_TARGET_COLUMN,
    PROJECT,
    ROOT,
    SENSITIVITY_TARGET_COLUMN,
    load_common_passenger_cohort,
    stable_hash,
)


def _load(mode: str, override: Path | None = None) -> dict[str, Any]:
    cfg = yaml.safe_load((ROOT / "config" / "v3.yaml").read_text(encoding="utf-8"))
    if override:
        path = override if override.is_absolute() else ROOT / override
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cfg = strict_deep_merge(cfg, payload)
    output_name = str(cfg.get("output_name") or mode)
    pre_output_name = str(cfg.get("pre_output_name") or output_name)
    cfg["mode"] = output_name
    cfg["pre_mode"] = pre_output_name
    profile_id = "middle" if mode == "middle_smoke" else mode
    cfg["compute_mode"] = "full" if profile_id in {"acceptance_23d", "middle", "full"} else profile_id
    cfg["profile_id"] = profile_id
    cfg["run_profile"] = None if profile_id == "acceptance_23d" else profile_id
    cfg["acceptance_profile"] = "acceptance_23d" if profile_id == "acceptance_23d" else None
    cfg["smoke_subset"] = mode == "middle_smoke"
    cfg["upstream"] = PROJECT / "overall_run" / "output" / output_name
    cfg["pre"] = PROJECT / "pre" / "output" / pre_output_name
    cfg["output"] = ROOT / "output" / output_name
    cfg["samples"] = int(cfg[f"predictive_samples_{cfg['compute_mode']}"])
    cfg["bootstrap"] = int(cfg[f"bootstrap_{cfg['compute_mode']}"])
    cfg["config_hash"] = stable_hash(
        {key: value for key, value in cfg.items() if key not in {"upstream", "pre", "output", "config_hash"}}
    )
    return cfg


def _upstream(cfg: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    cohort, audit = load_common_passenger_cohort(
        PROJECT,
        cfg["mode"],
        pre_mode=cfg["pre_mode"],
    )
    required = [
        "metrics/m1_predictions_evaluation.parquet",
        "metrics/m2_summary.parquet",
        "m1_predictive_samples/part.parquet",
        "m4_action_scores.parquet",
        "m4_recommendations.parquet",
        "artifact_registry.json",
        "run_summary.json",
    ]
    missing = [name for name in required if not (cfg["upstream"] / name).exists()]
    if missing:
        raise FileNotFoundError("UNIFIED_UPSTREAM_ARTIFACT_MISSING:" + ",".join(missing))
    return cohort, audit


def _matrix(
    frame: pd.DataFrame, features: list[str], medians: pd.Series | None = None
) -> tuple[np.ndarray, pd.Series]:
    numeric = frame[features].apply(pd.to_numeric, errors="coerce")
    median = numeric.median().fillna(0) if medians is None else medians
    return numeric.fillna(median).to_numpy(float), median


def _crps(samples: np.ndarray, outcome: np.ndarray) -> np.ndarray:
    first = np.mean(np.abs(samples - outcome[:, None]), axis=1)
    ordered = np.sort(samples, axis=1)
    count = ordered.shape[1]
    weights = 2 * np.arange(1, count + 1) - count - 1
    second = np.sum(ordered * weights, axis=1) / (count * count)
    return first - second


def _weighted_quantile(values: np.ndarray, quantiles: np.ndarray, weights: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    x = np.asarray(values, float)[order]
    w = np.asarray(weights, float)[order]
    if len(x) == 0 or not np.isfinite(w).all() or w.sum() <= 0:
        raise ValueError("INVALID_WEIGHTED_QUANTILE_INPUT")
    cumulative = (np.cumsum(w) - 0.5 * w) / w.sum()
    return np.interp(quantiles, cumulative, x, left=x[0], right=x[-1])


def _formal_quantiles(scientific: dict[str, Any], prediction_columns: Any) -> tuple[np.ndarray, list[str]]:
    quantiles = np.asarray(scientific["m1"]["quantiles"], float)
    quantile_columns = [f"q_{str(q).replace('.', '_')}" for q in quantiles]
    available = set(prediction_columns)
    missing = [column for column in quantile_columns if column not in available]
    if missing:
        raise ValueError("FORMAL_QUANTILE_GRID_MISMATCH:" + ",".join(missing))
    return quantiles, quantile_columns


def _calibrate_quantiles(
    raw_validation: np.ndarray,
    validation: pd.DataFrame,
    raw_target: np.ndarray,
    target: pd.DataFrame,
    quantiles: np.ndarray,
    min_support: int = 200,
    min_positive: int = 20,
) -> tuple[np.ndarray, list[str], dict[str, Any]]:
    residual = validation["observed_outcome"].to_numpy(float)[:, None] - raw_validation
    global_offsets = np.asarray([np.quantile(residual[:, index], q) for index, q in enumerate(quantiles)])
    global_offsets = IsotonicRegression(increasing=True).fit_transform(quantiles, global_offsets)
    calibrated = np.empty_like(raw_target, dtype=float)
    levels: list[str] = []
    for index, record in enumerate(target.itertuples(index=False)):
        masks = [
            (
                "airport_stage",
                validation["airport_id"].eq(record.airport_id)
                & validation["snapshot_stage"].eq(record.snapshot_stage),
            ),
            ("stage", validation["snapshot_stage"].eq(record.snapshot_stage)),
            ("airport", validation["airport_id"].eq(record.airport_id)),
        ]
        selected = global_offsets
        level = "global"
        for candidate_level, mask in masks:
            cell = residual[np.asarray(mask)]
            positives = int((validation.loc[mask, "observed_outcome"] > 15).sum())
            if len(cell) >= min_support and positives >= min_positive:
                offsets = np.asarray([np.quantile(cell[:, q_index], q) for q_index, q in enumerate(quantiles)])
                selected = IsotonicRegression(increasing=True).fit_transform(quantiles, offsets)
                level = candidate_level
                break
        calibrated[index] = np.maximum.accumulate(raw_target[index] + selected)
        levels.append(level)
    raw_crossing = (np.diff(raw_target, axis=1) < 0).any(axis=1)
    repair = np.max(np.abs(calibrated - raw_target), axis=1)
    return calibrated, levels, {"raw_crossing": raw_crossing, "repair_magnitude": repair}


def _confusion(outcome: np.ndarray, decision: np.ndarray, threshold: float = 15.0) -> dict[str, Any]:
    actual = outcome > threshold
    predicted = np.asarray(decision, bool)
    tp = int(np.sum(actual & predicted))
    fp = int(np.sum(~actual & predicted))
    tn = int(np.sum(~actual & ~predicted))
    fn = int(np.sum(actual & ~predicted))
    ratio = lambda numerator, denominator: float(numerator / denominator) if denominator else np.nan
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "recall": ratio(tp, tp + fn),
        "missed_trigger_rate": ratio(fn, tp + fn),
        "precision": ratio(tp, tp + fp),
        "false_alarm_ratio": ratio(fp, tp + fp),
        "false_positive_rate": ratio(fp, fp + tn),
        "specificity": ratio(tn, tn + fp),
    }


def _select_flights(frame: pd.DataFrame, maximum: int, salt: str) -> set[str]:
    flights = frame["flight_id"].astype(str).drop_duplicates().to_frame()
    flights["key"] = flights["flight_id"].map(lambda value: stable_hash([salt, value]))
    return set(flights.sort_values("key", kind="mergesort").head(maximum)["flight_id"])


def _model_frame(cfg: dict[str, Any], cohort: pd.DataFrame) -> pd.DataFrame:
    overall_cfg = yaml.safe_load((PROJECT / "overall_run" / "config" / "default.yaml").read_text(encoding="utf-8"))
    features = overall_cfg["m1"]["feature_allowlist"]
    identity = [
        "episode_id", "snapshot_id", "snapshot_stage", "split", "airport", "flight_id",
        "anchor_date", "is_primary_snapshot", "snapshot_valid", "formal_eligible",
    ]
    columns = list(dict.fromkeys(identity + features))
    snapshots = pd.read_parquet(cfg["pre"] / "snapshots.parquet", columns=columns)
    episodes = pd.read_parquet(
        cfg["pre"] / "episodes.parquet",
        columns=["episode_id", FORMAL_TARGET_COLUMN, SENSITIVITY_TARGET_COLUMN, "episode_valid"],
    )
    frame = snapshots.merge(episodes, on="episode_id", how="left", validate="many_to_one")
    frame = frame[
        frame["snapshot_valid"].fillna(False).astype(bool)
        & frame["formal_eligible"].fillna(False).astype(bool)
        & frame["is_primary_snapshot"].fillna(False).astype(bool)
        & frame["episode_valid"].fillna(False).astype(bool)
        & pd.to_numeric(frame[FORMAL_TARGET_COLUMN], errors="coerce").notna()
    ].copy()
    frame["observed_outcome"] = pd.to_numeric(frame[FORMAL_TARGET_COLUMN], errors="coerce")
    frame["observed_outcome_source"] = FORMAL_TARGET_COLUMN
    raw = pd.to_numeric(frame[FORMAL_TARGET_COLUMN], errors="coerce")
    mismatch = ~(frame["observed_outcome"].eq(raw) | (frame["observed_outcome"].isna() & raw.isna()))
    if int(mismatch.sum()):
        raise ValueError("PART_ADV_OBSERVED_OUTCOME_RAW_IDENTITY_MISMATCH")
    frame["airport_id"] = frame["airport"].astype(str)
    frame["sample_weight"] = 1.0 / frame.groupby("flight_id", observed=True)["snapshot_id"].transform("count").clip(lower=1)
    train = frame[frame["split"].eq("train")]
    validation = frame[frame["split"].eq("validation")]
    train_ids = _select_flights(train, int(overall_cfg["m1"]["max_train_episodes"]), "part-train")
    validation_ids = _select_flights(
        validation, int(overall_cfg["m1"]["max_validation_episodes"]), "part-validation"
    )
    evaluation_ids = set(cohort["snapshot_id"].astype(str))
    selected = pd.concat(
        [
            train[train["flight_id"].astype(str).isin(train_ids)],
            validation[validation["flight_id"].astype(str).isin(validation_ids)],
            frame[frame["snapshot_id"].astype(str).isin(evaluation_ids)],
        ],
        ignore_index=True,
    ).drop_duplicates("snapshot_id")
    return selected.sort_values(["split", "anchor_date", "flight_id", "snapshot_id"], kind="mergesort")


