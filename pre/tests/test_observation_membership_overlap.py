from __future__ import annotations

import pandas as pd

from src.core.membership import build_membership


def test_observation_can_belong_to_overlapping_chains() -> None:
    observation = pd.DataFrame([{
        "observation_id": "o1", "source": "weather", "airport_id": "EHAM",
        "aircraft_id": pd.NA, "flight_id": pd.NA,
        "event_time": pd.Timestamp("2022-05-02 10:00", tz="UTC"),
        "availability_time": pd.Timestamp("2022-05-02 10:00", tz="UTC"),
    }])
    requests = pd.DataFrame([
        {"chain_episode_id": chain, "source": "weather", "airport": "EHAM", "icao24": code,
         "request_start": pd.Timestamp("2022-05-02 09:00", tz="UTC"),
         "request_end": pd.Timestamp("2022-05-02 11:00", tz="UTC"),
         "interval_type": "INPUT_HISTORY_AND_ACTIVE_INTERVAL", "split": split}
        for chain, code, split in [("c1", "abc123", "train"), ("c2", "def456", "validation")]
    ])
    membership = build_membership(observation, requests)
    assert len(membership) == 2
    assert set(membership["chain_episode_id"]) == {"c1", "c2"}
