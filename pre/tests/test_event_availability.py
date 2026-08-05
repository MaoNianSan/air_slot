from __future__ import annotations

from src.core.chain_builder import build_chains
from src.core.event_builder import build_events
from core_fixtures import core_cfg, matched_flights


def test_completed_flight_event_availability_is_lastseen() -> None:
    cfg = core_cfg()
    flights = matched_flights()
    events = build_events(flights, build_chains(flights, cfg), cfg)
    predecessor = flights.iloc[0]
    atot = events[
        events["flight_id"].eq(predecessor.flight_id)
        & events["event_name"].eq("ATOT_MINUS")
    ].iloc[0]
    assert atot.event_time == predecessor.firstseen_utc
    assert atot.availability_time == predecessor.lastseen_utc
    assert str(atot.event_time.tzinfo) == "UTC"
