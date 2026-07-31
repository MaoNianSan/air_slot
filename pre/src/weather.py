from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .reference import WEATHER_FIELDS, WeatherClimatology


OBSERVED = "OBSERVED"
AGGREGATE_PROXY = "AGGREGATE_PROXY"
UNOBSERVED = "UNOBSERVED"


def _latest_weather(
    row: pd.Series,
    metar: pd.DataFrame,
    climatology: WeatherClimatology,
    cfg: dict[str, Any],
    *,
    indexed_latest: pd.Series | None = None,
    index_was_used: bool = False,
) -> dict[str, Any]:
    decision = row["decision_time_utc"]
    airport = str(row["airport"])
    if index_was_used:
        latest = indexed_latest
    else:
        subset = metar[(metar["airport"] == airport) & (metar["availability_time"] <= decision)].sort_values("observation_time")
        latest = None if subset.empty else subset.iloc[-1]
    base: dict[str, Any] = {
        "wind_speed": np.nan,
        "wind_gust": np.nan,
        "visibility": np.nan,
        "ceiling": np.nan,
        "precipitation_flag": False,
        "weather_code": "UNKNOWN",
        "temperature_dewpoint_spread": np.nan,
        "metar_age": np.nan,
        "weather_observed": False,
        "weather_imputed": False,
        "weather_source": "UNOBSERVED",
        "weather_evidence_status": UNOBSERVED,
        "weather_missing_reason": "",
        "_weather_event_time": pd.NaT,
        "_weather_availability_time": pd.NaT,
        "_weather_source_record_ids": "",
        "_weather_raw_file": "",
        "_weather_raw_hash": "",
        "_weather_fallback_level": "",
        "_weather_cell_size": 0,
    }
    if latest is not None:
        for field in WEATHER_FIELDS:
            base[field] = float(latest[field]) if pd.notna(latest[field]) else np.nan
        base.update({
            "precipitation_flag": bool(latest.get("precipitation_flag", False)),
            "weather_code": str(latest.get("weather_code", "UNKNOWN")),
            "metar_age": float((decision - latest["observation_time"]).total_seconds() / 60.0),
            "weather_observed": True,
            "weather_source": "IEM_METAR",
            "weather_evidence_status": OBSERVED,
            "_weather_event_time": latest["observation_time"],
            "_weather_availability_time": latest["availability_time"],
            "_weather_source_record_ids": str(latest.get("source_record_id", "")),
            "_weather_raw_file": str(latest.get("raw_source_file", "")),
            "_weather_raw_hash": str(latest.get("raw_source_hash", "")),
        })
        return base

    region = cfg["airports"]["regions"].get(airport, "UNKNOWN")
    resolved = climatology.resolve(airport, region, int(row["month"]), str(row["time_bin"]))
    if resolved is None:
        base["weather_missing_reason"] = "SOURCE_COVERAGE_GAP"
        return base
    values, level, cell_size = resolved
    base.update(values)
    base.update({
        "weather_code": "CLIMATOLOGY",
        "weather_imputed": True,
        "weather_source": "TRAINING_CLIMATOLOGY",
        "weather_evidence_status": AGGREGATE_PROXY,
        "weather_missing_reason": "CALIBRATION_IMPUTED",
        "_weather_fallback_level": level,
        "_weather_cell_size": cell_size,
    })
    return base


def attach_weather(
    snapshots: pd.DataFrame,
    metar: pd.DataFrame,
    climatology: WeatherClimatology,
    cfg: dict[str, Any],
) -> pd.DataFrame:
    # Build an exact causal index once per airport.  For every availability
    # prefix, ``best_positions`` points to the record with the greatest
    # observation time in that prefix.  A binary search therefore reproduces
    # the previous filter-and-sort semantics without scanning the entire METAR
    # table for every snapshot.
    airport_index: dict[str, tuple[pd.DataFrame, np.ndarray, np.ndarray]] = {}
    usable = metar.dropna(subset=["airport", "availability_time", "observation_time"])
    for airport, group in usable.groupby("airport", sort=False):
        ordered = group.sort_values(["availability_time", "observation_time"], kind="mergesort").reset_index(drop=True)
        availability_ns = ordered["availability_time"].astype("int64").to_numpy()
        observation_ns = ordered["observation_time"].astype("int64").to_numpy()
        best_positions = np.empty(len(ordered), dtype=np.int64)
        best_position = -1
        best_observation = np.iinfo(np.int64).min
        for position, observation in enumerate(observation_ns):
            if observation >= best_observation:
                best_observation = int(observation)
                best_position = position
            best_positions[position] = best_position
        airport_index[str(airport)] = (ordered, availability_ns, best_positions)

    rows = []
    for _, row in snapshots.iterrows():
        indexed_latest = None
        entry = airport_index.get(str(row["airport"]))
        if entry is not None:
            ordered, availability_ns, best_positions = entry
            prefix_position = int(np.searchsorted(availability_ns, int(row["decision_time_utc"].value), side="right") - 1)
            if prefix_position >= 0:
                indexed_latest = ordered.iloc[int(best_positions[prefix_position])]
        rows.append(
            _latest_weather(
                row,
                metar,
                climatology,
                cfg,
                indexed_latest=indexed_latest,
                index_was_used=True,
            )
        )
    return pd.concat([snapshots.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
