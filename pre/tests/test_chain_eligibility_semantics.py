from __future__ import annotations

from core_fixtures import core_cfg, matched_flights
from src.core.chain_builder import build_chains


def test_observed_proxy_is_engineering_not_scientific_eligible() -> None:
    row = build_chains(matched_flights(), core_cfg()).iloc[0]
    assert bool(row.core_eligible)
    assert bool(row.engineering_eligible)
    assert not bool(row.scientific_chain_eligible)
    assert bool(row.core_eligible) == bool(row.engineering_eligible)
    assert {
        "core_eligible",
        "engineering_eligible",
        "scientific_chain_eligible",
    }.issubset(row.index)
