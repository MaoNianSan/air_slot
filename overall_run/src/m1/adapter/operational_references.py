from __future__ import annotations

from datetime import datetime

import pandas as pd

from ..contracts import OperationalReferences, SupportedOperationalValue


SUPPORTED_REFERENCE_LEVELS = {
    "OFFICIAL_OBSERVED",
    "RECONSTRUCTED_HIGH",
    "SUPPORTED_PROXY",
    "OFFICIAL_OPERATIONAL",
    "INFERRED_OPERATIONAL",
    "OBSERVED_CHAIN_PROXY",
}


def _datetime(value: object) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    timestamp = pd.Timestamp(value)
    normalized = (
        timestamp.tz_localize("UTC")
        if timestamp.tzinfo is None
        else timestamp.tz_convert("UTC")
    )
    return normalized.to_pydatetime()


def _inactive(reason: str) -> SupportedOperationalValue:
    return SupportedOperationalValue(
        value=None,
        active=False,
        support_level="UNSUPPORTED",
        source_field=None,
        source_event_id=None,
        availability_time=None,
        reference_version=None,
        inactive_reason=reason,
    )


def _episode_reference(
    episode: pd.Series,
    *,
    value_field: str,
    support_field: str,
    version_field: str,
    required_type: str | None = None,
    type_field: str | None = None,
) -> SupportedOperationalValue:
    value = episode.get(value_field)
    support = str(episode.get(support_field, "UNSUPPORTED"))
    reference_type = str(episode.get(type_field, "")) if type_field else ""
    version = episode.get(version_field)
    active = (
        pd.notna(value)
        and pd.notna(version)
        and support in SUPPORTED_REFERENCE_LEVELS
        and (required_type is None or reference_type == required_type)
    )
    if not active:
        reason = "REFERENCE_PROVENANCE_MISSING"
        if required_type and reference_type and reference_type != required_type:
            reason = f"REFERENCE_TYPE_NOT_{required_type}"
        return _inactive(reason)
    return SupportedOperationalValue(
        value=value,
        active=True,
        support_level=support,
        source_field=value_field,
        source_event_id=None,
        availability_time=_datetime(episode.get(f"{value_field}_availability_time")),
        reference_version=str(version),
        inactive_reason=None,
    )


def _event_value(
    events: pd.DataFrame,
    flight_id: str,
    event_name: str,
) -> SupportedOperationalValue:
    rows = events[
        events.get("flight_id", pd.Series(dtype=str)).astype(str).eq(flight_id)
        & events.get("event_name", pd.Series(dtype=str)).astype(str).eq(event_name)
    ]
    if rows.empty:
        return _inactive(f"{event_name}_NOT_AVAILABLE")
    ordered = rows.assign(
        _availability=pd.to_datetime(rows["availability_time"], utc=True, errors="coerce")
    ).sort_values(["_availability", "event_id"], kind="mergesort")
    row = ordered.iloc[-1]
    support = str(row.get("support_level", "UNSUPPORTED"))
    if support == "UNSUPPORTED" or pd.isna(row.get("event_time")):
        return _inactive(f"{event_name}_UNSUPPORTED")
    return SupportedOperationalValue(
        value=_datetime(row.get("event_time")),
        active=True,
        support_level=support,
        source_field=str(row.get("source_field", event_name)),
        source_event_id=str(row.get("event_id")),
        availability_time=_datetime(row.get("availability_time")),
        reference_version=str(row.get("source_hash", "PRE_EVENT_V2")),
        inactive_reason=None,
    )


def build_operational_references(
    episode: pd.Series,
    visible_events: pd.DataFrame,
) -> OperationalReferences:
    predecessor = str(episode.get("predecessor_flight_id", ""))
    successor = str(episode.get("successor_flight_id", ""))
    return OperationalReferences(
        successor_sobt=_episode_reference(
            episode,
            value_field="successor_sobt",
            support_field="successor_sobt_support_level",
            version_field="successor_sobt_reference_version",
        ),
        turnaround_floor_minutes=_episode_reference(
            episode,
            value_field="turnaround_floor_minutes",
            support_field="turnaround_reference_support",
            version_field="turnaround_reference_version",
            required_type="OFFICIAL_FLOOR",
            type_field="turnaround_reference_type",
        ),
        taxi_reference_minutes=_episode_reference(
            episode,
            value_field="taxi_reference_minutes",
            support_field="taxi_reference_support",
            version_field="taxi_reference_version",
        ),
        predecessor_inblock_observed=_event_value(
            visible_events, predecessor, "AIBT_MINUS"
        ),
        successor_offblock_observed=_event_value(
            visible_events, successor, "AOBT_PLUS"
        ),
        successor_takeoff_observed=_event_value(
            visible_events, successor, "ATOT_PLUS"
        ),
    )
