"""Single source of truth for M1 event-time semantics.

V2 principal contract (Round-2 empirical model alignment, Tranche 2):

    T_IB_A00 -> D_OB -> D_TX          (formal primitive chain)
    R_IB = max(0, T_IB_A00 - t)       (derived)
    D_TO = D_OB + D_TX                (derived, never a separate head)

    D_OB >= 0    successor off-block delay (hurdle + conditional quantile)
    D_TX >= 0    successor excess taxi delay (hurdle + conditional quantile)
    D_TX conditions on formal D_OB, never on signed DELTA_OB.

``DELTA_OB`` / ``T_TX`` / taxi-reference reconstructions are LEGACY_V1 /
LABEL_CONSTRUCTION / EVALUATION_AUXILIARY only and are not V2 formal
stochastic parents.  The V1 helper functions below are retained unchanged so
that historical V1 artifacts and legacy consumers keep their provenance.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

FORMAL_FORECAST_HORIZONS_MINUTES: Final[tuple[int, ...]] = (0, 15, 60)
DELAY_THRESHOLDS_MINUTES: Final[tuple[int, ...]] = (15, 30, 60)
EVALUATION_ONLY_FORECAST_HORIZONS_MINUTES: Final[tuple[int, ...]] = (
    0,
    30,
    60,
    120,
    180,
    240,
    300,
    360,
    420,
    480,
)

# ---------------------------------------------------------------------------
# V2 principal contract (Round-2 M1 V2 real estimator).
# ---------------------------------------------------------------------------
M1_V2_PRIMITIVE_TARGETS: Final[tuple[str, ...]] = ("T_IB_A00", "D_OB", "D_TX")
M1_V2_DERIVED_TARGETS: Final[tuple[str, ...]] = ("R_IB", "D_TO")
M1_V2_ALL_TARGETS: Final[tuple[str, ...]] = (
    M1_V2_PRIMITIVE_TARGETS + M1_V2_DERIVED_TARGETS
)
# Round 2.1 coordinate separation: the public primitive T_IB_A00 is the
# absolute predecessor in-block event time (ISO UTC); the hazard head/label
# parameterize the INTERNAL remaining-time coordinate from the decision node.
# Public T_IB_A00 = decision_time + internal hazard coordinate.
M1_V2_HAZARD_COORDINATE_TARGET: Final[str] = "T_IB_REMAINING_HAZARD"
# DELTA_OB / raw T_TX are LEGACY_V1 / LABEL_CONSTRUCTION / EVALUATION_AUXILIARY
# only; they are never V2 formal stochastic parents.
M1_V2_LEGACY_AUXILIARY_TARGETS: Final[tuple[str, ...]] = ("DELTA_OB", "T_TX")

# V1 formal output contract (Round-1 reconciliation 2026-08-19): predecessor
# in-block (R_IB) plus the nonnegative successor delay pair; D_TO derived.
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


M1_V2_TARGET_SEMANTICS: Final[dict[str, dict[str, str]]] = {
    "T_IB_A00": {
        "external_name": "predecessor_A00_in_block_event_time",
        "quantity": "absolute predecessor in-block event time (decision-time unresolved; discrete hazard)",
        "role": "FORMAL_PRIMITIVE",
    },
    "R_IB": {
        "external_name": "predecessor_in_block_remaining_time",
        "quantity": "derived max(0, T_IB_A00 - t); never a separately trained head",
        "role": "FORMAL_DERIVED",
    },
    "D_OB": {
        "external_name": "successor_off_block_delay_distribution",
        "quantity": "nonnegative successor off-block delay; hurdle + positive conditional quantile",
        "role": "FORMAL_PRIMITIVE",
    },
    "D_TX": {
        "external_name": "successor_excess_taxi_delay_distribution",
        "quantity": "nonnegative successor excess taxi delay; hurdle + positive conditional quantile conditioned on formal D_OB",
        "role": "FORMAL_PRIMITIVE",
    },
    "D_TO": {
        "external_name": "successor_total_takeoff_delay_distribution",
        "quantity": "D_OB plus D_TX per aligned scenario; never a separately trained head",
        "role": "FORMAL_DERIVED",
    },
    "T_IB_REMAINING_HAZARD": {
        "external_name": "predecessor_in_block_remaining_time_hazard_coordinate",
        "quantity": "internal remaining-time hazard coordinate in minutes from the decision node; public T_IB_A00 = decision_time + coordinate; R_IB = max(0, T_IB_A00 - decision_time)",
        "role": "INTERNAL_HAZARD_COORDINATE",
    },
}


def derived_r_ib_minutes(
    t_ib_a00_utc: str | None, decision_time_utc: str | None
) -> float | None:
    """Derived R_IB = max(0, T_IB_A00 - t); never a trained head."""
    if t_ib_a00_utc is None or decision_time_utc is None:
        return None
    try:
        remaining = (
            datetime.fromisoformat(t_ib_a00_utc)
            - datetime.fromisoformat(decision_time_utc)
        ).total_seconds() / 60.0
    except ValueError:
        return None
    return max(0.0, remaining)


def remaining_hazard_coordinate_minutes(
    t_ib_a00_utc: str | None, decision_time_utc: str | None
) -> float | None:
    """Internal hazard coordinate: max(0, T_IB_A00 - decision_time) minutes.

    This is the same quantity as the derived R_IB; the name makes the
    remaining-time hazard-coordinate semantics explicit for the internal
    head/label parameterization.
    """
    return derived_r_ib_minutes(t_ib_a00_utc, decision_time_utc)


def t_ib_a00_from_remaining_minutes(
    decision_time_utc: str, remaining_minutes: float
) -> str:
    """Public absolute event time T_IB_A00 = decision_time + remaining minutes.

    Raises ``ValueError`` (``M1_V2_DECISION_TIME_REQUIRED``) when the decision
    time is missing; the caller decides the error class.
    """
    if decision_time_utc is None:
        raise ValueError("M1_V2_DECISION_TIME_REQUIRED")
    return (
        datetime.fromisoformat(decision_time_utc)
        + timedelta(minutes=float(remaining_minutes))
    ).isoformat()


def derived_r_ib_from_remaining(remaining_minutes: float | None) -> float | None:
    """Derived R_IB from a nonnegative remaining-time draw (hazard parameterization)."""
    if remaining_minutes is None:
        return None
    return max(0.0, float(remaining_minutes))


def derived_d_to_from_primitives(
    d_ob_minutes: float | None, d_tx_minutes: float | None
) -> float | None:
    """V2 D_TO = D_OB + D_TX per scenario (never a separate head)."""
    if d_ob_minutes is None or d_tx_minutes is None:
        return None
    return float(d_ob_minutes) + float(d_tx_minutes)


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


def takeoff_event_time_minutes(
    t_ob_minutes: float | None, t_tx_minutes: float | None
) -> float | None:
    if t_ob_minutes is None or t_tx_minutes is None:
        return None
    return float(t_ob_minutes) + float(t_tx_minutes)


def total_takeoff_delay_minutes(
    *,
    delta_ob_minutes: float | None = None,
    t_tx_minutes: float | None,
    taxi_reference_minutes: float | None,
    t_ob_minutes: float | None = None,
    scheduled_ob_minutes: float | None = None,
) -> float | None:
    """Return the formal total takeoff delay ``D_TO = D_OB + D_TX``."""
    if (
        delta_ob_minutes is None
        and t_ob_minutes is not None
        and scheduled_ob_minutes is not None
    ):
        delta_ob_minutes = float(t_ob_minutes) - float(scheduled_ob_minutes)
    if (
        delta_ob_minutes is None
        or t_tx_minutes is None
        or taxi_reference_minutes is None
    ):
        return None
    return derived_d_to_minutes(delta_ob_minutes, t_tx_minutes, taxi_reference_minutes)


def delay_from_event_times(
    t_ob: datetime | None,
    taxi_duration_minutes: float | None,
    scheduled_ob: datetime | None,
    taxi_reference_minutes: float | None,
) -> float | None:
    if (
        t_ob is None
        or taxi_duration_minutes is None
        or scheduled_ob is None
        or taxi_reference_minutes is None
    ):
        return None
    delta_ob = (t_ob - scheduled_ob).total_seconds() / 60.0
    return total_takeoff_delay_minutes(
        delta_ob_minutes=delta_ob,
        t_tx_minutes=taxi_duration_minutes,
        taxi_reference_minutes=taxi_reference_minutes,
    )


def external_target_name(target_name: str) -> str:
    if target_name in M1_V2_TARGET_SEMANTICS:
        return M1_V2_TARGET_SEMANTICS[target_name]["external_name"]
    try:
        return M1_TARGET_SEMANTICS[target_name]["external_name"]
    except KeyError as exc:
        raise ValueError(f"UNKNOWN_M1_TARGET:{target_name}") from exc
