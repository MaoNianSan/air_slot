from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .contracts import EventName, SupportLevel, stable_id, utc_series


def _event_row(
    flight: pd.Series,
    event_name: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    spec = cfg["event_specs"][event_name]
    time_column = spec["time_column"]
    source_field = spec["source_field"]
    supported = time_column is not None and pd.notna(flight.get(time_column))
    lag = float(cfg["availability_lag_minutes"].get("completed_flightlist", 0))
    availability = (
        pd.Timestamp(flight["lastseen_utc"]) + pd.to_timedelta(lag, unit="m")
        if supported and pd.notna(flight.get("lastseen_utc"))
        else pd.NaT
    )
    return {
        "event_id": stable_id(flight["flight_id"], event_name),
        "flight_id": flight["flight_id"],
        "event_name": event_name,
        "event_time": flight.get(time_column) if supported else pd.NaT,
        "availability_time": availability,
        "source_type": "OPEN_SKY_FLIGHTLIST" if supported else "UNSUPPORTED",
        "source_field": source_field if supported else pd.NA,
        "support_level": spec["support_level"],
        "reconstruction_method": spec["reconstruction_method"],
        "confidence": 0.7 if supported else np.nan,
        "source_record_id": flight.get("source_record_id", pd.NA),
        "source_file": flight.get("raw_source_file", pd.NA),
        "source_hash": flight.get("raw_source_hash", pd.NA),
        "quality_flags": "[]" if supported else '["UNSUPPORTED_EVENT"]',
    }


def build_events(
    flights: pd.DataFrame, episodes: pd.DataFrame, cfg: dict[str, Any]
) -> pd.DataFrame:
    roles: list[tuple[str, list[str]]] = [
        (
            "predecessor_flight_id",
            [
                EventName.ATOT_MINUS.value,
                EventName.ALDT_MINUS.value,
                EventName.AIBT_MINUS.value,
            ],
        ),
        (
            "successor_flight_id",
            [EventName.AOBT_PLUS.value, EventName.ATOT_PLUS.value],
        ),
    ]
    indexed = flights.set_index("flight_id", drop=False)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for column, event_names in roles:
        for flight_id in episodes[column].dropna().astype(str).unique():
            if flight_id not in indexed.index:
                continue
            flight = indexed.loc[flight_id]
            if isinstance(flight, pd.DataFrame):
                flight = flight.iloc[0]
            for event_name in event_names:
                key = (flight_id, event_name)
                if key not in seen:
                    rows.append(_event_row(flight, event_name, cfg))
                    seen.add(key)
    events = pd.DataFrame(rows)
    if events.empty:
        return events
    for column in ("event_time", "availability_time"):
        events[column] = utc_series(events[column])
    return events.sort_values(["flight_id", "event_name"], kind="mergesort").reset_index(drop=True)
