from __future__ import annotations

import pandas as pd

from src.core.chain_builder import build_chains
from src.core.observation_requests import build_observation_requests
from core_fixtures import core_cfg, matched_flights


def test_observation_requests_use_chain_interval_without_ratio() -> None:
    cfg = core_cfg()
    episodes = build_chains(matched_flights(), cfg)
    requests = build_observation_requests(episodes, cfg)
    assert set(requests["source"]) == {"state", "weather", "flow"}
    assert not any("ratio" in column for column in requests.columns)
    expected = episodes.iloc[0].episode_start_time - pd.Timedelta(minutes=20)
    assert requests["request_start"].eq(expected).all()
    assert requests["request_end"].eq(episodes.iloc[0].episode_end_time).all()
