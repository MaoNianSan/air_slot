from __future__ import annotations

import math
from typing import Mapping


REQUIRED_CHANNELS = ("F", "P", "R")


def validate_currency_mapping(rates: Mapping[str, object]) -> None:
    if any(channel not in rates for channel in REQUIRED_CHANNELS):
        raise ValueError("M2_CURRENCY_MAPPING_INCOMPLETE")
    for channel in REQUIRED_CHANNELS:
        try:
            rate = float(rates[channel])
        except (TypeError, ValueError) as exc:
            raise ValueError("M2_CURRENCY_MAPPING_INCOMPLETE") from exc
        if not math.isfinite(rate) or rate < 0.0:
            raise ValueError("M2_CURRENCY_MAPPING_INCOMPLETE")


def to_rmb(
    channel_units: Mapping[str, float | None],
    rates: Mapping[str, object],
) -> dict[str, float | None]:
    validate_currency_mapping(rates)
    return {
        channel: (
            None if channel_units.get(channel) is None
            else float(channel_units[channel]) * float(rates[channel])
        )
        for channel in REQUIRED_CHANNELS
    }


def subitems_to_rmb(
    subitem_units: Mapping[str, float | None],
    rates: Mapping[str, object],
) -> dict[str, float | None]:
    validate_currency_mapping(rates)
    return {
        subitem: (
            None if value is None else float(value) * float(rates[subitem[0]])
        )
        for subitem, value in subitem_units.items()
    }
