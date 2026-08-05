from __future__ import annotations

import pandas as pd

from core_fixtures import core_cfg, flight
from src.core.chain_builder import build_chains


def test_chain_search_skips_invalid_earliest_candidate() -> None:
    flights = pd.DataFrame([
        flight("abc123", "EDDF", "EHAM", "2022-05-02 08:00", "2022-05-02 10:00", seed=True, record="pred"),
        flight("abc123", "EDDM", "LEMD", "2022-05-02 11:00", "2022-05-02 13:00", seed=False, record="invalid"),
        flight("abc123", "EHAM", "LEBL", "2022-05-02 12:00", "2022-05-02 14:00", seed=False, record="valid"),
    ])
    episodes = build_chains(flights, core_cfg())
    assert len(episodes) == 1
    assert episodes.iloc[0].successor_source_record_id == "valid"
    audit = episodes.attrs["candidate_rejections"]
    assert audit.iloc[0].rejection_reason == "AIRPORT_DISCONTINUITY"

