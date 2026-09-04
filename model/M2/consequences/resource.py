"""Operating/resource consequence projections."""

from .engine import native_quantities


def resource_quantities(scenario, context):
    return tuple(item for item in native_quantities(scenario, context) if item.component_id == "R_operating")


__all__ = ["resource_quantities"]
