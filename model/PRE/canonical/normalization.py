import math
import re
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from model.common.errors import ContractError
from model.common.value_objects import ProvenanceRef
from model.PRE.contracts.canonical import (AggregateReference, AirportReference,
    FlightRecord, OperationalEventRecord, TrajectoryObservation, WeatherObservation)
from .timezone import infer_rollover, local_hhmm_to_utc
from model.PRE.episode.event_detection import TrajectoryEventRecord
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
    elif isinstance(value, (int, float)) or str(value).strip().replace(".", "", 1).isdigit():
        parsed = datetime.fromtimestamp(float(value), timezone.utc)
    else: parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _provenance(dataset: str, logical_source: str, source_record_id: str,
                rule_id: str) -> ProvenanceRef:
    return ProvenanceRef(dataset_instance_id=dataset, logical_source=logical_source,
        source_record_id=source_record_id, rule_id=rule_id, source_version="2019")


def canonicalize_metar_row(row: dict[str, Any], *, replay_lag_minutes: int | None) -> WeatherObservation:
    if replay_lag_minutes is None: raise ContractError("REPLAY_LAG_NOT_FROZEN")
    event_time = parse_utc(row["valid"])
    match = re.search(r"(?:^|\s)Q(\d{4})(?:\s|$)", str(row.get("metar", "")))
    raw_id = deterministic_id("raw", {"source":"iem_metar", "station":row.get("station"), "valid":row.get("valid")})
    sky_codes = (row.get("skyc1"), row.get("skyc2"), row.get("skyc3"))
    sky_bases = (row.get("skyl1"), row.get("skyl2"), row.get("skyl3"))
    cloud_layers = [(str(code).strip().upper(), base) for code, base in zip(sky_codes, sky_bases)
                    if not missing(code)]
    cloud_cover_codes = tuple(code for code, _ in cloud_layers)
    cloud_base_m = tuple(None if missing(base) else hundreds_feet_to_m(float(base))
                         for _, base in cloud_layers)
    ceiling_codes = {"BKN", "OVC", "VV"}
    ceiling_layers = [code for code, _ in cloud_layers if code in ceiling_codes]
    ceiling_bases = [hundreds_feet_to_m(float(base)) for code, base in cloud_layers
                     if code in ceiling_codes and not missing(base)]
    if not cloud_layers:
        ceiling_base_m, cloud_flag = None, "CLOUD_LAYERS_MISSING"
    elif ceiling_layers and len(ceiling_bases) != len(ceiling_layers):
        ceiling_base_m, cloud_flag = None, "CEILING_BASE_MISSING_MASKED"
    elif ceiling_bases:
        ceiling_base_m, cloud_flag = min(ceiling_bases), "CEILING_DERIVED_MIN_BKN_OVC"
    else:
        ceiling_base_m, cloud_flag = None, "CEILING_UNLIMITED"
    converted = {
        "canonical_object_type": "WeatherObservation", "dataset_instance_id": "data1_2019",
        "airport_id": str(row["station"]).strip().upper(), "event_time": event_time,
        "availability_time": event_time + timedelta(minutes=replay_lag_minutes),
        "availability_basis": "REPLAY_EVENT_TIME", "provenance_rule_id": "D1-METAR",
        "decision_time_role":"INFERENCE_EVIDENCE",
        "provenance":_provenance("data1_2019", "iem_metar", raw_id, "D1-METAR"),
        "temperature_c": None if missing(row.get("tmpf")) else fahrenheit_to_celsius(float(row["tmpf"])),
        "dewpoint_c": None if missing(row.get("dwpf")) else fahrenheit_to_celsius(float(row["dwpf"])),
        "wind_direction_deg": number(row.get("drct")),
        "wind_speed_mps": None if missing(row.get("sknt")) else knots_to_mps(float(row["sknt"])),
        "wind_gust_mps": None if missing(row.get("gust")) else knots_to_mps(float(row["gust"])),
        "visibility_m": None if missing(row.get("vsby")) else statute_miles_to_m(float(row["vsby"])),
        "qnh_hpa": int(match.group(1)) if match else None, "mslp_hpa": None,
        "cloud_cover_codes": cloud_cover_codes,
        "cloud_base_m": cloud_base_m,
        "ceiling_base_m": ceiling_base_m,
        "present_weather_codes": None if missing(row.get("wxcodes")) else str(row["wxcodes"]),
        "quality_flags": tuple(sorted([flag for flag, condition in (
            ("QNH_DERIVED_FROM_METAR", bool(match)), ("MSLP_UNSUPPORTED", True),
            (cloud_flag, True)) if condition])),
    }
    converted["canonical_record_id"] = deterministic_id("weather", {"station": converted["airport_id"], "event_time": event_time.isoformat()})
    return WeatherObservation.model_validate(converted)


def _normalize_isd_station_id(station: object) -> str:
    """Zero-pad the WBAN part of an ISD station id to 5 digits.

    NOAA names files as {USAF:6}{WBAN:5}; the local station map drops the
    leading zero of short WBANs (e.g. 7256503017 vs file 72565003017).
    """
    sid = str(station).strip()
    if len(sid) == 11:
        return sid
    if len(sid) == 10:
        return sid[:6] + "0" + sid[6:]
    if len(sid) == 5:
        return "999999" + sid
    return sid


def _isd_component(value: object, index: int, default: str = "") -> str:
    if missing(value):
        return default
    parts = str(value).split(",")
    return parts[index] if len(parts) > index else default


def _isd_signed_tenths(value: object) -> float | None:
    raw = _isd_component(value, 0)
    if missing(raw):
        return None
    try:
        digits = abs(int(str(raw).strip()))
    except ValueError:
        return None
    if digits >= 9990:
        return None
    return float(raw) / 10.0


def _isd_wind(value: object) -> tuple[float | None, float | None]:
    raw = _isd_component(value, 0)
    try:
        direction = int(raw)
    except ValueError:
        direction = 999
    if direction >= 990:  # 990-999: variable / calm / missing
        direction = None
    speed_tenths = _isd_component(value, 3)
    if missing(speed_tenths):
        speed = None
    else:
        try:
            speed = float(speed_tenths) / 10.0 if int(speed_tenths) < 9990 else None
        except ValueError:
            speed = None
    return direction, speed


def _isd_visibility_m(value: object) -> float | None:
    raw = _isd_component(value, 0)
    if missing(raw):
        return None
    try:
        meters = int(raw)
    except ValueError:
        return None
    return None if meters >= 99999 else float(meters)


def _isd_ceiling_m(value: object) -> tuple[float | None, str]:
    """ISD CIG: lowest broken/overcast layer base, meters x 10.

    Coded values: 99999 = missing, 22000 = unlimited ceiling.
    """
    raw = _isd_component(value, 0)
    if missing(raw):
        return None, "CEILING_MISSING"
    try:
        coded = int(raw)
    except ValueError:
        return None, "CEILING_MISSING"
    if coded == 22000:
        return None, "CEILING_UNLIMITED"
    if coded >= 99999:
        return None, "CEILING_MISSING"
    return coded / 10.0, "CEILING_FROM_ISD_CIG"


_SKY_GROUP = re.compile(r"(?:^|\s)(FEW|SCT|BKN|OVC|VV)(\d{3})(CB|TCU)?(?=\s|$)")
_ALTIMETER = re.compile(r"(?:^|\s)A(\d{4})(?:\s|$)")
_WX_TOKEN = re.compile(
    r"(?:^|\s)([+-]{0,2}(?:(?:MI|PR|BC|DR|BL|SH|TS|FZ|VC)?"
    r"(?:DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS)|"
    r"(?:BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS)))(?=\s|$)"
)


def _metar_sky_groups(metar_text: str) -> tuple[list[str], list[float], float | None, str]:
    layers = [(code, int(base)) for code, base, _tcu in _SKY_GROUP.findall(metar_text)]
    cover_codes = tuple(code for code, _base in layers)
    base_m = tuple(hundreds_feet_to_m(float(base)) for _code, base in layers)
    ceiling_bases = [hundreds_feet_to_m(float(base)) for code, base in layers
                     if code in {"BKN", "OVC", "VV"}]
    if ceiling_bases:
        ceiling, flag = min(ceiling_bases), "CEILING_FROM_METAR_TEXT"
    else:
        ceiling, flag = None, "CEILING_UNLIMITED_OR_METAR_ABSENT"
    return cover_codes, base_m, ceiling, flag


def canonicalize_isd_row(row: dict[str, Any], *, station_map: dict[str, str],
                         replay_lag_minutes: int | None) -> WeatherObservation:
    """NOAA ISD (global-hourly) row -> WeatherObservation (data2 scope).

    D2-NOAA-ISD@1.0.0: official NOAA ISD fields (TMP/DEW/WND/VIS/CIG) plus the
    embedded official METAR text (REM column) for altimeter and cloud layers.
    The station map joins ISD station id -> IATA airport. Availability follows
    REPLAY_EVENT_TIME with a frozen replay lag (same boundary as data1 METAR).
    """
    if replay_lag_minutes is None:
        raise ContractError("REPLAY_LAG_NOT_FROZEN")
    if missing(row.get("DATE")) or missing(row.get("STATION")):
        raise ContractError("WEATHER_ROW_MISSING:DATE_OR_STATION")
    event_time = parse_utc(row["DATE"])
    station = _normalize_isd_station_id(row.get("STATION"))
    if station not in station_map:
        raise ContractError(f"WEATHER_STATION_UNMAPPED:{station}")
    airport_id = station_map[station]

    temperature_c = _isd_signed_tenths(row.get("TMP"))
    dewpoint_c = _isd_signed_tenths(row.get("DEW"))
    wind_direction_deg, wind_speed_mps = _isd_wind(row.get("WND"))
    visibility_m = _isd_visibility_m(row.get("VIS"))
    ceiling_m, ceiling_flag = _isd_ceiling_m(row.get("CIG"))

    metar_text = "" if missing(row.get("REM")) else str(row["REM"])
    qnh_match = _ALTIMETER.search(metar_text)
    if qnh_match:
        qnh_hpa = round(int(qnh_match.group(1)) / 100.0 * 33.8639, 1)
        qnh_flag = "QNH_DERIVED_FROM_METAR"
    else:
        qnh_hpa, qnh_flag = None, "QNH_ABSENT"
    cover_codes, cloud_base_m, metar_ceiling, metar_flag = _metar_sky_groups(metar_text)
    if metar_text and ceiling_m is None and metar_ceiling is not None:
        ceiling_m, ceiling_flag = metar_ceiling, "CEILING_FROM_METAR_TEXT"
    if not metar_text:
        cover_codes, cloud_base_m = (), ()
        metar_flag = "METAR_TEXT_ABSENT"
    wx_tokens = sorted({token for token in _WX_TOKEN.findall(metar_text)})
    present_weather_codes = " ".join(wx_tokens) if wx_tokens else None

    raw_id = deterministic_id("raw", {"source": "noaa_isd", "station": station,
                                      "valid": str(row.get("DATE"))})
    flags = tuple(sorted({flag for flag in (
        qnh_flag, ceiling_flag, metar_flag, "SLP_ISD_UNMAPPED",
        "REPORT_TYPE=" + str(row.get("REPORT_TYPE", "")) if row.get("REPORT_TYPE") else None,
        "PRESENT_WEATHER_FROM_METAR_TEXT" if present_weather_codes else None,
    ) if flag}))
    converted = {
        "canonical_object_type": "WeatherObservation", "dataset_instance_id": "data2_2019",
        "airport_id": airport_id, "event_time": event_time,
        "availability_time": event_time + timedelta(minutes=replay_lag_minutes),
        "availability_basis": "REPLAY_EVENT_TIME", "provenance_rule_id": "D2-NOAA-ISD",
        "decision_time_role": "INFERENCE_EVIDENCE",
        "provenance": _provenance("data2_2019", "noaa_isd", raw_id, "D2-NOAA-ISD"),
        "temperature_c": temperature_c, "dewpoint_c": dewpoint_c,
        "wind_direction_deg": wind_direction_deg, "wind_speed_mps": wind_speed_mps,
        "wind_gust_mps": None, "visibility_m": visibility_m,
        "qnh_hpa": qnh_hpa, "mslp_hpa": None,
        "cloud_cover_codes": cover_codes, "cloud_base_m": cloud_base_m,
        "ceiling_base_m": ceiling_m,
        "present_weather_codes": present_weather_codes,
        "quality_flags": flags,
    }
    converted["canonical_record_id"] = deterministic_id(
        "weather", {"station": station, "event_time": event_time.isoformat()})
    return WeatherObservation.model_validate(converted)


def canonicalize_ontime_row(row: dict[str, Any], timezones: dict[str, str]) -> tuple[FlightRecord, OperationalEventRecord]:
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
    if schedule_dep is None or schedule_arr is None:
        raise ContractError("SCHEDULE_REFERENCE_MISSING")
    raw_id = deterministic_id("raw", {"source":"bts_ontime", **flight_parts,
        "tail":row.get("Tail_Number")})
    flight_id = deterministic_id("flight", flight_parts)
    schedule = FlightRecord.model_validate({"canonical_object_type": "FlightRecord", "dataset_instance_id": "data2_2019",
        "canonical_record_id":deterministic_id("canonical-flight", {"raw":raw_id, "role":"schedule"}),
        "flight_id": flight_id, "service_date": day,
        "source_flight_id": "|".join(str(v) for v in flight_parts.values()),
        "aircraft_id": None if missing(row.get("Tail_Number")) else str(row["Tail_Number"]).strip(),
        "aircraft_id_namespace": "REGISTRATION", "origin_airport_id": origin, "destination_airport_id": dest,
        "scheduled_departure_utc": schedule_dep, "scheduled_arrival_utc": schedule_arr,
        "event_time":schedule_dep, "availability_time":None,
        "event_start_time": schedule_dep, "event_end_time": schedule_arr,
        "schedule_semantics": "CRS_DEPARTURE", "availability_basis": "SCHEDULE_REFERENCE_ASSUMPTION",
        "decision_time_role":"FROZEN_REFERENCE", "provenance_rule_id": "D2-BTS-SCHEDULE",
        "provenance":_provenance("data2_2019", "bts_ontime", raw_id, "D2-BTS-SCHEDULE")})
    # HHMM does not carry a date and is ambiguous for delays longer than twelve
    # hours.  BTS delay minutes are evaluation-only fields and are used here
    # solely to restore the typed outcome timestamp's date offset.
    dep_delay = number(row.get("DepDelayMinutes"))
    arr_delay = number(row.get("ArrDelayMinutes"))
    taxi_out = number(row.get("TaxiOut"))
    taxi_in = number(row.get("TaxiIn"))
    if schedule_dep is not None and dep_delay is not None:
        actual["DepTime"] = schedule_dep + timedelta(minutes=dep_delay)
    if schedule_arr is not None and arr_delay is not None:
        actual["ArrTime"] = schedule_arr + timedelta(minutes=arr_delay)
    if actual["DepTime"] is not None and taxi_out is not None:
        actual["WheelsOff"] = actual["DepTime"] + timedelta(minutes=taxi_out)
    if actual["ArrTime"] is not None and taxi_in is not None:
        actual["WheelsOn"] = actual["ArrTime"] - timedelta(minutes=taxi_in)
    actual_times = [value for value in actual.values() if value is not None]
    outcome = OperationalEventRecord.model_validate({
        "canonical_object_type":"OperationalEventRecord", "dataset_instance_id":"data2_2019",
        "canonical_record_id":deterministic_id("canonical-event", {"raw":raw_id, "role":"actual"}),
        "flight_id":flight_id, "event_type":"COMPLETED_OPERATIONAL_OUTCOME",
        "event_time":min(actual_times) if actual_times else None, "availability_time":None,
        "event_time_lower":min(actual_times) if actual_times else None,
        "event_time_upper":max(actual_times) if actual_times else None,
        "actual_departure_utc":actual["DepTime"], "wheels_off_utc":actual["WheelsOff"],
        "wheels_on_utc":actual["WheelsOn"], "actual_arrival_utc":actual["ArrTime"],
        "taxi_out_minutes":taxi_out, "taxi_in_minutes":taxi_in,
        "cancelled":bool(number(row.get("Cancelled")) or 0), "diverted":bool(number(row.get("Diverted")) or 0),
        "reconstruction_rule_id":"local_actual_to_utc", "decision_time_role":"EVAL_OUTCOME",
        "availability_basis":"POSTHOC_ONLY", "provenance_rule_id":"D2-BTS-ACTUAL",
        "quality_flags":tuple(sorted(flag for flag, condition in (
            ("ACTUAL_DEPARTURE_DATE_OFFSET_FROM_DELAY_MINUTES", dep_delay is not None),
            ("ACTUAL_ARRIVAL_DATE_OFFSET_FROM_DELAY_MINUTES", arr_delay is not None),
        ) if condition)),
        "provenance":_provenance("data2_2019", "bts_ontime", raw_id, "D2-BTS-ACTUAL")})
    return schedule, outcome


def canonicalize_flightlist_row(row: dict[str, Any]) -> tuple[FlightRecord, OperationalEventRecord]:
    parts = {key: row.get(key) for key in ("callsign", "day", "origin", "destination", "icao24")}
    first_seen, last_seen = parse_utc(row["firstseen"]), parse_utc(row["lastseen"])
    raw_id = deterministic_id("raw", {"source":"opensky_flightlist", **parts,
        "firstseen":first_seen.isoformat(), "lastseen":last_seen.isoformat()})
    flight_id = deterministic_id("flight", parts)
    flight = FlightRecord.model_validate({"canonical_object_type": "FlightRecord", "dataset_instance_id": "data1_2019",
        "canonical_record_id":deterministic_id("canonical-flight", {"raw":raw_id, "role":"episode"}),
        "flight_id": flight_id, "source_flight_id": str(row.get("callsign", "")).strip(),
        "aircraft_id": str(row.get("icao24", "")).lower(), "aircraft_id_namespace": "ICAO24",
        "origin_airport_id": None if missing(row.get("origin")) else row.get("origin"),
        "destination_airport_id": None if missing(row.get("destination")) else row.get("destination"),
        "event_time":first_seen, "availability_time":None,
        "first_seen_utc":first_seen, "last_seen_utc":last_seen,
        "event_start_time":first_seen, "event_end_time":last_seen,
        "decision_time_role": "EPISODE_CONSTRUCTION", "availability_basis": "ARCHIVE_PUBLICATION_RULE",
        "provenance_rule_id": "D1-OPENSKY-FLIGHT",
        "provenance":_provenance("data1_2019", "opensky_flightlist", raw_id, "D1-OPENSKY-FLIGHT")})
    event = OperationalEventRecord.model_validate({
        "canonical_object_type":"OperationalEventRecord", "dataset_instance_id":"data1_2019",
        "canonical_record_id":deterministic_id("canonical-event", {"raw":raw_id, "role":"proxy-outcome"}),
        "flight_id":flight_id, "event_type":"ARCHIVE_FLIGHT_INTERVAL_PROXY", "event_time":first_seen,
        "availability_time":None, "event_time_lower":first_seen, "event_time_upper":last_seen,
        "reconstruction_rule_id":"interval_event_proxy", "decision_time_role":"EVAL_OUTCOME",
        "availability_basis":"POSTHOC_ONLY", "provenance_rule_id":"D1-OPENSKY-FLIGHT-EVENT",
        "provenance":_provenance("data1_2019", "opensky_flightlist", raw_id, "D1-OPENSKY-FLIGHT-EVENT")})
    return flight, event


def canonicalize_state_vector_row(row: dict[str, Any], *, replay_lag_minutes: int | None) -> TrajectoryObservation:
    if replay_lag_minutes is None: raise ContractError("REPLAY_LAG_NOT_FROZEN")
    event_time = datetime.fromtimestamp(float(row["time"]), timezone.utc)
    availability_time = event_time + timedelta(minutes=replay_lag_minutes)
    raw_id = deterministic_id("raw", {"source":"opensky_state_vectors", "aircraft":row.get("icao24"), "time":row.get("time")})
    values = {"canonical_object_type": "TrajectoryObservation", "dataset_instance_id": "data1_2019",
        "aircraft_id": str(row["icao24"]).lower(), "aircraft_id_namespace": "ICAO24",
        "event_time": event_time, "availability_time": availability_time,
        "availability_basis": "REPLAY_EVENT_TIME", "provenance_rule_id": "D1-OPENSKY-STATE",
        "decision_time_role":"INFERENCE_EVIDENCE",
        "provenance":_provenance("data1_2019", "opensky_state_vectors", raw_id, "D1-OPENSKY-STATE"),
        "latitude_deg": number(row.get("lat")), "longitude_deg": number(row.get("lon")),
        "baro_altitude_m": number(row.get("baroaltitude")), "geo_altitude_m": number(row.get("geoaltitude")),
        "velocity_mps": number(row.get("velocity")), "heading_deg": number(row.get("heading")),
        "vertical_rate_mps": number(row.get("vertrate")),
        "on_ground": None if missing(row.get("onground")) else str(row["onground"]).strip().lower() in {"true", "1"},
        "position_time": None if missing(row.get("lastposupdate")) else datetime.fromtimestamp(float(row["lastposupdate"]), timezone.utc),
        "contact_time": None if missing(row.get("lastcontact")) else datetime.fromtimestamp(float(row["lastcontact"]), timezone.utc)}
    values["canonical_record_id"] = deterministic_id("trajectory", {"aircraft": values["aircraft_id"], "event_time": event_time.isoformat()})
    return TrajectoryObservation.model_validate(values)


def canonicalize_airport_row(row: dict[str, Any], *, dataset_instance_id: str = "data1_2019",
                             rule_id: str = "D1-OURAIRPORTS",
                             logical_source: str = "ourairports") -> AirportReference:
    ident = str(row.get("ident", "")).strip().upper()
    iata = None if missing(row.get("iata_code")) else str(row["iata_code"]).strip().upper()
    if not ident:
        raise ContractError("AIRPORT_IDENTITY_MISSING")
    raw_id = deterministic_id("raw", {"source":logical_source, "ident":ident})
    value = {"canonical_object_type":"AirportReference", "dataset_instance_id":dataset_instance_id,
             "canonical_record_id":deterministic_id("airport",{"dataset":dataset_instance_id,"ident":ident}),
             "airport_id":ident,"airport_id_namespace":"ICAO_OR_LOCAL","icao_code":ident if len(ident)==4 else None,
             "iata_code":iata,"latitude_deg":number(row.get("latitude_deg")),"longitude_deg":number(row.get("longitude_deg")),
             "elevation_m":None if missing(row.get("elevation_ft")) else float(row["elevation_ft"])*0.3048,
             "airport_type":row.get("type"),"event_time":None,"availability_time":None,
             "availability_basis":"REFERENCE_PERIOD","provenance_rule_id":"D1-OURAIRPORTS","quality_flags":()}
    value["provenance_rule_id"] = rule_id
    value["decision_time_role"] = "FROZEN_REFERENCE"
    value["provenance"] = _provenance(dataset_instance_id, logical_source, raw_id, rule_id)
    return AirportReference.model_validate(value)


def canonicalize_timezone_row(row: dict[str, Any]) -> AirportReference:
    iata=str(row.get("iata","")).strip().upper();ident=str(row.get("ident","")).strip().upper()
    if not iata or not row.get("timezone"):
        raise ContractError("TIMEZONE_REFERENCE_IDENTITY_MISSING")
    raw_id=deterministic_id("raw",{"source":"timezone_reference","iata":iata,"timezone":row["timezone"]})
    return AirportReference.model_validate({"canonical_object_type":"AirportReference","dataset_instance_id":"data2_2019",
            "canonical_record_id":deterministic_id("timezone",{"iata":iata,"timezone":row["timezone"]}),
            "airport_id":iata,"airport_id_namespace":"IATA","icao_code":ident or None,"iata_code":iata,
            "timezone":row["timezone"],"latitude_deg":number(row.get("lat")),"longitude_deg":number(row.get("lon")),
            "event_time":None,"availability_time":None,"availability_basis":"REFERENCE_PERIOD",
            "decision_time_role":"FROZEN_REFERENCE", "provenance_rule_id":"D2-TIMEZONE",
            "provenance":_provenance("data2_2019","timezone_reference",raw_id,"D2-TIMEZONE"),"quality_flags":()})


def canonicalize_aggregate_row(row: dict[str, Any], *, dataset_instance_id: str, source_family: str) -> AggregateReference:
    normalized={str(key):value for key,value in row.items()}
    upper={key.upper():value for key,value in normalized.items()}
    if source_family=="bts_db1b":
        origin=str(upper.get("ORIGIN","")).strip();dest=str(upper.get("DEST","")).strip();value=number(upper.get("PASSENGERS"));unit="passengers";period="2019"
        join={"origin":origin,"destination":dest}
    elif source_family=="bts_t100":
        origin=str(upper.get("ORIGIN","")).strip();dest=str(upper.get("DEST","")).strip();service_class=str(upper.get("CLASS","")).strip() or None;value={"passengers":number(upper.get("PASSENGERS")),"seats":number(upper.get("SEATS")),"service_class":service_class};unit="counts";period=f"{upper.get('YEAR','')}-{str(upper.get('MONTH','')).zfill(2)}"
        join={"origin":origin,"destination":dest}
    else:
        raise ContractError("AGGREGATE_SOURCE_UNSUPPORTED")
    record_id=deterministic_id("aggregate",{"source":source_family,"period":period,"join":join,"value":value})
    rule_id=f"D2-{source_family.split('_')[-1].upper()}"
    raw_id=deterministic_id("raw",{"source":source_family,"period":period,"join":join,"value":value})
    return AggregateReference.model_validate({"canonical_object_type":"AggregateReference","dataset_instance_id":dataset_instance_id,
            "canonical_record_id":record_id,
            "reference_name":source_family,"grain":"origin_destination_period","join_key":join,
            "reference_period":period,"value":value,"unit":unit,"event_time":None,"availability_time":None,
            "availability_basis":"REFERENCE_PERIOD","provenance_rule_id":f"D2-{source_family.split('_')[-1].upper()}","quality_flags":()}
            | {"decision_time_role":"FROZEN_REFERENCE",
               "provenance":_provenance(dataset_instance_id,source_family,raw_id,rule_id)})


def canonicalize_eurostat_payload(payload: dict[str, Any]) -> AggregateReference:
    if payload.get("class") != "dataset" or "value" not in payload:
        raise ContractError("EUROSTAT_JSON_STAT_SCHEMA_MISMATCH")
    period=next(iter(payload.get("dimension",{}).get("time",{}).get("category",{}).get("index",{})),"UNKNOWN")
    record_id=deterministic_id("aggregate",{"source":payload.get("source"),"period":period,"updated":payload.get("updated")})
    raw_id=deterministic_id("raw",{"source":"eurostat","period":period,"updated":payload.get("updated")})
    return AggregateReference.model_validate({"canonical_object_type":"AggregateReference","dataset_instance_id":"data1_2019",
            "canonical_record_id":record_id,
            "reference_name":payload.get("extension",{}).get("id",payload.get("label","EUROSTAT")),"grain":"json_stat_cube",
            "join_key":{"dataset":payload.get("extension",{}).get("id","UNKNOWN")},"reference_period":period,
            "value":{"observations":len(payload.get("value",{})),"source_updated":payload.get("updated")},"unit":"source_defined_counts",
            "event_time":None,"availability_time":None,"availability_basis":"REFERENCE_PERIOD",
            "decision_time_role":"FROZEN_REFERENCE", "provenance_rule_id":"D1-EUROSTAT",
            "provenance":_provenance("data1_2019","eurostat",raw_id,"D1-EUROSTAT"),"quality_flags":()})

_EUROSTAT_PASSENGER_SLICE = {
    "freq": "M",
    "unit": "PAS",
    "tra_meas": "PAS_BRD",
    "schedule": "TOT",
    "tra_cov": "TOTAL",
}


def _eurostat_airport_month_record(airport: str, period: str, value: Any) -> AggregateReference:
    join = {"rep_airp": airport, "time": period, "measure": "PAS_BRD",
            "schedule": "TOT", "tra_cov": "TOTAL"}
    raw_id = deterministic_id("raw", {"source": "eurostat", "period": period,
        "airport": airport, "measure": "PAS_BRD", "schedule": "TOT", "tra_cov": "TOTAL"})
    record_id = deterministic_id("aggregate", {"source": "eurostat", "period": period,
        "airport": airport, "measure": "PAS_BRD", "schedule": "TOT", "tra_cov": "TOTAL",
        "value": value})
    return AggregateReference.model_validate({"canonical_object_type": "AggregateReference",
        "dataset_instance_id": "data1_2019", "canonical_record_id": record_id,
        "reference_name": "passenger_reference", "grain": "airport_month",
        "join_key": join, "reference_period": period, "value": value,
        "unit": "passengers", "event_time": None, "availability_time": None,
        "availability_basis": "REFERENCE_PERIOD", "decision_time_role": "FROZEN_REFERENCE",
        "provenance_rule_id": "D1-EUROSTAT",
        "provenance": _provenance("data1_2019", "eurostat", raw_id, "D1-EUROSTAT"),
        "quality_flags": ()})


def canonicalize_eurostat_passengers_payload(payload: dict[str, Any]) -> tuple[AggregateReference, ...]:
    """Materialize per-airport-month passenger reference records (D1-11 freeze).

    Frozen slice (2026-08-13): avia_paoa passengers cube, freq=M (monthly),
    unit=PAS, tra_meas=PAS_BRD, schedule=TOT, tra_cov=TOTAL; grain = airport x
    month. Sparse json-stat cells that are absent are NOT materialized
    (missing, never zero-fabricated); explicit zero values are preserved as
    observed zeros.
    """
    if payload.get("class") != "dataset" or "value" not in payload:
        raise ContractError("EUROSTAT_JSON_STAT_SCHEMA_MISMATCH")
    dim_ids = tuple(payload.get("id") or ())
    sizes = tuple(payload.get("size") or ())
    if len(dim_ids) != len(sizes) or "rep_airp" not in dim_ids or "time" not in dim_ids:
        raise ContractError("EUROSTAT_JSON_STAT_DIMENSIONS_MISMATCH")
    dimensions = payload.get("dimension", {})
    slice_positions: dict[str, int] = {}
    for dim_id, label in _EUROSTAT_PASSENGER_SLICE.items():
        position = dimensions.get(dim_id, {}).get("category", {}).get("index", {}).get(label)
        if position is None:
            raise ContractError(f"EUROSTAT_SLICE_MISSING:{dim_id}:{label}")
        slice_positions[dim_id] = position

    def labels(dim_id: str) -> dict[int, str]:
        return {pos: label for label, pos in
                dimensions.get(dim_id, {}).get("category", {}).get("index", {}).items()}

    airport_labels = labels("rep_airp")
    time_labels = labels("time")
    raw_cells = payload["value"]
    cells = ((int(key), value) for key, value in raw_cells.items()) if isinstance(raw_cells, dict)         else enumerate(raw_cells)
    records: list[AggregateReference] = []
    for index, raw_value in cells:
        decoded: dict[str, int] = {}
        remaining = index
        for position, dim_id in enumerate(dim_ids):
            stride = 1
            for size in sizes[position + 1:]:
                stride *= size
            decoded[dim_id] = remaining // stride
            remaining %= stride
        if any(decoded[dim_id] != position for dim_id, position in slice_positions.items()):
            continue
        airport = airport_labels.get(decoded["rep_airp"])
        period = time_labels.get(decoded["time"])
        if airport is None or period is None:
            continue
        records.append(_eurostat_airport_month_record(airport, period, raw_value))
    return tuple(sorted(records,
        key=lambda record: (record.reference_period, record.join_key.get("rep_airp", ""))))


def canonicalize_trajectory_event(record: TrajectoryEventRecord, *,
                                  flight_id: str | None = None) -> OperationalEventRecord:
    raw_id = deterministic_id("raw", {"source": "opensky_state_vectors",
        "aircraft": record.aircraft_id, "event_type": record.event_type,
        "event_time": record.event_time.isoformat()})
    return OperationalEventRecord.model_validate({
        "canonical_object_type": "OperationalEventRecord", "dataset_instance_id": "data1_2019",
        "canonical_record_id": deterministic_id("canonical-event", {"raw": raw_id, "role": "trajectory"}),
        "flight_id": flight_id, "aircraft_id": record.aircraft_id,
        "event_type": f"TRAJECTORY_{record.event_type}", "event_time": record.event_time,
        "availability_time": None, "event_time_lower": record.event_time,
        "event_time_upper": record.event_time,
        "reconstruction_rule_id": "trajectory_event_detection",
        "decision_time_role": "EVAL_OUTCOME", "availability_basis": "POSTHOC_ONLY",
        "provenance_rule_id": "D1-TRAJECTORY-EVENT",
        "quality_flags": record.quality_flags,
        "provenance": _provenance("data1_2019", "opensky_state_vectors", raw_id,
            "D1-TRAJECTORY-EVENT")})
