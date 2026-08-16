"""Single source of truth for the external M1 delay semantics."""

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
    "R_OB": {
        "external_name": "successor_off_block_delay_distribution",
        "quantity": "successor additional off-block delay beyond schedule",
    },
    "T_TX": {
        "external_name": "successor_taxi_out_duration_distribution",
        "quantity": "successor taxi-out duration used in the takeoff event-time identity",
    },
    "D_TO": {
        "external_name": "successor_total_takeoff_delay_distribution",
        "quantity": "successor total takeoff delay",
    },
}


def takeoff_event_time_minutes(t_ob_minutes: float | None, t_tx_minutes: float | None) -> float | None:
    """Return event-time identity ``T_TO = T_OB + T_TX``."""
    if t_ob_minutes is None or t_tx_minutes is None:
        return None
    return float(t_ob_minutes) + float(t_tx_minutes)


def total_takeoff_delay_minutes(*, t_ob_minutes: float | None, t_tx_minutes: float | None,
                                scheduled_ob_minutes: float | None = None,
                                taxi_reference_minutes: float | None = None) -> float | None:
    """Derive ``D_TO`` from event time and its own reference terms.

    With explicit references this is the V5 definition. The no-reference fallback is retained only
    for legacy fixture rows and is never a claim that delay components are additively identical.
    """
    event_time = takeoff_event_time_minutes(t_ob_minutes, t_tx_minutes)
    if event_time is None:
        return None
    if scheduled_ob_minutes is None or taxi_reference_minutes is None:
        return event_time
    return max(0.0, event_time - (float(scheduled_ob_minutes) + float(taxi_reference_minutes)))


def takeoff_delay_minutes(r_ob_minutes: float | None, t_tx_minutes: float | None) -> float | None:
    """Legacy additive fixture helper; forbidden in V5 formal/evaluation code."""
    if r_ob_minutes is None or t_tx_minutes is None:
        return None
    return float(r_ob_minutes) + float(t_tx_minutes)


def delay_from_event_times(t_ob: datetime | None, taxi_duration_minutes: float | None,
                           scheduled_ob: datetime | None, taxi_reference_minutes: float | None) -> float | None:
    """Clock-time V5 ``D_TO`` helper used by formal artifact adapters."""
    if t_ob is None or taxi_duration_minutes is None or scheduled_ob is None or taxi_reference_minutes is None:
        return None
    event_minutes = (t_ob - scheduled_ob).total_seconds() / 60.0 + float(taxi_duration_minutes)
    return max(0.0, event_minutes - float(taxi_reference_minutes))


def external_target_name(target_name: str) -> str:
    try:
        return M1_TARGET_SEMANTICS[target_name]["external_name"]
    except KeyError as exc:
        raise ValueError(f"UNKNOWN_M1_TARGET:{target_name}") from exc
