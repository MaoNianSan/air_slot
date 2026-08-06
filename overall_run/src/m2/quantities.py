from __future__ import annotations

from typing import Mapping

from .contracts import FlightContext, PassengerContext, ResourceContext, ValuationContext
from .events import RuntimeEvents
from .rules import bounded_multiplier, continuous, excess, threshold


def _parameter(valuation: ValuationContext, subitem: str, name: str) -> float:
    try:
        return float(valuation.rule_parameters[subitem][name])
    except KeyError as exc:
        raise ValueError(f"M2_RULE_PARAMETER_NOT_CONFIGURED:{subitem}:{name}") from exc


def build_quantities(events: RuntimeEvents, flight: FlightContext, passenger: PassengerContext, resource: ResourceContext, active: Mapping[str, object], valuation: ValuationContext) -> dict[str, float | None]:
    wait = events.extra_offblock_wait_minutes
    taxi = events.extra_taxi_minutes
    takeoff = events.takeoff_delay_minutes
    turn = events.turn_deficit_minutes
    quantities: dict[str, float | None] = {
        "F_TURN": excess(turn or 0.0, 0.0, max(flight.continuity_exposure, 1.0)) if active["F_TURN"].status.value in {"ACTIVE", "PROXY_ACTIVE"} else None,
        "F_WAIT": continuous(wait or 0.0, max(flight.execution_window_margin, 1.0)) if active["F_WAIT"].status.value in {"ACTIVE", "PROXY_ACTIVE"} else None,
        "F_PROPAGATION": continuous(takeoff or 0.0, max(flight.downstream_leg_count, 0.0)) if active["F_PROPAGATION"].status.value in {"ACTIVE", "PROXY_ACTIVE"} else None,
        "P_DELAY": continuous(takeoff or 0.0, passenger.passenger_load_proxy or 0.0) if active["P_DELAY"].status.value in {"ACTIVE", "PROXY_ACTIVE"} else None,
        "P_CONNECTION": excess(takeoff or 0.0, passenger.connection_slack or 0.0, passenger.connection_pressure or 0.0) if active["P_CONNECTION"].status.value in {"ACTIVE", "PROXY_ACTIVE"} else None,
        "P_CARE": threshold(takeoff or 0.0, _parameter(valuation, "P_CARE", "threshold_minutes"), passenger.passenger_load_proxy or 0.0) if active["P_CARE"].status.value in {"ACTIVE", "PROXY_ACTIVE"} else None,
        "R_GROUND": continuous(wait or 0.0, bounded_multiplier(resource.ground_support_pressure or 0.0, _parameter(valuation, "R_GROUND", "context_gamma"))) if active["R_GROUND"].status.value in {"ACTIVE", "PROXY_ACTIVE"} else None,
        "R_TAXI": continuous(taxi or 0.0, bounded_multiplier(resource.airport_flow_pressure or 0.0, _parameter(valuation, "R_TAXI", "context_gamma"))) if active["R_TAXI"].status.value in {"ACTIVE", "PROXY_ACTIVE"} else None,
        "R_SCARCITY": threshold(wait or 0.0, _parameter(valuation, "R_SCARCITY", "wait_threshold_minutes"), resource.resource_availability or 0.0) if active["R_SCARCITY"].status.value in {"ACTIVE", "PROXY_ACTIVE"} else None,
    }
    return quantities
