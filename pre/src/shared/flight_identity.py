from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

from ..input import normalize_airport, normalize_icao24


AIRCRAFT_PREFIX_GROUPS = {
    "narrow_body": ("A31", "A32", "B73", "B38", "B39", "E19", "BCS"),
    "wide_body": ("A33", "A34", "A35", "A38", "B74", "B75", "B76", "B77", "B78"),
    "regional": ("AT4", "AT7", "CRJ", "DH8", "E17", "E18", "F70", "F10"),
    "turboprop": ("AT", "DH", "SF3", "JS3"),
}


def time_bin(value: pd.Timestamp) -> str:
    if pd.isna(value):
        return "UNKNOWN"
    hour = int(value.hour)
    if hour < 6:
        return "00_06"
    if hour < 12:
        return "06_12"
    if hour < 18:
        return "12_18"
    return "18_24"


def split_for(value: pd.Timestamp, splits: dict[str, list[str]]) -> str | None:
    if pd.isna(value):
        return None
    timestamp = pd.Timestamp(value)
    timestamp = (
        timestamp.tz_localize("UTC")
        if timestamp.tzinfo is None
        else timestamp.tz_convert("UTC")
    )
    for name, (start, end) in splits.items():
        if pd.Timestamp(start, tz="UTC") <= timestamp < pd.Timestamp(end, tz="UTC"):
            return name
    return None


def aircraft_group(typecode: Any) -> str:
    text = "" if pd.isna(typecode) else str(typecode).strip().upper()
    if not text:
        return "unknown"
    for group, prefixes in AIRCRAFT_PREFIX_GROUPS.items():
        if text.startswith(prefixes):
            return group
    return "other"


def stable_flight_id(
    icao24: str,
    origin: str,
    destination: str,
    firstseen: pd.Timestamp,
    lastseen: pd.Timestamp,
) -> str:
    values = [
        normalize_icao24(icao24),
        normalize_airport(origin),
        normalize_airport(destination),
        pd.Timestamp(firstseen).isoformat(),
        pd.Timestamp(lastseen).isoformat(),
    ]
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()[:32]
