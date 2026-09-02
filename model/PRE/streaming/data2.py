from __future__ import annotations

import csv
import gc
import json
import random
import time
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterable

import torch

from model.common.identity import content_id
from model.PRE.adapters.data2 import Data2Adapter, _normalize_isd_station_id
from model.PRE.adapters.registry import RawReadRequest
from model.PRE.canonical.data2_timestamps import (
    resolve_bts_actual_timestamp,
    resolve_bts_event_clock,
)
from model.PRE.canonical.normalization import (
    canonicalize_isd_row,
    canonicalize_ontime_row,
)
from model.PRE.canonical.normalization_common import deterministic_id, missing, number
from model.PRE.canonical.timezone import infer_rollover, local_hhmm_to_utc
from model.PRE.cohort import split_for_date
from model.PRE.episode.builder import (
    build_data2_episode_records,
)
from model.PRE.episode.containment import episode_containment_from_rows
from model.PRE.episode.node_builder import build_rolling_decision_nodes
from model.PRE.feature_registry.loader import load_registry_bundle
from model.PRE.pipeline import ProductionPREPublisher, ProductionPRERequest

PROJECTED_ONTIME_COLUMNS = (
    "FlightDate",
    "Reporting_Airline",
    "Tail_Number",
    "Flight_Number_Reporting_Airline",
    "Origin",
    "Dest",
    "CRSDepTime",
    "CRSArrTime",
    "DepTime",
    "ArrTime",
    "WheelsOff",
    "WheelsOn",
    "TaxiOut",
    "TaxiIn",
    "DepDelay",
    "ArrDelay",
    "DepDelayMinutes",
    "ArrDelayMinutes",
    "Cancelled",
    "Diverted",
)

FINAL_TEST_START = date(2019, 10, 1)
Heartbeat = Callable[..., None]


def load_timezones(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {row["iata"]: row["timezone"] for row in csv.DictReader(stream)}


def config_hash(root: Path) -> str:
    paths = (
        root / "configs" / "scientific" / "foundation.yaml",
        root / "configs" / "reproducibility" / "smoke.yaml",
        root / "configs" / "engineering" / "local.example.yaml",
    )
    ids = [
        {
            "path": str(path.relative_to(root)),
            "sha256": sha256(path.read_bytes()).hexdigest(),
        }
        for path in paths
    ]
    return content_id(ids)


def registry_hash(root: Path) -> str:
    bundle = load_registry_bundle(root / "registries")
    published = json.loads(
        (root / "registries" / "registry_manifest.json").read_text(encoding="utf-8")
    )
    if bundle.manifest.combined_sha256 != published["combined_sha256"]:
        raise RuntimeError("REGISTRY_MANIFEST_MISMATCH")
    return bundle.manifest.combined_sha256


def ontime_paths(
    root: Path,
    months: Iterable[int] = range(1, 10),
    *,
    allow_final_test: bool = False,
) -> tuple[Path, ...]:
    """Return month-bounded BTS paths.

    Development callers keep the historic Jan--Sep default and retain the
    Final Test guard.  A separately authorized FINAL_TEST materializer passes
    ``allow_final_test=True`` with Q4 month numbers; it never expands the
    source window beyond those requested partitions.
    """
    selected_months = tuple(int(month) for month in months)
    paths = tuple(
        next(
            (
                root
                / "data2"
                / "raw"
                / "bts"
                / "ontime"
                / "2019"
                / f"month={month:02d}"
            ).glob("*.csv")
        )
        for month in selected_months
    )
    if (
        not allow_final_test
        and any(path.parent.name in {"month=10", "month=11", "month=12"} for path in paths)
    ):
        raise RuntimeError("FINAL_TEST_ONTIME_PATH_SELECTED")
    return paths


def development_source_paths(root: Path) -> tuple[Path, ...]:
    data2_root = root / "data2"
    paths = (
        ontime_paths(root)
        + tuple(
            sorted((data2_root / "raw" / "weather" / "noaa" / "2019").glob("*.csv"))
        )
        + (
            data2_root / "refs" / "weather_station_map.csv",
            data2_root / "refs" / "us_airport_timezones.csv",
        )
    )
    forbidden = [
        path
        for path in paths
        if path.parent.name in {"month=10", "month=11", "month=12"}
    ]
    if forbidden:
        raise RuntimeError(f"FINAL_TEST_SOURCE_PATH_SELECTED:{forbidden[0]}")
    return paths


def development_source_manifest_hash(root: Path) -> str:
    return content_id(
        {
            str(path.relative_to(root)): [path.stat().st_size, path.stat().st_mtime_ns]
            for path in development_source_paths(root)
        }
    )


def aircraft_tail(rows: Iterable[dict]) -> tuple[dict, ...]:
    tail: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = (
            row["dataset_instance_id"],
            row["aircraft_id_namespace"],
            row["aircraft_id"],
        )
        order = (
            row["actual_departure_utc"],
            row["actual_arrival_utc"],
            row["flight_id"],
        )
        previous = tail.get(key)
        if previous is None or order > (
            previous["actual_departure_utc"],
            previous["actual_arrival_utc"],
            previous["flight_id"],
        ):
            tail[key] = row
    return tuple(tail.values())


def iter_lightweight_flights(
    path: Path,
    zones: dict[str, str],
    *,
    heartbeat: Heartbeat | None = None,
    phase: str = "DATA_PREPARATION_ONTIME",
    include_warning_fields: bool = False,
):
    started = last_heartbeat = time.perf_counter()
    input_rows = skipped = 0
    total_bytes = path.stat().st_size
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        positions = {name: header.index(name) for name in PROJECTED_ONTIME_COLUMNS}
        for raw in reader:
            input_rows += 1

            def value(name: str) -> str:
                position = positions[name]
                return raw[position] if position < len(raw) else ""

            try:
                day = date.fromisoformat(value("FlightDate")[:10])
                origin, destination = value("Origin"), value("Dest")
                if (
                    origin not in zones
                    or destination not in zones
                    or missing(value("Tail_Number"))
                ):
                    raise ValueError
                scheduled_departure = local_hhmm_to_utc(
                    day, value("CRSDepTime"), zones[origin]
                )
                scheduled_arrival = local_hhmm_to_utc(
                    day, value("CRSArrTime"), zones[destination]
                )
                if scheduled_departure is None or scheduled_arrival is None:
                    raise ValueError
                scheduled_arrival = infer_rollover(
                    scheduled_departure, scheduled_arrival
                )
                if bool(number(value("Cancelled")) or 0) or bool(
                    number(value("Diverted")) or 0
                ):
                    raise ValueError
                departure = resolve_bts_actual_timestamp(
                    service_day=day,
                    schedule_utc=scheduled_departure,
                    direct_hhmm=value("DepTime"),
                    timezone_name=zones[origin],
                    signed_delay_value=value("DepDelay"),
                    reporting_delay_minutes_value=value("DepDelayMinutes"),
                    label="DEPARTURE",
                )
                arrival = resolve_bts_actual_timestamp(
                    service_day=day,
                    schedule_utc=scheduled_arrival,
                    direct_hhmm=value("ArrTime"),
                    timezone_name=zones[destination],
                    signed_delay_value=value("ArrDelay"),
                    reporting_delay_minutes_value=value("ArrDelayMinutes"),
                    label="ARRIVAL",
                )
                taxi_out = number(value("TaxiOut"))
                actual_departure = departure.canonical_utc
                actual_arrival = arrival.canonical_utc
                if actual_departure is None or actual_arrival is None:
                    raise ValueError
                direct_wheels_off = resolve_bts_event_clock(
                    service_day=day,
                    reference_utc=actual_departure,
                    direct_hhmm=value("WheelsOff"),
                    timezone_name=zones[origin],
                )
                derived_wheels_off = (
                    None
                    if taxi_out is None
                    else actual_departure + timedelta(minutes=taxi_out)
                )
                wheels_off = direct_wheels_off or derived_wheels_off
                flight_parts = {
                    name: value(name)
                    for name in (
                        "FlightDate",
                        "Reporting_Airline",
                        "Flight_Number_Reporting_Airline",
                        "Origin",
                        "Dest",
                    )
                }
                row = {
                    "flight_id": deterministic_id("flight", flight_parts),
                    "aircraft_id": value("Tail_Number").strip(),
                    "aircraft_id_namespace": "REGISTRATION",
                    "origin_airport_id": origin,
                    "destination_airport_id": destination,
                    "event_start_time": scheduled_departure,
                    "event_end_time": scheduled_arrival,
                    "actual_arrival_utc": actual_arrival,
                    "actual_departure_utc": actual_departure,
                    "dataset_instance_id": "data2_2019",
                    "service_date": day.isoformat(),
                }
                if include_warning_fields:
                    row.update(
                        {
                            "scheduled_departure_utc": scheduled_departure,
                            "scheduled_arrival_utc": scheduled_arrival,
                            "wheels_off_utc": wheels_off,
                            "taxi_out_minutes": taxi_out,
                            "canonical_schedule_record_id": deterministic_id(
                                "canonical-flight",
                                {
                                    "raw": deterministic_id(
                                        "raw",
                                        {
                                            "source": "bts_ontime",
                                            **flight_parts,
                                            "tail": value("Tail_Number"),
                                        },
                                    ),
                                    "role": "schedule",
                                },
                            ),
                        }
                    )
                yield row
            except Exception:
                skipped += 1
            now = time.perf_counter()
            if heartbeat and now - last_heartbeat >= 45:
                heartbeat(
                    phase,
                    started=started,
                    rows=input_rows,
                    current_file=path.name,
                    progress=min(stream.buffer.tell() / max(total_bytes, 1), 1.0),
                )
                last_heartbeat = now
    return {"input_rows": input_rows, "skipped_rows": skipped}


def lightweight_flights(
    path: Path,
    zones: dict[str, str],
    *,
    heartbeat: Heartbeat | None = None,
    include_warning_fields: bool = False,
) -> tuple[list[dict], int]:
    rows = []
    generator = iter_lightweight_flights(
        path,
        zones,
        heartbeat=heartbeat,
        include_warning_fields=include_warning_fields,
    )
    try:
        while True:
            rows.append(next(generator))
    except StopIteration as stop:
        audit = stop.value or {}
    return rows, int(audit.get("skipped_rows", 0))


def episode_records_from_lightweight_flights(rows: Iterable[dict]):
    return build_data2_episode_records(rows)


def preparation_state_key(
    root: Path,
    paths: tuple[Path, ...],
    counts: dict,
    seed: int,
    *,
    semantic_token: str | None = None,
) -> str:
    payload = {
        "sources": {
            str(path.relative_to(root)): [path.stat().st_size, path.stat().st_mtime_ns]
            for path in paths
        },
        "cohort_counts": counts,
        "cohort_seed": seed,
        "carry_rule": "LAST_ACTUAL_DEPARTURE_ROW_PER_AIRCRAFT",
        "split_containment_rule": "V5_FULL_EPISODE_SUPPORT_V1",
    }
    if semantic_token is not None:
        payload["semantic_token"] = semantic_token
    return content_id(payload)


def save_preparation_state(
    *,
    state_path: Path,
    manifest_path: Path,
    key: str,
    next_month: int,
    reservoirs: dict,
    pool_sizes: dict,
    rng: random.Random,
    previous_rows: tuple[dict, ...],
    per_month: dict,
    skipped_total: int,
    total_episodes: int,
) -> None:
    payload = {
        "state_key": key,
        "next_month": next_month,
        "reservoirs": reservoirs,
        "pool_sizes": pool_sizes,
        "rng_state": rng.getstate(),
        "previous_rows": previous_rows,
        "per_month": per_month,
        "skipped_total": skipped_total,
        "total_episodes": total_episodes,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(state_path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(state_path)
    manifest = {
        "schema_version": "PRE_DATA2_COHORT_PREPARATION_PROGRESS_V2",
        "state_key": key,
        "completed_months": [f"2019-{month:02d}" for month in range(1, next_month)],
        "next_month": None if next_month > 9 else f"2019-{next_month:02d}",
        "completion_status": "PASS" if next_month > 9 else "RUNNING",
        "pool_sizes": dict(pool_sizes),
        "sampled_counts": {name: len(values) for name, values in reservoirs.items()},
        "cross_month_carry_rows": len(previous_rows),
        "final_test_access_count": 0,
    }
    temporary_manifest = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    temporary_manifest.replace(manifest_path)


def episode_reservoirs(
    root: Path,
    paths: tuple[Path, ...],
    zones: dict[str, str],
    *,
    cohort_counts: dict[str, int],
    cohort_seed: int,
    state_path: Path,
    manifest_path: Path,
    resume: bool = True,
    heartbeat: Heartbeat | None = None,
    semantic_token: str | None = None,
    include_warning_fields: bool = False,
    flight_observer: Callable[[str, list[dict]], None] | None = None,
    episode_observer: Callable[[str, object, dict[str, dict]], None] | None = None,
):
    reservoirs = {name: [] for name in cohort_counts}
    pool_sizes = {name: 0 for name in cohort_counts}
    rng = random.Random(cohort_seed)
    previous_rows: tuple[dict, ...] = ()
    per_month: dict[str, int] = {}
    skipped_total = total_episodes = 0
    start_month = 1
    state_key = preparation_state_key(
        root,
        paths,
        cohort_counts,
        cohort_seed,
        semantic_token=semantic_token,
    )
    if resume and state_path.is_file():
        payload = torch.load(state_path, map_location="cpu", weights_only=False)
        if payload.get("state_key") == state_key:
            reservoirs = payload["reservoirs"]
            pool_sizes = payload["pool_sizes"]
            rng.setstate(payload["rng_state"])
            previous_rows = tuple(payload["previous_rows"])
            per_month = payload["per_month"]
            skipped_total = payload["skipped_total"]
            total_episodes = payload["total_episodes"]
            start_month = int(payload["next_month"])
    for month, path in enumerate(paths, start=1):
        if month < start_month:
            continue
        month_started = time.perf_counter()
        current_rows, skipped = lightweight_flights(
            path,
            zones,
            heartbeat=heartbeat,
            include_warning_fields=include_warning_fields,
        )
        skipped_total += skipped
        per_month[f"{month:02d}"] = len(current_rows)
        if flight_observer is not None:
            current_split = split_for_date(date(2019, month, 1))
            flight_observer(current_split, current_rows)
        chunk = list(previous_rows) + current_rows
        by_id = {row["flight_id"]: row for row in chunk}
        month_key = f"2019-{month:02d}"
        month_episodes = 0
        for episode in sorted(
            build_data2_episode_records(chunk), key=lambda item: item.episode_id
        ):
            service_date = by_id[episode.successor_flight_id].get("service_date")
            if not service_date or service_date[:7] != month_key:
                continue
            split = split_for_date(date.fromisoformat(service_date))
            if episode_observer is not None:
                episode_observer(split, episode, by_id)
            containment = episode_containment_from_rows(episode, by_id)
            if not containment.allowed:
                continue
            if split == "test":
                raise RuntimeError("FINAL_TEST_EPISODE_MATERIALIZED")
            pool_sizes[split] += 1
            total_episodes += 1
            month_episodes += 1
            target = cohort_counts[split]
            if target <= 0:
                continue
            reservoir = reservoirs[split]
            seen = pool_sizes[split]
            if len(reservoir) < target:
                reservoir.append(episode)
            else:
                index = rng.randrange(seen)
                if index < target:
                    reservoir[index] = episode
        previous_rows = aircraft_tail(current_rows)
        save_preparation_state(
            state_path=state_path,
            manifest_path=manifest_path,
            key=state_key,
            next_month=month + 1,
            reservoirs=reservoirs,
            pool_sizes=pool_sizes,
            rng=rng,
            previous_rows=previous_rows,
            per_month=per_month,
            skipped_total=skipped_total,
            total_episodes=total_episodes,
        )
        if heartbeat:
            heartbeat(
                "DATA_PREPARATION_MONTH_COMPLETE",
                started=month_started,
                rows=len(current_rows),
                episodes=month_episodes,
                current_month=month_key,
                current_file=path.name,
                progress=month / len(paths),
            )
        del chunk, by_id, current_rows
        gc.collect()
    return reservoirs, pool_sizes, total_episodes, per_month, skipped_total


def load_selected_typed_records(
    episodes,
    paths: tuple[Path, ...],
    zones: dict[str, str],
    *,
    heartbeat: Heartbeat | None = None,
):
    needed = {
        flight_id
        for episode in episodes
        for flight_id in (episode.predecessor_flight_id, episode.successor_flight_id)
    }
    schedules, outcomes = {}, {}
    started = last_heartbeat = time.perf_counter()
    input_rows = 0
    for path in paths:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            for raw in csv.DictReader(stream):
                input_rows += 1
                flight_parts = {
                    name: raw.get(name)
                    for name in (
                        "FlightDate",
                        "Reporting_Airline",
                        "Flight_Number_Reporting_Airline",
                        "Origin",
                        "Dest",
                    )
                }
                flight_id = deterministic_id("flight", flight_parts)
                if flight_id not in needed or flight_id in schedules:
                    continue
                try:
                    schedule, outcome = canonicalize_ontime_row(
                        {name: raw.get(name, "") for name in PROJECTED_ONTIME_COLUMNS},
                        zones,
                    )
                except Exception:
                    continue
                schedules[flight_id], outcomes[flight_id] = schedule, outcome
                now = time.perf_counter()
                if heartbeat and now - last_heartbeat >= 45:
                    heartbeat(
                        "DATA_PREPARATION_TYPED_RECORDS",
                        started=started,
                        rows=input_rows,
                        episodes=len(schedules) // 2,
                        current_file=path.name,
                    )
                    last_heartbeat = now
    missing_ids = needed - set(schedules)
    if missing_ids:
        raise RuntimeError(f"COHORT_FLIGHT_RECORD_MISSING:{sorted(missing_ids)[:5]}")
    return schedules, outcomes


def weather_index(
    data2_root: Path,
    replay_lag_minutes: int,
    *,
    start_inclusive: date | None = None,
    end_exclusive: date = FINAL_TEST_START,
    heartbeat: Heartbeat | None = None,
):
    with (data2_root / "refs" / "weather_station_map.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        station_map = {
            _normalize_isd_station_id(row["station"]): row["airport"]
            for row in csv.DictReader(stream)
        }
    index = defaultdict(list)
    accepted = input_rows = 0
    started = last_heartbeat = time.perf_counter()
    paths = tuple(
        sorted((data2_root / "raw" / "weather" / "noaa" / "2019").glob("*.csv"))
    )
    limit = end_exclusive.isoformat()
    start = None if start_inclusive is None else start_inclusive.isoformat()
    for path_index, path in enumerate(paths, start=1):
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            for row in csv.DictReader(stream):
                input_rows += 1
                stamp = str(row.get("DATE", ""))
                if stamp >= limit:
                    break
                if not stamp.startswith("2019-"):
                    continue
                if start is not None and stamp < start:
                    continue
                try:
                    observation = canonicalize_isd_row(
                        row,
                        station_map=station_map,
                        replay_lag_minutes=replay_lag_minutes,
                    )
                except Exception:
                    continue
                index[observation.airport_id].append(observation)
                accepted += 1
                now = time.perf_counter()
                if heartbeat and now - last_heartbeat >= 45:
                    heartbeat(
                        "DATA_PREPARATION_WEATHER",
                        started=started,
                        rows=input_rows,
                        current_file=path.name,
                        progress=path_index / max(len(paths), 1),
                    )
                    last_heartbeat = now
    packed = {}
    for airport, observations in index.items():
        ordered = tuple(sorted(observations, key=lambda item: item.availability_time))
        packed[airport] = (
            tuple(item.availability_time for item in ordered),
            ordered,
        )
    return packed, {
        "accepted_train_calibration_development_observations": accepted,
        "airports": len(packed),
        "final_test_access_count": 0,
    }


def latest_weather(index, airport_id, cutoff, max_age_minutes):
    values = index.get(airport_id)
    if not values:
        return None
    times, observations = values
    position = bisect_right(times, cutoff) - 1
    if position < 0:
        return None
    observation = observations[position]
    if observation.availability_time < cutoff - timedelta(minutes=max_age_minutes):
        return None
    return observation


def publish_episode_states(
    item,
    config_hash_value: str,
    registry_hash_value: str,
    weather,
    weather_max_age_minutes: int,
    *,
    publisher: ProductionPREPublisher,
    taxi_reference=None,
    turnaround_reference=None,
):
    episode, successor_schedule, predecessor_outcome, successor_outcome = item
    nodes = build_rolling_decision_nodes(
        episode=episode,
        predecessor_outcome=predecessor_outcome,
        successor_outcome=successor_outcome,
        config_hash=config_hash_value,
        registry_hash=registry_hash_value,
        factual_availability_policy=publisher.factual_availability_policy,
        factual_replay_declared_lag_minutes=publisher.factual_replay_declared_lag_minutes,
    )
    states = []
    for node in nodes:
        observation = latest_weather(
            weather,
            episode.connection_airport_id,
            node.information_cutoff,
            weather_max_age_minutes,
        )
        records = (successor_schedule, predecessor_outcome, successor_outcome)
        if observation is not None:
            records = records + (observation,)
        states.append(
            publisher.publish(
                ProductionPRERequest(
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
                    factual_availability_policy=publisher.factual_availability_policy,
                    factual_replay_declared_lag_minutes=publisher.factual_replay_declared_lag_minutes,
                    taxi_reference=taxi_reference,
                    turnaround_reference=turnaround_reference,
                )
            ).pre_state
        )
    return nodes, tuple(states)


def stream_completed_flights(
    csv_paths,
    projected,
    zones,
    *,
    include_service_date: bool = False,
):
    flight_rows, taxi_rows = [], []
    skipped = 0
    per_month = Counter()
    for csv_path in csv_paths:
        month = csv_path.parent.name.replace("month=", "")
        with csv_path.open(
            encoding="utf-8-sig", errors="replace", newline=""
        ) as stream:
            for raw in csv.DictReader(stream):
                try:
                    schedule, outcome = canonicalize_ontime_row(
                        {key: raw.get(key, "") for key in projected}, zones
                    )
                except Exception:
                    skipped += 1
                    continue
                if (
                    schedule.aircraft_id is None
                    or outcome.cancelled
                    or outcome.diverted
                ):
                    skipped += 1
                    continue
                row = {
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
                }
                if include_service_date:
                    row["service_date"] = (
                        schedule.service_date.isoformat()
                        if schedule.service_date
                        else None
                    )
                flight_rows.append(row)
                per_month[month] += 1
                if outcome.taxi_out_minutes is not None:
                    taxi = {
                        "dataset_instance_id": schedule.dataset_instance_id,
                        "aircraft_id": schedule.aircraft_id,
                        "flight_id": schedule.flight_id,
                        "origin_airport_id": schedule.origin_airport_id,
                        "taxi_out_minutes": outcome.taxi_out_minutes,
                    }
                    if include_service_date:
                        taxi["service_date"] = row["service_date"]
                    taxi_rows.append(taxi)
    return flight_rows, taxi_rows, skipped, dict(per_month)


def weather_index_and_stats(
    data2_root: Path,
    output: Path,
    replay_lag_minutes: int,
    *,
    period: str | None,
):
    request = RawReadRequest(
        dataset_instance_id="data2_2019",
        source_family="noaa_isd",
        raw_root=data2_root,
        output_root=output,
        year=2019,
    )
    index, per_airport = defaultdict(list), Counter()
    total = 0
    for observation in Data2Adapter().iter_canonical(
        request, replay_lag_minutes=replay_lag_minutes
    ):
        if observation.event_time is None:
            continue
        if period and observation.event_time.strftime("%Y-%m") != period:
            continue
        if not period and observation.event_time.year != 2019:
            continue
        if not observation.airport_id or observation.availability_time is None:
            continue
        total += 1
        per_airport[observation.airport_id] += 1
        index[observation.airport_id].append(observation)
    for airport in index:
        index[airport].sort(key=lambda observation: observation.availability_time)
    label = "january_observations" if period else "year_observations"
    return dict(index), {
        label: total,
        "airports_covered": len(per_airport),
        "top_airports": per_airport.most_common(10),
        "injected": True,
    }
