"""Shared BTS actual-time reconstruction under signed-delay semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .normalization_common import number
from .timezone import infer_rollover, local_hhmm_to_utc


@dataclass(frozen=True)
class BtsActualTimestampResolution:
    canonical_utc: datetime | None
    direct_utc: datetime | None
    signed_target_utc: datetime | None
    normal_rollover_direct_utc: datetime | None
    difference_minutes: float | None
    date_offset_resolved: bool
    date_offset_days: int
    multi_day_offset: bool
    flags: tuple[str, ...]


def _date_resolved_direct(
    *,
    service_day: date,
    direct_hhmm: Any,
    timezone_name: str,
    signed_target_utc: datetime,
) -> datetime:
    target_day = signed_target_utc.astimezone(ZoneInfo(timezone_name)).date()
    candidates = tuple(
        local_hhmm_to_utc(
            target_day + timedelta(days=offset), direct_hhmm, timezone_name
        )
        for offset in (-1, 0, 1)
    )
    available = tuple(item for item in candidates if item is not None)
    if not available:
        raise ValueError("BTS_DIRECT_CLOCK_EXPECTED")
    return min(
        available,
        key=lambda item: (abs((item - signed_target_utc).total_seconds()), item),
    )


def resolve_bts_actual_timestamp(
    *,
    service_day: date,
    schedule_utc: datetime,
    direct_hhmm: Any,
    timezone_name: str,
    signed_delay_value: Any,
    reporting_delay_minutes_value: Any,
    label: str,
) -> BtsActualTimestampResolution:
    """Resolve a BTS direct HHMM using signed delay only for date disambiguation."""
    signed_delay = number(signed_delay_value)
    reporting_delay = number(reporting_delay_minutes_value)
    parsed_direct = local_hhmm_to_utc(service_day, direct_hhmm, timezone_name)
    normal_direct = (
        None if parsed_direct is None else infer_rollover(schedule_utc, parsed_direct)
    )
    signed_target = (
        None if signed_delay is None else schedule_utc + timedelta(minutes=signed_delay)
    )
    flags = {"BTS_DIRECT_CLOCK_WITH_SIGNED_DELAY_DATE_DISAMBIGUATION"}

    if signed_delay is not None and reporting_delay is not None:
        if abs(reporting_delay - max(signed_delay, 0.0)) > 1.0:
            flags.add("BTS_NONNEGATIVE_DELAY_REPORTING_RELATION_VIOLATION")

    resolved_direct = normal_direct
    difference = None
    date_offset_resolved = False
    date_offset_days = 0
    if parsed_direct is not None and signed_target is not None:
        resolved_direct = _date_resolved_direct(
            service_day=service_day,
            direct_hhmm=direct_hhmm,
            timezone_name=timezone_name,
            signed_target_utc=signed_target,
        )
        difference = abs((resolved_direct - signed_target).total_seconds()) / 60.0
        if normal_direct is not None:
            zone = ZoneInfo(timezone_name)
            date_offset_days = (
                resolved_direct.astimezone(zone).date()
                - normal_direct.astimezone(zone).date()
            ).days
            date_offset_resolved = date_offset_days != 0
        if date_offset_resolved:
            flags.add(f"BTS_SIGNED_DELAY_DATE_OFFSET_RESOLVED_{label}")
        if difference > 1.0:
            flags.update(
                {
                    "BTS_SIGNED_DELAY_DIRECT_CLOCK_INCONSISTENCY",
                    f"BTS_SIGNED_DELAY_DIRECT_CLOCK_INCONSISTENCY_{label}",
                }
            )
    elif parsed_direct is not None:
        flags.add("SIGNED_DELAY_DATE_DISAMBIGUATION_UNAVAILABLE")
    elif signed_target is not None:
        flags.add("DIRECT_CLOCK_MISSING_SIGNED_DELAY_FALLBACK")
    else:
        flags.add("BTS_ACTUAL_TIMESTAMP_UNSUPPORTED")

    multi_day = signed_delay is not None and abs(signed_delay) >= 24 * 60
    if multi_day:
        flags.add(f"BTS_SIGNED_DELAY_MULTI_DAY_OFFSET_{label}")
    canonical = resolved_direct if resolved_direct is not None else signed_target
    return BtsActualTimestampResolution(
        canonical_utc=canonical,
        direct_utc=resolved_direct,
        signed_target_utc=signed_target,
        normal_rollover_direct_utc=normal_direct,
        difference_minutes=difference,
        date_offset_resolved=date_offset_resolved,
        date_offset_days=date_offset_days,
        multi_day_offset=multi_day,
        flags=tuple(sorted(flags)),
    )


def resolve_bts_event_clock(
    *,
    service_day: date,
    reference_utc: datetime,
    direct_hhmm: Any,
    timezone_name: str,
) -> datetime | None:
    parsed = local_hhmm_to_utc(service_day, direct_hhmm, timezone_name)
    return None if parsed is None else infer_rollover(reference_utc, parsed)


__all__ = [
    "BtsActualTimestampResolution",
    "resolve_bts_actual_timestamp",
    "resolve_bts_event_clock",
]
