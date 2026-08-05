from __future__ import annotations

import pandas as pd

from src.core.chain_builder import build_chains
from core_fixtures import core_cfg, flight


def test_chain_builder_preserves_tied_ambiguity() -> None:
    flights = pd.DataFrame(
        [
            flight("abc123", "EDDF", "EHAM", "2022-05-02 08:00", "2022-05-02 10:00", seed=True, record="pred"),
            flight("abc123", "EHAM", "LEMD", "2022-05-02 11:00", "2022-05-02 13:00", seed=False, record="succ1"),
            flight("abc123", "EHAM", "LEBL", "2022-05-02 11:00", "2022-05-02 13:30", seed=False, record="succ2"),
        ]
    )
    episodes = build_chains(flights, core_cfg())
    assert len(episodes) == 2
    assert episodes["chain_match_status"].eq("AMBIGUOUS").all()
    assert not episodes["engineering_eligible"].any()
