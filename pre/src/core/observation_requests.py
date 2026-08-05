from __future__ import annotations

from typing import Any

import pandas as pd

from ..input import object_hash
from .contracts import OBSERVATION_CONTRACT_ID, stable_id, utc_series


def build_observation_requests(
    episodes: pd.DataFrame, cfg: dict[str, Any]
) -> pd.DataFrame:
    history = pd.to_timedelta(cfg["state_vectors"]["lookback_minutes"], unit="m")
    rows: list[dict[str, Any]] = []
    eligibility = episodes["engineering_eligible"]
    eligible = episodes[eligibility.fillna(False).astype(bool)].copy()
    for episode in eligible.itertuples(index=False):
        start = pd.Timestamp(episode.episode_start_time) - history
        end = pd.Timestamp(episode.episode_end_time)
        interval_hash = object_hash(
            {
                "chain_episode_id": episode.chain_episode_id,
                "start": str(start),
                "end": str(end),
            }
        )
        for source in cfg["request_contract"]["sources"]:
            rows.append(
                {
                    "request_id": stable_id(
                        OBSERVATION_CONTRACT_ID, episode.chain_episode_id, source
                    ),
                    "chain_episode_id": episode.chain_episode_id,
                    "predecessor_flight_id": episode.predecessor_flight_id,
                    "successor_flight_id": episode.successor_flight_id,
                    "flight_id": episode.predecessor_flight_id,
                    "icao24": episode.aircraft_id,
                    "airport": episode.turnaround_airport,
                    "source": source,
                    "request_start": start,
                    "request_end": end,
                    "date": start.normalize().tz_localize(None),
                    "interval_type": cfg["request_contract"]["interval_type"],
                    "episode_interval_hash": interval_hash,
                    "episode_start_time": episode.episode_start_time,
                    "predecessor_lastseen_proxy": episode.predecessor_lastseen_proxy,
                    "successor_firstseen_proxy": episode.successor_firstseen_proxy,
                    "split": episode.split,
                }
            )
    requests = pd.DataFrame(rows)
    if requests.empty:
        return requests
    for column in [
        "request_start",
        "request_end",
        "episode_start_time",
        "predecessor_lastseen_proxy",
        "successor_firstseen_proxy",
    ]:
        requests[column] = utc_series(requests[column])
    return requests.sort_values(
        ["source", "request_start", "chain_episode_id"], kind="mergesort"
    ).reset_index(drop=True)


def observation_request_hashes(requests: pd.DataFrame) -> dict[str, str]:
    columns = ["chain_episode_id", "source", "request_start", "request_end"]
    payload = requests[columns].astype(str).to_dict("records") if not requests.empty else []
    intervals = (
        sorted(requests["episode_interval_hash"].dropna().astype(str).unique())
        if not requests.empty
        else []
    )
    return {
        "request_contract_hash": object_hash(
            {
                "id": OBSERVATION_CONTRACT_ID,
                "sources": sorted(requests["source"].astype(str).unique())
                if not requests.empty
                else [],
            }
        ),
        "episode_interval_hash": object_hash(intervals),
        "request_rows_hash": object_hash(payload),
    }
