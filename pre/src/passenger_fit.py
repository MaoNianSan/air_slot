from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .passenger_reference import PassengerReference


def fit_passenger_reference(passengers: pd.DataFrame, flights: pd.DataFrame, legs: pd.DataFrame, cfg: dict[str, Any]) -> PassengerReference:
    train_end_exclusive = pd.Timestamp(cfg["splits"]["train"][1])
    reference_cutoff_date = train_end_exclusive - pd.Timedelta(nanoseconds=1)
    reference_cutoff_period = reference_cutoff_date.to_period("M")

    def with_period(frame: pd.DataFrame) -> pd.DataFrame:
        output = frame.copy()
        output["_period"] = output["source_period"].map(
            lambda value: pd.Period(str(value), freq="M") if pd.notna(value) else pd.NaT
        )
        return output[output["_period"].notna()].copy()

    p_all = with_period(passengers)
    f_all = with_period(flights)
    all_periods = pd.concat([p_all["_period"], f_all["_period"]], ignore_index=True)
    eligible_p = p_all[p_all["_period"].map(lambda value: value.end_time <= reference_cutoff_date)].copy()
    eligible_f = f_all[f_all["_period"].map(lambda value: value.end_time <= reference_cutoff_date)].copy()
    future_excluded = int(len(p_all) - len(eligible_p) + len(f_all) - len(eligible_f))

    def aggregate_source(frame: pd.DataFrame, value: str) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=[
                "airport", "source_period", value,
                f"{value}_source_record_ids", f"{value}_raw_files", f"{value}_raw_hashes",
            ])
        grouped = frame.groupby(["airport", "source_period"], as_index=False).agg(
            **{
                value: (value, "sum"),
                f"{value}_source_record_ids": (
                    "source_record_id",
                    lambda values: json.dumps(sorted(set(map(str, values)))),
                ),
                f"{value}_raw_files": (
                    "raw_source_file",
                    lambda values: json.dumps(sorted(set(map(str, values)))),
                ),
                f"{value}_raw_hashes": (
                    "raw_source_hash",
                    lambda values: json.dumps(sorted(set(map(str, values)))),
                ),
            }
        )
        return grouped

    p = aggregate_source(eligible_p, "passengers")
    f = aggregate_source(eligible_f, "commercial_flights")
    merged = p.merge(f, on=["airport", "source_period"], how="inner")
    merged = merged.rename(columns={"airport": "destination"})
    merged["source_month"] = merged["source_period"].map(lambda value: pd.Period(str(value), freq="M").month)
    merged["airport_region"] = merged["destination"].map(cfg["airports"]["regions"]).fillna("UNKNOWN")

    seats = {
        str(key): float(value)
        for key, value in cfg["references"]["aircraft_seat_reference"].items()
        if str(key) != "unknown"
    }
    train_legs = legs[(legs["split"] == "train") & legs["candidate_episode"]].copy()
    train_legs["period"] = (
        pd.to_datetime(train_legs["firstseen_utc"], utc=True)
        .dt.tz_localize(None)
        .dt.to_period("M")
        .astype(str)
    )
    train_legs["seat"] = train_legs["aircraft_group"].map(seats)
    known_seats = train_legs.dropna(subset=["seat"]).copy()
    destination_seat = known_seats.groupby("destination")["seat"].median()
    destination_seat_support = known_seats.groupby("destination")["seat"].size()
    merged["seat_capacity_denominator_per_flight"] = merged["destination"].map(destination_seat)
    merged["seat_capacity_reference_support"] = (
        merged["destination"].map(destination_seat_support).fillna(0).astype(int)
    )
    merged["seat_capacity_denominator"] = (
        pd.to_numeric(merged["commercial_flights"], errors="coerce")
        * pd.to_numeric(merged["seat_capacity_denominator_per_flight"], errors="coerce")
    )
    merged["passenger_per_flight"] = (
        pd.to_numeric(merged["passengers"], errors="coerce")
        / pd.to_numeric(merged["commercial_flights"], errors="coerce").replace(0, np.nan)
    )
    raw_load_factor = (
        pd.to_numeric(merged["passengers"], errors="coerce")
        / pd.to_numeric(merged["seat_capacity_denominator"], errors="coerce").replace(0, np.nan)
    )
    merged["load_factor"] = raw_load_factor.where(raw_load_factor.between(0.0, 1.0, inclusive="both"))
    merged["support_size"] = pd.to_numeric(
        merged["commercial_flights"], errors="coerce"
    ).fillna(0).clip(lower=0).astype(int)
    merged["reference_key"] = (
        "destination=" + merged["destination"].astype(str)
        + "|period=" + merged["source_period"].astype(str)
    )
    merged["source_record_ids"] = [
        json.dumps(sorted(set(json.loads(a) + json.loads(b))))
        for a, b in zip(
            merged["passengers_source_record_ids"],
            merged["commercial_flights_source_record_ids"],
        )
    ]
    merged["raw_files"] = [
        json.dumps(sorted(set(json.loads(a) + json.loads(b))))
        for a, b in zip(merged["passengers_raw_files"], merged["commercial_flights_raw_files"])
    ]
    merged["raw_hashes"] = [
        json.dumps(sorted(set(json.loads(a) + json.loads(b))))
        for a, b in zip(merged["passengers_raw_hashes"], merged["commercial_flights_raw_hashes"])
    ]
    merged["evidence_status"] = np.where(
        merged["load_factor"].notna() & merged["seat_capacity_denominator_per_flight"].notna(),
        "SUPPORTED_PROXY",
        "UNSUPPORTED",
    )

    arrivals = train_legs.groupby(
        ["destination", "period", "firstseen_time_bin"], as_index=False
    ).agg(arrival_wave_count=("episode_id", "size"))
    arrivals = arrivals.rename(columns={
        "destination": "airport",
        "firstseen_time_bin": "time_bin",
    })
    departures = train_legs.groupby(
        ["origin", "period", "firstseen_time_bin"], as_index=False
    ).agg(
        departure_wave_count=("episode_id", "size"),
        alternative_destinations=("destination", "nunique"),
        alternative_capacity=("seat", lambda values: pd.to_numeric(values, errors="coerce").sum(min_count=1)),
        flight_support=("episode_id", "size"),
        seat_typical=("seat", "median"),
    )
    departures = departures.rename(columns={
        "origin": "airport",
        "firstseen_time_bin": "time_bin",
    })
    operations = arrivals.merge(
        departures, on=["airport", "period", "time_bin"], how="outer"
    )
    raw_connection = (
        pd.to_numeric(operations.get("arrival_wave_count"), errors="coerce")
        * pd.to_numeric(operations.get("departure_wave_count"), errors="coerce")
        * np.log1p(pd.to_numeric(operations.get("alternative_destinations"), errors="coerce"))
    )
    finite_connection = raw_connection.dropna()
    if not finite_connection.empty and float(finite_connection.max()) > float(finite_connection.min()):
        low = float(finite_connection.quantile(0.05))
        high = float(finite_connection.quantile(0.95))
        if high > low:
            operations["connection_opportunity"] = ((raw_connection - low) / (high - low)).clip(0.0, 1.0)
        else:
            operations["connection_opportunity"] = np.nan
    else:
        operations["connection_opportunity"] = np.nan

    group_support = (
        train_legs["aircraft_group"].astype(str).value_counts().astype(int).to_dict()
        if not train_legs.empty else {}
    )
    eligible_periods = pd.concat(
        [eligible_p["_period"], eligible_f["_period"]], ignore_index=True
    )
    metadata = {
        "reference_cutoff_date": str(reference_cutoff_date),
        "reference_cutoff_period": str(reference_cutoff_period),
        "source_min_period": str(min(all_periods)) if not all_periods.empty else "",
        "source_max_period": str(max(all_periods)) if not all_periods.empty else "",
        "eligible_source_min_period": str(min(eligible_periods)) if not eligible_periods.empty else "",
        "eligible_source_max_period": str(max(eligible_periods)) if not eligible_periods.empty else "",
        "eligible_source_row_count": int(len(eligible_p) + len(eligible_f)),
        "future_source_row_count_excluded": future_excluded,
        "monthly_availability_semantics": "AVAILABLE_AFTER_SOURCE_PERIOD_END",
        "historical_reference_semantics": "FROZEN_AT_TRAIN_END_EXCLUSIVE",
        "maximum_lag_months": int(
            cfg["references"].get("passenger", {}).get(
                "maximum_lag_months", 3
            )
        ),
        "airport_code_system": "EUROSTAT_REP_AIRP_ICAO_SUFFIX",
        "od_month_aircraft_group_available": False,
        "od_month_available": False,
        "destination_lagged_month_available": bool(not merged.empty and merged["load_factor"].notna().any()),
        "actual_highest_supported_level": (
            "DESTINATION_LAGGED_MONTH"
            if not merged.empty and merged["load_factor"].notna().any()
            else "UNSUPPORTED"
        ),
        "empty_reason": (
            ""
            if not merged.empty and merged["load_factor"].notna().any()
            else "SOURCE_HISTORY_INSUFFICIENT"
            if eligible_periods.empty
            else "LOAD_FACTOR_REFERENCE_EMPTY"
        ),
    }
    return PassengerReference(
        merged,
        operations,
        cfg["airports"]["regions"],
        seats,
        group_support,
        metadata,
    )


