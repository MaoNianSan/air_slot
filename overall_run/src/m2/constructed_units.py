from __future__ import annotations

from typing import Mapping

from .contracts import ValuationContext
from .subitem_values import value_for


def subitem_units(quantities: Mapping[str, float | None], valuation: ValuationContext) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for name, quantity in quantities.items():
        result[name] = None if quantity is None else value_for(name, valuation) * max(float(quantity), 0.0)
    return result


def channel_units(units: Mapping[str, float | None]) -> dict[str, float | None]:
    channels = {"F": ("F_TURN", "F_WAIT", "F_PROPAGATION"), "P": ("P_DELAY", "P_CONNECTION", "P_CARE"), "R": ("R_GROUND", "R_TAXI", "R_SCARCITY")}
    result: dict[str, float | None] = {}
    for channel, names in channels.items():
        values = [units.get(name) for name in names]
        supported = [float(value) for value in values if value is not None]
        result[channel] = sum(supported) if supported else None
    return result
