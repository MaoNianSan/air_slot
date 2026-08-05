from __future__ import annotations

import pandas as pd

from membership_test_data import brute_force_membership, state_observations, state_request
from src.core.membership import interval_join_partition


def test_interval_join_matches_brute_force_reference() -> None:
    observations = state_observations(
        ["2022-05-02 09:30", "2022-05-02 10:05", "2022-05-02 10:25"]
    )
    observations.loc[2, "availability_time"] = pd.Timestamp(
        "2022-05-02 11:30", tz="UTC"
    )
    requests = pd.concat(
        [
            state_request(),
            state_request(
                chain_episode_id="c2",
                request_start=pd.Timestamp("2022-05-02 10:00", tz="UTC"),
                split="validation",
            ),
        ],
        ignore_index=True,
    )
    actual = interval_join_partition(
        observations, requests, source="state", observation_date="2022-05-02"
    )
    expected = brute_force_membership(observations, requests)
    columns = [
        "membership_id", "chain_episode_id", "observation_id",
        "membership_role", "availability_supported", "split",
    ]
    pd.testing.assert_frame_equal(actual[columns], expected[columns], check_dtype=False)
