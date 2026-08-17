from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from model.common.identity import content_id
from model.PRE.adapters.data2 import _normalize_isd_station_id
from model.PRE.canonical.normalization import canonicalize_isd_row, canonicalize_ontime_row
from model.PRE.episode.builder import build_data2_episode_records
from model.PRE.episode.node_builder import build_rolling_decision_nodes
from model.PRE.pipeline import ProductionPREPublisher, ProductionPRERequest, publish_production_pre
from model.PRE.streaming.data2 import (
    PROJECTED_ONTIME_COLUMNS,
    config_hash,
    latest_weather,
    load_timezones,
    registry_hash,
)


ROW_LIMIT = 50_000
EPISODE_LIMIT = 8
PROFILE_MONTH = "2019-01"


@dataclass(frozen=True)
class PREProfileBundle:
    selected: tuple
    items: dict
    nodes_by_episode: dict
    states_by_episode: dict
    profile_input_hash: str
    input_rows: int
    decision_node_count: int
    airport: str
    station: str
    weather_rows: int
    bytes_read: int


def _discover_source(data2_root: Path) -> Path:
    files = tuple(
        sorted((data2_root / "raw" / "bts" / "ontime" / "2019" / "month=01").glob("*.csv"))
    )
    if len(files) != 1:
        raise RuntimeError(f"PROFILE_JANUARY_FILE_COUNT:{len(files)}")
    return files[0]


def _read_projected_subset(path: Path) -> list[dict[str, str]]:
    rows = []
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        positions = {name: header.index(name) for name in PROJECTED_ONTIME_COLUMNS}
        for raw in reader:
            rows.append(
                {
                    name: raw[index] if index < len(raw) else ""
                    for name, index in positions.items()
                }
            )
            if len(rows) >= ROW_LIMIT:
                break
    return rows


def _convert_rows(raw_rows, zones):
    converted = []
    for raw in raw_rows:
        try:
            converted.append(canonicalize_ontime_row(raw, zones))
        except Exception:
            continue
    return converted


def _filter_completed(converted):
    rows = []
    records = {}
    for schedule, outcome in converted:
        if schedule.aircraft_id is None or outcome.cancelled or outcome.diverted:
            continue
        if outcome.actual_arrival_utc is None or outcome.actual_departure_utc is None:
            continue
        rows.append(
            {
                "flight_id": schedule.flight_id,
                "aircraft_id": schedule.aircraft_id,
                "aircraft_id_namespace": schedule.aircraft_id_namespace,
                "origin_airport_id": schedule.origin_airport_id,
                "destination_airport_id": schedule.destination_airport_id,
                "event_start_time": schedule.event_start_time,
                "event_end_time": schedule.event_end_time,
                "actual_arrival_utc": outcome.actual_arrival_utc,
                "actual_departure_utc": outcome.actual_departure_utc,
                "dataset_instance_id": schedule.dataset_instance_id,
                "service_date": schedule.service_date.isoformat(),
            }
        )
        records[schedule.flight_id] = (schedule, outcome)
    return rows, records


def _weather_sources(data2_root: Path):
    station_map_path = data2_root / "refs" / "weather_station_map.csv"
    with station_map_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = tuple(csv.DictReader(stream))
    airport_to_station = {
        row["airport"]: _normalize_isd_station_id(row["station"]) for row in rows
    }
    station_to_airport = {
        _normalize_isd_station_id(row["station"]): row["airport"] for row in rows
    }
    files = {
        _normalize_isd_station_id(path.stem): path
        for path in sorted((data2_root / "raw" / "weather" / "noaa" / "2019").glob("*.csv"))
    }
    return station_map_path, airport_to_station, station_to_airport, files


def _select_episodes(episodes, airport_to_station, weather_files):
    available = [
        episode
        for episode in episodes
        if airport_to_station.get(episode.connection_airport_id) in weather_files
    ]
    counts = Counter(episode.connection_airport_id for episode in available)
    if not counts:
        raise RuntimeError("PROFILE_NO_EPISODE_WITH_WEATHER_STATION")
    airport = sorted(counts, key=lambda item: (-counts[item], item))[0]
    selected = tuple(
        sorted(
            (episode for episode in available if episode.connection_airport_id == airport),
            key=lambda item: item.episode_id,
        )[:EPISODE_LIMIT]
    )
    if len(selected) < EPISODE_LIMIT:
        raise RuntimeError(f"PROFILE_EPISODE_COUNT_TOO_SMALL:{len(selected)}")
    return airport, selected


def _read_weather(path, station_to_airport, replay_lag_minutes):
    observations = []
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
        for row in csv.DictReader(stream):
            stamp = str(row.get("DATE", ""))
            if stamp >= "2019-02-01":
                break
            if not stamp.startswith(PROFILE_MONTH):
                continue
            try:
                observations.append(
                    canonicalize_isd_row(
                        row,
                        station_map=station_to_airport,
                        replay_lag_minutes=replay_lag_minutes,
                    )
                )
            except Exception:
                continue
    return tuple(sorted(observations, key=lambda item: item.availability_time))


def _build_nodes(items, config_hash_value, registry_hash_value):
    return {
        episode_id: tuple(
            build_rolling_decision_nodes(
                episode=item[0],
                predecessor_outcome=item[2],
                successor_outcome=item[3],
                config_hash=config_hash_value,
                registry_hash=registry_hash_value,
            )
        )
        for episode_id, item in items.items()
    }


def _match_weather(items, nodes_by_episode, observations, max_age):
    if observations:
        airport = observations[0].airport_id
        index = {
            airport: (
                tuple(item.availability_time for item in observations),
                observations,
            )
        }
    else:
        index = {}
    return {
        episode_id: tuple(
            latest_weather(
                index,
                item[0].connection_airport_id,
                node.information_cutoff,
                max_age,
            )
            for node in nodes_by_episode[episode_id]
        )
        for episode_id, item in items.items()
    }


def _publish(
    items,
    nodes_by_episode,
    weather_by_episode,
    config_hash_value,
    registry_hash_value,
    *,
    optimized,
):
    publisher = ProductionPREPublisher.from_project() if optimized else None
    states_by_episode = {}
    for episode_id, item in items.items():
        episode, schedule, _, _ = item
        states = []
        for node, observation in zip(
            nodes_by_episode[episode_id], weather_by_episode[episode_id]
        ):
            records = (schedule,) if observation is None else (schedule, observation)
            request = ProductionPRERequest(
                episode_id=episode.episode_id,
                predecessor_id=episode.predecessor_flight_id,
                successor_id=episode.successor_flight_id,
                dataset_instance_id="data2_2019",
                decision_time=node.decision_time,
                information_cutoff=node.information_cutoff,
                records=records,
                config_hash=config_hash_value,
                registry_hash=registry_hash_value,
                connection_airport_id=episode.connection_airport_id,
                operational_stage=node.operational_stage,
                node_index=node.node_index,
                roll_minutes=node.roll_minutes,
            )
            result = (
                publish_production_pre(request)
                if publisher is None
                else publisher.publish(request)
            )
            states.append(result.pre_state)
        states_by_episode[episode_id] = tuple(states)
    return states_by_episode


def build_profile_pre_bundle(scientific, *, root: Path, profiler, optimized: bool):
    data2_root = root / "data2"
    path = profiler.capture("file_discovery", lambda: _discover_source(data2_root))
    raw_rows = profiler.capture(
        "source_read",
        lambda: _read_projected_subset(path),
        bytes_read=path.stat().st_size,
        note="PRE-owned projected source read.",
    )
    input_hash = content_id({"path": str(path.relative_to(root)), "rows": raw_rows})
    zones = load_timezones(data2_root / "refs" / "us_airport_timezones.csv")
    converted = profiler.capture(
        "dtype_datetime_conversion", lambda: _convert_rows(raw_rows, zones), input_rows=len(raw_rows)
    )
    filtered, records = profiler.capture(
        "flight_filtering", lambda: _filter_completed(converted), input_rows=len(converted)
    )
    episodes = profiler.capture(
        "predecessor_successor_pairing",
        lambda: build_data2_episode_records(filtered),
        input_rows=len(filtered),
    )
    station_map_path, airport_to_station, station_to_airport, weather_files = _weather_sources(
        data2_root
    )
    airport, selected = _select_episodes(episodes, airport_to_station, weather_files)
    items = profiler.capture(
        "schedule_identity_join",
        lambda: {
            episode.episode_id: (
                episode,
                records[episode.successor_flight_id][0],
                records[episode.predecessor_flight_id][1],
                records[episode.successor_flight_id][1],
            )
            for episode in selected
        },
        input_rows=len(selected),
    )
    station = airport_to_station[airport]
    weather_path = weather_files[station]
    replay_lag = int(scientific.parameters["data2_weather_replay_lag_minutes"].value)
    weather = profiler.capture(
        "weather_read",
        lambda: _read_weather(weather_path, station_to_airport, replay_lag),
        bytes_read=weather_path.stat().st_size,
    )
    config_hash_value, registry_hash_value = config_hash(root), registry_hash(root)
    nodes_by_episode = profiler.capture(
        "canonical_rolling_node_construction",
        lambda: _build_nodes(items, config_hash_value, registry_hash_value),
        input_rows=len(items),
    )
    decision_node_count = sum(len(value) for value in nodes_by_episode.values())
    max_age = int(scientific.parameters["weather_max_age_minutes"].value)
    weather_by_episode = profiler.capture(
        "weather_matching_join",
        lambda: _match_weather(items, nodes_by_episode, weather, max_age),
        input_rows=decision_node_count,
    )
    states_by_episode = profiler.capture(
        "pre_safe_feature_construction",
        lambda: _publish(
            items,
            nodes_by_episode,
            weather_by_episode,
            config_hash_value,
            registry_hash_value,
            optimized=optimized,
        ),
        input_rows=decision_node_count,
    )
    return PREProfileBundle(
        selected=selected,
        items=items,
        nodes_by_episode=nodes_by_episode,
        states_by_episode=states_by_episode,
        profile_input_hash=input_hash,
        input_rows=len(raw_rows),
        decision_node_count=decision_node_count,
        airport=airport,
        station=station,
        weather_rows=len(weather),
        bytes_read=path.stat().st_size + weather_path.stat().st_size + station_map_path.stat().st_size,
    )
