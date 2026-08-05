from __future__ import annotations

from src.core.chain_builder import build_chains
from src.core.chain_validation import validate_chains
from core_fixtures import core_cfg, matched_flights


def test_chain_builder_matches_immediate_continuous_leg() -> None:
    episodes = build_chains(matched_flights(), core_cfg())
    assert len(episodes) == 1
    row = episodes.iloc[0]
    assert row.chain_match_status == "MATCHED"
    assert row.chain_support_level == "OBSERVED_CHAIN_PROXY"
    assert bool(row.formal_eligible)
    assert validate_chains(episodes)["status"] == "PASS"
