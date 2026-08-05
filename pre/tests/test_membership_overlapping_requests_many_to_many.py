from __future__ import annotations

import pandas as pd

from membership_test_data import state_observations, state_request
from src.core.observation_membership import build_observation_membership


def test_overlapping_requests_create_many_to_many_membership() -> None:
    observations = state_observations(["2022-05-02 10:00"])
    requests = pd.concat(
        [state_request(), state_request(chain_episode_id="c2", split="test")],
        ignore_index=True,
    )
    result = build_observation_membership(observations, requests)
    assert len(result) == 2
    assert set(result["chain_episode_id"]) == {"c1", "c2"}
