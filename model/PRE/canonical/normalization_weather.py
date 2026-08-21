import re
from datetime import timedelta
from typing import Any

from model.common.errors import ContractError
from model.PRE.contracts.canonical import WeatherObservation

from .normalization_common import deterministic_id, missing, number, parse_utc, provenance
from .units import fahrenheit_to_celsius, hundreds_feet_to_m, knots_to_mps, statute_miles_to_m


def canonicalize_metar_row(row: dict[str, Any], *,
                           replay_lag_minutes: int | None) -> WeatherObservation:
    if replay_lag_minutes is None:
        raise ContractError("REPLAY_LAG_NOT_FROZEN")
    event_time = parse_utc(row["valid"])
    match = re.search(r"(?:^|\s)Q(\d{4})(?:\s|$)", str(row.get("metar", "")))
    raw_id = deterministic_id(
        "raw",
        {"source": "iem_metar", "station": row.get("station"), "valid": row.get("valid")},
    )
    sky_codes = (row.get("skyc1"), row.get("skyc2"), row.get("skyc3"))
    sky_bases = (row.get("skyl1"), row.get("skyl2"), row.get("skyl3"))
    cloud_layers = [
        (str(code).strip().upper(), base)
        for code, base in zip(sky_codes, sky_bases)
        if not missing(code)
    ]
    cloud_cover_codes = tuple(code for code, _ in cloud_layers)
    cloud_base_m = tuple(
        None if missing(base) else hundreds_feet_to_m(float(base))
        for _, base in cloud_layers
    )
    ceiling_codes = {"BKN", "OVC", "VV"}
    ceiling_layers = [code for code, _ in cloud_layers if code in ceiling_codes]
    ceiling_bases = [
        hundreds_feet_to_m(float(base))
        for code, base in cloud_layers
        if code in ceiling_codes and not missing(base)
    ]
    if not cloud_layers:
        ceiling_base_m, ceiling_status, cloud_flag = None, "MISSING", "CLOUD_LAYERS_MISSING"
    elif ceiling_layers and len(ceiling_bases) != len(ceiling_layers):
        ceiling_base_m, ceiling_status, cloud_flag = None, "MISSING", "CEILING_BASE_MISSING_MASKED"
    elif ceiling_bases:
        ceiling_base_m, ceiling_status, cloud_flag = min(ceiling_bases), "FINITE", "CEILING_DERIVED_MIN_BKN_OVC"
    else:
        ceiling_base_m, ceiling_status, cloud_flag = None, "UNLIMITED", "CEILING_UNLIMITED"
    converted = {
        "canonical_object_type": "WeatherObservation",
        "dataset_instance_id": "data1_2019",
        "airport_id": str(row["station"]).strip().upper(),
        "event_time": event_time,
        "availability_time": event_time + timedelta(minutes=replay_lag_minutes),
        "availability_basis": "REPLAY_EVENT_TIME",
        "provenance_rule_id": "D1-METAR",
        "decision_time_role": "INFERENCE_EVIDENCE",
        "provenance": provenance("data1_2019", "iem_metar", raw_id, "D1-METAR"),
        "temperature_c": None if missing(row.get("tmpf"))
        else fahrenheit_to_celsius(float(row["tmpf"])),
        "dewpoint_c": None if missing(row.get("dwpf"))
        else fahrenheit_to_celsius(float(row["dwpf"])),
        "wind_direction_deg": number(row.get("drct")),
        "wind_speed_mps": None if missing(row.get("sknt"))
        else knots_to_mps(float(row["sknt"])),
        "wind_gust_mps": None if missing(row.get("gust"))
        else knots_to_mps(float(row["gust"])),
        "visibility_m": None if missing(row.get("vsby"))
        else statute_miles_to_m(float(row["vsby"])),
        "qnh_hpa": int(match.group(1)) if match else None,
        "mslp_hpa": None,
        "cloud_cover_codes": cloud_cover_codes,
        "cloud_base_m": cloud_base_m,
        "ceiling_base_m": ceiling_base_m,
        "ceiling_status": ceiling_status,
        "present_weather_codes": None if missing(row.get("wxcodes"))
        else str(row["wxcodes"]),
        "quality_flags": tuple(sorted(
            flag for flag, condition in (
                ("QNH_DERIVED_FROM_METAR", bool(match)),
                ("MSLP_UNSUPPORTED", True),
                (cloud_flag, True),
            ) if condition
        )),
    }
    converted["canonical_record_id"] = deterministic_id(
        "weather",
        {"station": converted["airport_id"], "event_time": event_time.isoformat()},
    )
    return WeatherObservation.model_validate(converted)


def _normalize_isd_station_id(station: object) -> str:
    """Zero-pad the WBAN part of an ISD station id to 5 digits."""
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
    if direction >= 990:
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
    return None if meters == 999999 else float(meters)


def _isd_ceiling_m(value: object) -> tuple[float | None, str, str]:
    raw = _isd_component(value, 0)
    if missing(raw):
        return None, "MISSING", "CEILING_MISSING"
    try:
        coded = int(raw)
    except ValueError:
        return None, "MISSING", "CEILING_MISSING"
    if coded == 22000:
        return None, "UNLIMITED", "CEILING_UNLIMITED"
    if coded >= 99999:
        return None, "MISSING", "CEILING_MISSING"
    return float(coded), "FINITE", "CEILING_FROM_ISD_CIG"


_SKY_GROUP = re.compile(r"(?:^|\s)(FEW|SCT|BKN|OVC|VV)(\d{3})(CB|TCU)?(?=\s|$)")
_ALTIMETER = re.compile(r"(?:^|\s)A(\d{4})(?:\s|$)")
_WX_TOKEN = re.compile(
    r"(?:^|\s)([+-]{0,2}(?:(?:MI|PR|BC|DR|BL|SH|TS|FZ|VC)?"
    r"(?:DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS)|"
    r"(?:BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS)))(?=\s|$)"
)


def _metar_sky_groups(metar_text: str) -> tuple[list[str], list[float], float | None, str, str]:
    layers = [(code, int(base)) for code, base, _tcu in _SKY_GROUP.findall(metar_text)]
    cover_codes = tuple(code for code, _base in layers)
    base_m = tuple(hundreds_feet_to_m(float(base)) for _code, base in layers)
    ceiling_bases = [
        hundreds_feet_to_m(float(base))
        for code, base in layers
        if code in {"BKN", "OVC", "VV"}
    ]
    if ceiling_bases:
        ceiling, status, flag = min(ceiling_bases), "FINITE", "CEILING_FROM_METAR_TEXT"
    else:
        ceiling, status, flag = None, "UNLIMITED", "CEILING_UNLIMITED_OR_METAR_ABSENT"
    return cover_codes, base_m, ceiling, status, flag


def canonicalize_isd_row(row: dict[str, Any], *, station_map: dict[str, str],
                         replay_lag_minutes: int | None) -> WeatherObservation:
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
    ceiling_m, ceiling_status, ceiling_flag = _isd_ceiling_m(row.get("CIG"))

    metar_text = "" if missing(row.get("REM")) else str(row["REM"])
    qnh_match = _ALTIMETER.search(metar_text)
    if qnh_match:
        qnh_hpa = round(int(qnh_match.group(1)) / 100.0 * 33.8639, 1)
        qnh_flag = "QNH_DERIVED_FROM_METAR"
    else:
        qnh_hpa, qnh_flag = None, "QNH_ABSENT"
    cover_codes, cloud_base_m, metar_ceiling, metar_status, metar_flag = _metar_sky_groups(metar_text)
    if metar_text and ceiling_status != "FINITE" and metar_ceiling is not None:
        ceiling_m, ceiling_status, ceiling_flag = metar_ceiling, metar_status, "CEILING_FROM_METAR_TEXT"
    if not metar_text:
        cover_codes, cloud_base_m = (), ()
        metar_flag = "METAR_TEXT_ABSENT"
    wx_tokens = sorted({token for token in _WX_TOKEN.findall(metar_text)})
    present_weather_codes = " ".join(wx_tokens) if wx_tokens else None

    raw_id = deterministic_id(
        "raw", {"source": "noaa_isd", "station": station, "valid": str(row.get("DATE"))}
    )
    flags = tuple(sorted({
        flag for flag in (
            qnh_flag,
            ceiling_flag,
            metar_flag,
            "SLP_ISD_UNMAPPED",
            "REPORT_TYPE=" + str(row.get("REPORT_TYPE", ""))
            if row.get("REPORT_TYPE") else None,
            "PRESENT_WEATHER_FROM_METAR_TEXT" if present_weather_codes else None,
        ) if flag
    }))
    converted = {
        "canonical_object_type": "WeatherObservation",
        "dataset_instance_id": "data2_2019",
        "airport_id": airport_id,
        "event_time": event_time,
        "availability_time": event_time + timedelta(minutes=replay_lag_minutes),
        "availability_basis": "REPLAY_EVENT_TIME",
        "provenance_rule_id": "D2-NOAA-ISD",
        "decision_time_role": "INFERENCE_EVIDENCE",
        "provenance": provenance("data2_2019", "noaa_isd", raw_id, "D2-NOAA-ISD"),
        "temperature_c": temperature_c,
        "dewpoint_c": dewpoint_c,
        "wind_direction_deg": wind_direction_deg,
        "wind_speed_mps": wind_speed_mps,
        "wind_gust_mps": None,
        "visibility_m": visibility_m,
        "qnh_hpa": qnh_hpa,
        "mslp_hpa": None,
        "cloud_cover_codes": cover_codes,
        "cloud_base_m": cloud_base_m,
        "ceiling_base_m": ceiling_m,
        "ceiling_status": ceiling_status,
        "present_weather_codes": present_weather_codes,
        "quality_flags": flags,
    }
    converted["canonical_record_id"] = deterministic_id(
        "weather", {"station": station, "event_time": event_time.isoformat()}
    )
    return WeatherObservation.model_validate(converted)
