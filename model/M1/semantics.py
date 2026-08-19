"""Single source of truth for M1 event-time semantics.

Formal successor contract (manuscript reconciliation 2026-08-19):

    D_OB >= 0      successor off-block delay  = max(0, DELTA_OB)
    D_TX >= 0      successor excess taxi delay = max(0, T_TX - taxi_reference)
    D_TO = D_OB + D_TX   (per-scenario identity, not a separately trained head)

``DELTA_OB`` and ``T_TX`` remain internal predictive auxiliaries; downstream
M2/M4 may only consume the formal scenario contract fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final


FORMAL_FORECAST_HORIZONS_MINUTES: Final[tuple[int, ...]] = (0, 15, 60)
DELAY_THRESHOLDS_MINUTES: Final[tuple[int, ...]] = (15, 30, 60)
EVALUATION_ONLY_FORECAST_HORIZONS_MINUTES: Final[tuple[int, ...]] = (
    0, 30, 60, 120, 180, 240, 300, 360, 420, 480
)

# Formal M1 output contract: predecessor in-block (R_IB / T_IB_A00) plus the
# nonnegative successor delay pair; D_TO is always derived from D_OB + D_TX.
M1_FORMAL_TARGETS: Final[tuple[str, ...]] = ("R_IB", "D_OB", "D_TX")
M1_DERIVED_TARGETS: Final[tuple[str, ...]] = ("D_TO",)
M1_INTERNAL_AUXILIARY_TARGETS: Final[tuple[str, ...]] = ("DELTA_OB", "T_TX")

M1_TARGET_SEMANTICS: Final[dict[str, dict[str, str]]] = {
    "R_IB": {
        "external_name": "predecessor_A00_in_block_time_distribution",
        "quantity": "predecessor in-block time remaining from decision time",
        "role": "FORMAL_TARGET",
        "canonical_alias": "T_IB_A00",
    },
    "DELTA_OB": {
        "external_name": "internal_auxiliary_signed_off_block_offset",
        "quantity": "successor actual off-block time minus CRS scheduled departure (signed internal predictive auxiliary)",
        "role": "INTERNAL_AUXILIARY",
    },
    "T_TX": {
        "external_name": "internal_auxiliary_taxi_out_duration",
        "quantity": "successor taxi-out duration (internal predictive auxiliary; not the formal D_TX)",
        "role": "INTERNAL_AUXILIARY",
    },
    "R_OB": {
        "external_name": "successor_nonnegative_off_block_delay",
        "quantity": "derived max(0, DELTA_OB); compatibility alias of formal D_OB",
        "role": "DERIVED",
    },
    "D_OB": {
        "external_name": "successor_off_block_delay_distribution",
        "quantity": "max(0, DELTA_OB); nonnegative successor off-block delay",
        "role": "FORMAL_TARGET",
    },
    "D_TX": {
        "external_name": "successor_excess_taxi_delay_distribution",
        "quantity": "max(0, T_TX minus train-frozen taxi reference); nonnegative successor excess taxi delay",
        "role": "FORMAL_TARGET",
    },
    "D_TO": {
        "external_name": "successor_total_takeoff_delay_distribution",
        "quantity": "D_OB plus D_TX per aligned scenario; never a separately trained head",
        "role": "FORMAL_DERIVED",
    },
    "T_OB": {
        "external_name": "successor_off_block_event_time",
        "quantity": "scheduled departure plus signed DELTA_OB",
        "role": "DERIVED",
    },
    "T_TO": {
        "external_name": "successor_takeoff_event_time",
        "quantity": "T_OB plus T_TX",
        "role": "DERIVED",
    },
}


def derived_r_ob_minutes(delta_ob_minutes: float | None) -> float | None:
    return None if delta_ob_minutes is None else max(0.0, float(delta_ob_minutes))


def derived_d_ob_minutes(delta_ob_minutes: float | None) -> float | None:
    """Formal nonnegative successor off-block delay D_OB = max(0, DELTA_OB)."""
    return derived_r_ob_minutes(delta_ob_minutes)


def derived_d_tx_minutes(
    t_tx_minutes: float | None, taxi_reference_minutes: float | None
) -> float | None:
    """Formal nonnegative successor excess taxi delay D_TX."""
    if t_tx_minutes is None or taxi_reference_minutes is None:
        return None
    return max(0.0, float(t_tx_minutes) - float(taxi_reference_minutes))


def derived_d_to_minutes(
    delta_ob_minutes: float | None,
    t_tx_minutes: float | None,
    taxi_reference_minutes: float | None,
) -> float | None:
    """D_TO = D_OB + D_TX per aligned scenario (manuscript identity)."""
    d_ob = derived_d_ob_minutes(delta_ob_minutes)
    d_tx = derived_d_tx_minutes(t_tx_minutes, taxi_reference_minutes)
    if d_ob is None or d_tx is None:
        return None
    return d_ob + d_tx


def takeoff_event_time_minutes(t_ob_minutes: float | None, t_tx_minutes: float | None) -> float | None:
    if t_ob_minutes is None or t_tx_minutes is None:
        return None
    return float(t_ob_minutes) + float(t_tx_minutes)


def total_takeoff_delay_minutes(*, delta_ob_minutes: float | None = None,
                                t_tx_minutes: float | None,
                                taxi_reference_minutes: float | None,
                                t_ob_minutes: float | None = None,
                                scheduled_ob_minutes: float | None = None) -> float | None:
    """Return the formal total takeoff delay ``D_TO = D_OB + D_TX``."""
    if delta_ob_minutes is None and t_ob_minutes is not None and scheduled_ob_minutes is not None:
        delta_ob_minutes = float(t_ob_minutes) - float(scheduled_ob_minutes)
    if delta_ob_minutes is None or t_tx_minutes is None or taxi_reference_minutes is None:
        return None
    return derived_d_to_minutes(delta_ob_minutes, t_tx_minutes, taxi_reference_minutes)


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
