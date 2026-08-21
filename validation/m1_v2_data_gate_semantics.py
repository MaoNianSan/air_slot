"""Unresolved column semantics and upstream traces for M1 V2 Data Gate A."""

from __future__ import annotations

from model.M1.data import FEATURE_NAMES_V2, encode_pre_sequence


SPLITS = ("train", "calibration", "development")


def _weather_field_summary(cohorts, field: str) -> dict:
    total = 0
    values = []
    for split in SPLITS:
        for prepared in sorted(
            getattr(cohorts, split), key=lambda item: item.episode.episode_id
        ):
            for state in prepared.states:
                total += 1
                weather = state.current_state.get("current_weather")
                payload = getattr(weather, "value", None)
                value = payload.get(field) if isinstance(payload, dict) else None
                if value is not None:
                    values.append(float(value))
    return {
        "dtype": "float_or_missing",
        "observed_count": len(values),
        "missing_pct": 100.0 * (1.0 - len(values) / max(total, 1)),
        "sample_values": sorted(set(values))[:5],
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def _stage_source_summary(cohorts) -> tuple[list[dict], list[dict]]:
    records = []
    samples = []
    for split in SPLITS:
        for prepared in sorted(
            getattr(cohorts, split), key=lambda item: item.episode.episode_id
        ):
            predecessor = prepared.predecessor_outcome
            successor = prepared.successor_outcome
            records.append(
                {
                    "ArrTime": predecessor.actual_arrival_utc,
                    "DepTime": successor.actual_departure_utc,
                    "WheelsOff": successor.wheels_off_utc,
                    "predecessor_availability": predecessor.actual_arrival_utc,
                    "successor_departure_availability": successor.actual_departure_utc,
                    "successor_wheels_off_availability": successor.wheels_off_utc,
                }
            )
            if len(samples) < 5:
                samples.append(
                    {
                        "split": split,
                        "episode_id": prepared.episode.episode_id,
                        "ArrTime": predecessor.actual_arrival_utc,
                        "DepTime": successor.actual_departure_utc,
                        "WheelsOff": successor.wheels_off_utc,
                    }
                )
    candidates = []
    for name, canonical, source_key in (
        (
            "ArrTime / ArrDelay (signed date disambiguation)",
            "predecessor_outcome.actual_arrival_utc",
            "ArrTime",
        ),
        (
            "DepTime / DepDelay (signed date disambiguation)",
            "successor_outcome.actual_departure_utc",
            "DepTime",
        ),
        (
            "WheelsOff or DepTime + TaxiOut",
            "successor_outcome.wheels_off_utc",
            "WheelsOff",
        ),
    ):
        observed = sum(row[source_key] is not None for row in records)
        candidates.append(
            {
                "column_name": name,
                "canonical_field": canonical,
                "dtype": "timezone_aware_datetime",
                "missing_pct": 100.0 * (1.0 - observed / max(len(records), 1)),
            }
        )
    return candidates, samples


def unresolved_column_queue(cohorts) -> list[dict]:
    stage_candidates, stage_samples = _stage_source_summary(cohorts)
    direction = _weather_field_summary(cohorts, "wind_direction_deg")
    ceiling = _weather_field_summary(cohorts, "ceiling_base_m")
    gust = _weather_field_summary(cohorts, "wind_gust_mps")
    return [
        {
            "Scientific variable": "decision-time operational stage",
            "Candidate fields": stage_candidates,
            "Sample values": stage_samples,
            "Current inference": (
                "PRE stage_at consumes only cutoff-legal declared event-time replay; "
                "the canonical BTS outcome remains POSTHOC_ONLY."
            ),
            "Confidence": "HIGH_ON_LINEAGE_AND_ADMISSIBILITY",
            "Human decision required": "NO",
        },
        {
            "Scientific variable": "wind direction change and AR summary",
            "Candidate fields": [
                {
                    "column_name": "NOAA ISD WND direction component",
                    "canonical_field": "current_weather.wind_direction_deg",
                    **direction,
                }
            ],
            "Sample values": direction["sample_values"],
            "Current inference": (
                "Principal retains sin/cos only; linear direction delta and AR "
                "features are removed."
            ),
            "Confidence": "HIGH",
            "Human decision required": "NO",
        },
        {
            "Scientific variable": "ceiling base versus unlimited sky",
            "Candidate fields": [
                {
                    "column_name": "NOAA ISD CIG",
                    "canonical_field": "current_weather.ceiling_base_m",
                    **ceiling,
                }
            ],
            "Sample values": ceiling["sample_values"],
            "Current inference": (
                "Canonical CIG uses meter units with explicit FINITE, UNLIMITED, "
                "and MISSING status."
            ),
            "Confidence": "HIGH",
            "Human decision required": "NO",
        },
        {
            "Scientific variable": "wind gust speed",
            "Candidate fields": [
                {
                    "column_name": "NO_AUTHORITATIVE_ISD_FIELD_MAPPED",
                    "canonical_field": "current_weather.wind_gust_mps",
                    **gust,
                }
            ],
            "Sample values": gust["sample_values"],
            "Current inference": (
                "NOAA ISD gust is not mapped; the field and its derived principal "
                "features are removed while PRE canonical remains permissive."
            ),
            "Confidence": "HIGH",
            "Human decision required": "NO",
        },
    ]


def upstream_trace_cases(cohorts, normalization) -> list[dict]:
    feature_index = {name: index for index, name in enumerate(FEATURE_NAMES_V2)}
    traced_features = tuple(
        name
        for name in FEATURE_NAMES_V2
        if name.startswith("state.")
    )
    traces = []
    for split in SPLITS:
        selected = None
        for prepared in sorted(
            getattr(cohorts, split), key=lambda item: item.episode.episode_id
        ):
            for index, state in enumerate(prepared.states):
                if state.decision_node.operational_stage.value != "PRE_IB":
                    selected = (prepared, index, state)
                    break
            if selected is not None:
                break
        if selected is None:
            continue
        prepared, index, state = selected
        predecessor = prepared.predecessor_outcome
        successor = prepared.successor_outcome
        encoded = encode_pre_sequence(prepared.states[: index + 1], normalization)[-1]
        traces.append(
            {
                "split": split,
                "RAW SOURCE ID": {
                    "predecessor_bts_row": predecessor.provenance.source_record_id,
                    "successor_bts_row": successor.provenance.source_record_id,
                },
                "canonical record ID": {
                    "predecessor_outcome": predecessor.canonical_record_id,
                    "successor_outcome": successor.canonical_record_id,
                },
                "episode ID": prepared.episode.episode_id,
                "decision node ID": state.decision_node.decision_node_id,
                "PRE published variable": {
                    "name": "decision_node.operational_stage",
                    "value": state.decision_node.operational_stage.value,
                    "source_values": {
                        "predecessor_actual_arrival_utc": predecessor.actual_arrival_utc,
                        "successor_actual_departure_utc": successor.actual_departure_utc,
                        "successor_wheels_off_utc": successor.wheels_off_utc,
                    },
                    "source_availability_basis": {
                        "predecessor": predecessor.availability_basis.value,
                        "successor": successor.availability_basis.value,
                    },
                    "declared_availability_checks": {
                        "predecessor_ib": predecessor.actual_arrival_utc <= state.decision_node.information_cutoff,
                        "successor_ob": successor.actual_departure_utc <= state.decision_node.information_cutoff,
                        "successor_to": successor.wheels_off_utc <= state.decision_node.information_cutoff,
                    },
                },
                "model encoded value": {
                    name: float(encoded[feature_index[name]])
                    for name in traced_features
                },
                "experiment consumption": (
                    "M1 V2 recurrent state consumed by downstream M2/Exp paths"
                ),
                "first semantic deviation": (
                    "PRE rolling-node stage construction uses declared event-time "
                    "replay projection; source outcome remains posthoc."
                ),
            }
        )
    return traces


def potential_downstream_error_sources(time_checks: dict, static: dict) -> list[dict]:
    return [
        {
            "variable_or_step": "scheduled departure parsing",
            "current_status": time_checks["hhmm_parser"],
            "possible_affected_modules": ["M1", "Exp3", "Exp4"],
            "risk": "LOW",
        },
        {
            "variable_or_step": "operational stage / factual replay availability",
            "current_status": "DECLARED_EVENT_TIME_REPLAY_CUTOFF_GATED",
            "possible_affected_modules": ["PRE", "M1", "M2", "Exp1-Exp4"],
            "risk": "CRITICAL",
        },
        {
            "variable_or_step": "weather normalization",
            "current_status": "FIX_APPLIED_TRAIN_ONLY",
            "possible_affected_modules": ["M1"],
            "risk": "LOW",
        },
        {
            "variable_or_step": "derived weather missing sentinel",
            "current_status": "FIXED_DERIVED_MISSING_PROPAGATION",
            "possible_affected_modules": ["M1", "M2", "Exp1-Exp4"],
            "risk": "HIGH",
        },
        {
            "variable_or_step": "wind direction delta / AR semantics",
            "current_status": "REMOVED_FROM_PRINCIPAL",
            "possible_affected_modules": ["M1", "M2"],
            "risk": "HIGH",
        },
        {
            "variable_or_step": "ceiling unlimited versus missing",
            "current_status": "FIXED_TYPED_STATUS_AND_MASKS",
            "possible_affected_modules": ["PRE", "M1", "M2"],
            "risk": "HIGH",
        },
        {
            "variable_or_step": "wind gust source mapping",
            "current_status": "REMOVED_FROM_PRINCIPAL_NO_AUTHORITATIVE_MAPPING",
            "possible_affected_modules": ["PRE", "M1"],
            "risk": "HIGH",
        },
        {
            "variable_or_step": "static reference cache roundtrip",
            "current_status": "PASS" if static["cache_roundtrip_equal"] else "FAIL",
            "possible_affected_modules": ["M1", "M2"],
            "risk": "LOW" if static["cache_roundtrip_equal"] else "HIGH",
        },
    ]
