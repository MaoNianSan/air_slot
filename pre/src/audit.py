from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd


STATE_OBSERVED = {"current_latitude", "current_longitude", "current_altitude", "current_velocity", "vertical_rate"}
STATE_DERIVED = {
    "trajectory_coverage", "state_observation_age", "state_record_count", "state_lookback_minutes",
    "state_source_coverage", "state_source_coverage_status", "state_is_imputed",
    "state_imputation_method", "state_imputation_gap_minutes",
}
WEATHER = {
    "wind_speed", "wind_gust", "visibility", "ceiling", "precipitation_flag", "weather_code",
    "temperature_dewpoint_spread", "metar_age",
}
FLOW = {"airport_flow_pressure"}
AGGREGATE = {"continuity_exposure", "turnaround_margin", "airport_scale", "estimated_passenger_load", "connection_pressure_proxy", "rebooking_scarcity_proxy"}
PASSENGER_PROXY = {
    "seat_capacity",
    "load_factor",
    "estimated_passenger_load",
    "connection_pressure_proxy",
    "rebooking_scarcity_proxy",
}
STATIC = {"runway_count", "infrastructure_flexibility"}
RULE_DERIVED = {"episode_capacity_margin", "episode_ops_margin", "lead_time_margin", "execution_window_margin"}
DERIVED_KEYS = {
    "elapsed_ratio", "snapshot_ratio", "snapshot_stage", "airport", "origin", "destination",
    "month", "time_bin", "aircraft_group",
}


def _value_type(value: Any) -> str:
    if isinstance(value, (bool, np.bool_)):
        return "bool"
    if isinstance(value, (int, np.integer)):
        return "int"
    if isinstance(value, (float, np.floating)):
        return "float"
    if isinstance(value, pd.Timestamp):
        return "timestamp"
    return "string"


def _audit_record(row: pd.Series, feature: str, cfg: dict[str, Any]) -> dict[str, Any]:
    value = row.get(feature)
    missing = bool(pd.isna(value)) if not isinstance(value, (list, dict)) else False
    evidence = "DERIVED"
    imputation = "NOT_IMPUTED"
    missing_reason = ""
    event_time = row["decision_time_utc"]
    availability_time = row["decision_time_utc"]
    source = "PRE_DERIVED"
    standard = "ARR_CS"
    source_version = cfg["schema_version"]
    raw_file = ""
    raw_hash = ""
    source_ids = "[]"
    fallback = ""
    cell = 0

    if feature in STATE_OBSERVED:
        evidence = "OBSERVED" if not missing else "UNOBSERVED"
        event_time = row.get("_state_event_time", pd.NaT)
        availability_time = row.get("_state_availability_time", pd.NaT)
        source = "OPEN_SKY_STATE_VECTOR"
        standard = "OPEN_SKY_SCIENTIFIC"
        raw_file = str(row.get("_state_raw_file", ""))
        raw_hash = str(row.get("_state_raw_hash", ""))
        source_ids = json.dumps([str(row.get("_state_source_record_ids", ""))])
        missing_reason = str(row.get("_state_missing_reason", "")) if missing else ""
        if bool(row.get("state_is_imputed", False)):
            imputation = "CAUSAL_IMPUTED"
            evidence = "DERIVED"
    elif feature in STATE_DERIVED:
        source = "OPEN_SKY_STATE_VECTOR_WINDOW"
        missing_reason = str(row.get("_state_missing_reason", "")) if missing else ""
        if feature.startswith("state_imputation") or feature == "state_is_imputed":
            imputation = "CAUSAL_IMPUTED" if bool(row.get("state_is_imputed", False)) else "NOT_IMPUTED"
    elif feature in WEATHER:
        evidence = str(row.get("weather_evidence_status", "UNOBSERVED"))
        source = str(row.get("weather_source", "UNOBSERVED"))
        standard = "METAR"
        event_time = row.get("_weather_event_time", pd.NaT)
        availability_time = row.get("_weather_availability_time", pd.NaT)
        raw_file = str(row.get("_weather_raw_file", ""))
        raw_hash = str(row.get("_weather_raw_hash", ""))
        source_ids = json.dumps([str(row.get("_weather_source_record_ids", ""))])
        fallback = str(row.get("_weather_fallback_level", ""))
        cell = int(row.get("_weather_cell_size", 0) or 0)
        if bool(row.get("weather_imputed", False)):
            imputation = "CALIBRATION_IMPUTED"
        missing_reason = str(row.get("weather_missing_reason", "")) if missing or bool(row.get("weather_imputed", False)) else ""
    elif feature in FLOW:
        evidence = str(row.get("flow_evidence_status", "UNOBSERVED"))
        source = "OPEN_SKY_AIRPORT_FLOW"
        standard = "OPEN_SKY_SCIENTIFIC"
        missing_reason = str(row.get("flow_missing_reason", "")) if missing else ""
    elif feature in PASSENGER_PROXY:
        status_fields = {
            "seat_capacity": "seat_capacity_evidence_status",
            "load_factor": "load_factor_evidence_status",
            "estimated_passenger_load": "passenger_proxy_evidence_status",
            "connection_pressure_proxy": "connection_pressure_evidence_status",
            "rebooking_scarcity_proxy": "rebooking_scarcity_evidence_status",
        }
        level_fields = {
            "seat_capacity": "seat_capacity_level",
            "load_factor": "passenger_proxy_level",
            "estimated_passenger_load": "passenger_proxy_level",
            "connection_pressure_proxy": "connection_pressure_level",
            "rebooking_scarcity_proxy": "rebooking_scarcity_level",
        }
        support_fields = {
            "seat_capacity": "seat_capacity_support",
            "load_factor": "load_factor_support",
            "estimated_passenger_load": "passenger_proxy_support",
            "connection_pressure_proxy": "connection_pressure_support",
            "rebooking_scarcity_proxy": "rebooking_scarcity_support",
        }
        reason_fields = {
            "seat_capacity": "passenger_proxy_missing_reason",
            "load_factor": "passenger_proxy_missing_reason",
            "estimated_passenger_load": "passenger_proxy_missing_reason",
            "connection_pressure_proxy": "connection_pressure_missing_reason",
            "rebooking_scarcity_proxy": "rebooking_scarcity_missing_reason",
        }
        evidence = str(row.get(status_fields[feature], "UNSUPPORTED"))
        source = "EUROSTAT_MONTHLY_AND_FROZEN_TRAINING_PROXY"
        standard = "EUROSTAT_SDMX_AND_OPEN_SKY_SCIENTIFIC"
        source_version = "EUROSTAT_2022_CANONICAL_MEASURES"
        fallback = str(row.get(level_fields[feature], "UNSUPPORTED"))
        cell = int(row.get(support_fields[feature], 0) or 0)
        missing_reason = str(row.get(reason_fields[feature], "UNKNOWN")) if missing else ""
        raw_file = str(row.get("_passenger_raw_files", "[]"))
        raw_hash = str(row.get("_passenger_raw_hashes", "[]"))
        source_ids = str(row.get("_passenger_source_record_ids", "[]"))
        reference_period = str(row.get("passenger_proxy_reference_period", ""))
        if reference_period:
            period_end = pd.Period(reference_period, freq="M").end_time.tz_localize("UTC")
            event_time = period_end
            availability_time = period_end
        imputation = "FROZEN_REFERENCE_IMPUTED" if evidence in {"SUPPORTED_PROXY", "FALLBACK_PROXY"} else "NOT_IMPUTED"
    elif feature in AGGREGATE:
        evidence = "AGGREGATE_PROXY" if not missing else "UNOBSERVED"
        source = "TRAINING_REFERENCE"
        fallback = str(row.get("_turnaround_fallback_level", ""))
        cell = int(row.get("_turnaround_cell_size", 0) or 0)
        imputation = "FROZEN_REFERENCE_IMPUTED"
        missing_reason = "SOURCE_COVERAGE_GAP" if missing else ""
    elif feature in STATIC:
        fallback = str(row.get("_infrastructure_fallback_level", ""))
        source_version = str(row.get("_airport_source_version", ""))
        source = "OURAIRPORTS"
        standard = "AIXM_ALIGNED_PROXY"
        evidence = "AGGREGATE_PROXY" if "MEDIAN" in fallback else "DERIVED"
        imputation = "FROZEN_REFERENCE_IMPUTED" if evidence == "AGGREGATE_PROXY" else "NOT_IMPUTED"
        missing_reason = "SOURCE_NOT_PROVIDED" if missing else ""
    elif feature in RULE_DERIVED:
        evidence = "RULE_GENERATED" if feature == "episode_ops_margin" else "DERIVED"
        source = "PROJECT_RULE"
        standard = "A_CDM_WASG_SEMANTIC"
        missing_reason = "RECORD_EXPECTED_BUT_MISSING" if missing else ""
    elif feature in DERIVED_KEYS:
        source = "FLIGHTLIST_AND_PROJECT_RULE"
    elif missing:
        evidence = "UNOBSERVED"
        missing_reason = "RECORD_EXPECTED_BUT_MISSING"

    factual = evidence in {"OBSERVED", "DERIVED"}
    available = True if not factual else bool(pd.notna(availability_time) and availability_time <= row["decision_time_utc"])
    if feature in PASSENGER_PROXY:
        available = not bool(row.get("passenger_proxy_future_data_used", False))
    return {
        "episode_id": row["episode_id"],
        "snapshot_id": row["snapshot_id"],
        "feature_name": feature,
        "feature_value_type": _value_type(value),
        "evidence_status": evidence,
        "imputation_status": imputation,
        "missing_reason": missing_reason,
        "event_time": event_time,
        "availability_time": availability_time,
        "decision_time": row["decision_time_utc"],
        "ingested_time": pd.Timestamp.now(tz="UTC"),
        "available_by_t": available,
        "source": source,
        "source_standard": standard,
        "source_version": source_version,
        "raw_file": raw_file,
        "raw_file_hash": raw_hash,
        "source_record_ids": source_ids,
        "generation_rule": f"PRE_{feature.upper()}_V1",
        "generation_config_hash": cfg["config_hash"],
        "quality_flag": "missing" if missing else evidence.lower(),
        "fallback_level": fallback,
        "cell_size": cell,
    }


def build_evidence_audit(snapshots: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    aliases = cfg["schema"].get("aliases", {})
    requested = cfg["schema"]["m1_required_inputs"]["continuous"] + cfg["schema"]["m1_required_inputs"]["categorical"]
    features = [aliases.get(feature, feature) for feature in requested]
    features += [
        "state_source_coverage_status", "state_is_imputed", "state_imputation_method",
        "state_imputation_gap_minutes", "infrastructure_flexibility", "episode_capacity_margin",
        "episode_ops_margin",
        "estimated_passenger_load", "connection_pressure_proxy", "rebooking_scarcity_proxy",
        "seat_capacity", "load_factor",
    ]
    features = list(dict.fromkeys(features))
    if snapshots.empty:
        return pd.DataFrame()
    base_episode = pd.Categorical(snapshots["episode_id"])
    base_snapshot = pd.Categorical(snapshots["snapshot_id"])
    decision = pd.to_datetime(snapshots["decision_time_utc"], utc=True)
    ingested = pd.Timestamp.now(tz="UTC")

    def values(name: str, default: Any = pd.NA) -> pd.Series:
        return snapshots[name].reset_index(drop=True) if name in snapshots else pd.Series(default, index=np.arange(len(snapshots)))

    def string(name: str, default: str = "") -> pd.Series:
        return values(name, default).astype("string").fillna(default)

    blocks: list[pd.DataFrame] = []
    for feature in features:
        feature_values = values(feature)
        missing = feature_values.isna()
        evidence: Any = pd.Series("DERIVED", index=np.arange(len(snapshots)), dtype="string")
        imputation: Any = pd.Series("NOT_IMPUTED", index=np.arange(len(snapshots)), dtype="string")
        missing_reason: Any = pd.Series("", index=np.arange(len(snapshots)), dtype="string")
        event_time = decision.reset_index(drop=True).copy()
        availability_time = decision.reset_index(drop=True).copy()
        source: Any = pd.Series("PRE_DERIVED", index=np.arange(len(snapshots)), dtype="string")
        standard: Any = pd.Series("ARR_CS", index=np.arange(len(snapshots)), dtype="string")
        source_version: Any = pd.Series(cfg["schema_version"], index=np.arange(len(snapshots)), dtype="string")
        raw_file: Any = pd.Series("", index=np.arange(len(snapshots)), dtype="string")
        raw_hash: Any = pd.Series("", index=np.arange(len(snapshots)), dtype="string")
        source_ids: Any = pd.Series("[]", index=np.arange(len(snapshots)), dtype="string")
        fallback: Any = pd.Series("", index=np.arange(len(snapshots)), dtype="string")
        cell = pd.Series(0, index=np.arange(len(snapshots)), dtype="int64")

        if feature in STATE_OBSERVED:
            evidence = pd.Series(np.where(missing, "UNOBSERVED", "OBSERVED"), dtype="string")
            event_time = pd.to_datetime(values("_state_event_time"), utc=True, errors="coerce")
            availability_time = pd.to_datetime(values("_state_availability_time"), utc=True, errors="coerce")
            source[:] = "OPEN_SKY_STATE_VECTOR"; standard[:] = "OPEN_SKY_SCIENTIFIC"
            raw_file = string("_state_raw_file"); raw_hash = string("_state_raw_hash")
            source_ids = string("_state_source_record_ids").map(lambda value: json.dumps([str(value)]))
            missing_reason = string("_state_missing_reason").where(missing, "")
            state_imputed = values("state_is_imputed", False).fillna(False).astype(bool)
            imputation = pd.Series(np.where(state_imputed, "CAUSAL_IMPUTED", "NOT_IMPUTED"), dtype="string")
            evidence = evidence.mask(state_imputed, "DERIVED")
        elif feature in STATE_DERIVED:
            source[:] = "OPEN_SKY_STATE_VECTOR_WINDOW"
            missing_reason = string("_state_missing_reason").where(missing, "")
            if feature.startswith("state_imputation") or feature == "state_is_imputed":
                state_imputed = values("state_is_imputed", False).fillna(False).astype(bool)
                imputation = pd.Series(np.where(state_imputed, "CAUSAL_IMPUTED", "NOT_IMPUTED"), dtype="string")
        elif feature in WEATHER:
            evidence = string("weather_evidence_status", "UNOBSERVED")
            source = string("weather_source", "UNOBSERVED"); standard[:] = "METAR"
            event_time = pd.to_datetime(values("_weather_event_time"), utc=True, errors="coerce")
            availability_time = pd.to_datetime(values("_weather_availability_time"), utc=True, errors="coerce")
            raw_file = string("_weather_raw_file"); raw_hash = string("_weather_raw_hash")
            source_ids = string("_weather_source_record_ids").map(lambda value: json.dumps([str(value)]))
            fallback = string("_weather_fallback_level")
            cell = pd.to_numeric(values("_weather_cell_size", 0), errors="coerce").fillna(0).astype("int64")
            weather_imputed = values("weather_imputed", False).fillna(False).astype(bool)
            imputation = pd.Series(np.where(weather_imputed, "CALIBRATION_IMPUTED", "NOT_IMPUTED"), dtype="string")
            missing_reason = string("weather_missing_reason").where(missing | weather_imputed, "")
        elif feature in FLOW:
            evidence = string("flow_evidence_status", "UNOBSERVED")
            source[:] = "OPEN_SKY_AIRPORT_FLOW"; standard[:] = "OPEN_SKY_SCIENTIFIC"
            missing_reason = string("flow_missing_reason").where(missing, "")
        elif feature in PASSENGER_PROXY:
            status_fields = {"seat_capacity": "seat_capacity_evidence_status", "load_factor": "load_factor_evidence_status", "estimated_passenger_load": "passenger_proxy_evidence_status", "connection_pressure_proxy": "connection_pressure_evidence_status", "rebooking_scarcity_proxy": "rebooking_scarcity_evidence_status"}
            level_fields = {"seat_capacity": "seat_capacity_level", "load_factor": "passenger_proxy_level", "estimated_passenger_load": "passenger_proxy_level", "connection_pressure_proxy": "connection_pressure_level", "rebooking_scarcity_proxy": "rebooking_scarcity_level"}
            support_fields = {"seat_capacity": "seat_capacity_support", "load_factor": "load_factor_support", "estimated_passenger_load": "passenger_proxy_support", "connection_pressure_proxy": "connection_pressure_support", "rebooking_scarcity_proxy": "rebooking_scarcity_support"}
            reason_fields = {"seat_capacity": "passenger_proxy_missing_reason", "load_factor": "passenger_proxy_missing_reason", "estimated_passenger_load": "passenger_proxy_missing_reason", "connection_pressure_proxy": "connection_pressure_missing_reason", "rebooking_scarcity_proxy": "rebooking_scarcity_missing_reason"}
            evidence = string(status_fields[feature], "UNSUPPORTED")
            source[:] = "EUROSTAT_MONTHLY_AND_FROZEN_TRAINING_PROXY"; standard[:] = "EUROSTAT_SDMX_AND_OPEN_SKY_SCIENTIFIC"; source_version[:] = "EUROSTAT_2022_CANONICAL_MEASURES"
            fallback = string(level_fields[feature], "UNSUPPORTED")
            cell = pd.to_numeric(values(support_fields[feature], 0), errors="coerce").fillna(0).astype("int64")
            missing_reason = string(reason_fields[feature], "UNKNOWN").where(missing, "")
            raw_file = string("_passenger_raw_files", "[]"); raw_hash = string("_passenger_raw_hashes", "[]"); source_ids = string("_passenger_source_record_ids", "[]")
            period = string("passenger_proxy_reference_period")
            period_map = {}
            for value in period[period.ne("")].unique():
                period_map[value] = pd.Period(value, freq="M").end_time.tz_localize("UTC")
            period_time = pd.to_datetime(period.map(period_map), utc=True, errors="coerce")
            event_time = event_time.where(period.eq(""), period_time); availability_time = availability_time.where(period.eq(""), period_time)
            imputation = pd.Series(np.where(evidence.isin(["SUPPORTED_PROXY", "FALLBACK_PROXY"]), "FROZEN_REFERENCE_IMPUTED", "NOT_IMPUTED"), dtype="string")
        elif feature in AGGREGATE:
            evidence = pd.Series(np.where(missing, "UNOBSERVED", "AGGREGATE_PROXY"), dtype="string")
            source[:] = "TRAINING_REFERENCE"; fallback = string("_turnaround_fallback_level")
            cell = pd.to_numeric(values("_turnaround_cell_size", 0), errors="coerce").fillna(0).astype("int64")
            imputation[:] = "FROZEN_REFERENCE_IMPUTED"; missing_reason = pd.Series(np.where(missing, "SOURCE_COVERAGE_GAP", ""), dtype="string")
        elif feature in STATIC:
            fallback = string("_infrastructure_fallback_level"); source_version = string("_airport_source_version")
            source[:] = "OURAIRPORTS"; standard[:] = "AIXM_ALIGNED_PROXY"
            evidence = pd.Series(np.where(fallback.str.contains("MEDIAN", na=False), "AGGREGATE_PROXY", "DERIVED"), dtype="string")
            imputation = pd.Series(np.where(evidence.eq("AGGREGATE_PROXY"), "FROZEN_REFERENCE_IMPUTED", "NOT_IMPUTED"), dtype="string")
            missing_reason = pd.Series(np.where(missing, "SOURCE_NOT_PROVIDED", ""), dtype="string")
        elif feature in RULE_DERIVED:
            evidence[:] = "RULE_GENERATED" if feature == "episode_ops_margin" else "DERIVED"
            source[:] = "PROJECT_RULE"; standard[:] = "A_CDM_WASG_SEMANTIC"
            missing_reason = pd.Series(np.where(missing, "RECORD_EXPECTED_BUT_MISSING", ""), dtype="string")
        elif feature in DERIVED_KEYS:
            source[:] = "FLIGHTLIST_AND_PROJECT_RULE"
        else:
            evidence = evidence.mask(missing, "UNOBSERVED")
            missing_reason = missing_reason.mask(missing, "RECORD_EXPECTED_BUT_MISSING")

        factual = evidence.isin(["OBSERVED", "DERIVED"])
        available = (~factual) | (availability_time.notna() & availability_time.le(decision.reset_index(drop=True)))
        if feature in PASSENGER_PROXY:
            available = ~values("passenger_proxy_future_data_used", False).fillna(False).astype(bool)
        if pd.api.types.is_bool_dtype(feature_values.dtype):
            value_type = "bool"
        elif pd.api.types.is_integer_dtype(feature_values.dtype):
            value_type = "int"
        elif pd.api.types.is_numeric_dtype(feature_values.dtype):
            value_type = "float"
        elif pd.api.types.is_datetime64_any_dtype(feature_values.dtype):
            value_type = "timestamp"
        else:
            value_type = "string"
        block = pd.DataFrame({
            "episode_id": base_episode, "snapshot_id": base_snapshot, "feature_name": feature,
            "feature_value_type": value_type, "evidence_status": evidence, "imputation_status": imputation,
            "missing_reason": missing_reason, "event_time": event_time, "availability_time": availability_time,
            "decision_time": decision.reset_index(drop=True), "ingested_time": ingested, "available_by_t": available,
            "source": source, "source_standard": standard, "source_version": source_version,
            "raw_file": raw_file, "raw_file_hash": raw_hash, "source_record_ids": source_ids,
            "generation_rule": f"PRE_{feature.upper()}_V1", "generation_config_hash": cfg["config_hash"],
            "quality_flag": pd.Series(np.where(missing, "missing", evidence.str.lower()), dtype="string"),
            "fallback_level": fallback, "cell_size": cell,
        })
        for column in block.select_dtypes(include=["object", "string"]).columns:
            block[column] = block[column].astype("category")
        blocks.append(block)
    result = pd.concat(blocks, ignore_index=True)
    for column in result.select_dtypes(include=["object", "string"]).columns:
        result[column] = result[column].astype("category")
    return result
