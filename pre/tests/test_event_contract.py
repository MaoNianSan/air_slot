from __future__ import annotations

from src.core.chain_builder import build_chains
from src.core.event_builder import build_events
from src.core.event_validation import validate_events
from core_fixtures import core_cfg, matched_flights


def test_event_contract_proxy_and_unsupported_facts() -> None:
    cfg = core_cfg()
    flights = matched_flights()
    events = build_events(flights, build_chains(flights, cfg), cfg)
    result = validate_events(events)
    assert result["status"] == "PASS"
    assert result["official_proxy_confusion"] == 0
    unsupported = events[events["support_level"].eq("UNSUPPORTED")]
    assert unsupported["event_time"].isna().all()
    assert not unsupported["event_time"].eq(0).any()
