"""Decision-time and information-cutoff predicates owned by PRE."""

from __future__ import annotations

from datetime import datetime

from model.common.errors import ContractError


def information_cutoff_legal(
    *, event_time: datetime | None, availability_time: datetime | None, cutoff: datetime
) -> bool:
    """Return true only when both event and availability are known by cutoff."""
    if event_time is None or availability_time is None:
        return False
    for value in (event_time, availability_time, cutoff):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ContractError("PRE_CUTOFF_TIMEZONE_REQUIRED")
    return event_time <= cutoff and availability_time <= cutoff


__all__ = ["information_cutoff_legal"]
