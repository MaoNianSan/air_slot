from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from model.common.errors import ContractError


def local_hhmm_to_utc(
    day: date, value: object, timezone_name: str, *, rollover_days: int = 0
) -> datetime | None:
    text = "" if value is None else str(value).strip().replace(".0", "")
    if not text or text.upper() in {"NAN", "NA", "M", "NONE"}:
        return None
    text = text.zfill(4)
    if not text.isdigit() or len(text) != 4:
        raise ContractError("INVALID_LOCAL_HHMM")
    hour, minute = int(text[:2]), int(text[2:])
    if minute >= 60 or hour > 24 or (hour == 24 and minute != 0):
        raise ContractError("INVALID_LOCAL_HHMM")
    if hour == 24:
        hour = 0
        rollover_days += 1
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ContractError("UNKNOWN_AIRPORT_TIMEZONE") from exc
    local = datetime.combine(
        day + timedelta(days=rollover_days), datetime.min.time(), zone
    )
    return local.replace(hour=hour, minute=minute).astimezone(timezone.utc)


def infer_rollover(reference: datetime, candidate: datetime) -> datetime:
    while candidate < reference - timedelta(hours=12):
        candidate += timedelta(days=1)
    return candidate
