from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .cohort import Cohorts
from .config import RunConfig
from .failures import FormalRunBlocked
from .input import validate_bundle
from .utils import stable_hash


def resolve_pre_output(cfg: RunConfig, override: Path | None) -> Path:
    if override:
        return override.resolve()
    raw = Path(cfg.scientific.get("paths", {}).get("pre_output", "../pre/output"))
    base = (cfg.root / raw).resolve() if not raw.is_absolute() else raw.resolve()
    mode_path = base / cfg.mode_name
    return mode_path if mode_path.exists() else base


def validate_bundle_with_rule_anchors(
    bundle: Any,
    scientific: dict[str, Any],
) -> dict[str, Any]:
    """Validate PRE and resolve resource availability from the rules table."""
    adjusted = json.loads(json.dumps(scientific, default=str))
    groups = adjusted.get("m2", {}).get("required_anchor_groups", {})
    resource_aliases = list(
        groups.pop(
            "resource_available",
            ["resource_available_r", "resource_availability_r"],
        )
    )
    result = validate_bundle(bundle, adjusted)
    if not any(alias in bundle.rules.columns for alias in resource_aliases):
        raise FormalRunBlocked(
            "M2_RESOURCE_AVAILABILITY_RULE_ANCHOR_MISSING:"
            + ",".join(resource_aliases)
        )
    result["issues"].append({
        "code": "m2_anchor_source:resource_available",
        "value": "rules",
        "hard": True,
    })
    return result


def enrich_snapshots(
    snapshots: pd.DataFrame,
    calibration: pd.DataFrame,
) -> pd.DataFrame:
    """Attach frozen calibration fields without replacing decision-time fields."""
    snapshot_frame = snapshots.copy()
    calibration_frame = calibration.copy()
    if calibration_frame.empty:
        return snapshot_frame
    if "airport" in snapshot_frame.columns:
        snapshot_frame["airport"] = snapshot_frame["airport"].astype(str).str.upper()
    if "airport" in calibration_frame.columns:
        calibration_frame["airport"] = calibration_frame["airport"].astype(str).str.upper()
    keys = [
        column
        for column in ("airport", "month", "time_bin")
        if column in snapshot_frame.columns and column in calibration_frame.columns
    ]
    if not keys:
        return snapshot_frame
    for key in keys:
        if key != "airport":
            snapshot_frame[key] = snapshot_frame[key].astype("string")
            calibration_frame[key] = calibration_frame[key].astype("string")
    calibration_frame = calibration_frame.drop_duplicates(keys, keep="last")
    added = [
        column
        for column in calibration_frame.columns
        if column not in keys and column not in snapshot_frame.columns
    ]
    if not added:
        return snapshot_frame
    return snapshot_frame.merge(
        calibration_frame[keys + added],
        on=keys,
        how="left",
        validate="many_to_one",
    )


def set_model_attrs(
    frame: pd.DataFrame,
    features: list[str],
    numeric: list[str],
    categorical: list[str],
) -> pd.DataFrame:
    result = frame.copy()
    result.attrs["feature_columns"] = list(features)
    result.attrs["numeric_columns"] = list(numeric)
    result.attrs["categorical_columns"] = list(categorical)
    return result


def filter_training_features(
    train: pd.DataFrame,
    features: list[str],
    numeric: list[str],
    categorical: list[str],
) -> tuple[list[str], list[str], list[str], pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    active: list[str] = []
    for column in features:
        nonmissing = int(train[column].notna().sum())
        unique_nonmissing = int(train[column].dropna().nunique())
        status = "selected" if nonmissing > 0 else "excluded_all_missing_train"
        if nonmissing > 0:
            active.append(column)
        rows.append({
            "feature": column,
            "dtype": str(train[column].dtype),
            "training_nonmissing": nonmissing,
            "training_unique_nonmissing": unique_nonmissing,
            "status": status,
        })
    if not active:
        raise FormalRunBlocked("M1_ALL_FEATURES_MISSING_IN_TRAIN")
    active_numeric = [column for column in numeric if column in active]
    active_categorical = [column for column in categorical if column in active]
    return active, active_numeric, active_categorical, pd.DataFrame(rows)


def stable_scale_frame(train: pd.DataFrame, cfg: RunConfig, mode: str) -> pd.DataFrame:
    scale_cfg = cfg.compute.get("m2_unit_scale", {})
    maximum_key = f"{mode}_max_snapshots"
    fallback_key = "fast_max_snapshots" if mode == "fast" else "full_max_snapshots"
    maximum_rows = int(scale_cfg.get(maximum_key, scale_cfg.get(fallback_key, 1000)))
    if len(train) <= maximum_rows:
        return train.copy().reset_index(drop=True)
    flights = train.groupby("flight_id", as_index=False).agg(
        airport=("airport", "first"),
        snapshot_count=("snapshot_id", "count"),
    )
    flights["selection_key"] = flights["flight_id"].map(
        lambda flight_id: stable_hash(
            cfg.compute["random_seed"], "m2_unit_scale", flight_id
        )
    )
    mean_count = max(float(flights["snapshot_count"].mean()), 1.0)
    target_flights = max(1, int(maximum_rows / mean_count))
    parts = []
    total = max(len(flights), 1)
    for _, group in flights.groupby("airport", sort=True, dropna=False):
        quota = max(1, round(target_flights * len(group) / total))
        parts.append(group.sort_values("selection_key", kind="mergesort").head(quota))
    selected = (
        pd.concat(parts, ignore_index=True)
        .sort_values("selection_key", kind="mergesort")
        .head(target_flights)
    )
    return (
        train[train["flight_id"].isin(set(selected["flight_id"]))]
        .sort_values(["flight_id", "snapshot_id"], kind="mergesort")
        .head(maximum_rows)
        .copy()
        .reset_index(drop=True)
    )


def flight_weights(frame: pd.DataFrame) -> pd.Series:
    counts = frame.groupby("flight_id")["snapshot_id"].transform("count").clip(lower=1)
    return 1.0 / counts


def role_mask(series: pd.Series, roles: list[str]) -> pd.Series:
    allowed = {str(value).lower() for value in roles}
    return series.astype(str).str.lower().isin(allowed)


def write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = frame.copy()
    for column in output.select_dtypes(include=["object"]).columns:
        types = {type(value) for value in output[column].dropna()}
        if len(types) > 1:
            output[column] = output[column].map(
                lambda value: "" if pd.isna(value) else str(value)
            )
    output.to_parquet(path, index=False)


def save_cohorts(cohorts: Cohorts, root: Path) -> None:
    for name in ("all_valid", "balanced_rolling", "formal_core", "precision"):
        write_frame(getattr(cohorts, name), root / f"{name}.parquet")


def subset_rules(rules: pd.DataFrame, snapshots: pd.DataFrame) -> pd.DataFrame:
    keys = ["episode_id", "snapshot_id"]
    available = [
        column
        for column in (
            "airport_flow_pressure", "airport_flow", "flow_pressure",
            "lead_time_margin", "execution_window_margin",
        )
        if column in snapshots.columns and column not in rules.columns
    ]
    snapshot_context = snapshots[keys + available].drop_duplicates(keys)
    return rules.merge(snapshot_context, on=keys, how="inner", validate="many_to_one")


def attach_rule_context(
    snapshots: pd.DataFrame,
    rules: pd.DataFrame,
) -> pd.DataFrame:
    """Expose declared resource state to M2 without inferring it from flow."""
    keys = ["episode_id", "snapshot_id"]
    columns = [
        column
        for column in (
            "resource_profile_id", "resource_available_f", "resource_available_p",
            "resource_available_r", "authority_profile_id",
        )
        if column in rules.columns
    ]
    if not columns:
        return snapshots
    context = rules[keys + columns].drop_duplicates(keys)
    return snapshots.merge(context, on=keys, how="left", validate="one_to_one")


def validate_action_library(rules: pd.DataFrame, actions: dict[str, Any]) -> None:
    required = ("authority_profile_id", "resource_profile_id")
    missing = [column for column in required if column not in rules]
    if missing:
        raise FormalRunBlocked("PRE_RULE_CONTEXT_MISSING:" + ",".join(missing))
    declared_ids = set(rules["action_id"].astype(str))
    if declared_ids != set(actions):
        raise FormalRunBlocked(
            "ACTION_LIBRARY_PRE_MISMATCH:"
            + ",".join(sorted(declared_ids.symmetric_difference(set(actions))))
        )
    optional = {"capacity_required", "window_type"}
    if optional.issubset(rules.columns):
        declared = rules[["action_id", "capacity_required", "window_type"]].drop_duplicates()
        for row in declared.itertuples(index=False):
            action = actions.get(str(row.action_id))
            mismatched = (
                action is None
                or bool(row.capacity_required) != bool(action.capacity_required)
                or str(row.window_type) != str(action.window_type)
            )
            if mismatched:
                raise FormalRunBlocked(f"ACTION_LIBRARY_PRE_MISMATCH:{row.action_id}")


def prediction_table(
    frame: pd.DataFrame,
    prediction: dict[str, Any],
    quantiles: list[float],
) -> pd.DataFrame:
    output = frame[
        ["episode_id", "flight_id", "snapshot_id", "airport", "snapshot_stage", "target"]
    ].copy().reset_index(drop=True)
    for index, quantile in enumerate(quantiles):
        suffix = str(quantile).replace(".", "_")
        if "raw_quantiles" in prediction:
            output[f"raw_q_{suffix}"] = prediction["raw_quantiles"][:, index]
        output[f"q_{suffix}"] = prediction["quantiles"][:, index]
    output["p_exceed_15"] = prediction["p_exceed_15"]
    output["p_window"] = prediction.get("p_window", np.full(len(output), np.nan))
    output["calibration_level"] = prediction["calibration_level"]
    output["flight_weight"] = flight_weights(frame).to_numpy(float)
    return output


def trigger(prediction: dict[str, Any], scientific: dict[str, Any]) -> np.ndarray:
    config = scientific["m1"]["trigger"]
    exceedance = np.asarray(prediction["p_exceed_15"], dtype=float)
    window = np.asarray(prediction["p_window"], dtype=float)
    return (exceedance > float(config["exceedance_probability"])) | (
        np.isfinite(window) & (window > float(config["window_probability"]))
    )


def safe_nanmean(matrix: np.ndarray) -> np.ndarray:
    values = np.asarray(matrix, dtype=float)
    finite = np.isfinite(values)
    total = np.where(finite, values, 0.0).sum(axis=1)
    count = finite.sum(axis=1)
    return np.divide(total, count, out=np.full(len(values), np.nan), where=count > 0)


def safe_nanquantile(matrix: np.ndarray, quantile: float) -> np.ndarray:
    rows = []
    for row in np.asarray(matrix, dtype=float):
        finite = row[np.isfinite(row)]
        rows.append(float(np.quantile(finite, quantile)) if len(finite) else np.nan)
    return np.asarray(rows, dtype=float)


def authoritative_m2_summary(
    frame: pd.DataFrame,
    result: dict[str, Any],
) -> pd.DataFrame:
    output = frame[
        ["episode_id", "flight_id", "snapshot_id", "airport", "snapshot_stage"]
    ].copy().reset_index(drop=True)
    for channel in ("F", "P", "R"):
        raw_quantity = np.asarray(result["raw_quantities"][channel], dtype=float)
        unit_quantity = np.asarray(result["quantities_unit"][channel], dtype=float)
        cost = np.asarray(result["costs_rmb"][channel], dtype=float)
        output[f"base_exposure_{channel}"] = result["base_exposures"][channel]
        output[f"exposure_{channel}"] = result["exposures"][channel]
        output[f"threshold_{channel}"] = result["thresholds"][channel]
        output[f"raw_quantity_mean_{channel}"] = safe_nanmean(raw_quantity)
        output[f"raw_quantity_p90_{channel}"] = safe_nanquantile(raw_quantity, 0.90)
        output[f"common_unit_scale_{channel}"] = float(result["unit_scales"][channel])
        output[f"quantity_unit_mean_{channel}"] = safe_nanmean(unit_quantity)
        output[f"quantity_unit_p90_{channel}"] = safe_nanquantile(unit_quantity, 0.90)
        output[f"unit_cost_rmb_{channel}"] = float(result["unit_costs_rmb"][channel])
        output[f"cost_rmb_mean_{channel}"] = safe_nanmean(cost)
        output[f"cost_rmb_p90_{channel}"] = safe_nanquantile(cost, 0.90)
        output[f"loss_mean_{channel}"] = output[f"cost_rmb_mean_{channel}"]
        output[f"positive_{channel}"] = np.where(
            np.isfinite(cost).any(axis=1), (cost > 0).mean(axis=1), np.nan
        )
    for edge, values in result.get("edge_contributions", {}).items():
        output[f"edge_contribution_{edge}"] = np.asarray(values, dtype=float)
    total = np.asarray(result["total_cost_rmb"], dtype=float)
    output["total_pre_action_cost_rmb_mean"] = safe_nanmean(total)
    output["total_pre_action_cost_rmb_p90"] = safe_nanquantile(total, 0.90)
    output["passenger_proxy_used"] = np.asarray(result["passenger_proxy_used"], dtype=bool)
    output["passenger_proxy_missing_reason"] = np.asarray(
        result["passenger_proxy_missing_reason"], dtype=object
    )
    output["passenger_cost_fallback_used"] = np.asarray(
        result["passenger_cost_fallback_used"], dtype=bool
    )
    for name, values in result.get("anchor_statuses", {}).items():
        output[f"anchor_{name}_status"] = np.asarray(values, dtype=object)
    status_columns = [
        column
        for column in output
        if column.startswith("anchor_") and column.endswith("_status")
    ]
    if status_columns:
        output["m2_calibration_imputation_count"] = (
            output[status_columns].eq("CALIBRATION_IMPUTED").sum(axis=1)
        )
        output["m2_unsupported_anchor_count"] = (
            output[status_columns].eq("UNSUPPORTED_INPUT").sum(axis=1)
        )
    return output


def passenger_support(frame: pd.DataFrame) -> pd.Series:
    required = [
        "estimated_passenger_load",
        "connection_pressure_proxy",
        "rebooking_scarcity_proxy",
        "passenger_proxy_support",
        "passenger_proxy_evidence_status",
    ]
    if any(column not in frame for column in required):
        return pd.Series(False, index=frame.index)
    evidence = frame["passenger_proxy_evidence_status"].astype("string")
    return (
        frame[required[:3]].notna().all(axis=1)
        & pd.to_numeric(frame["passenger_proxy_support"], errors="coerce").gt(0)
        & evidence.notna()
        & ~evidence.eq("UNOBSERVED")
    )
