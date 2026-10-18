"""Shared pure M2 native passenger formulas."""

from __future__ import annotations

import math


def _finite_nonnegative(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"M2_INVALID_NUMERIC_INPUT:{name}")
    return value


def p_time_native(expected_pax: float, d_to: float) -> float:
    return _finite_nonnegative(expected_pax, "expected_pax") * _finite_nonnegative(d_to, "d_to")


def p_itinerary_native(expected_pax: float, connection_share: float, d_to: float, itinerary_threshold_minutes: float) -> float:
    pax = _finite_nonnegative(expected_pax, "expected_pax")
    share = float(connection_share)
    delay = _finite_nonnegative(d_to, "d_to")
    threshold = float(itinerary_threshold_minutes)
    if not math.isfinite(share) or not 0.0 <= share <= 1.0:
        raise ValueError("M2_INVALID_NUMERIC_INPUT:connection_share")
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("M2_INVALID_NUMERIC_INPUT:itinerary_threshold_minutes")
    return pax * share * (1.0 if delay > threshold else 0.0)


def p_service_native(expected_pax: float, d_to: float, service_threshold_minutes: float) -> float:
    pax = _finite_nonnegative(expected_pax, "expected_pax")
    delay = _finite_nonnegative(d_to, "d_to")
    threshold = float(service_threshold_minutes)
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("M2_INVALID_NUMERIC_INPUT:service_threshold_minutes")
    return pax * (1.0 if delay >= threshold else 0.0)


def d_ob_realized(actual_departure_utc, scheduled_departure_utc) -> float:
    return max(0.0, (actual_departure_utc - scheduled_departure_utc).total_seconds() / 60.0)


def d_tx_realized(taxi_out_minutes: float, taxi_reference: float) -> float:
    return max(0.0, float(taxi_out_minutes) - float(taxi_reference))


def d_to_from_components(d_ob: float, d_tx: float) -> float:
    return _finite_nonnegative(d_ob, "d_ob") + _finite_nonnegative(d_tx, "d_tx")
