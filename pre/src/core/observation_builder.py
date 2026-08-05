from __future__ import annotations

import pandas as pd

from ..state import StateStore
from .observation_flow import build_flow_observations
from .observation_state import build_state_observations
from .observation_weather import build_weather_observations


COMMON_COLUMNS = [
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
]

MEMBERSHIP_ONLY_COLUMNS = [
    "chain_episode_id",
    "request_start",
    "request_end",
    "interval_type",
    "split",
]


def _align(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    output = output.drop(
        columns=[column for column in MEMBERSHIP_ONLY_COLUMNS if column in output],
        errors="ignore",
    )
    for column in COMMON_COLUMNS:
        if column not in output:
            output[column] = pd.NA
    source_columns = [
        column
        for column in output.columns
        if column not in COMMON_COLUMNS
        and column not in {"raw_source_file", "raw_source_hash"}
    ]
    return output[COMMON_COLUMNS + source_columns].copy()


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
    for column in ["observation_time", "event_time", "availability_time"]:
        observations[column] = pd.to_datetime(observations[column], utc=True, errors="coerce")
    observations = observations.sort_values(
        ["source", "observation_date", "observation_time", "observation_id"],
        kind="mergesort",
    )
    return observations.reset_index(drop=True)
