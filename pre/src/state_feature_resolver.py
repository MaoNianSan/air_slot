from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .state import StateStore
from .state_quality import coverage_status, evaluate_state_window


STATE_SOURCE_FIELDS = [
    "latitude",
    "longitude",
    "altitude",
    "velocity",
    "vertical_rate",
]
STATE_OUTPUT_FIELDS = [
    "current_latitude",
    "current_longitude",
    "current_altitude",
    "current_velocity",
    "vertical_rate",
]


def _state_for_snapshot(
    row: pd.Series,
    aircraft: pd.DataFrame,
    status: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    decision = row["decision_time_utc"]
    base: dict[str, Any] = {
        "current_latitude": np.nan,
        "current_longitude": np.nan,
        "current_altitude": np.nan,
        "current_velocity": np.nan,
        "vertical_rate": np.nan,
        "trajectory_coverage": 0.0,
        "state_observation_age": np.nan,
        "state_record_count": 0,
        "state_lookback_minutes": float(
            cfg["state_vectors"]["lookback_minutes"]
        ),
        "state_source_coverage": 0.0 if status == "SOURCE_COVERAGE_GAP" else 1.0,
        "state_source_coverage_status": status,
        "state_is_imputed": False,
        "state_imputation_method": "none",
        "state_imputation_gap_minutes": np.nan,
        "_state_event_time": pd.NaT,
        "_state_availability_time": pd.NaT,
        "_state_source_record_ids": "",
        "_state_raw_file": "",
        "_state_raw_hash": "",
        "_state_missing_reason": "",
        "_state_quality_ok": False,
    }
    if status == "SOURCE_COVERAGE_GAP":
        base["_state_missing_reason"] = "SOURCE_COVERAGE_GAP"
        return base
    if aircraft.empty:
        base["_state_missing_reason"] = "RECORD_EXPECTED_BUT_MISSING"
        return base
    lookback = pd.to_timedelta(
        cfg["state_vectors"]["lookback_minutes"], unit="m"
    )
    subset = aircraft[
        (aircraft["availability_time"] <= decision)
        & (aircraft["event_time"] >= decision - lookback)
        & (aircraft["event_time"] <= decision)
    ].sort_values("event_time")
    if subset.empty:
        base["_state_missing_reason"] = "RECORD_NOT_AVAILABLE_BY_T"
        return base
    latest = subset.iloc[-1]
    for source, target in zip(STATE_SOURCE_FIELDS, STATE_OUTPUT_FIELDS):
        base[target] = (
            float(latest[source]) if pd.notna(latest[source]) else np.nan
        )
    quality = evaluate_state_window(subset, decision, cfg)
    base.update(
        {
            "trajectory_coverage": quality.trajectory_coverage,
            "state_observation_age": quality.observation_age_minutes,
            "state_record_count": quality.record_count,
            "state_is_imputed": bool(latest.get("state_is_imputed", False)),
            "state_imputation_method": str(
                latest.get("state_imputation_method", "none")
            ),
            "state_imputation_gap_minutes": latest.get(
                "state_imputation_gap_minutes", np.nan
            ),
            "_state_event_time": latest["event_time"],
            "_state_availability_time": latest["availability_time"],
            "_state_source_record_ids": str(latest.get("source_record_id", "")),
            "_state_raw_file": str(latest.get("raw_source_file", "")),
            "_state_raw_hash": str(latest.get("raw_source_hash", "")),
            "_state_quality_ok": quality.quality_ok,
            "_state_missing_reason": (
                "" if quality.quality_ok else "FAILED_QUALITY_CHECK"
            ),
        }
    )
    return base


def attach_state_features(
    snapshots: pd.DataFrame, store: StateStore, cfg: dict[str, Any]
) -> pd.DataFrame:
    pieces = []
    date_series = (
        snapshots["decision_time_utc"]
        .dt.tz_convert("UTC")
        .dt.normalize()
        .dt.tz_localize(None)
    )
    lookback_hours = int(
        np.ceil(float(cfg["state_vectors"]["lookback_minutes"]) / 60.0)
    )
    source_cols = [
        *STATE_SOURCE_FIELDS,
        "event_time",
        "availability_time",
        "icao24",
        "state_is_imputed",
        "state_imputation_method",
        "state_imputation_gap_minutes",
        "source_record_id",
        "raw_source_file",
        "raw_source_hash",
    ]
    for date, group in snapshots.groupby(date_series, sort=True):
        dates = [pd.Timestamp(date)]
        if int(group["decision_time_utc"].dt.hour.min()) < lookback_hours:
            dates.append(pd.Timestamp(date) - pd.Timedelta(days=1))
        day = pd.concat(
            [store.load("candidate", d, columns=source_cols) for d in dates],
            ignore_index=True,
        )
        requested = set(group["icao24"].astype(str))
        day = day[day["icao24"].astype(str).isin(requested)] if not day.empty else day
        by_aircraft = (
            {
                str(code): aircraft.sort_values("event_time").reset_index(drop=True)
                for code, aircraft in day.groupby("icao24", sort=False)
            }
            if not day.empty
            else {}
        )
        features = [
            _state_for_snapshot(
                row,
                by_aircraft.get(str(row["icao24"]), pd.DataFrame()),
                coverage_status(
                    store.coverage,
                    pd.Timestamp(date),
                    row["decision_time_utc"].hour,
                ),
                cfg,
            )
            for _, row in group.iterrows()
        ]
        piece = pd.concat(
            [group.reset_index(), pd.DataFrame(features)], axis=1
        ).set_index("index")
        pieces.append(piece)
    output = pd.concat(pieces).sort_index() if pieces else snapshots.copy()
    failed = ~output["_state_quality_ok"].fillna(False)
    output.loc[failed, "snapshot_valid"] = False
    mask = failed & output["snapshot_exclusion_reason"].eq("")
    output.loc[mask, "snapshot_exclusion_reason"] = output.loc[
        mask, "_state_missing_reason"
    ]
    return output
