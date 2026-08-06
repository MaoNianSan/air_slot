from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .contracts import FlightContext


@dataclass(frozen=True)
class RuntimeEvents:
    turn_deficit_minutes: float | None
    turn_deficit_semantics: str
    extra_offblock_wait_minutes: float | None
    extra_taxi_minutes: float | None
    takeoff_delay_minutes: float | None


def build_events(sample: object, flight: FlightContext) -> RuntimeEvents:
    r_ib = getattr(sample, "r_ib_minutes", None)
    r_ob = getattr(sample, "r_ob_minutes", None)
    taxi = getattr(sample, "extra_taxi_delay", None)
    takeoff = getattr(sample, "total_takeoff_delay", None)
    semantics = "OFFICIAL_FLOOR" if flight.turnaround_reference_type == "OFFICIAL_FLOOR" else "PROXY"
    deficit = None
    inblock = getattr(sample, "T_predecessor_inblock", None)
    if inblock is not None and flight.turnaround_reference_minutes is not None and flight.successor_sobt is not None:
        required = inblock + timedelta(minutes=float(flight.turnaround_reference_minutes))
        deficit = max((required - flight.successor_sobt).total_seconds() / 60.0, 0.0)
    return RuntimeEvents(deficit, semantics, r_ob, taxi, takeoff)
