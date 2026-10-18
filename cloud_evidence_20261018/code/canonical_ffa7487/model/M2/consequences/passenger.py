"""Passenger consequence projections."""

from .engine import native_quantities

_PASSENGER = frozenset({"P_time", "P_itinerary", "P_service"})


def passenger_quantities(scenario, context):
    return tuple(item for item in native_quantities(scenario, context) if item.component_id in _PASSENGER)


__all__ = ["passenger_quantities"]
