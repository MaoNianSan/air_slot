from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .reference import AirportReference, TurnaroundReference
from .state import StateStore


STATE_SOURCE_FIELDS = ["latitude", "longitude", "altitude", "velocity", "vertical_rate"]
STATE_OUTPUT_FIELDS = ["current_latitude", "current_longitude", "current_altitude", "current_velocity", "vertical_rate"]


def _time_bin(value: pd.Timestamp) -> str:
    hour = int(value.hour)
    return "00_06" if hour < 6 else "06_12" if hour < 12 else "12_18" if hour < 18 else "18_24"


def build_snapshot_grid(episodes: pd.DataFrame, legs: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    attributes = legs[["episode_id", "aircraft_group", "aircraft_type_unknown"]].drop_duplicates("episode_id")
    rows: list[dict[str, Any]] = []
    ratios = [float(value) for value in cfg["snapshots"]["ratios"]]
    stage_map = cfg["snapshots"]["dense_stage_map"]
    primary_stages = set(cfg["snapshots"]["primary_stage_map"].values())
    for episode in episodes.itertuples(index=False):
        if not bool(episode.episode_valid):
            continue
        for ratio in ratios:
            stage = stage_map[f"{ratio:.1f}"]
            elapsed = ratio * float(episode.reference_movement_time)
            decision = episode.firstseen_utc + pd.to_timedelta(elapsed, unit="m")
            valid = bool(episode.lastseen_utc > decision)
            rows.append({
                "episode_id": episode.episode_id,
                "snapshot_id": f"{episode.episode_id}__{stage}",
                "snapshot_stage": stage,
                "snapshot_ratio": ratio,
                "elapsed_ratio": ratio,
                "is_primary_snapshot": stage in primary_stages,
                "decision_time_utc": decision,
                "elapsed_minutes": elapsed,
                "split": episode.split,
                "airport": episode.airport,
                "origin": episode.origin,
                "destination": episode.destination,
                "month": int(episode.firstseen_utc.month),
                "decision_month": int(decision.month),
                "period": str(decision.tz_localize(None).to_period("M")),
                "time_bin": _time_bin(decision),
                "firstseen_time_bin": _time_bin(episode.firstseen_utc),
                "icao24": episode.icao24,
                "reference_movement_time": episode.reference_movement_time,
                "firstseen_utc": episode.firstseen_utc,
                "lastseen_utc": episode.lastseen_utc,
                "snapshot_valid": valid,
                "snapshot_exclusion_reason": "" if valid else "FLIGHT_COMPLETED_BEFORE_SNAPSHOT",
            })
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.merge(attributes, on="episode_id", how="left", validate="many_to_one")


def derive_state_requests(snapshots: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Materialize the minimal state-vector windows required by snapshot matching."""
    columns = ["episode_id", "snapshot_id", "icao24", "decision_time_utc"]
    frame = snapshots.loc[snapshots["snapshot_valid"].fillna(False), columns].copy()
    lookback = pd.to_timedelta(float(cfg["state_vectors"]["lookback_minutes"]), unit="m")
    frame["request_start"] = frame["decision_time_utc"] - lookback
    frame["request_end"] = frame["decision_time_utc"]
    frame["date"] = frame["decision_time_utc"].dt.tz_convert("UTC").dt.normalize().dt.tz_localize(None)
    frame["hour"] = frame["decision_time_utc"].dt.hour.astype(int)
    return frame.sort_values(["date", "hour", "icao24", "request_start"], kind="mergesort").reset_index(drop=True)


def _coverage_status(coverage: pd.DataFrame, date: pd.Timestamp, hour: int) -> str:
    if coverage.empty:
        return "SOURCE_COVERAGE_GAP"
    subset = coverage[(coverage["date"] == pd.Timestamp(date).normalize()) & (coverage["hour"] == int(hour))]
    return str(subset.iloc[0]["coverage_status"]) if not subset.empty else "SOURCE_COVERAGE_GAP"


def _state_for_snapshot(row: pd.Series, aircraft: pd.DataFrame, status: str, cfg: dict[str, Any]) -> dict[str, Any]:
    decision = row["decision_time_utc"]
    base: dict[str, Any] = {
        "current_latitude": np.nan,
        "current_longitude": np.nan,
        "current_altitude": np.nan,
        "current_velocity": np.nan,
        "vertical_rate": np.nan,
        "trajectory_coverage": 0.0,
        "state_observation_age": np.nan,
        "state_record_count": 0,
        "state_lookback_minutes": float(cfg["state_vectors"]["lookback_minutes"]),
        "state_source_coverage": 0.0 if status == "SOURCE_COVERAGE_GAP" else 1.0,
        "state_source_coverage_status": status,
        "state_is_imputed": False,
        "state_imputation_method": "none",
        "state_imputation_gap_minutes": np.nan,
        "_state_event_time": pd.NaT,
        "_state_availability_time": pd.NaT,
        "_state_source_record_ids": "",
        "_state_raw_file": "",
        "_state_raw_hash": "",
        "_state_missing_reason": "",
        "_state_quality_ok": False,
    }
    if status == "SOURCE_COVERAGE_GAP":
        base["_state_missing_reason"] = "SOURCE_COVERAGE_GAP"
        return base
    if aircraft.empty:
        base["_state_missing_reason"] = "RECORD_EXPECTED_BUT_MISSING"
        return base
    lookback = pd.to_timedelta(cfg["state_vectors"]["lookback_minutes"], unit="m")
    subset = aircraft[
        (aircraft["availability_time"] <= decision)
        & (aircraft["event_time"] >= decision - lookback)
        & (aircraft["event_time"] <= decision)
    ].sort_values("event_time")
    if subset.empty:
        base["_state_missing_reason"] = "RECORD_NOT_AVAILABLE_BY_T"
        return base
    latest = subset.iloc[-1]
    for source, target in zip(STATE_SOURCE_FIELDS, STATE_OUTPUT_FIELDS):
        base[target] = float(latest[source]) if pd.notna(latest[source]) else np.nan
    age = float((decision - latest["event_time"]).total_seconds() / 60.0)
    expected = max(1, int(float(cfg["state_vectors"]["lookback_minutes"]) * 60 / float(cfg["state_vectors"]["expected_interval_seconds"])) + 1)
    interval = max(1, int(cfg["state_vectors"]["expected_interval_seconds"]))
    rounded = subset["event_time"].dt.floor(f"{interval}s").nunique()
    coverage = min(1.0, float(rounded / expected))
    quality = (
        len(subset) >= int(cfg["state_vectors"]["minimum_records"])
        and age <= float(cfg["state_vectors"]["maximum_observation_age_minutes"])
        and coverage >= float(cfg["state_vectors"]["minimum_trajectory_coverage"])
    )
    base.update({
        "trajectory_coverage": coverage,
        "state_observation_age": age,
        "state_record_count": int(len(subset)),
        "state_is_imputed": bool(latest.get("state_is_imputed", False)),
        "state_imputation_method": str(latest.get("state_imputation_method", "none")),
        "state_imputation_gap_minutes": latest.get("state_imputation_gap_minutes", np.nan),
        "_state_event_time": latest["event_time"],
        "_state_availability_time": latest["availability_time"],
        "_state_source_record_ids": str(latest.get("source_record_id", "")),
        "_state_raw_file": str(latest.get("raw_source_file", "")),
        "_state_raw_hash": str(latest.get("raw_source_hash", "")),
        "_state_quality_ok": quality,
        "_state_missing_reason": "" if quality else "FAILED_QUALITY_CHECK",
    })
    return base


def attach_state_features(snapshots: pd.DataFrame, store: StateStore, cfg: dict[str, Any]) -> pd.DataFrame:
    pieces = []
    date_series = snapshots["decision_time_utc"].dt.tz_convert("UTC").dt.normalize().dt.tz_localize(None)
    lookback_hours = int(np.ceil(float(cfg["state_vectors"]["lookback_minutes"]) / 60.0))
    source_cols = [*STATE_SOURCE_FIELDS, "event_time", "availability_time", "icao24", "state_is_imputed", "state_imputation_method", "state_imputation_gap_minutes", "source_record_id", "raw_source_file", "raw_source_hash"]
    for date, group in snapshots.groupby(date_series, sort=True):
        dates = [pd.Timestamp(date)]
        if int(group["decision_time_utc"].dt.hour.min()) < lookback_hours:
            dates.append(pd.Timestamp(date) - pd.Timedelta(days=1))
        day = pd.concat([
            store.load("candidate", d, columns=source_cols)
            for d in dates
        ], ignore_index=True)
        # Build only the requested aircraft groups, never a day-wide dataframe dictionary.
        requested = set(group["icao24"].astype(str))
        day = day[day["icao24"].astype(str).isin(requested)] if not day.empty else day
        by_aircraft = {str(code): aircraft.sort_values("event_time").reset_index(drop=True) for code, aircraft in day.groupby("icao24", sort=False)} if not day.empty else {}
        features = [_state_for_snapshot(row, by_aircraft.get(str(row["icao24"]), pd.DataFrame()), _coverage_status(store.coverage, pd.Timestamp(date), row["decision_time_utc"].hour), cfg) for _, row in group.iterrows()]
        piece = pd.concat([group.reset_index(), pd.DataFrame(features)], axis=1).set_index("index")
        pieces.append(piece)
    output = pd.concat(pieces).sort_index() if pieces else snapshots.copy()
    failed = ~output["_state_quality_ok"].fillna(False)
    output.loc[failed, "snapshot_valid"] = False
    output.loc[failed & output["snapshot_exclusion_reason"].eq(""), "snapshot_exclusion_reason"] = output.loc[
        failed & output["snapshot_exclusion_reason"].eq(""), "_state_missing_reason"
    ]
    return output


def attach_aggregate_references(
    snapshots: pd.DataFrame,
    turnaround: TurnaroundReference,
    airport_reference: AirportReference,
    passenger_reference: Any,
) -> pd.DataFrame:
    rows = []
    turnaround_cache: dict[tuple[str, str, str], tuple[Any, ...] | Exception] = {}
    passenger_cache: dict[tuple[str, str, str, str, str], dict[str, Any] | Exception] = {}
    airport_cache: dict[str, Any | Exception] = {}
    for _, row in snapshots.iterrows():
        values: dict[str, Any] = {
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
        try:
            turnaround_key = (str(row["airport"]), str(row.get("aircraft_group", "unknown")), str(row["firstseen_time_bin"]))
            if turnaround_key not in turnaround_cache:
                try:
                    turnaround_cache[turnaround_key] = turnaround.resolve(*turnaround_key)
                except Exception as error:
                    turnaround_cache[turnaround_key] = error
            turnaround_value = turnaround_cache[turnaround_key]
            if isinstance(turnaround_value, Exception):
                raise turnaround_value
            _, _, margin, continuity, level, cell = turnaround_value
            values.update({
                "turnaround_margin": margin,
                "continuity_exposure": continuity,
                "_turnaround_fallback_level": level,
                "_turnaround_cell_size": cell,
            })
        except Exception:
            pass
        try:
            passenger_key = (
                str(row["origin"]),
                str(row["destination"]),
                str(
                    row.get(
                        "period",
                        pd.Timestamp(row["decision_time_utc"]).tz_localize(None).to_period("M"),
                    )
                ),
                str(row.get("aircraft_group", "unknown")),
                str(row.get("time_bin", "00_06")),
            )
            if passenger_key not in passenger_cache:
                try:
                    passenger_cache[passenger_key] = passenger_reference.resolve(
                        *passenger_key,
                        available_at=row["decision_time_utc"],
                    )
                except Exception as error:
                    passenger_cache[passenger_key] = error
            passenger = passenger_cache[passenger_key]
            if isinstance(passenger, Exception):
                raise passenger
            values.update({
                "estimated_passenger_load": passenger["estimated_passenger_load"],
                "connection_pressure_proxy": passenger["connection_pressure_proxy"],
                "rebooking_scarcity_proxy": passenger["rebooking_scarcity_proxy"],
                "passenger_proxy_level": passenger["level"], "passenger_proxy_support": passenger["support"],
                "passenger_proxy_evidence_status": passenger["evidence_status"],
                "passenger_proxy_source_period": passenger["reference_period"],
                "passenger_proxy_fallback_reason": passenger["fallback_reason"],
                "passenger_proxy_reference_period": passenger["reference_period"],
                "passenger_proxy_source_key": passenger["source_key"],
                "passenger_proxy_future_data_used": passenger["future_data_used"],
                "passenger_proxy_missing_reason": passenger["missing_reason"],
                "passenger_proxy_attempted_levels": passenger["attempted_levels"],
                "passenger_target_period": passenger["passenger_target_period"],
                "passenger_source_period": passenger["passenger_source_period"],
                "passenger_period_end": passenger["passenger_period_end"],
                "passenger_lag_months": passenger["passenger_lag_months"],
                "passenger_requested_level": passenger["passenger_requested_level"],
                "passenger_used_level": passenger["passenger_used_level"],
                "passenger_evidence_status": passenger["passenger_evidence_status"],
                "passenger_missing_reason": passenger["passenger_missing_reason"],
                "passenger_support_count": passenger["passenger_support_count"],
                "passenger_source_dataset": passenger["passenger_source_dataset"],
                "passenger_measure_filter": passenger["passenger_measure_filter"],
                "passenger_future_data_used": passenger["passenger_future_data_used"],
                "seat_capacity": passenger["seat_capacity"],
                "seat_capacity_level": passenger["seat_capacity_level"],
                "seat_capacity_support": passenger["seat_capacity_support"],
                "seat_capacity_evidence_status": passenger["seat_capacity_evidence_status"],
                "load_factor": passenger["load_factor"],
                "load_factor_support": passenger["load_factor_support"],
                "load_factor_evidence_status": passenger["load_factor_evidence_status"],
                "connection_pressure_support": passenger["connection_pressure_support"],
                "connection_pressure_level": passenger["connection_pressure_level"],
                "connection_pressure_evidence_status": passenger["connection_pressure_evidence_status"],
                "connection_pressure_missing_reason": passenger["connection_pressure_missing_reason"],
                "rebooking_scarcity_support": passenger["rebooking_scarcity_support"],
                "rebooking_scarcity_level": passenger["rebooking_scarcity_level"],
                "rebooking_scarcity_evidence_status": passenger["rebooking_scarcity_evidence_status"],
                "rebooking_scarcity_missing_reason": passenger["rebooking_scarcity_missing_reason"],
                "_passenger_source_record_ids": passenger["source_record_ids"],
                "_passenger_raw_files": passenger["raw_files"],
                "_passenger_raw_hashes": passenger["raw_hashes"],
            })
        except Exception:
            pass
        try:
            airport_key = str(row["airport"])
            if airport_key not in airport_cache:
                try:
                    airport_cache[airport_key] = airport_reference.resolve(airport_key)
                except Exception as error:
                    airport_cache[airport_key] = error
            airport = airport_cache[airport_key]
            if isinstance(airport, Exception):
                raise airport
            values.update({
                "runway_count": float(airport.get("runway_count", np.nan)),
                "infrastructure_flexibility": float(airport.get("infrastructure_flexibility", np.nan)),
                "airport_scale": float(airport.get("airport_scale", np.nan)),
                "_infrastructure_fallback_level": str(airport.get("infrastructure_fallback_level", "")),
                "_airport_source_version": str(airport.get("source_version", "")),
            })
        except Exception:
            pass
        rows.append(values)
    return pd.concat([snapshots.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def finalize_snapshot_quality(snapshots: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    output = snapshots.copy()
    features = [column for column in cfg["schema"]["evidence_completeness_features"] if column in output.columns]
    present = output[features].notna()
    output["evidence_completeness"] = present.mean(axis=1)
    output["observed_feature_count"] = present.sum(axis=1).astype(int)
    output["causally_interpolated_count"] = output["state_is_imputed"].fillna(False).astype(int)
    output["calibration_imputed_count"] = output["weather_imputed"].fillna(False).astype(int)
    output["structural_missing_count"] = 0
    output["temporal_missing_count"] = (~present).sum(axis=1).astype(int)

    primary_stages = set(cfg["snapshots"]["primary_stage_map"].values())
    balanced: dict[str, bool] = {}
    for episode_id, group in output[output["is_primary_snapshot"]].groupby("episode_id"):
        counts = group.groupby("snapshot_stage").size().to_dict()
        balanced[episode_id] = bool(
            all(counts.get(stage, 0) == 1 for stage in primary_stages)
            and group["snapshot_valid"].all()
            and group["split"].nunique() == 1
            and (group["airport"] == group["destination"]).all()
        )
    output["balanced_primary_cohort"] = output["episode_id"].map(balanced).fillna(False).astype(bool)
    return output
