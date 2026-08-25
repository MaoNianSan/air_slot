"""Field lineage, unresolved semantics, and upstream traces for Data Gate A."""

from __future__ import annotations

from collections import Counter

from model.M1.data import FEATURE_NAMES_V2, V2_WEATHER_FIELDS

NOAA_RAW = {
    "temperature_c": "TMP",
    "dewpoint_c": "DEW",
    "wind_direction_deg": "WND",
    "wind_speed_mps": "WND",
    "qnh_hpa": "REM",
    "visibility_m": "VIS",
    "ceiling_base_m": "CIG",
}


def lineage_rows(train_stats: list[dict]) -> list[dict]:
    stats = {row["feature"]: row for row in train_stats}
    records = []
    for name in FEATURE_NAMES_V2:
        if name.startswith("state."):
            source = "bts_ontime"
            raw = "ArrTime;DepTime;WheelsOff"
            canonical = "realized_operational_event"
            pre_output = "decision_node.operational_stage"
            unit = "binary"
            transform = "declared_replay_event_to_realized_state_flag"
            availability = "DECLARED_EVENT_TIME_REPLAY_CUTOFF_GATED"
            risk = "LOW"
            decision = "KEEP_MODEL_FEATURE"
            fit = False
        elif "weather." in name:
            field = next(
                (field for field in V2_WEATHER_FIELDS if field in name),
                "observation_age",
            )
            source = "noaa_isd"
            raw = NOAA_RAW.get(field, "DATE")
            canonical = "current_weather"
            pre_output = f"current_weather.{field}"
            unit = "canonical_or_binary"
            transform = "current/delta/cumulative_mean/mask/one_hot"
            availability = "event_time_plus_5min_replay_lag_max_age_60"
            fit = name.startswith("weather.") and not name.endswith(
                (".sin", ".cos", "_mask")
            )
            if field == "wind_direction_deg" and name.startswith(("delta.", "ar.")):
                risk, decision = "HIGH", "REMOVE_CIRCULAR_LINEAR_FEATURE"
            elif name.endswith("unlimited_mask"):
                risk, decision = "LOW", "KEEP_MODEL_FEATURE"
            elif name.endswith("derived_missing_mask"):
                risk, decision = "LOW", "KEEP_MODEL_FEATURE"
            else:
                risk, decision = "MEDIUM", "KEEP_MODEL_FEATURE"
        elif "schedule." in name:
            source = "bts_ontime+timezone_reference"
            raw = "FlightDate;CRSDepTime;iata;timezone"
            canonical = "scheduled_departure_utc"
            pre_output = "schedule_reference.scheduled_departure_utc"
            unit = "minutes_or_binary"
            transform = "UTC_countdown_then_train_standardize/delta/mask"
            availability = "SCHEDULE_REFERENCE_ASSUMPTION"
            risk = "LOW"
            fit = "missing_mask" not in name
            decision = (
                "REMOVE_NO_INFORMATION"
                if name.startswith("delta.schedule")
                else "KEEP_MODEL_FEATURE"
            )
        elif name == "node.spacing_minutes":
            source = "PRE rolling grid"
            raw = "decision_time"
            canonical = "decision_node"
            pre_output = "decision_node.decision_time"
            unit = "minutes"
            transform = "train_standardize"
            availability = "BY_CONSTRUCTION"
            risk = "LOW"
            fit = True
            decision = "REMOVE_NO_INFORMATION"
        else:
            source = "PRE registry/state"
            raw = "NONE"
            canonical = "evidence_or_support"
            pre_output = "evidence/support metadata"
            unit = "binary"
            transform = "one_hot"
            availability = "PRE_ADMISSIBILITY"
            risk = "LOW"
            fit = False
            decision = (
                "REMOVE_NO_INFORMATION"
                if stats[name]["constant"]
                else "KEEP_MODEL_FEATURE"
            )
        if decision == "KEEP_MODEL_FEATURE" and (
            stats[name]["constant"] or stats[name]["near_constant"]
        ):
            decision = "REMOVE_NO_INFORMATION"
        records.append(
            {
                "SOURCE": source,
                "RAW_COLUMN": raw,
                "CANONICAL_FIELD": canonical,
                "PRE_OUTPUT": pre_output,
                "M1_FIELD": name,
                "ROLE": "DYNAMIC_MODEL_FEATURE",
                "DTYPE": "float32",
                "UNIT": unit,
                "TRANSFORMATION": transform,
                "MISSING_RULE": "zero_with_mask_or_not_applicable",
                "AVAILABILITY_RULE": availability,
                "TRAIN_FIT_REQUIRED": fit,
                "LEAKAGE_RISK": risk,
                "FEATURE_DECISION": decision,
            }
        )
    for name, raw, pre_output in (
        (
            "turnaround_reference_minutes",
            "DepTime;ArrTime",
            "turnaround_reference.value",
        ),
        ("taxi_reference_minutes", "TaxiOut", "taxi_reference.value"),
    ):
        records.append(
            {
                "SOURCE": "bts_ontime_train_frozen_reference",
                "RAW_COLUMN": raw,
                "CANONICAL_FIELD": name,
                "PRE_OUTPUT": pre_output,
                "M1_FIELD": name,
                "ROLE": "STATIC_MODEL_FEATURE",
                "DTYPE": "float32",
                "UNIT": "minutes",
                "TRANSFORMATION": "train_frozen_median_with_declared_fallback",
                "MISSING_RULE": "ABSTAIN_IF_NO_REFERENCE_CELL",
                "AVAILABILITY_RULE": "TRAIN_FROZEN_REFERENCE_ONLY",
                "TRAIN_FIT_REQUIRED": True,
                "LEAKAGE_RISK": "LOW",
                "FEATURE_DECISION": "KEEP_MODEL_FEATURE",
            }
        )
    for name in (
        "route_context",
        "carrier_context",
        "aircraft_identity",
        "schedule_reference",
    ):
        records.append(
            {
                "SOURCE": "bts_ontime",
                "RAW_COLUMN": ("Origin;Dest;Reporting_Airline;Tail_Number;CRSDepTime"),
                "CANONICAL_FIELD": name,
                "PRE_OUTPUT": name,
                "M1_FIELD": name,
                "ROLE": "IDENTITY_CONTEXT_ONLY",
                "DTYPE": "typed_context",
                "UNIT": "identity_or_UTC",
                "TRANSFORMATION": "retained_without_ordinal_encoding",
                "MISSING_RULE": "ABSTAIN",
                "AVAILABILITY_RULE": "SCHEDULE_REFERENCE_ASSUMPTION",
                "TRAIN_FIT_REQUIRED": False,
                "LEAKAGE_RISK": "LOW",
                "FEATURE_DECISION": "KEEP_CONTEXT_ONLY",
            }
        )
    for name, raw in (
        ("T_IB_A00", "ArrTime;ArrDelay;ArrDelayMinutes(reporting_only)"),
        ("D_OB", "DepTime;DepDelay;DepDelayMinutes(reporting_only);CRSDepTime"),
        ("D_TX", "TaxiOut"),
    ):
        records.append(
            {
                "SOURCE": "bts_ontime",
                "RAW_COLUMN": raw,
                "CANONICAL_FIELD": "realized_operational_event",
                "PRE_OUTPUT": "EVAL_OUTCOME/TRAIN_LABEL_ONLY",
                "M1_FIELD": name,
                "ROLE": "TRAIN_LABEL",
                "DTYPE": "float_minutes_or_UTC",
                "UNIT": "minutes_or_UTC",
                "TRANSFORMATION": "stage_gated_v2_label",
                "MISSING_RULE": "ABSTAIN",
                "AVAILABILITY_RULE": "POSTHOC_ONLY",
                "TRAIN_FIT_REQUIRED": False,
                "LEAKAGE_RISK": "LOW_IF_LABEL_ONLY",
                "FEATURE_DECISION": "KEEP_LABEL",
            }
        )
    return records


def feature_decisions(rows: list[dict]) -> dict[str, int]:
    return dict(Counter(row["FEATURE_DECISION"] for row in rows))
