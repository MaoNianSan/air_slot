from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .reference_models import (
    AirportReference,
    FlowReference,
    MovementTimeReference,
    TurnaroundReference,
    WeatherClimatology,
)
from .reference_utils import WEATHER_FIELDS, _normalize, _time_bin


def _aggregate_movement(train: pd.DataFrame, keys: list[str], min_cell: int) -> pd.DataFrame:
    table = train.groupby(keys, dropna=False)["observed_movement_time"].agg(
        reference_movement_time="median", cell_size="size"
    ).reset_index()
    return table[table["cell_size"] >= min_cell].copy()


def fit_movement_reference(legs: pd.DataFrame, cfg: dict[str, Any]) -> MovementTimeReference:
    train = legs[(legs["split"] == "train") & legs["candidate_episode"]].copy()
    if train.empty:
        raise ValueError("no training legs for T_ref")
    minimum = int(cfg["references"]["movement_min_cell"])
    tables = {
        "L1": _aggregate_movement(train, ["origin", "destination", "firstseen_month", "firstseen_time_bin", "aircraft_group"], minimum),
        "L2": _aggregate_movement(train, ["origin", "destination", "firstseen_month", "firstseen_time_bin"], minimum),
        "L3": _aggregate_movement(train, ["origin", "destination", "firstseen_month"], minimum),
        "L4": _aggregate_movement(train, ["origin", "destination"], minimum),
        "L5": _aggregate_movement(train, ["distance_bin", "region_pair"], minimum),
        "L6": _aggregate_movement(train, ["distance_bin"], minimum),
    }
    if tables["L6"].empty:
        tables["L6"] = _aggregate_movement(train, ["distance_bin"], 1)
    if tables["L6"].empty:
        raise ValueError("global distance-bin T_ref is empty")
    return MovementTimeReference(tables)


def _weather_aggregate(frame: pd.DataFrame, keys: list[str], minimum: int) -> pd.DataFrame:
    named = {field: (field, "median") for field in WEATHER_FIELDS}
    table = frame.groupby(keys, dropna=False).agg(**named, cell_size=("airport", "size")).reset_index()
    return table[table["cell_size"] >= minimum].copy()


def fit_weather_climatology(metar: pd.DataFrame, cfg: dict[str, Any]) -> WeatherClimatology:
    train_end = pd.Timestamp(cfg["splits"]["train"][1], tz="UTC")
    frame = metar[metar["observation_time"] < train_end].copy()
    frame["month"] = frame["observation_time"].dt.month
    frame["time_bin"] = frame["observation_time"].map(_time_bin)
    frame["airport_region"] = frame["airport"].map(cfg["airports"]["regions"]).fillna("UNKNOWN")
    minimum = int(cfg["references"].get("weather_min_cell", 5))
    tables = {
        "L0": _weather_aggregate(frame, ["airport", "month", "time_bin"], minimum),
        "L1": _weather_aggregate(frame, ["airport", "month"], minimum),
        "L2": _weather_aggregate(frame, ["airport"], minimum),
        "L3": _weather_aggregate(frame, ["airport_region", "month"], minimum),
        "L4": _weather_aggregate(frame, ["month"], minimum),
        "L5": _weather_aggregate(frame.assign(global_key="GLOBAL"), ["global_key"], 1),
    }
    return WeatherClimatology(tables)


def fit_flow_reference(training_snapshots: pd.DataFrame) -> FlowReference:
    clean = training_snapshots.dropna(subset=["airport_flow_pressure"]).copy()
    clean["airport_flow_pressure"] = pd.to_numeric(clean["airport_flow_pressure"], errors="coerce")
    clean = clean.dropna(subset=["airport_flow_pressure"])
    if clean.empty:
        return FlowReference(pd.DataFrame(columns=[
            "airport", "time_bin", "flow_p05", "flow_p50", "flow_p90", "flow_p95", "flow_cell_size"
        ]))
    grouped = clean.groupby(["airport", "time_bin"], dropna=False)["airport_flow_pressure"]
    table = grouped.quantile([0.05, 0.50, 0.90, 0.95]).unstack().reset_index()
    table.columns = ["airport", "time_bin", "flow_p05", "flow_p50", "flow_p90", "flow_p95"]
    sizes = grouped.size().rename("flow_cell_size").reset_index()
    return FlowReference(table.merge(sizes, on=["airport", "time_bin"], how="left"))


def _turnaround_aggregate(frame: pd.DataFrame, keys: list[str], minimum: int, horizon: float) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    grouped = frame.groupby(keys, dropna=False)["gap_minutes"]
    table = grouped.quantile([0.1, 0.5]).unstack().reset_index()
    table.columns = [*keys, "turnaround_minimum", "turnaround_typical"]
    sizes = grouped.size().rename("cell_size").reset_index()
    continuity = frame.assign(_continuity=(frame["gap_minutes"] <= horizon).astype(float)).groupby(
        keys, dropna=False
    )["_continuity"].mean().rename("continuity_probability").reset_index()
    table = table.merge(sizes, on=keys, how="left").merge(continuity, on=keys, how="left")
    return table[table["cell_size"] >= minimum].copy()


def fit_turnaround_reference(legs: pd.DataFrame, cfg: dict[str, Any]) -> TurnaroundReference:
    train = legs[legs["split"] == "train"].sort_values(["icao24", "firstseen_utc"]).copy()
    next_rows = train.groupby("icao24").shift(-1)
    gaps = pd.DataFrame({
        "airport": train["destination"],
        "next_origin": next_rows["origin"],
        "aircraft_group": train["aircraft_group"],
        "firstseen_time_bin": train["firstseen_time_bin"],
        "gap_minutes": (next_rows["firstseen_utc"] - train["lastseen_utc"]).dt.total_seconds() / 60.0,
    })
    low, high = cfg["references"]["turnaround_gap_minutes"]
    gaps = gaps[(gaps["airport"] == gaps["next_origin"]) & gaps["gap_minutes"].between(low, high, inclusive="both")]
    minimum = int(cfg["references"]["movement_min_cell"])
    horizon = float(cfg["references"]["continuity_horizon_minutes"])
    tables = {
        "airport_aircraft_time": _turnaround_aggregate(gaps, ["airport", "aircraft_group", "firstseen_time_bin"], minimum, horizon),
        "airport_aircraft": _turnaround_aggregate(gaps, ["airport", "aircraft_group"], minimum, horizon),
        "airport": _turnaround_aggregate(gaps, ["airport"], minimum, horizon),
        "global_aircraft": _turnaround_aggregate(gaps, ["aircraft_group"], minimum, horizon),
        "global": _turnaround_aggregate(gaps.assign(global_key="GLOBAL"), ["global_key"], 1, horizon),
    }
    return TurnaroundReference(tables)


def fit_airport_reference(airports: pd.DataFrame, flights: pd.DataFrame, cfg: dict[str, Any]) -> AirportReference:
    cohort = airports[airports["airport"].isin(cfg["airports"]["m1"])].copy()
    train_end_month = pd.Timestamp(cfg["splits"]["train"][1]).month
    flights = flights[pd.to_numeric(flights["month"], errors="coerce") < train_end_month].copy()
    runways = pd.to_numeric(cohort["runway_count"], errors="coerce")
    if runways.notna().any():
        fill_value = float(runways.median())
        cohort["infrastructure_fallback_level"] = np.where(runways.isna(), "AIRPORT_CLASS_MEDIAN", "FROZEN_STATIC")
        cohort["runway_count"] = runways.fillna(fill_value)
        low, high = float(cohort["runway_count"].quantile(0.05)), float(cohort["runway_count"].quantile(0.95))
        if high <= low:
            high = low + 1.0
        cohort["infrastructure_flexibility"] = cohort["runway_count"].map(lambda x: _normalize(float(x), low, high))
    else:
        cohort["infrastructure_fallback_level"] = "MISSING"
        cohort["infrastructure_flexibility"] = np.nan
    totals = flights.groupby("airport")["commercial_flights"].sum(min_count=1)
    cohort["commercial_total"] = cohort["airport"].map(totals)
    values = pd.to_numeric(cohort["commercial_total"], errors="coerce")
    if values.notna().any():
        low, high = float(values.quantile(0.05)), float(values.quantile(0.95))
        if high <= low:
            high = low + max(1.0, abs(low) * 1e-6)
        cohort["airport_scale"] = values.map(lambda x: _normalize(float(x), low, high) if pd.notna(x) else np.nan)
    else:
        cohort["airport_scale"] = np.nan
    cohort["airport_scale_fallback_level"] = np.where(cohort["airport_scale"].isna(), "MISSING", "TRAINING_COMMERCIAL_TOTAL")
    return AirportReference(cohort)


