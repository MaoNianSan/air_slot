from __future__ import annotations

import pytest

from overall_run.src.m1.adapter.stage_builder import flight_chain_stage, state_reset_required
from overall_run.src.m1.contracts import FlightChainStage


@pytest.mark.parametrize(
    ("query_time", "expected"),
    [
        ("2026-01-01T10:20:00Z", FlightChainStage.PREDECESSOR_ENROUTE),
        ("2026-01-01T10:22:00Z", FlightChainStage.PREDECESSOR_GROUND),
        ("2026-01-01T10:32:00Z", FlightChainStage.TURNAROUND),
        ("2026-01-01T11:12:00Z", FlightChainStage.SUCCESSOR_TAXI),
        ("2026-01-01T11:32:00Z", FlightChainStage.COMPLETED),
    ],
)
def test_stage_transitions_use_availability_time(published_bundle, query_time, expected) -> None:
    episode = published_bundle.episodes.iloc[0]
    assert flight_chain_stage(episode, published_bundle.events, query_time) is expected


def test_reset_reasons_are_explicit() -> None:
    assert state_reset_required("old", "new")
    assert state_reset_required("ep", "ep", aircraft_swap_terminal=True)
    assert state_reset_required("ep", "ep", model_compatible=False)
    assert not state_reset_required("ep", "ep")
