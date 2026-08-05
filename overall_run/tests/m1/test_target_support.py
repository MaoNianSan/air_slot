from __future__ import annotations

import pandas as pd

from overall_run.src.m1.adapter.target_builder import build_target_contracts, target_values


def test_target_support_and_preserved_event_evidence(published_bundle) -> None:
    episode = published_bundle.episodes.iloc[0]
    contracts = build_target_contracts(episode, published_bundle.events)
    assert set(contracts) == {"R_IB", "R_OB", "T_TX"}
    assert all(contract.active for contract in contracts.values())
    assert contracts["R_OB"].m1_support_level == "OFFICIAL_OPERATIONAL"
    assert contracts["R_OB"].event_details["AIBT_MINUS"]["reconstruction_method"] == "DIRECT"
    values = target_values(episode, published_bundle.events, "2026-01-01T10:00:00Z")
    assert values == {"R_IB": 30.0, "R_OB": 10.0, "T_TX": 20.0}


def test_missing_schedule_field_deactivates_target(published_bundle) -> None:
    episode = published_bundle.episodes.iloc[0].copy()
    episode["successor_sobt"] = pd.NaT
    contract = build_target_contracts(episode, published_bundle.events)["R_OB"]
    assert contract.active is False
    assert contract.m1_support_level == "UNSUPPORTED"
    assert contract.inactive_reason
