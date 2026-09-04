"""Canonical PRE availability boundary; implementation remains in factual lane."""

from model.PRE.factual.availability import (
    Data2FactualReplayAvailabilityPolicy,
    factual_availability_time,
    factual_replay_legal,
)

__all__ = [
    "Data2FactualReplayAvailabilityPolicy",
    "factual_availability_time",
    "factual_replay_legal",
]
