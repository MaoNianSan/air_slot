"""Flight consequence projections."""

from .engine import native_quantities

_FLIGHT = frozenset({"F_continuity", "F_execution", "F_propagation"})


def flight_quantities(scenario, context):
    return tuple(item for item in native_quantities(scenario, context) if item.component_id in _FLIGHT)


__all__ = ["flight_quantities"]
