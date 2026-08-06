from __future__ import annotations

from .contracts import ValuationContext


def value_for(subitem: str, valuation: ValuationContext) -> float:
    if subitem not in valuation.subitem_value_parameters:
        raise ValueError(f"M2_VALUE_PARAMETER_NOT_CONFIGURED:{subitem}")
    value = float(valuation.subitem_value_parameters[subitem])
    if value < 0:
        raise ValueError(f"M2_VALUE_PARAMETER_INVALID:{subitem}")
    return value
