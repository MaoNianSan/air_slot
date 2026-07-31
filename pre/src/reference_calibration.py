from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .passenger_reference import PassengerReference
from .reference_models import (
    AirportReference,
    FlowReference,
    TurnaroundReference,
    WeatherClimatology,
)
from .reference_utils import TIME_BINS, WEATHER_FIELDS


def build_calibration(
    cfg: dict[str, Any],
    passenger: PassengerReference,
    flow: FlowReference,
    turnaround: TurnaroundReference,
    airport: AirportReference,
    climatology: WeatherClimatology,
) -> pd.DataFrame:
    train_period = f"{cfg['splits']['train'][0]}/{cfg['splits']['train'][1]}"
    rows = []
    for code in cfg["airports"]["m1"]:
        region = cfg["airports"]["regions"].get(code, "UNKNOWN")
        try:
            airport_row = airport.resolve(code)
        except KeyError:
            airport_row = pd.Series(dtype=object)
        try:
            typical, minimum, margin, continuity, turn_level, turn_cell = turnaround.resolve(code, "other", "00_06")
        except Exception:
            typical = minimum = margin = continuity = np.nan
            turn_level = "MISSING"
            turn_cell = 0
        for month in range(1, 13):
            for time_bin in TIME_BINS:
                try:
                    passenger_record = passenger.resolve(
                        "UNKNOWN",
                        code,
                        f"{int(cfg['reference_year']):04d}-{month:02d}",
                        aircraft_group="other",
                        time_bin=time_bin,
                    )
                except Exception:
                    passenger_record = PassengerReference._empty_result(
                        target_period=f"{int(cfg['reference_year']):04d}-{month:02d}",
                        attempted_levels=[
                            "OD_MONTH_AIRCRAFT_GROUP",
                            "OD_MONTH",
                            "DESTINATION_MONTH",
                        ],
                        missing_reason="UNKNOWN",
                    )
                flow_values: dict[str, float] = {}
                flow_levels: dict[str, str] = {}
                flow_cells: dict[str, int] = {}
                for field in ["flow_p05", "flow_p50", "flow_p90", "flow_p95"]:
                    try:
                        value, level, cell = flow.resolve(code, time_bin, field)
                    except Exception:
                        value, level, cell = np.nan, "MISSING", 0
                    flow_values[field] = value
                    flow_levels[field] = level
                    flow_cells[field] = cell
                weather = climatology.resolve(code, region, month, time_bin)
                weather_values, weather_level, weather_cell = weather if weather else (
                    {field: np.nan for field in WEATHER_FIELDS}, "MISSING", 0
                )
                rows.append({
                    "airport": code,
                    "airport_region": region,
                    "month": month,
                    "time_bin": time_bin,
                    "passenger_reference": passenger_record["passenger_reference"],
                    "passenger_reference_cell_size": passenger_record["support"],
                    "passenger_reference_fallback_level": passenger_record["level"],
                    "passenger_reference_source_period": passenger_record["reference_period"],
                    "passenger_reference_source_version": "EUROSTAT_2022",
                    "commercial_flight_reference": passenger_record["commercial_flight_reference"],
                    "commercial_flight_cell_size": passenger_record["support"],
                    "commercial_flight_fallback_level": passenger_record["level"],
                    "seat_reference": passenger_record["seat_reference"],
                    "airport_month_load_factor_proxy": passenger_record["airport_month_load_factor_proxy"],
                    "route_month_load_factor": passenger_record["route_month_load_factor"],
                    "estimated_passenger_load": passenger_record["estimated_passenger_load"],
                    "connection_pressure_proxy": passenger_record["connection_pressure_proxy"],
                    "rebooking_scarcity_proxy": passenger_record["rebooking_scarcity_proxy"],
                    "passenger_proxy_level": passenger_record["level"],
                    "passenger_proxy_support": passenger_record["support"],
                    "passenger_proxy_evidence_status": passenger_record["evidence_status"],
                    "passenger_proxy_source_period": passenger_record["reference_period"],
                    "passenger_proxy_fallback_reason": passenger_record["fallback_reason"],
                    "passenger_proxy_reference_period": passenger_record["reference_period"],
                    "passenger_proxy_source_key": passenger_record["source_key"],
                    "passenger_proxy_future_data_used": passenger_record["future_data_used"],
                    "passenger_proxy_missing_reason": passenger_record["missing_reason"],
                    "passenger_target_period": passenger_record["passenger_target_period"],
                    "passenger_source_period": passenger_record["passenger_source_period"],
                    "passenger_period_end": passenger_record["passenger_period_end"],
                    "passenger_lag_months": passenger_record["passenger_lag_months"],
                    "passenger_requested_level": passenger_record["passenger_requested_level"],
                    "passenger_used_level": passenger_record["passenger_used_level"],
                    "passenger_evidence_status": passenger_record["passenger_evidence_status"],
                    "passenger_missing_reason": passenger_record["passenger_missing_reason"],
                    "passenger_support_count": passenger_record["passenger_support_count"],
                    "passenger_source_dataset": passenger_record["passenger_source_dataset"],
                    "passenger_measure_filter": passenger_record["passenger_measure_filter"],
                    "passenger_future_data_used": passenger_record["passenger_future_data_used"],
                    "seat_capacity": passenger_record["seat_capacity"],
                    "seat_capacity_level": passenger_record["seat_capacity_level"],
                    "seat_capacity_support": passenger_record["seat_capacity_support"],
                    "seat_capacity_evidence_status": passenger_record["seat_capacity_evidence_status"],
                    "load_factor": passenger_record["load_factor"],
                    "load_factor_support": passenger_record["load_factor_support"],
                    "load_factor_evidence_status": passenger_record["load_factor_evidence_status"],
                    "connection_pressure_support": passenger_record["connection_pressure_support"],
                    "connection_pressure_level": passenger_record["connection_pressure_level"],
                    "connection_pressure_evidence_status": passenger_record["connection_pressure_evidence_status"],
                    "connection_pressure_missing_reason": passenger_record["connection_pressure_missing_reason"],
                    "rebooking_scarcity_support": passenger_record["rebooking_scarcity_support"],
                    "rebooking_scarcity_level": passenger_record["rebooking_scarcity_level"],
                    "rebooking_scarcity_evidence_status": passenger_record["rebooking_scarcity_evidence_status"],
                    "rebooking_scarcity_missing_reason": passenger_record["rebooking_scarcity_missing_reason"],
                    **flow_values,
                    "flow_cell_size": max(flow_cells.values()) if flow_cells else 0,
                    "flow_fallback_level": flow_levels.get("flow_p90", "MISSING"),
                    "flow_source_period": train_period,
                    "flow_source_version": "OPEN_SKY_TRAINING",
                    "capacity_threshold": flow_values.get("flow_p90", np.nan),
                    "capacity_cell_size": flow_cells.get("flow_p90", 0),
                    "capacity_fallback_level": flow_levels.get("flow_p90", "MISSING"),
                    "turnaround_typical": typical,
                    "turnaround_minimum": minimum,
                    "turnaround_margin_reference": margin,
                    "turnaround_cell_size": turn_cell,
                    "turnaround_fallback_level": turn_level,
                    "continuity_probability": continuity,
                    "continuity_cell_size": turn_cell,
                    "continuity_fallback_level": turn_level,
                    "runway_count": float(airport_row.get("runway_count", np.nan)),
                    "infrastructure_flexibility": float(airport_row.get("infrastructure_flexibility", np.nan)),
                    "infrastructure_fallback_level": str(airport_row.get("infrastructure_fallback_level", "MISSING")),
                    "infrastructure_source_version": str(airport_row.get("source_version", "MISSING")),
                    "airport_scale": float(airport_row.get("airport_scale", np.nan)),
                    "airport_scale_cell_size": int(len(airport.table)),
                    "airport_scale_fallback_level": str(airport_row.get("airport_scale_fallback_level", "MISSING")),
                    "climatology_weather_fields": json.dumps(weather_values, sort_keys=True),
                    "climatology_cell_size": weather_cell,
                    "climatology_fallback_level": weather_level,
                    "climatology_source_version": "IEM_METAR_TRAINING",
                })
    return pd.DataFrame(rows)


