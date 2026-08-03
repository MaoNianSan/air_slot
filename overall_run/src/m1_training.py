from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


def prepare_model_frame(
    snapshots: pd.DataFrame,
    episodes: pd.DataFrame,
    scientific: dict[str, Any],
) -> tuple[pd.DataFrame, list[str], list[str], list[str]]:
    """Build the formal raw-label M1 frame and frozen feature schema."""
    configured = scientific.get("m1", {}).get("formal_target")
    if configured != "y_movement_raw" or "target_candidates" in scientific.get("m1", {}):
        raise RuntimeError("FORMAL_TARGET_CONFIG_INVALID")
    if "y_movement_raw" not in episodes.columns:
        raise RuntimeError("FORMAL_TARGET_MISSING:y_movement_raw")
    target_columns = ["episode_id", "y_movement_raw"]
    if "target" in episodes.columns:
        target_columns.append("target")
    frame = snapshots.merge(
        episodes[target_columns], on="episode_id", how="left", validate="many_to_one"
    )
    raw = pd.to_numeric(frame["y_movement_raw"], errors="coerce")
    if "target" in frame:
        alias = pd.to_numeric(frame["target"], errors="coerce")
        mismatch = ~(alias.eq(raw) | (alias.isna() & raw.isna()))
        if int(mismatch.sum()):
            raise RuntimeError("OBSERVED_OUTCOME_SOURCE_IDENTITY_MISMATCH")
    frame["target"] = raw
    if "time_bin" not in frame.columns:
        frame["time_bin"] = (
            frame["decision_time"].dt.hour.floordiv(6).astype("Int64").astype(str)
        )

    prohibited = [str(value).lower() for value in scientific["m1"].get("prohibited_patterns", [])]
    fixed_exclude = {
        "episode_id", "flight_id", "snapshot_id", "split", "target", "decision_time",
        "snapshot_valid", "is_valid", "valid", "balanced_primary", "balanced_primary_cohort",
        "formal_eligible", "is_primary_snapshot", "snapshot_exclusion_reason", "episode_valid",
        "candidate_episode", "exclusion_reason", "selection_key", "subset_role", "anchor_date",
    }
    allowlist = [str(value) for value in scientific["m1"].get("feature_allowlist", [])]
    candidate_columns = allowlist if allowlist else list(frame.columns)
    features = []
    for column in candidate_columns:
        if column not in frame.columns:
            continue
        if column in fixed_exclude or any(token in column.lower() for token in prohibited):
            continue
        if frame[column].map(lambda value: isinstance(value, (list, dict, tuple, set))).any():
            continue
        features.append(column)
    numeric = [column for column in features if pd.api.types.is_numeric_dtype(frame[column])]
    categorical = [
        column for column in features
        if column not in numeric and not pd.api.types.is_datetime64_any_dtype(frame[column])
    ]
    for column in categorical:
        frame[column] = frame[column].astype(object).where(
            frame[column].notna(), np.nan
        )
    features = numeric + categorical
    if not features:
        raise RuntimeError("M1_FEATURE_SCHEMA_EMPTY")
    return frame, features, numeric, categorical


def _make_ohe() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=True)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=True)


def make_transformer(
    numeric: list[str],
    categorical: list[str],
) -> ColumnTransformer:
    transformers = []
    if numeric:
        transformers.append(
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median"))]), numeric)
        )
    if categorical:
        transformers.append(
            (
                "cat",
                Pipeline([
                    ("imputer", SimpleImputer(strategy="most_frequent")),
                    ("onehot", _make_ohe()),
                ]),
                categorical,
            )
        )
    return ColumnTransformer(transformers, remainder="drop")


def make_quantile_regressor(
    params: dict[str, Any],
    tau: float,
    n_estimators: int,
    seed: int,
    n_jobs: int,
) -> LGBMRegressor:
    return LGBMRegressor(
        objective="quantile",
        alpha=float(tau),
        n_estimators=int(n_estimators),
        num_leaves=int(params["num_leaves"]),
        max_depth=int(params["max_depth"]),
        min_child_samples=int(params["min_child_samples"]),
        learning_rate=float(params["learning_rate"]),
        colsample_bytree=float(params["feature_fraction"]),
        subsample=float(params["bagging_fraction"]),
        subsample_freq=1 if float(params["bagging_fraction"]) < 1.0 else 0,
        reg_lambda=float(params["reg_lambda"]),
        random_state=int(seed),
        deterministic=True,
        force_col_wise=True,
        verbosity=-1,
        n_jobs=max(1, int(n_jobs)),
    )


def blocked_folds(frame: pd.DataFrame) -> list[tuple[np.ndarray, np.ndarray]]:
    """Use Jan-Apr -> May-Jun and Jan-Jun -> Jul-Aug when available."""
    months = pd.to_datetime(frame["decision_time"], utc=True, errors="coerce").dt.month.to_numpy()
    formal_folds = []
    for train_months, validation_months in [
        ({1, 2, 3, 4}, {5, 6}),
        ({1, 2, 3, 4, 5, 6}, {7, 8}),
    ]:
        train = np.flatnonzero(np.isin(months, list(train_months)))
        validation = np.flatnonzero(np.isin(months, list(validation_months)))
        if len(train) and len(validation):
            formal_folds.append((train, validation))
    if len(formal_folds) == 2:
        return formal_folds

    dates = np.array(sorted(pd.Series(frame["decision_time"].dt.date.unique()).dropna()))
    if len(dates) < 4:
        indices = np.arange(len(frame))
        split = max(1, int(len(indices) * 0.75))
        if split >= len(indices):
            split = max(1, len(indices) - 1)
        return [(indices[:split], indices[split:])]
    folds = []
    date_values = frame["decision_time"].dt.date.to_numpy()
    for train_fraction, validation_fraction in [(0.50, 0.75), (0.75, 1.00)]:
        train_end = max(1, int(len(dates) * train_fraction))
        validation_end = min(
            len(dates), max(train_end + 1, int(len(dates) * validation_fraction))
        )
        train = np.flatnonzero(np.isin(date_values, dates[:train_end]))
        validation = np.flatnonzero(np.isin(date_values, dates[train_end:validation_end]))
        if len(train) and len(validation):
            folds.append((train, validation))
    if not folds:
        raise RuntimeError("M1_BLOCKED_FOLDS_UNAVAILABLE")
    return folds
