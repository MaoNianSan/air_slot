from __future__ import annotations

import pandas as pd

from src.core.observation_state import _assign_requests
from src.core.observation_weather import build_weather_observations
from src.core.observation_builder import _align
from src.core.observation_validation import validate_observations


def _requests(source: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "chain_episode_id": "c1",
                "predecessor_flight_id": "p1",
                "successor_flight_id": "s1",
                "icao24": "abc123",
                "airport": "EHAM",
                "source": source,
                "request_start": pd.Timestamp("2022-05-02 09:00", tz="UTC"),
                "request_end": pd.Timestamp("2022-05-02 12:00", tz="UTC"),
                "predecessor_lastseen_proxy": pd.Timestamp("2022-05-02 10:00", tz="UTC"),
                "successor_firstseen_proxy": pd.Timestamp("2022-05-02 11:00", tz="UTC"),
                "interval_type": "INPUT_HISTORY_AND_ACTIVE_INTERVAL",
                "split": "train",
            },
            {
                "chain_episode_id": "c2",
                "predecessor_flight_id": "p2",
                "successor_flight_id": "s2",
                "icao24": "def456",
                "airport": "EHAM",
                "source": source,
                "request_start": pd.Timestamp("2022-05-02 09:30", tz="UTC"),
                "request_end": pd.Timestamp("2022-05-02 12:30", tz="UTC"),
                "predecessor_lastseen_proxy": pd.Timestamp("2022-05-02 10:30", tz="UTC"),
                "successor_firstseen_proxy": pd.Timestamp("2022-05-02 11:30", tz="UTC"),
                "interval_type": "INPUT_HISTORY_AND_ACTIVE_INTERVAL",
                "split": "train",
            },
        ]
    )


def test_weather_record_is_not_duplicated_across_chains() -> None:
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
    observations = build_weather_observations(_requests("weather"), metar)
    assert len(observations) == 1
    assert pd.isna(observations.iloc[0].chain_episode_id)
    aligned = _align(observations)
    for column in ["observation_time", "event_time", "availability_time", "request_start", "request_end"]:
        aligned[column] = pd.to_datetime(aligned[column], utc=True, errors="coerce")
    assert validate_observations(aligned)["status"] == "PASS"


def test_state_record_gets_one_interval_assignment() -> None:
    states = pd.DataFrame(
        [
            {"event_time": pd.Timestamp("2022-05-02 09:45", tz="UTC")},
            {"event_time": pd.Timestamp("2022-05-02 10:30", tz="UTC")},
        ]
    )
    assigned = _assign_requests(states, _requests("state").iloc[[0]])
    assert len(assigned) == 2
    assert assigned["chain_episode_id"].eq("c1").all()
    assert assigned["flight_id"].isna().iloc[1]
