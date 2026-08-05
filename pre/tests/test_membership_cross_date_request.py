from __future__ import annotations

import pandas as pd

from membership_test_data import state_observations, state_request
from src.core.observation_membership import build_observation_membership


def test_cross_date_request_reads_each_observation_partition_once() -> None:
    observations = state_observations(
        ["2022-05-02 23:55", "2022-05-03 00:05"]
    )
    requests = state_request(
        request_start=pd.Timestamp("2022-05-02 23:50", tz="UTC"),
        request_end=pd.Timestamp("2022-05-03 00:10", tz="UTC"),
    )
    result = build_observation_membership(observations, requests)
    assert len(result) == 2
    assert result["observation_id"].nunique() == 2
