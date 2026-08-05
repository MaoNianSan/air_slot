from __future__ import annotations

from typing import Iterable

import pandas as pd


IDENTITY_COLUMNS = {
    "observation_id",
    "source",
    "observation_date",
    "observation_time",
    "event_time",
    "availability_time",
    "source_record_id",
    "source_file",
    "source_hash",
    "airport_id",
    "aircraft_id",
    "flight_id",
}


def available_observations(
    observations: pd.DataFrame,
    membership: pd.DataFrame,
    chain_episode_id: str,
    query_time: object,
) -> pd.DataFrame:
    query = pd.Timestamp(query_time)
    query = query.tz_localize("UTC") if query.tzinfo is None else query.tz_convert("UTC")
    linked = membership[
        membership["chain_episode_id"].astype(str).eq(str(chain_episode_id))
    ].copy()
    if "availability_supported" in linked:
        linked = linked[linked["availability_supported"].fillna(False).astype(bool)]
    joined = linked.merge(
        observations,
        on=["observation_id", "source"],
        how="inner",
        validate="many_to_one",
        suffixes=("_membership", ""),
    )
    if joined.empty:
        return joined
    joined["availability_time"] = pd.to_datetime(
        joined["availability_time"], utc=True, errors="coerce"
    )
    joined = joined[joined["availability_time"].le(query)].copy()
    joined["observation_age_minutes"] = (
        query - joined["availability_time"]
    ).dt.total_seconds() / 60.0
    return joined.sort_values(
        ["availability_time", "observation_id"], kind="mergesort"
    ).reset_index(drop=True)


def latest_values(
    frame: pd.DataFrame,
    allowed_columns: Iterable[str],
) -> dict[str, dict[str, object]]:
    allowed = [column for column in allowed_columns if column in frame.columns]
    selected: dict[str, dict[str, object]] = {}
    for column in allowed:
        valid = frame[frame[column].notna()]
        if valid.empty:
            continue
        row = valid.iloc[-1]
        selected[column] = {
            "value": row[column],
            "availability_time": row.get("availability_time"),
            "event_time": row.get("event_time"),
            "age_minutes": row.get("observation_age_minutes"),
            "source": row.get("source"),
            "source_hash": row.get("source_hash"),
            "membership_role": row.get("membership_role"),
        }
    return selected
