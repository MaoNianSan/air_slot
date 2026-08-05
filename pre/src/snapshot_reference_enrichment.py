from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .reference import AirportReference, TurnaroundReference


def _empty_values(row: pd.Series) -> dict[str, Any]:
    return {
        "turnaround_margin": np.nan,
        "continuity_exposure": np.nan,
        "_turnaround_fallback_level": "",
        "_turnaround_cell_size": 0,
        "runway_count": np.nan,
        "infrastructure_flexibility": np.nan,
        "airport_scale": np.nan,
        "_infrastructure_fallback_level": "",
        "_airport_source_version": "",
        "estimated_passenger_load": np.nan,
        "connection_pressure_proxy": np.nan,
        "rebooking_scarcity_proxy": np.nan,
        "passenger_proxy_level": "MISSING",
        "passenger_proxy_support": 0,
        "passenger_proxy_evidence_status": "UNOBSERVED",
        "passenger_proxy_source_period": "",
        "passenger_proxy_fallback_reason": "",
        "passenger_proxy_reference_period": "",
        "passenger_proxy_source_key": "",
        "passenger_proxy_future_data_used": False,
        "passenger_proxy_missing_reason": "UNKNOWN",
        "passenger_proxy_attempted_levels": "[]",
        "passenger_target_period": str(row.get("period", "")),
        "passenger_source_period": "",
        "passenger_period_end": "",
        "passenger_lag_months": pd.NA,
        "passenger_requested_level": "DESTINATION_LAGGED_MONTH",
        "passenger_used_level": "UNSUPPORTED",
        "passenger_evidence_status": "UNSUPPORTED",
        "passenger_missing_reason": "UNKNOWN",
        "passenger_support_count": 0,
        "passenger_source_dataset": "EUROSTAT_AVIA_PAOA_AND_AVIA_TF_AIRPM",
        "passenger_measure_filter": "",
        "passenger_future_data_used": False,
        "seat_capacity": np.nan,
        "seat_capacity_level": "UNSUPPORTED",
        "seat_capacity_support": 0,
        "seat_capacity_evidence_status": "UNSUPPORTED",
        "load_factor": np.nan,
        "load_factor_support": 0,
        "load_factor_evidence_status": "UNSUPPORTED",
        "connection_pressure_support": 0,
        "connection_pressure_level": "UNSUPPORTED",
        "connection_pressure_evidence_status": "UNSUPPORTED",
        "connection_pressure_missing_reason": "UNKNOWN",
        "rebooking_scarcity_support": 0,
        "rebooking_scarcity_level": "UNSUPPORTED",
        "rebooking_scarcity_evidence_status": "UNSUPPORTED",
        "rebooking_scarcity_missing_reason": "UNKNOWN",
        "_passenger_source_record_ids": "[]",
        "_passenger_raw_files": "[]",
        "_passenger_raw_hashes": "[]",
    }


def _turnaround_values(
    row: pd.Series,
    reference: TurnaroundReference,
    cache: dict[tuple[str, str, str], tuple[Any, ...] | Exception],
) -> dict[str, Any]:
    key = (
        str(row["airport"]),
        str(row.get("aircraft_group", "unknown")),
        str(row["firstseen_time_bin"]),
    )
    if key not in cache:
        try:
            cache[key] = reference.resolve(*key)
        except Exception as error:
            cache[key] = error
    result = cache[key]
    if isinstance(result, Exception):
        raise result
    _, _, margin, continuity, level, cell = result
    return {
        "turnaround_margin": margin,
        "continuity_exposure": continuity,
        "_turnaround_fallback_level": level,
        "_turnaround_cell_size": cell,
    }


def _passenger_key(row: pd.Series) -> tuple[str, str, str, str, str]:
    period = row.get(
        "period",
        pd.Timestamp(row["decision_time_utc"]).tz_localize(None).to_period("M"),
    )
    return (
        str(row["origin"]),
        str(row["destination"]),
        str(period),
        str(row.get("aircraft_group", "unknown")),
        str(row.get("time_bin", "00_06")),
    )


def _passenger_values(passenger: dict[str, Any]) -> dict[str, Any]:
    direct = [
        "passenger_target_period",
        "passenger_source_period",
        "passenger_period_end",
        "passenger_lag_months",
        "passenger_requested_level",
        "passenger_used_level",
        "passenger_evidence_status",
        "passenger_missing_reason",
        "passenger_support_count",
        "passenger_source_dataset",
        "passenger_measure_filter",
        "passenger_future_data_used",
        "seat_capacity",
        "seat_capacity_level",
        "seat_capacity_support",
        "seat_capacity_evidence_status",
        "load_factor",
        "load_factor_support",
        "load_factor_evidence_status",
        "connection_pressure_support",
        "connection_pressure_level",
        "connection_pressure_evidence_status",
        "connection_pressure_missing_reason",
        "rebooking_scarcity_support",
        "rebooking_scarcity_level",
        "rebooking_scarcity_evidence_status",
        "rebooking_scarcity_missing_reason",
    ]
    values = {key: passenger[key] for key in direct}
    values.update(
        {
            "estimated_passenger_load": passenger["estimated_passenger_load"],
            "connection_pressure_proxy": passenger["connection_pressure_proxy"],
            "rebooking_scarcity_proxy": passenger["rebooking_scarcity_proxy"],
            "passenger_proxy_level": passenger["level"],
            "passenger_proxy_support": passenger["support"],
            "passenger_proxy_evidence_status": passenger["evidence_status"],
            "passenger_proxy_source_period": passenger["reference_period"],
            "passenger_proxy_fallback_reason": passenger["fallback_reason"],
            "passenger_proxy_reference_period": passenger["reference_period"],
            "passenger_proxy_source_key": passenger["source_key"],
            "passenger_proxy_future_data_used": passenger["future_data_used"],
            "passenger_proxy_missing_reason": passenger["missing_reason"],
            "passenger_proxy_attempted_levels": passenger["attempted_levels"],
            "_passenger_source_record_ids": passenger["source_record_ids"],
            "_passenger_raw_files": passenger["raw_files"],
            "_passenger_raw_hashes": passenger["raw_hashes"],
        }
    )
    return values


def _resolve_passenger(
    row: pd.Series,
    reference: Any,
    cache: dict[tuple[str, str, str, str, str], dict[str, Any] | Exception],
) -> dict[str, Any]:
    key = _passenger_key(row)
    if key not in cache:
        try:
            cache[key] = reference.resolve(
                *key, available_at=row["decision_time_utc"]
            )
        except Exception as error:
            cache[key] = error
    passenger = cache[key]
    if isinstance(passenger, Exception):
        raise passenger
    return _passenger_values(passenger)


def _airport_values(
    row: pd.Series,
    reference: AirportReference,
    cache: dict[str, Any | Exception],
) -> dict[str, Any]:
    key = str(row["airport"])
    if key not in cache:
        try:
            cache[key] = reference.resolve(key)
        except Exception as error:
            cache[key] = error
    airport = cache[key]
    if isinstance(airport, Exception):
        raise airport
    return {
        "runway_count": float(airport.get("runway_count", np.nan)),
        "infrastructure_flexibility": float(
            airport.get("infrastructure_flexibility", np.nan)
        ),
        "airport_scale": float(airport.get("airport_scale", np.nan)),
        "_infrastructure_fallback_level": str(
            airport.get("infrastructure_fallback_level", "")
        ),
        "_airport_source_version": str(airport.get("source_version", "")),
    }


def attach_aggregate_references(
    snapshots: pd.DataFrame,
    turnaround: TurnaroundReference,
    airport_reference: AirportReference,
    passenger_reference: Any,
) -> pd.DataFrame:
    rows = []
    turnaround_cache: dict[tuple[str, str, str], tuple[Any, ...] | Exception] = {}
    passenger_cache: dict[
        tuple[str, str, str, str, str], dict[str, Any] | Exception
    ] = {}
    airport_cache: dict[str, Any | Exception] = {}
    resolvers = [
        lambda row: _turnaround_values(row, turnaround, turnaround_cache),
        lambda row: _resolve_passenger(row, passenger_reference, passenger_cache),
        lambda row: _airport_values(row, airport_reference, airport_cache),
    ]
    for _, row in snapshots.iterrows():
        values = _empty_values(row)
        for resolver in resolvers:
            try:
                values.update(resolver(row))
            except Exception:
                pass
        rows.append(values)
    return pd.concat(
        [snapshots.reset_index(drop=True), pd.DataFrame(rows)], axis=1
    )
