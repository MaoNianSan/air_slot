from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class EventTimeResult:
    event_time: pd.Timestamp | None
    event_type: str
    evidence_tier: str
    confidence: float
    uncertainty_seconds: float
    airport: str | None
    source_fields: tuple[str, ...] = ()
    source_files: tuple[str, ...] = ()
    rule_id: str = ""
    quality_flags: tuple[str, ...] = ()
    is_supported: bool = False


class FlightEventTimeProvider(Protocol):
    def infer_departure_event(
        self,
        states: pd.DataFrame,
        airport: str | None,
        fallback_time: pd.Timestamp | None,
    ) -> EventTimeResult: ...

    def infer_arrival_event(
        self,
        states: pd.DataFrame,
        airport: str | None,
        fallback_time: pd.Timestamp | None,
    ) -> EventTimeResult: ...


class ScheduleTimeProvider(Protocol):
    def planned_departure(self, flight_key: str) -> EventTimeResult: ...

    def planned_arrival(self, flight_key: str) -> EventTimeResult: ...


class OperationalEventProvider(Protocol):
    def official_departure(self, flight_key: str) -> EventTimeResult: ...

    def official_arrival(self, flight_key: str) -> EventTimeResult: ...


class AircraftRotationProvider(Protocol):
    def planned_successor(self, flight_key: str) -> str | None: ...


class FlightIdentityResolver(Protocol):
    def resolve(self, source_record: dict[str, object]) -> str | None: ...


@dataclass(frozen=True)
class AirportPoint:
    airport: str
    latitude: float
    longitude: float
    elevation_m: float


@dataclass
class EventProviderContext:
    airports: dict[str, AirportPoint] = field(default_factory=dict)

