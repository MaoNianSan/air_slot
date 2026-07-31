from __future__ import annotations

import numpy as np
import pandas as pd

TIME_BINS = ["00_06", "06_12", "12_18", "18_24"]
WEATHER_FIELDS = [
    "wind_speed", "wind_gust", "visibility", "ceiling",
    "temperature_dewpoint_spread",
]
MOVEMENT_LEVELS = ["L1", "L2", "L3", "L4", "L5", "L6"]


def _normalize(value: float, low: float, high: float) -> float:
    if not np.isfinite(value) or not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return np.nan
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))


def _time_bin(value: pd.Timestamp) -> str:
    if pd.isna(value):
        return "UNKNOWN"
    hour = int(value.hour)
    return "00_06" if hour < 6 else "06_12" if hour < 12 else "12_18" if hour < 18 else "18_24"


