"""Single source of truth for the signed M1 event-time semantics."""

from __future__ import annotations

from datetime import datetime
from typing import Final


FORMAL_FORECAST_HORIZONS_MINUTES: Final[tuple[int, ...]] = (0, 15, 60)
DELAY_THRESHOLDS_MINUTES: Final[tuple[int, ...]] = (15, 30, 60)
EVALUATION_ONLY_FORECAST_HORIZONS_MINUTES: Final[tuple[int, ...]] = (
    0, 30, 60, 120, 180, 240, 300, 360, 420, 480
)

M1_TARGET_SEMANTICS: Final[dict[str, dict[str, str]]] = {
    "R_IB": {
        "external_name": "predecessor_A00_in_block_time_distribution",
        "quantity": "predecessor in-block time remaining from decision time",
    },
    "DELTA_OB": {
        "external_name": "successor_signed_off_block_offset_distribution",
        "quantity": "successor actual off-block time minus CRS scheduled departure",
    },
    "T_TX": {
        "external_name": "successor_taxi_out_duration_distribution",
        "quantity": "successor taxi-out duration used in the takeoff event-time identity",
    },
    "R_OB": {
        "external_name": "successor_nonnegative_off_block_delay",
        "quantity": "derived max(0, DELTA_OB)",
    },
    "T_OB": {
        "external_name": "successor_off_block_event_time",
        "quantity": "scheduled departure plus DELTA_OB",
    },
    "T_TO": {
        "external_name": "successor_takeoff_event_time",
        "quantity": "T_OB plus T_TX",
    },
    "D_TO": {
        "external_name": "successor_total_takeoff_delay",
        "quantity": "max(0, DELTA_OB plus T_TX minus train-frozen taxi reference)",
    },
}


def derived_r_ob_minutes(delta_ob_minutes: float | None) -> float | None:
    return None if delta_ob_minutes is None else max(0.0, float(delta_ob_minutes))


def takeoff_event_time_minutes(t_ob_minutes: float | None, t_tx_minutes: float | None) -> float | None:
    if t_ob_minutes is None or t_tx_minutes is None:
        return None
    return float(t_ob_minutes) + float(t_tx_minutes)


def total_takeoff_delay_minutes(*, delta_ob_minutes: float | None = None,
                                t_tx_minutes: float | None,
                                taxi_reference_minutes: float | None,
                                t_ob_minutes: float | None = None,
                                scheduled_ob_minutes: float | None = None) -> float | None:
    """Return D3 total delay from the signed offset or equivalent event times."""
    if delta_ob_minutes is None and t_ob_minutes is not None and scheduled_ob_minutes is not None:
        delta_ob_minutes = float(t_ob_minutes) - float(scheduled_ob_minutes)
    if delta_ob_minutes is None or t_tx_minutes is None or taxi_reference_minutes is None:
        return None
    return max(
        0.0,
        float(delta_ob_minutes) + float(t_tx_minutes) - float(taxi_reference_minutes),
    )


def delay_from_event_times(t_ob: datetime | None, taxi_duration_minutes: float | None,
                           scheduled_ob: datetime | None, taxi_reference_minutes: float | None) -> float | None:
    if t_ob is None or taxi_duration_minutes is None or scheduled_ob is None or taxi_reference_minutes is None:
        return None
    delta_ob = (t_ob - scheduled_ob).total_seconds() / 60.0
    return total_takeoff_delay_minutes(
        delta_ob_minutes=delta_ob,
        t_tx_minutes=taxi_duration_minutes,
        taxi_reference_minutes=taxi_reference_minutes,
    )


def external_target_name(target_name: str) -> str:
    try:
        return M1_TARGET_SEMANTICS[target_name]["external_name"]
    except KeyError as exc:
        raise ValueError(f"UNKNOWN_M1_TARGET:{target_name}") from exc
