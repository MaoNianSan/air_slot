from __future__ import annotations

import pandas as pd

from src.core.chain_builder import build_chains
from core_fixtures import core_cfg, flight


def test_chain_split_uses_episode_start_not_successor_time() -> None:
    flights = pd.DataFrame(
        [
            flight("abc123", "EDDF", "EHAM", "2022-05-16 22:00", "2022-05-16 23:00", seed=True, record="pred"),
            flight("abc123", "EHAM", "LEMD", "2022-05-17 00:30", "2022-05-17 02:00", seed=False, record="succ"),
        ]
    )
    episode = build_chains(flights, core_cfg()).iloc[0]
    assert episode.split == "train"
