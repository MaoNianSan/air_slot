from __future__ import annotations

import pandas as pd

from ..state import StateStore
from .contracts import stable_id, utc_series


def _archive_lookup(inventory: pd.DataFrame) -> dict[tuple[str, int], tuple[str, str]]:
    state = inventory[inventory["source"].eq("state_vectors")].copy()
    state["date_key"] = pd.to_datetime(state["date"]).dt.strftime("%Y-%m-%d")
    result: dict[tuple[str, int], tuple[str, str]] = {}
    for row in state.itertuples(index=False):
        result[(row.date_key, int(row.hour))] = (str(row.absolute_path), str(row.sha256))
    return result


def build_flow_observations(
    requests: pd.DataFrame, store: StateStore, inventory: pd.DataFrame
) -> pd.DataFrame:
    flow_requests = requests[requests["source"].eq("flow")].copy()
    if flow_requests.empty:
        return pd.DataFrame()
    lookup = _archive_lookup(inventory)
    dates = pd.date_range(
        flow_requests["request_start"].min().normalize(),
        flow_requests["request_end"].max().normalize(),
        freq="D",
    )
    pieces: list[pd.DataFrame] = []
    for date in dates:
        day_start = pd.Timestamp(date)
        day_end = day_start + pd.Timedelta(days=1)
        day_requests = flow_requests[
            flow_requests["request_start"].lt(day_end)
            & flow_requests["request_end"].ge(day_start)
        ]
        for airport, relevant in day_requests.groupby("airport", sort=False):
            raw = store.load(
                "flow", date.tz_localize(None), hours=list(range(24)), airport=str(airport)
            )
            if raw.empty:
                continue
            raw["event_time"] = utc_series(raw["event_time"])
            raw["availability_time"] = utc_series(raw["availability_time"])
            counts = (
                raw.groupby(["event_time", "availability_time"], dropna=False)["icao24"]
                .nunique()
                .rename("flow_count")
                .reset_index()
            )
            selected_mask = pd.Series(False, index=counts.index)
            split_values = pd.Series(pd.NA, index=counts.index, dtype="string")
            for request in relevant.itertuples(index=False):
                mask = counts["event_time"].between(
                    request.request_start, request.request_end, inclusive="both"
                )
                selected_mask |= mask
                split_values.loc[mask] = request.split
            selected = counts.loc[selected_mask].copy()
            if selected.empty:
                continue
            selected["chain_episode_id"] = pd.NA
            selected["flight_id"] = pd.NA
            selected["source"] = "flow"
            selected["observation_time"] = selected["event_time"]
            selected["observation_date"] = selected["event_time"].dt.strftime("%Y-%m-%d")
            selected["airport_id"] = airport
            hours = selected["event_time"].dt.hour.astype(int)
            date_keys = selected["event_time"].dt.strftime("%Y-%m-%d")
            provenance = [lookup.get((day, hour), ("", "")) for day, hour in zip(date_keys, hours)]
            selected["source_file"] = [value[0] for value in provenance]
            selected["source_hash"] = [value[1] for value in provenance]
            selected["source_record_id"] = [
                f"FLOW_COUNT:{airport}:{timestamp.isoformat()}"
                for timestamp in selected["event_time"]
            ]
            selected["request_start"] = pd.NaT
            selected["request_end"] = pd.NaT
            selected["interval_type"] = "SOURCE_UNION_FOR_ON_DEMAND_JOIN"
            selected["split"] = split_values.loc[selected.index]
            selected["observation_id"] = [
                stable_id("flow", record_id) for record_id in selected["source_record_id"]
            ]
            pieces.append(selected)
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()
