from __future__ import annotations

import pandas as pd

from ..state import StateStore
from .observation_flow import build_flow_observations
from .observation_state import build_state_observations
from .observation_weather import build_weather_observations


COMMON_COLUMNS = [
    "observation_id",
    "chain_episode_id",
    "flight_id",
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
    "latitude",
    "longitude",
    "altitude",
    "velocity",
    "vertical_rate",
    "heading",
    "onground",
    "wind_speed",
    "wind_gust",
    "visibility",
    "ceiling",
    "weather_code",
    "temperature",
    "dewpoint",
    "flow_count",
    "request_start",
    "request_end",
    "interval_type",
    "split",
]


def _align(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in COMMON_COLUMNS:
        if column not in output:
            output[column] = pd.NA
    return output[COMMON_COLUMNS]


def build_observations(
    requests: pd.DataFrame,
    store: StateStore,
    metar: pd.DataFrame,
    inventory: pd.DataFrame,
) -> pd.DataFrame:
    pieces = [
        build_state_observations(requests, store),
        build_weather_observations(requests, metar),
        build_flow_observations(requests, store, inventory),
    ]
    nonempty = [_align(frame) for frame in pieces if not frame.empty]
    if not nonempty:
        return pd.DataFrame(columns=COMMON_COLUMNS)
    observations = pd.concat(nonempty, ignore_index=True)
    for column in [
        "observation_time",
        "event_time",
        "availability_time",
        "request_start",
        "request_end",
    ]:
        observations[column] = pd.to_datetime(observations[column], utc=True, errors="coerce")
    observations = observations.sort_values(
        ["source", "observation_date", "chain_episode_id", "observation_time", "observation_id"],
        kind="mergesort",
    )
    return observations.reset_index(drop=True)
