from __future__ import annotations

import pandas as pd

from src.core.contracts import stable_id
from src.core.membership import MEMBERSHIP_COLUMNS


def brute_force_membership(
    observations: pd.DataFrame, requests: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    for request in requests.itertuples(index=False):
        source_observations = observations[observations["source"].eq(request.source)]
        identity_column = "aircraft_id" if request.source == "state" else "airport_id"
        identity = request.icao24 if request.source == "state" else request.airport
        candidates = source_observations[
            source_observations[identity_column].astype("string").eq(str(identity))
            & pd.to_datetime(source_observations["event_time"], utc=True).between(
                request.request_start, request.request_end, inclusive="both"
            )
        ]
        for observation in candidates.itertuples(index=False):
            event_time = pd.Timestamp(observation.event_time)
            if request.source == "weather":
                role = "WEATHER_CONTEXT"
            elif request.source == "flow":
                role = "AIRPORT_CONTEXT"
            elif pd.notna(getattr(request, "episode_start_time", pd.NaT)) and event_time < request.episode_start_time:
                role = "PREDECESSOR_HISTORY"
            elif pd.notna(getattr(request, "predecessor_lastseen_proxy", pd.NaT)) and event_time <= request.predecessor_lastseen_proxy:
                role = "PREDECESSOR_ACTIVE"
            elif pd.notna(getattr(request, "successor_firstseen_proxy", pd.NaT)) and event_time < request.successor_firstseen_proxy:
                role = "TURNAROUND_CONTEXT"
            else:
                role = "SUCCESSOR_CONTEXT"
            available = bool(
                pd.notna(observation.availability_time)
                and observation.availability_time <= request.request_end
            )
            rows.append(
                {
                    "membership_id": stable_id(
                        request.chain_episode_id,
                        observation.observation_id,
                        request.interval_type,
                    ),
                    "chain_episode_id": request.chain_episode_id,
                    "observation_id": observation.observation_id,
                    "source": request.source,
                    "flight_id": getattr(observation, "flight_id", pd.NA),
                    "request_start": request.request_start,
                    "request_end": request.request_end,
                    "interval_type": request.interval_type,
                    "split": request.split,
                    "membership_role": role,
                    "availability_supported": available,
                    "membership_reason": (
                        "EVENT_IN_REQUEST_AND_IDENTITY_MATCH"
                        if available
                        else "EVENT_MATCHED_BUT_AVAILABLE_AFTER_REQUEST_END"
                    ),
                }
            )
    frame = pd.DataFrame(rows, columns=MEMBERSHIP_COLUMNS)
    if frame.empty:
        return frame
    return frame.drop_duplicates(
        ["chain_episode_id", "observation_id", "interval_type"], keep="last"
    ).sort_values(
        ["chain_episode_id", "source", "observation_id"], kind="mergesort"
    ).reset_index(drop=True)


def state_observations(times: list[str]) -> pd.DataFrame:
    rows = []
    for index, value in enumerate(times):
        timestamp = pd.Timestamp(value, tz="UTC")
        rows.append(
            {
                "observation_id": f"o{index}",
                "source": "state",
                "observation_date": timestamp.strftime("%Y-%m-%d"),
                "event_time": timestamp,
                "availability_time": timestamp,
                "aircraft_id": "abc123",
                "flight_id": pd.NA,
            }
        )
    return pd.DataFrame(rows)


def state_request(**overrides) -> pd.DataFrame:
    row = {
        "chain_episode_id": "c1",
        "source": "state",
        "icao24": "abc123",
        "request_start": pd.Timestamp("2022-05-02 09:00", tz="UTC"),
        "request_end": pd.Timestamp("2022-05-02 11:00", tz="UTC"),
        "interval_type": "INPUT_HISTORY_AND_ACTIVE_INTERVAL",
        "split": "train",
        "episode_start_time": pd.Timestamp("2022-05-02 10:00", tz="UTC"),
        "predecessor_lastseen_proxy": pd.Timestamp("2022-05-02 10:10", tz="UTC"),
        "successor_firstseen_proxy": pd.Timestamp("2022-05-02 10:20", tz="UTC"),
    }
    row.update(overrides)
    return pd.DataFrame([row])
