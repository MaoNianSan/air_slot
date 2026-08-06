from __future__ import annotations

from typing import Mapping


def to_rmb(channel_units: Mapping[str, float | None], rates: Mapping[str, float]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for channel, value in channel_units.items():
        result[channel] = None if value is None else float(value) * float(rates.get(channel, 1.0))
    return result
