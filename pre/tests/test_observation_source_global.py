from __future__ import annotations

import pandas as pd

from src.core.observation_builder import _align
from src.core.observation_weather import build_weather_observations
from src.core.observations import validate_observations


def _requests() -> pd.DataFrame:
    common = {
        "airport": "EHAM",
        "source": "weather",
        "request_start": pd.Timestamp("2022-05-02 09:00", tz="UTC"),
        "request_end": pd.Timestamp("2022-05-02 12:00", tz="UTC"),
        "interval_type": "INPUT_HISTORY_AND_ACTIVE_INTERVAL",
        "split": "train",
    }
    return pd.DataFrame(
        [
            {**common, "chain_episode_id": "c1"},
            {
                **common,
                "chain_episode_id": "c2",
                "request_start": pd.Timestamp("2022-05-02 09:30", tz="UTC"),
                "request_end": pd.Timestamp("2022-05-02 12:30", tz="UTC"),
            },
        ]
    )


def test_observation_is_source_global_and_split_neutral() -> None:
    metar = pd.DataFrame(
        [
            {
                "airport": "EHAM",
                "observation_time": pd.Timestamp("2022-05-02 10:00", tz="UTC"),
                "availability_time": pd.Timestamp("2022-05-02 10:00", tz="UTC"),
                "source_record_id": "metar:1",
                "raw_source_file": "metar.csv",
                "raw_source_hash": "a" * 64,
            }
        ]
    )
    observations = _align(build_weather_observations(_requests(), metar))
    assert len(observations) == 1
    forbidden = {
        "chain_episode_id",
        "request_start",
        "request_end",
        "interval_type",
        "split",
    }
    assert not forbidden.intersection(observations.columns)
    for column in ["observation_time", "event_time", "availability_time"]:
        observations[column] = pd.to_datetime(
            observations[column], utc=True, errors="coerce"
        )
    assert validate_observations(observations)["status"] == "PASS"
