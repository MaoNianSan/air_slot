from __future__ import annotations

import hashlib
import math
from typing import Any

import numpy as np
import pandas as pd

from .input import normalize_airport, normalize_icao24


AIRCRAFT_PREFIX_GROUPS = {
    "narrow_body": ("A31", "A32", "B73", "B38", "B39", "E19", "BCS"),
    "wide_body": ("A33", "A34", "A35", "A38", "B74", "B75", "B76", "B77", "B78"),
    "regional": ("AT4", "AT7", "CRJ", "DH8", "E17", "E18", "F70", "F10"),
    "turboprop": ("AT", "DH", "SF3", "JS3"),
}


def _time_bin(value: pd.Timestamp) -> str:
    if pd.isna(value):
        return "UNKNOWN"
    hour = int(value.hour)
    if 0 <= hour < 6:
        return "00_06"
    if 6 <= hour < 12:
        return "06_12"
    if 12 <= hour < 18:
        return "12_18"
    return "18_24"


def _split_for(value: pd.Timestamp, splits: dict[str, list[str]]) -> str | None:
    if pd.isna(value):
        return None
    value = pd.Timestamp(value)
    if value.tzinfo is None:
        value = value.tz_localize("UTC")
    else:
        value = value.tz_convert("UTC")
    for name, (start, end) in splits.items():
        if pd.Timestamp(start, tz="UTC") <= value < pd.Timestamp(end, tz="UTC"):
            return name
    return None


def _aircraft_group(typecode: Any) -> str:
    text = "" if pd.isna(typecode) else str(typecode).strip().upper()
    if not text:
        return "unknown"
    for group, prefixes in AIRCRAFT_PREFIX_GROUPS.items():
        if text.startswith(prefixes):
            return group
    return "other"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    if any(pd.isna(x) for x in (lat1, lon1, lat2, lon2)):
        return float("nan")
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _distance_bin(value: float, bins: list[float]) -> str:
    if not np.isfinite(value):
        return "UNKNOWN"
    for low, high in zip(bins[:-1], bins[1:]):
        if low <= value < high:
            return f"{int(low)}_{'INF' if high >= 1_000_000 else int(high)}"
    return "UNKNOWN"


def stable_flight_id(icao24: str, origin: str, destination: str, firstseen: pd.Timestamp, lastseen: pd.Timestamp) -> str:
    values = [
        normalize_icao24(icao24), normalize_airport(origin), normalize_airport(destination),
        pd.Timestamp(firstseen).isoformat(), pd.Timestamp(lastseen).isoformat(),
    ]
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()[:32]


def prepare_legs(
    flightlist: pd.DataFrame,
    aircraft: pd.DataFrame,
    airports: pd.DataFrame,
    complete_dates: set[pd.Timestamp],
    cfg: dict[str, Any],
) -> pd.DataFrame:
    frame = flightlist.copy().rename(columns={"firstseen": "firstseen_utc", "lastseen": "lastseen_utc"})
    frame["icao24"] = frame["icao24"].map(normalize_icao24)
    frame["origin"] = frame["origin"].map(normalize_airport)
    frame["destination"] = frame["destination"].map(normalize_airport)
    frame["observed_movement_time"] = (frame["lastseen_utc"] - frame["firstseen_utc"]).dt.total_seconds() / 60.0
    frame["split"] = frame["firstseen_utc"].map(lambda x: _split_for(x, cfg["splits"]))
    frame["firstseen_month"] = frame["firstseen_utc"].dt.month.astype("Int64")
    frame["firstseen_time_bin"] = frame["firstseen_utc"].map(_time_bin)
    frame["observation_date"] = frame["firstseen_utc"].dt.tz_convert("UTC").dt.normalize().dt.tz_localize(None)
    normalized_complete = {pd.Timestamp(x).normalize().tz_localize(None) if pd.Timestamp(x).tzinfo else pd.Timestamp(x).normalize() for x in complete_dates}
    frame["state_day_complete"] = frame["observation_date"].isin(normalized_complete)

    aircraft_columns = [
        column for column in ("icao24", "typecode", "registration")
        if column in aircraft.columns
    ]
    aircraft_map = (
        aircraft[aircraft_columns].drop_duplicates("icao24")
        if not aircraft.empty
        else pd.DataFrame(columns=["icao24", "typecode", "registration"])
    )
    frame = frame.merge(aircraft_map, on="icao24", how="left")
    if "registration" not in frame:
        frame["registration"] = pd.NA
    frame["aircraft_group"] = frame["typecode"].map(_aircraft_group)
    frame["aircraft_type_unknown"] = frame["aircraft_group"].eq("unknown")

    coords = airports[["airport", "airport_latitude", "airport_longitude"]].drop_duplicates("airport")
    origin_coords = coords.rename(columns={"airport": "origin", "airport_latitude": "origin_lat", "airport_longitude": "origin_lon"})
    destination_coords = coords.rename(columns={"airport": "destination", "airport_latitude": "destination_lat", "airport_longitude": "destination_lon"})
    frame = frame.merge(origin_coords, on="origin", how="left").merge(destination_coords, on="destination", how="left")
    frame["distance_km"] = [
        _haversine_km(a, b, c, d)
        for a, b, c, d in zip(frame["origin_lat"], frame["origin_lon"], frame["destination_lat"], frame["destination_lon"])
    ]
    frame["distance_bin"] = frame["distance_km"].map(lambda x: _distance_bin(x, cfg["references"]["distance_bins_km"]))
    regions = cfg["airports"]["regions"]
    frame["origin_region"] = frame["origin"].map(regions).fillna("UNKNOWN")
    frame["destination_region"] = frame["destination"].map(regions).fillna("UNKNOWN")
    frame["region_pair"] = frame["origin_region"] + "__" + frame["destination_region"]

    low, high = cfg["references"]["physical_movement_minutes"]
    required_complete = bool(cfg["validation"].get("require_complete_state_day", True))
    state_ok = frame["state_day_complete"] if required_complete else True
    eligible_airports = cfg["airports"]["core"] if cfg["validation"].get("strict_core_support", True) else cfg["airports"]["m1"]
    frame["candidate_episode"] = (
        frame["icao24"].str.len().eq(6)
        & frame["destination"].isin(eligible_airports)
        & frame["firstseen_utc"].notna()
        & frame["lastseen_utc"].notna()
        & (frame["lastseen_utc"] > frame["firstseen_utc"])
        & frame["observed_movement_time"].between(low, high, inclusive="both")
        & frame["split"].notna()
        & state_ok
    )
    frame["candidate_exclusion_reason"] = np.select(
        [
            ~frame["destination"].isin(eligible_airports),
            frame["firstseen_utc"].isna() | frame["lastseen_utc"].isna(),
            frame["lastseen_utc"] <= frame["firstseen_utc"],
            ~frame["observed_movement_time"].between(low, high, inclusive="both"),
            frame["split"].isna(),
            ~frame["state_day_complete"] if required_complete else pd.Series(False, index=frame.index),
        ],
        [
            "DESTINATION_OUTSIDE_COHORT", "INVALID_TIME", "NONPOSITIVE_DURATION",
            "PHYSICAL_RANGE_FAILURE", "OUTSIDE_FROZEN_SPLIT", "SOURCE_COVERAGE_GAP",
        ],
        default="",
    )
    frame["flight_id"] = [
        stable_flight_id(i, o, d, f, l) if pd.notna(f) and pd.notna(l) else None
        for i, o, d, f, l in zip(frame["icao24"], frame["origin"], frame["destination"], frame["firstseen_utc"], frame["lastseen_utc"])
    ]
    frame["episode_id"] = frame["flight_id"]
    duplicates = frame[frame["flight_id"].notna()].duplicated("flight_id", keep=False)
    if duplicates.any():
        identity = ["icao24", "origin", "destination", "firstseen_utc", "lastseen_utc", "observed_movement_time"]
        conflicts = frame.loc[duplicates].groupby("flight_id")[identity].nunique(dropna=False).max(axis=1).gt(1)
        if conflicts.any():
            raise ValueError(f"identity collision: {conflicts[conflicts].index[:5].tolist()}")
        frame = frame.drop_duplicates("flight_id", keep="first")
    return frame.reset_index(drop=True)


def build_episodes(legs: pd.DataFrame, movement_reference: Any, cfg: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, float]]:
    rows = []
    for _, row in legs.iterrows():
        record = row.to_dict()
        t_ref = np.nan
        level = ""
        cell = 0
        fallback = ""
        valid = bool(row["candidate_episode"])
        reason = str(row.get("candidate_exclusion_reason", "") or "")
        if valid:
            try:
                t_ref, level, cell, fallback = movement_reference.resolve(row)
                if not np.isfinite(t_ref) or t_ref <= 0:
                    raise ValueError("nonpositive reference")
            except Exception as exc:
                valid = False
                reason = f"T_REF_UNAVAILABLE:{exc}"
        record.update({
            "airport": row["destination"],
            "reference_movement_time": t_ref,
            "y_movement_raw": float(row["observed_movement_time"] - t_ref) if valid else np.nan,
            "reference_level_used": level,
            "reference_cell_size": cell,
            "reference_fallback_reason": fallback,
            "episode_valid": valid,
            "exclusion_reason": reason,
        })
        rows.append(record)
    full = pd.DataFrame(rows)
    training_y = pd.to_numeric(full.loc[(full["split"] == "train") & full["episode_valid"], "y_movement_raw"], errors="coerce").dropna()
    if training_y.empty:
        raise ValueError("no valid training outcomes for clipping")
    sensitivity = cfg["labels"]["sensitivity_transform"]
    low_q, high_q = sensitivity["clip_quantiles"]
    bounds = {
        "low_quantile": low_q, "high_quantile": high_q,
        "low": float(training_y.quantile(low_q)), "high": float(training_y.quantile(high_q)),
        "fit_split": sensitivity["fit_split"],
        "source_column": "y_movement_raw",
        "target_column": "y_movement_model",
        "role": "SENSITIVITY_ONLY",
        "transformation": sensitivity["method"],
    }
    full["y_movement_model"] = pd.to_numeric(full["y_movement_raw"], errors="coerce").clip(bounds["low"], bounds["high"])
    return full, bounds
