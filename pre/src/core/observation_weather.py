from __future__ import annotations

import pandas as pd

from .contracts import stable_id, utc_series


def build_weather_observations(
    requests: pd.DataFrame, metar: pd.DataFrame
) -> pd.DataFrame:
    weather_requests = requests[requests["source"].eq("weather")]
    if weather_requests.empty or metar.empty:
        return pd.DataFrame()
    frame = metar.copy()
    frame["observation_time"] = utc_series(frame["observation_time"])
    frame["availability_time"] = utc_series(frame["availability_time"])
    pieces: list[pd.DataFrame] = []
    for airport, group in frame.groupby("airport", sort=False):
        relevant = weather_requests[weather_requests["airport"].eq(str(airport))]
        if relevant.empty:
            continue
        selected_mask = pd.Series(False, index=group.index)
        split_values = pd.Series(pd.NA, index=group.index, dtype="string")
        for request in relevant.itertuples(index=False):
            mask = group["observation_time"].between(
                request.request_start, request.request_end, inclusive="both"
            )
            selected_mask |= mask
            split_values.loc[mask] = request.split
        selected = group.loc[selected_mask].copy()
        if selected.empty:
            continue
        selected["chain_episode_id"] = pd.NA
        selected["flight_id"] = pd.NA
        selected["source"] = "weather"
        selected["event_time"] = selected["observation_time"]
        selected["observation_date"] = selected["observation_time"].dt.strftime("%Y-%m-%d")
        selected["airport_id"] = selected["airport"]
        selected["source_file"] = selected["raw_source_file"]
        selected["source_hash"] = selected["raw_source_hash"]
        selected["request_start"] = pd.NaT
        selected["request_end"] = pd.NaT
        selected["interval_type"] = "SOURCE_UNION_FOR_ON_DEMAND_JOIN"
        selected["split"] = split_values.loc[selected.index]
        selected["observation_id"] = [
            stable_id("weather", record_id) for record_id in selected["source_record_id"]
        ]
        pieces.append(selected)
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()
