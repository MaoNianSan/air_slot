from __future__ import annotations

import math
from typing import Mapping

from .contracts import (
    ActivationStatus,
    AvailabilityStatus,
    FlightContext,
    M2ContractError,
    PassengerContext,
    ResourceContext,
    ValuationContext,
)
from .dependencies import SUBITEM_DEPENDENCIES
from .events import RuntimeEvents
from .rules import bounded_multiplier, continuous, excess, threshold


EXPECTED_RULE_TYPES = {
    "F_TURN": "EXCESS_ACCUMULATION",
    "F_WAIT": "CONTINUOUS_ACCUMULATION",
    "F_PROPAGATION": "CONTINUOUS_ACCUMULATION",
    "P_DELAY": "CONTINUOUS_ACCUMULATION",
    "P_CONNECTION": "EXCESS_ACCUMULATION",
    "P_CARE": "THRESHOLD_EVENT",
    "R_GROUND": "CONTINUOUS_ACCUMULATION",
    "R_TAXI": "CONTINUOUS_ACCUMULATION",
    "R_SCARCITY": "THRESHOLD_EVENT",
}


def _parameter(valuation: ValuationContext, subitem: str, name: str) -> float:
    try:
        value = float(valuation.rule_parameters[subitem][name])
    except (KeyError, TypeError, ValueError) as exc:
        raise M2ContractError(
            f"M2_RULE_PARAMETER_NOT_CONFIGURED:{subitem}:{name}"
        ) from exc
    if not math.isfinite(value):
        raise M2ContractError(f"M2_RULE_PARAMETER_INVALID:{subitem}:{name}")
    return value


def _rule_type(valuation: ValuationContext, subitem: str) -> None:
    actual = str(valuation.rule_parameters[subitem].get("rule_type", ""))
    if actual != EXPECTED_RULE_TYPES[subitem]:
        raise M2ContractError(
            f"M2_RULE_TYPE_MISMATCH:{subitem}:{actual}:{EXPECTED_RULE_TYPES[subitem]}"
        )


def _number(value: object, field: str) -> float:
    if value is None:
        raise M2ContractError(f"M2_SUBITEM_INPUT_CONTRACT_ERROR:{field}:MISSING")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise M2ContractError(
            f"M2_SUBITEM_INPUT_CONTRACT_ERROR:{field}:INVALID"
        ) from exc
    if not math.isfinite(result):
        raise M2ContractError(
            f"M2_SUBITEM_INPUT_CONTRACT_ERROR:{field}:NONFINITE"
        )
    return result


def _event(events: RuntimeEvents, name: str) -> float:
    status = events.event_status[name]
    if status not in {AvailabilityStatus.AVAILABLE, AvailabilityStatus.PROXY_AVAILABLE}:
        raise M2ContractError(
            f"M2_SUBITEM_INPUT_CONTRACT_ERROR:{name}:{status.value}"
        )
    return _number(events.event_value[name], name)


def _optional_event(events: RuntimeEvents, name: str) -> float | None:
    status = events.event_status[name]
    if status in {AvailabilityStatus.AVAILABLE, AvailabilityStatus.PROXY_AVAILABLE}:
        return _number(events.event_value[name], name)
    return None


def _multiplier(
    context_value: object,
    valuation: ValuationContext,
    subitem: str,
    field: str,
) -> float:
    return bounded_multiplier(
        _number(context_value, field),
        _parameter(valuation, subitem, "context_gamma"),
        _parameter(valuation, subitem, "context_multiplier_min"),
        _parameter(valuation, subitem, "context_multiplier_max"),
    )


def _is_active(active: Mapping[str, object], subitem: str) -> bool:
    status = active[subitem].status
    return status in {ActivationStatus.ACTIVE, ActivationStatus.PROXY_ACTIVE}


def build_quantities(
    events: RuntimeEvents,
    flight: FlightContext,
    passenger: PassengerContext,
    resource: ResourceContext,
    active: Mapping[str, object],
    valuation: ValuationContext,
) -> dict[str, float | None]:
    quantities = {name: None for name in SUBITEM_DEPENDENCIES}
    for subitem in quantities:
        if _is_active(active, subitem):
            _rule_type(valuation, subitem)

    if _is_active(active, "F_TURN"):
        quantities["F_TURN"] = excess(
            _event(events, "turn_deficit"),
            0.0,
            _multiplier(
                flight.continuity_exposure,
                valuation,
                "F_TURN",
                "continuity_exposure",
            ),
        )
    if _is_active(active, "F_WAIT"):
        quantities["F_WAIT"] = continuous(
            _event(events, "extra_offblock_wait"),
            _multiplier(
                flight.execution_window_pressure,
                valuation,
                "F_WAIT",
                "execution_window_pressure",
            ),
        )
    if _is_active(active, "F_PROPAGATION"):
        quantities["F_PROPAGATION"] = continuous(
            _event(events, "takeoff_delay"),
            _number(flight.downstream_leg_count, "downstream_leg_count"),
        )
    if _is_active(active, "P_DELAY"):
        quantities["P_DELAY"] = continuous(
            _event(events, "takeoff_delay"),
            _number(passenger.passenger_load_proxy, "passenger_load_proxy"),
        )
    if _is_active(active, "P_CONNECTION"):
        quantities["P_CONNECTION"] = excess(
            _event(events, "takeoff_delay"),
            _number(passenger.connection_slack, "connection_slack"),
            _multiplier(
                passenger.connection_pressure,
                valuation,
                "P_CONNECTION",
                "connection_pressure",
            ),
        )
    if _is_active(active, "P_CARE"):
        quantities["P_CARE"] = threshold(
            _event(events, "takeoff_delay"),
            _parameter(valuation, "P_CARE", "threshold_minutes"),
            _number(passenger.passenger_load_proxy, "passenger_load_proxy"),
        )
    if _is_active(active, "R_GROUND"):
        quantities["R_GROUND"] = continuous(
            _event(events, "extra_offblock_wait"),
            _multiplier(
                resource.ground_support_pressure,
                valuation,
                "R_GROUND",
                "ground_support_pressure",
            ),
        )
    if _is_active(active, "R_TAXI"):
        quantities["R_TAXI"] = continuous(
            _event(events, "extra_taxi_delay"),
            _multiplier(
                resource.airport_flow_pressure,
                valuation,
                "R_TAXI",
                "airport_flow_pressure",
            ),
        )
    if _is_active(active, "R_SCARCITY"):
        scarcity = _number(resource.resource_scarcity, "resource_scarcity")
        candidates: list[float] = []
        parameters = valuation.rule_parameters["R_SCARCITY"]
        wait = _optional_event(events, "extra_offblock_wait")
        if wait is not None and "wait_threshold_minutes" in parameters:
            candidates.append(
                threshold(
                    wait,
                    _parameter(
                        valuation, "R_SCARCITY", "wait_threshold_minutes"
                    ),
                    scarcity,
                )
            )
        taxi = _optional_event(events, "extra_taxi_delay")
        if taxi is not None and "taxi_threshold_minutes" in parameters:
            candidates.append(
                threshold(
                    taxi,
                    _parameter(
                        valuation, "R_SCARCITY", "taxi_threshold_minutes"
                    ),
                    scarcity,
                )
            )
        if not candidates:
            raise M2ContractError(
                "M2_SUBITEM_INPUT_CONTRACT_ERROR:R_SCARCITY:NO_CONFIGURED_TRIGGER"
            )
        quantities["R_SCARCITY"] = max(candidates)
    return quantities
