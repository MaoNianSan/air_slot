"""Compatibility imports plus validation-only summaries for Data2 M1 checks."""

from collections import Counter

from model.common.enums import SupportState
from model.M1.preparation import normalization_rows
from model.PRE.development_support import (
    chain_stats,
    exposure_cells,
    load_typed_records,
    passenger_cells,
    publish_states,
    reference_summary,
    sample_three_way_cohort,
    stream_coupon_routes,
    stream_january_flights,
    taxi_cells,
    turnaround_cells,
)
from model.PRE.streaming.data2 import (
    config_hash,
    latest_weather,
    load_timezones,
    registry_hash,
    stream_completed_flights,
    weather_index_and_stats,
)


def source_stats(paths, *, root):
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in paths
    }


def weather_state_stats(prefixes):
    total = supported = supported_with_values = 0
    abstain_reasons = Counter()
    for states in prefixes:
        for state in states:
            weather = state.current_state.get("current_weather")
            if weather is None:
                continue
            total += 1
            if weather.support_state is SupportState.SUPPORTED:
                supported += 1
                if (
                    isinstance(weather.value, dict)
                    and weather.value.get("temperature_c") is not None
                ):
                    supported_with_values += 1
            else:
                abstain_reasons[weather.reason_code] += 1
    return {
        "states_with_weather_slot": total,
        "supported": supported,
        "abstain": total - supported,
        "abstain_reasons": dict(abstain_reasons),
        "supported_with_temperature_values": supported_with_values,
    }


__all__ = [
    "chain_stats",
    "config_hash",
    "exposure_cells",
    "latest_weather",
    "load_timezones",
    "load_typed_records",
    "normalization_rows",
    "passenger_cells",
    "publish_states",
    "reference_summary",
    "registry_hash",
    "sample_three_way_cohort",
    "source_stats",
    "stream_completed_flights",
    "stream_coupon_routes",
    "stream_january_flights",
    "taxi_cells",
    "turnaround_cells",
    "weather_index_and_stats",
    "weather_state_stats",
]
