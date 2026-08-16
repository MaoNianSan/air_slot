"""Single source of truth for the external M1 delay semantics."""

from __future__ import annotations

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
        "external_name": "successor_additional_taxi_delay_distribution",
        "quantity": "successor additional taxi delay",
    },
    "D_TO": {
        "external_name": "successor_total_takeoff_delay_distribution",
        "quantity": "successor total takeoff delay",
    },
}


def takeoff_delay_minutes(r_ob_minutes: float | None, t_tx_minutes: float | None) -> float | None:
    """Return the sample-level total takeoff delay when both parents exist."""
    if r_ob_minutes is None or t_tx_minutes is None:
        return None
    return float(r_ob_minutes) + float(t_tx_minutes)


def external_target_name(target_name: str) -> str:
    try:
        return M1_TARGET_SEMANTICS[target_name]["external_name"]
    except KeyError as exc:
        raise ValueError(f"UNKNOWN_M1_TARGET:{target_name}") from exc
