from datetime import date, datetime, timedelta, timezone
from typing import Any

from model.common.errors import ContractError
from model.PRE.contracts.canonical import (
    FlightRecord,
    OperationalEventRecord,
    TrajectoryObservation,
)
from model.PRE.episode.event_detection import TrajectoryEventRecord

from .normalization_common import deterministic_id, missing, number, parse_utc, provenance
from .timezone import infer_rollover, local_hhmm_to_utc


def canonicalize_ontime_row(
    row: dict[str, Any], timezones: dict[str, str]
) -> tuple[FlightRecord, OperationalEventRecord]:
    day = date.fromisoformat(str(row["FlightDate"])[:10])
    origin, dest = str(row["Origin"]), str(row["Dest"])
    if origin not in timezones or dest not in timezones:
        raise ContractError("UNKNOWN_AIRPORT_TIMEZONE")
    schedule_dep = local_hhmm_to_utc(day, row.get("CRSDepTime"), timezones[origin])
    schedule_arr = local_hhmm_to_utc(day, row.get("CRSArrTime"), timezones[dest])
    if schedule_dep and schedule_arr:
        schedule_arr = infer_rollover(schedule_dep, schedule_arr)
    flight_parts = {
        key: row.get(key)
        for key in (
            "FlightDate",
            "Reporting_Airline",
            "Flight_Number_Reporting_Airline",
            "Origin",
            "Dest",
        )
    }
    actual = {}
    for key, airport, reference in (
        ("DepTime", origin, schedule_dep),
        ("WheelsOff", origin, schedule_dep),
        ("WheelsOn", dest, schedule_arr),
        ("ArrTime", dest, schedule_arr),
    ):
        value = local_hhmm_to_utc(day, row.get(key), timezones[airport])
        if value and reference:
            value = infer_rollover(reference, value)
        actual[key] = value
    if schedule_dep is None or schedule_arr is None:
        raise ContractError("SCHEDULE_REFERENCE_MISSING")
    raw_id = deterministic_id(
        "raw", {"source": "bts_ontime", **flight_parts, "tail": row.get("Tail_Number")}
    )
    flight_id = deterministic_id("flight", flight_parts)
    schedule = FlightRecord.model_validate({
        "canonical_object_type": "FlightRecord",
        "dataset_instance_id": "data2_2019",
        "canonical_record_id": deterministic_id(
            "canonical-flight", {"raw": raw_id, "role": "schedule"}
        ),
        "flight_id": flight_id,
        "service_date": day,
        "source_flight_id": "|".join(str(value) for value in flight_parts.values()),
        "aircraft_id": None if missing(row.get("Tail_Number"))
        else str(row["Tail_Number"]).strip(),
        "aircraft_id_namespace": "REGISTRATION",
        "carrier_id": None if missing(row.get("Reporting_Airline"))
        else str(row["Reporting_Airline"]).strip(),
        "origin_airport_id": origin,
        "destination_airport_id": dest,
        "scheduled_departure_utc": schedule_dep,
        "scheduled_arrival_utc": schedule_arr,
        "event_time": schedule_dep,
        "availability_time": None,
        "event_start_time": schedule_dep,
        "event_end_time": schedule_arr,
        "schedule_semantics": "CRS_DEPARTURE",
        "availability_basis": "SCHEDULE_REFERENCE_ASSUMPTION",
        "decision_time_role": "FROZEN_REFERENCE",
        "provenance_rule_id": "D2-BTS-SCHEDULE",
        "provenance": provenance("data2_2019", "bts_ontime", raw_id, "D2-BTS-SCHEDULE"),
    })
    dep_delay = number(row.get("DepDelayMinutes"))
    arr_delay = number(row.get("ArrDelayMinutes"))
    taxi_out = number(row.get("TaxiOut"))
    taxi_in = number(row.get("TaxiIn"))
    if dep_delay is not None:
        actual["DepTime"] = schedule_dep + timedelta(minutes=dep_delay)
    if arr_delay is not None:
        actual["ArrTime"] = schedule_arr + timedelta(minutes=arr_delay)
    if actual["DepTime"] is not None and taxi_out is not None:
        actual["WheelsOff"] = actual["DepTime"] + timedelta(minutes=taxi_out)
    if actual["ArrTime"] is not None and taxi_in is not None:
        actual["WheelsOn"] = actual["ArrTime"] - timedelta(minutes=taxi_in)
    actual_times = [value for value in actual.values() if value is not None]
    outcome = OperationalEventRecord.model_validate({
        "canonical_object_type": "OperationalEventRecord",
        "dataset_instance_id": "data2_2019",
        "canonical_record_id": deterministic_id(
            "canonical-event", {"raw": raw_id, "role": "actual"}
        ),
        "flight_id": flight_id,
        "event_type": "COMPLETED_OPERATIONAL_OUTCOME",
        "event_time": min(actual_times) if actual_times else None,
        "availability_time": None,
        "event_time_lower": min(actual_times) if actual_times else None,
        "event_time_upper": max(actual_times) if actual_times else None,
        "actual_departure_utc": actual["DepTime"],
        "wheels_off_utc": actual["WheelsOff"],
        "wheels_on_utc": actual["WheelsOn"],
        "actual_arrival_utc": actual["ArrTime"],
        "taxi_out_minutes": taxi_out,
        "taxi_in_minutes": taxi_in,
        "cancelled": bool(number(row.get("Cancelled")) or 0),
        "diverted": bool(number(row.get("Diverted")) or 0),
        "reconstruction_rule_id": "local_actual_to_utc",
        "decision_time_role": "EVAL_OUTCOME",
        "availability_basis": "POSTHOC_ONLY",
        "provenance_rule_id": "D2-BTS-ACTUAL",
        "quality_flags": tuple(sorted(
            flag for flag, condition in (
                ("ACTUAL_DEPARTURE_DATE_OFFSET_FROM_DELAY_MINUTES", dep_delay is not None),
                ("ACTUAL_ARRIVAL_DATE_OFFSET_FROM_DELAY_MINUTES", arr_delay is not None),
            ) if condition
        )),
        "provenance": provenance("data2_2019", "bts_ontime", raw_id, "D2-BTS-ACTUAL"),
    })
    return schedule, outcome


def canonicalize_flightlist_row(
    row: dict[str, Any]
) -> tuple[FlightRecord, OperationalEventRecord]:
    parts = {
        key: row.get(key)
        for key in ("callsign", "day", "origin", "destination", "icao24")
    }
    first_seen, last_seen = parse_utc(row["firstseen"]), parse_utc(row["lastseen"])
    raw_id = deterministic_id(
        "raw",
        {
            "source": "opensky_flightlist",
            **parts,
            "firstseen": first_seen.isoformat(),
            "lastseen": last_seen.isoformat(),
        },
    )
    flight_id = deterministic_id("flight", parts)
    flight = FlightRecord.model_validate({
        "canonical_object_type": "FlightRecord",
        "dataset_instance_id": "data1_2019",
        "canonical_record_id": deterministic_id(
            "canonical-flight", {"raw": raw_id, "role": "episode"}
        ),
        "flight_id": flight_id,
        "source_flight_id": str(row.get("callsign", "")).strip(),
        "aircraft_id": str(row.get("icao24", "")).lower(),
        "aircraft_id_namespace": "ICAO24",
        "origin_airport_id": None if missing(row.get("origin")) else row.get("origin"),
        "destination_airport_id": None if missing(row.get("destination"))
        else row.get("destination"),
        "event_time": first_seen,
        "availability_time": None,
        "first_seen_utc": first_seen,
        "last_seen_utc": last_seen,
        "event_start_time": first_seen,
        "event_end_time": last_seen,
        "decision_time_role": "EPISODE_CONSTRUCTION",
        "availability_basis": "ARCHIVE_PUBLICATION_RULE",
        "provenance_rule_id": "D1-OPENSKY-FLIGHT",
        "provenance": provenance(
            "data1_2019", "opensky_flightlist", raw_id, "D1-OPENSKY-FLIGHT"
        ),
    })
    event = OperationalEventRecord.model_validate({
        "canonical_object_type": "OperationalEventRecord",
        "dataset_instance_id": "data1_2019",
        "canonical_record_id": deterministic_id(
            "canonical-event", {"raw": raw_id, "role": "proxy-outcome"}
        ),
        "flight_id": flight_id,
        "event_type": "ARCHIVE_FLIGHT_INTERVAL_PROXY",
        "event_time": first_seen,
        "availability_time": None,
        "event_time_lower": first_seen,
        "event_time_upper": last_seen,
        "reconstruction_rule_id": "interval_event_proxy",
        "decision_time_role": "EVAL_OUTCOME",
        "availability_basis": "POSTHOC_ONLY",
        "provenance_rule_id": "D1-OPENSKY-FLIGHT-EVENT",
        "provenance": provenance(
            "data1_2019", "opensky_flightlist", raw_id, "D1-OPENSKY-FLIGHT-EVENT"
        ),
    })
    return flight, event


def canonicalize_state_vector_row(
    row: dict[str, Any], *, replay_lag_minutes: int | None
) -> TrajectoryObservation:
    if replay_lag_minutes is None:
        raise ContractError("REPLAY_LAG_NOT_FROZEN")
    event_time = datetime.fromtimestamp(float(row["time"]), timezone.utc)
    availability_time = event_time + timedelta(minutes=replay_lag_minutes)
    raw_id = deterministic_id(
        "raw",
        {
            "source": "opensky_state_vectors",
            "aircraft": row.get("icao24"),
            "time": row.get("time"),
        },
    )
    values = {
        "canonical_object_type": "TrajectoryObservation",
        "dataset_instance_id": "data1_2019",
        "aircraft_id": str(row["icao24"]).lower(),
        "aircraft_id_namespace": "ICAO24",
        "event_time": event_time,
        "availability_time": availability_time,
        "availability_basis": "REPLAY_EVENT_TIME",
        "provenance_rule_id": "D1-OPENSKY-STATE",
        "decision_time_role": "INFERENCE_EVIDENCE",
        "provenance": provenance(
            "data1_2019", "opensky_state_vectors", raw_id, "D1-OPENSKY-STATE"
        ),
        "latitude_deg": number(row.get("lat")),
        "longitude_deg": number(row.get("lon")),
        "baro_altitude_m": number(row.get("baroaltitude")),
        "geo_altitude_m": number(row.get("geoaltitude")),
        "velocity_mps": number(row.get("velocity")),
        "heading_deg": number(row.get("heading")),
        "vertical_rate_mps": number(row.get("vertrate")),
        "on_ground": None if missing(row.get("onground"))
        else str(row["onground"]).strip().lower() in {"true", "1"},
        "position_time": None if missing(row.get("lastposupdate"))
        else datetime.fromtimestamp(float(row["lastposupdate"]), timezone.utc),
        "contact_time": None if missing(row.get("lastcontact"))
        else datetime.fromtimestamp(float(row["lastcontact"]), timezone.utc),
    }
    values["canonical_record_id"] = deterministic_id(
        "trajectory",
        {"aircraft": values["aircraft_id"], "event_time": event_time.isoformat()},
    )
    return TrajectoryObservation.model_validate(values)


def canonicalize_trajectory_event(
    record: TrajectoryEventRecord, *, flight_id: str | None = None
) -> OperationalEventRecord:
    raw_id = deterministic_id(
        "raw",
        {
            "source": "opensky_state_vectors",
            "aircraft": record.aircraft_id,
            "event_type": record.event_type,
            "event_time": record.event_time.isoformat(),
        },
    )
    return OperationalEventRecord.model_validate({
        "canonical_object_type": "OperationalEventRecord",
        "dataset_instance_id": "data1_2019",
        "canonical_record_id": deterministic_id(
            "canonical-event", {"raw": raw_id, "role": "trajectory"}
        ),
        "flight_id": flight_id,
        "aircraft_id": record.aircraft_id,
        "event_type": f"TRAJECTORY_{record.event_type}",
        "event_time": record.event_time,
        "availability_time": None,
        "event_time_lower": record.event_time,
        "event_time_upper": record.event_time,
        "reconstruction_rule_id": "trajectory_event_detection",
        "decision_time_role": "EVAL_OUTCOME",
        "availability_basis": "POSTHOC_ONLY",
        "provenance_rule_id": "D1-TRAJECTORY-EVENT",
        "quality_flags": record.quality_flags,
        "provenance": provenance(
            "data1_2019", "opensky_state_vectors", raw_id, "D1-TRAJECTORY-EVENT"
        ),
    })
