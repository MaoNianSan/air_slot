import math
import re
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from model.common.errors import ContractError
from .timezone import infer_rollover, local_hhmm_to_utc
from .units import fahrenheit_to_celsius, knots_to_mps, statute_miles_to_m, hundreds_feet_to_m


_MISSING = {"", "M", "NA", "N/A", "NAN", "NONE", "NULL"}


def missing(value: object) -> bool:
    return value is None or str(value).strip().upper() in _MISSING


def number(value: object) -> float | None:
    if missing(value): return None
    result = float(str(value).strip())
    return None if math.isnan(result) else result


def deterministic_id(prefix: str, parts: dict[str, Any]) -> str:
    payload = "|".join(f"{key}={parts[key]}" for key in sorted(parts))
    return f"{prefix}:{sha256(payload.encode('utf-8')).hexdigest()}"


def parse_utc(value: object) -> datetime:
    if isinstance(value, datetime): parsed = value
    else: parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def canonicalize_metar_row(row: dict[str, Any], *, replay_lag_minutes: int | None) -> dict[str, Any]:
    if replay_lag_minutes is None: raise ContractError("REPLAY_LAG_NOT_FROZEN")
    event_time = parse_utc(row["valid"])
    match = re.search(r"(?:^|\s)Q(\d{4})(?:\s|$)", str(row.get("metar", "")))
    converted = {
        "canonical_object_type": "WeatherObservation", "dataset_instance_id": "data1_2019",
        "airport_id": str(row["station"]).strip().upper(), "event_time": event_time,
        "availability_time": event_time + timedelta(minutes=replay_lag_minutes),
        "availability_basis": "REPLAY_EVENT_TIME", "provenance_rule_id": "D1-METAR",
        "temperature_c": None if missing(row.get("tmpf")) else fahrenheit_to_celsius(float(row["tmpf"])),
        "dewpoint_c": None if missing(row.get("dwpf")) else fahrenheit_to_celsius(float(row["dwpf"])),
        "wind_direction_deg": number(row.get("drct")),
        "wind_speed_mps": None if missing(row.get("sknt")) else knots_to_mps(float(row["sknt"])),
        "wind_gust_mps": None if missing(row.get("gust")) else knots_to_mps(float(row["gust"])),
        "visibility_m": None if missing(row.get("vsby")) else statute_miles_to_m(float(row["vsby"])),
        "qnh_hpa": int(match.group(1)) if match else None, "mslp_hpa": None,
        "cloud_cover_codes": tuple(x for x in (row.get("skyc1"), row.get("skyc2"), row.get("skyc3")) if not missing(x)),
        "cloud_base_m": tuple(hundreds_feet_to_m(float(x)) for x in (row.get("skyl1"), row.get("skyl2"), row.get("skyl3")) if not missing(x)),
        "present_weather_codes": None if missing(row.get("wxcodes")) else str(row["wxcodes"]),
        "quality_flags": tuple(sorted([flag for flag, condition in (("QNH_DERIVED_FROM_METAR", bool(match)), ("MSLP_UNSUPPORTED", True)) if condition])),
    }
    converted["canonical_record_id"] = deterministic_id("weather", {"station": converted["airport_id"], "event_time": event_time.isoformat()})
    return converted


def canonicalize_ontime_row(row: dict[str, Any], timezones: dict[str, str]) -> dict[str, Any]:
    day = date.fromisoformat(str(row["FlightDate"])[:10]); origin, dest = str(row["Origin"]), str(row["Dest"])
    if origin not in timezones or dest not in timezones: raise ContractError("UNKNOWN_AIRPORT_TIMEZONE")
    schedule_dep = local_hhmm_to_utc(day, row.get("CRSDepTime"), timezones[origin])
    schedule_arr = local_hhmm_to_utc(day, row.get("CRSArrTime"), timezones[dest])
    if schedule_dep and schedule_arr: schedule_arr = infer_rollover(schedule_dep, schedule_arr)
    flight_parts = {key: row.get(key) for key in ("FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline", "Origin", "Dest")}
    actual = {}
    for key, airport, reference in (("DepTime", origin, schedule_dep), ("WheelsOff", origin, schedule_dep),
                                    ("WheelsOn", dest, schedule_arr), ("ArrTime", dest, schedule_arr)):
        value = local_hhmm_to_utc(day, row.get(key), timezones[airport])
        if value and reference: value = infer_rollover(reference, value)
        actual[key] = value
    event_start = actual["DepTime"] or schedule_dep
    event_end = actual["ArrTime"] or schedule_arr
    return {"canonical_object_type": "FlightRecord", "dataset_instance_id": "data2_2019",
        "flight_id": deterministic_id("flight", flight_parts), "source_flight_id": "|".join(str(v) for v in flight_parts.values()),
        "aircraft_id": None if missing(row.get("Tail_Number")) else str(row["Tail_Number"]).strip(),
        "aircraft_id_namespace": "REGISTRATION", "origin_airport_id": origin, "destination_airport_id": dest,
        "scheduled_departure_utc": schedule_dep, "scheduled_arrival_utc": schedule_arr,
        "event_start_time": event_start, "event_end_time": event_end,
        "schedule_semantics": "CRS_DEPARTURE", "availability_basis": "SCHEDULE_REFERENCE_ASSUMPTION",
        "provenance_rule_id": "D2-BTS-SCHEDULE", "realized_outcome": {
            **actual, "TaxiOut": number(row.get("TaxiOut")), "TaxiIn": number(row.get("TaxiIn")),
            "Cancelled": bool(number(row.get("Cancelled")) or 0), "Diverted": bool(number(row.get("Diverted")) or 0),
            "decision_time_role": "EVAL_OUTCOME", "availability_basis": "POSTHOC_ONLY",
            "provenance_rule_id": "D2-BTS-ACTUAL"}}


def canonicalize_flightlist_row(row: dict[str, Any]) -> dict[str, Any]:
    parts = {key: row.get(key) for key in ("callsign", "day", "origin", "destination", "icao24")}
    return {"canonical_object_type": "FlightRecord", "dataset_instance_id": "data1_2019",
        "flight_id": deterministic_id("flight", parts), "source_flight_id": str(row.get("callsign", "")).strip(),
        "aircraft_id": str(row.get("icao24", "")).lower(), "aircraft_id_namespace": "ICAO24",
        "origin_airport_id": None if missing(row.get("origin")) else row.get("origin"),
        "destination_airport_id": None if missing(row.get("destination")) else row.get("destination"),
        "first_seen_utc": datetime.fromtimestamp(float(row["firstseen"]), timezone.utc),
        "last_seen_utc": datetime.fromtimestamp(float(row["lastseen"]), timezone.utc),
        "event_start_time": datetime.fromtimestamp(float(row["firstseen"]), timezone.utc),
        "event_end_time": datetime.fromtimestamp(float(row["lastseen"]), timezone.utc),
        "decision_time_role": "EPISODE_CONSTRUCTION", "availability_basis": "ARCHIVE_PUBLICATION_RULE",
        "provenance_rule_id": "D1-OPENSKY-FLIGHT"}


def canonicalize_state_vector_row(row: dict[str, Any], *, replay_lag_minutes: int | None) -> dict[str, Any]:
    if replay_lag_minutes is None: raise ContractError("REPLAY_LAG_NOT_FROZEN")
    event_time = datetime.fromtimestamp(float(row["time"]), timezone.utc)
    availability_time = event_time + timedelta(minutes=replay_lag_minutes)
    values = {"canonical_object_type": "TrajectoryObservation", "dataset_instance_id": "data1_2019",
        "aircraft_id": str(row["icao24"]).lower(), "aircraft_id_namespace": "ICAO24",
        "event_time": event_time, "availability_time": availability_time,
        "availability_basis": "REPLAY_EVENT_TIME", "provenance_rule_id": "D1-OPENSKY-STATE",
        "latitude_deg": number(row.get("lat")), "longitude_deg": number(row.get("lon")),
        "baro_altitude_m": number(row.get("baroaltitude")), "geo_altitude_m": number(row.get("geoaltitude")),
        "velocity_mps": number(row.get("velocity")), "heading_deg": number(row.get("heading")),
        "vertical_rate_mps": number(row.get("vertrate")),
        "on_ground": None if missing(row.get("onground")) else str(row["onground"]).strip().lower() in {"true", "1"},
        "position_time": None if missing(row.get("lastposupdate")) else datetime.fromtimestamp(float(row["lastposupdate"]), timezone.utc),
        "contact_time": None if missing(row.get("lastcontact")) else datetime.fromtimestamp(float(row["lastcontact"]), timezone.utc)}
    values["canonical_record_id"] = deterministic_id("trajectory", {"aircraft": values["aircraft_id"], "event_time": event_time.isoformat()})
    return values


def canonicalize_airport_row(row: dict[str, Any], *, dataset_instance_id: str = "data1_2019") -> dict[str, Any]:
    ident = str(row.get("ident", "")).strip().upper()
    iata = None if missing(row.get("iata_code")) else str(row["iata_code"]).strip().upper()
    if not ident:
        raise ContractError("AIRPORT_IDENTITY_MISSING")
    value = {"canonical_object_type":"AirportReference", "dataset_instance_id":dataset_instance_id,
             "canonical_record_id":deterministic_id("airport",{"dataset":dataset_instance_id,"ident":ident}),
             "airport_id":ident,"airport_id_namespace":"ICAO_OR_LOCAL","icao_code":ident if len(ident)==4 else None,
             "iata_code":iata,"latitude_deg":number(row.get("latitude_deg")),"longitude_deg":number(row.get("longitude_deg")),
             "elevation_m":None if missing(row.get("elevation_ft")) else float(row["elevation_ft"])*0.3048,
             "airport_type":row.get("type"),"event_time":None,"availability_time":None,
             "availability_basis":"REFERENCE_PERIOD","provenance_rule_id":"D1-OURAIRPORTS","quality_flags":()}
    return value


def canonicalize_timezone_row(row: dict[str, Any]) -> dict[str, Any]:
    iata=str(row.get("iata","")).strip().upper();ident=str(row.get("ident","")).strip().upper()
    if not iata or not row.get("timezone"):
        raise ContractError("TIMEZONE_REFERENCE_IDENTITY_MISSING")
    return {"canonical_object_type":"AirportReference","dataset_instance_id":"data2_2019",
            "canonical_record_id":deterministic_id("timezone",{"iata":iata,"timezone":row["timezone"]}),
            "airport_id":iata,"airport_id_namespace":"IATA","icao_code":ident or None,"iata_code":iata,
            "timezone":row["timezone"],"latitude_deg":number(row.get("lat")),"longitude_deg":number(row.get("lon")),
            "event_time":None,"availability_time":None,"availability_basis":"REFERENCE_PERIOD",
            "provenance_rule_id":"D2-TIMEZONE","quality_flags":()}


def canonicalize_aggregate_row(row: dict[str, Any], *, dataset_instance_id: str, source_family: str) -> dict[str, Any]:
    normalized={str(key):value for key,value in row.items()}
    upper={key.upper():value for key,value in normalized.items()}
    if source_family=="bts_db1b":
        origin=str(upper.get("ORIGIN","")).strip();dest=str(upper.get("DEST","")).strip();value=number(upper.get("PASSENGERS"));unit="passengers";period="2019"
        join={"origin":origin,"destination":dest}
    elif source_family=="bts_t100":
        origin=str(upper.get("ORIGIN","")).strip();dest=str(upper.get("DEST","")).strip();value={"passengers":number(upper.get("PASSENGERS")),"seats":number(upper.get("SEATS"))};unit="counts";period=f"{upper.get('YEAR','')}-{str(upper.get('MONTH','')).zfill(2)}"
        join={"origin":origin,"destination":dest}
    else:
        raise ContractError("AGGREGATE_SOURCE_UNSUPPORTED")
    return {"canonical_object_type":"AggregateReference","dataset_instance_id":dataset_instance_id,
            "canonical_record_id":deterministic_id("aggregate",{"source":source_family,"period":period,"join":join,"value":value}),
            "reference_name":source_family,"grain":"origin_destination_period","join_key":join,
            "reference_period":period,"value":value,"unit":unit,"event_time":None,"availability_time":None,
            "availability_basis":"REFERENCE_PERIOD","provenance_rule_id":f"D2-{source_family.split('_')[-1].upper()}","quality_flags":()}


def canonicalize_eurostat_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("class") != "dataset" or "value" not in payload:
        raise ContractError("EUROSTAT_JSON_STAT_SCHEMA_MISMATCH")
    period=next(iter(payload.get("dimension",{}).get("time",{}).get("category",{}).get("index",{})),"UNKNOWN")
    return {"canonical_object_type":"AggregateReference","dataset_instance_id":"data1_2019",
            "canonical_record_id":deterministic_id("aggregate",{"source":payload.get("source"),"period":period,"updated":payload.get("updated")}),
            "reference_name":payload.get("extension",{}).get("id",payload.get("label","EUROSTAT")),"grain":"json_stat_cube",
            "join_key":{"dataset":payload.get("extension",{}).get("id","UNKNOWN")},"reference_period":period,
            "value":{"observations":len(payload.get("value",{})),"source_updated":payload.get("updated")},"unit":"source_defined_counts",
            "event_time":None,"availability_time":None,"availability_basis":"REFERENCE_PERIOD",
            "provenance_rule_id":"D1-EUROSTAT","quality_flags":()}
