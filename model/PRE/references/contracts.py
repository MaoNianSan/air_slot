"""Typed PRE reference bundle boundary consumed by M1/M2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PREReferenceContracts:
    """Named reference objects; no formulas or downstream consequence logic."""

    turnaround: Any
    taxi: Any
    downstream_exposure: Any
    passenger_load: Any | None = None
    connection_share: Any | None = None

    def objects(self) -> tuple[Any, ...]:
        return tuple(
            item
            for item in (
                self.turnaround,
                self.taxi,
                self.downstream_exposure,
                self.passenger_load,
                self.connection_share,
            )
            if item is not None
        )


__all__ = ["PREReferenceContracts"]
