from __future__ import annotations

import pandas as pd
import numpy as np

from ..state import StateStore
from .contracts import stable_id, utc_series


def _requests_on_date(requests: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame:
    start = pd.Timestamp(date)
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    end = start + pd.Timedelta(days=1)
    return requests[
        requests["request_start"].lt(end) & requests["request_end"].ge(start)
    ]


def _assign_requests(group: pd.DataFrame, requests: pd.DataFrame) -> pd.DataFrame:
    """Compatibility helper for legacy callers; Core V2 builders do not use it."""
    relevant = requests.sort_values("request_start", kind="mergesort").reset_index(drop=True)
    starts = relevant["request_start"].astype("int64").to_numpy()
    ends = relevant["request_end"].astype("int64").to_numpy()
    times = group["event_time"].astype("int64").to_numpy()
    positions = np.searchsorted(starts, times, side="right") - 1
    matched = positions >= 0
    matched[matched] &= times[matched] <= ends[positions[matched]]
    selected = group.loc[matched].copy()
    if selected.empty:
        return selected
    assigned = relevant.iloc[positions[matched]].reset_index(drop=True)
    selected = selected.reset_index(drop=True)
    selected["chain_episode_id"] = assigned["chain_episode_id"]
    selected["flight_id"] = assigned["predecessor_flight_id"].astype("string")
    after_predecessor = selected["event_time"].gt(assigned["predecessor_lastseen_proxy"])
    selected.loc[after_predecessor, "flight_id"] = pd.NA
    at_successor = selected["event_time"].ge(assigned["successor_firstseen_proxy"])
    selected.loc[at_successor, "flight_id"] = assigned.loc[at_successor, "successor_flight_id"]
    selected["request_start"] = assigned["request_start"]
    selected["request_end"] = assigned["request_end"]
    selected["interval_type"] = assigned["interval_type"]
    selected["split"] = assigned["split"]
    return selected


def _select_source_global(group: pd.DataFrame, requests: pd.DataFrame) -> pd.DataFrame:
    if group.empty or requests.empty:
        return group.iloc[0:0].copy()
    mask = np.zeros(len(group), dtype=bool)
    times = pd.to_datetime(group["event_time"], utc=True, errors="coerce")
    for request in requests.itertuples(index=False):
        mask |= times.between(
            request.request_start, request.request_end, inclusive="both"
        ).to_numpy()
    return group.loc[mask].drop_duplicates("source_record_id", keep="last").copy()


def build_state_observations(
    requests: pd.DataFrame, store: StateStore
) -> pd.DataFrame:
    requests = requests[requests["source"].eq("state")].copy()
    if requests.empty:
        return pd.DataFrame()
    dates = pd.date_range(
        requests["request_start"].min().normalize(),
        requests["request_end"].max().normalize(),
        freq="D",
    )
    pieces: list[pd.DataFrame] = []
    for date in dates:
        day_requests = _requests_on_date(requests, date)
        if day_requests.empty:
            continue
        states = store.load("candidate", date.tz_localize(None), hours=list(range(24)))
        if states.empty:
            continue
        states["event_time"] = utc_series(states["event_time"])
        states["availability_time"] = utc_series(states["availability_time"])
        for code, state_group in states.groupby("icao24", sort=False):
            relevant = day_requests[day_requests["icao24"].eq(str(code))]
            selected = _select_source_global(state_group, relevant)
            if selected.empty:
                continue
            selected["flight_id"] = pd.NA
            selected["source"] = "state"
            selected["observation_time"] = selected["event_time"]
            selected["observation_date"] = selected["event_time"].dt.strftime("%Y-%m-%d")
            selected["aircraft_id"] = selected["icao24"]
            selected["source_file"] = selected["raw_source_file"]
            selected["source_hash"] = selected["raw_source_hash"]
            selected["observation_id"] = [
                stable_id("state", record_id) for record_id in selected["source_record_id"]
            ]
            pieces.append(selected)
    if not pieces:
        return pd.DataFrame()
    return pd.concat(pieces, ignore_index=True).drop_duplicates(
        "observation_id", keep="last"
    )
