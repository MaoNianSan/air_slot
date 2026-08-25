"""Compatibility facade for source-family canonical normalizers."""

from .normalization_common import deterministic_id, missing, number, parse_utc
from .normalization_flights import (
    canonicalize_flightlist_row,
    canonicalize_ontime_row,
    canonicalize_state_vector_row,
    canonicalize_trajectory_event,
)
from .normalization_references import (
    canonicalize_aggregate_row,
    canonicalize_airport_row,
    canonicalize_eurostat_passengers_payload,
    canonicalize_eurostat_payload,
    canonicalize_timezone_row,
)
from .normalization_weather import (
    _normalize_isd_station_id,
    canonicalize_isd_row,
    canonicalize_metar_row,
)

__all__ = [
    "_normalize_isd_station_id",
    "canonicalize_aggregate_row",
    "canonicalize_airport_row",
    "canonicalize_eurostat_passengers_payload",
    "canonicalize_eurostat_payload",
    "canonicalize_flightlist_row",
    "canonicalize_isd_row",
    "canonicalize_metar_row",
    "canonicalize_ontime_row",
    "canonicalize_state_vector_row",
    "canonicalize_timezone_row",
    "canonicalize_trajectory_event",
    "deterministic_id",
    "missing",
    "number",
    "parse_utc",
]
