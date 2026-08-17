from __future__ import annotations

import csv
import random
from collections import defaultdict

from model.common.identity import content_id
from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.pipeline import ProductionPREPublisher
from model.PRE.streaming.data2 import load_timezones, publish_episode_states


def stream_january_flights(csv_path, projected, zones):
    from model.PRE.streaming.data2 import stream_completed_flights

    flight_rows, taxi_rows, skipped, _ = stream_completed_flights(
        (csv_path,), projected, zones, include_service_date=False
    )
    return flight_rows, taxi_rows, skipped


def stream_coupon_routes(csv_paths):
    sums, counts = defaultdict(float), defaultdict(int)
    raw_rows = missing_passengers = 0
    for csv_path in csv_paths:
        with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader)
            passenger_index = header.index("Passengers")
            origin_index = header.index("Origin")
            destination_index = header.index("Dest")
            for raw in reader:
                if not raw or len(raw) <= max(
                    passenger_index, origin_index, destination_index
                ):
                    continue
                raw_rows += 1
                origin = raw[origin_index].strip()
                destination = raw[destination_index].strip()
                if not origin or not destination:
                    continue
                try:
                    passengers = float(raw[passenger_index])
                except ValueError:
                    missing_passengers += 1
                    continue
                sums[(origin, destination)] += passengers
                counts[(origin, destination)] += 1
    rows = [
        {
            "dataset_instance_id": "data2_2019",
            "canonical_record_id": content_id(
                {"source": "bts_db1b", "origin": origin, "destination": destination}
            ),
            "join_key": {"origin": origin, "destination": destination},
            "reference_period": "2019",
            "value": total,
            "record_count": counts[(origin, destination)],
            "split": "train",
        }
        for (origin, destination), total in sorted(sums.items())
    ]
    return rows, raw_rows, missing_passengers


def reference_summary(reference, *, cells: list[dict], globals_: dict | None = None) -> dict:
    return {
        "rule_id": reference.rule_id,
        "rule_version": reference.rule_version,
        "reference_id": reference.reference_id,
        "fit_period": reference.fit_period,
        "manifest_freeze_id": reference.manifest_freeze_id,
        "support_state": reference.support_state.value,
        "cells_count": len(reference.cells),
        **(globals_ or {}),
        "cells": cells,
    }


def turnaround_cells(reference):
    return [
        {
            "airport_id": cell.airport_id,
            "value_minutes": cell.value_minutes,
            "sample_count": cell.sample_count,
            "fallback_level": cell.fallback_level,
            "provenance": list(cell.provenance),
        }
        for cell in reference.cells
    ]


def taxi_cells(reference):
    return turnaround_cells(reference)


def exposure_cells(reference):
    return [
        {
            "airport_id": cell.airport_id,
            "value_legs": cell.value_legs,
            "sample_count": cell.sample_count,
            "fallback_level": cell.fallback_level,
            "provenance": list(cell.provenance),
        }
        for cell in reference.cells
    ]


def passenger_cells(reference):
    return [
        {
            "origin": cell.origin_airport_id,
            "destination": cell.destination_airport_id,
            "value_passengers": cell.value_passengers,
            "sample_count": cell.sample_count,
            "provenance": list(cell.provenance),
        }
        for cell in reference.cells
    ]


def chain_stats(episodes, by_id):
    gaps = [
        (
            by_id[episode.successor_flight_id]["actual_departure_utc"]
            - by_id[episode.predecessor_flight_id]["actual_arrival_utc"]
        ).total_seconds()
        / 60
        for episode in episodes
    ]
    ordered, count = sorted(gaps), len(gaps)
    return {
        "count": count,
        "percentiles": {
            quantile: ordered[min(count - 1, int(quantile * count / 100.0))]
            for quantile in (5, 25, 50, 75, 95, 99)
        },
        "max": ordered[-1],
    }


def sample_three_way_cohort(
    episodes, *, seed, train_count, calibration_count, development_count
):
    rng = random.Random(seed)
    pool = sorted(
        episodes, key=lambda episode: (episode.episode_id, episode.predecessor_flight_id)
    )
    train = rng.sample(pool, train_count)
    train_ids = {episode.episode_id for episode in train}
    rest = [episode for episode in pool if episode.episode_id not in train_ids]
    calibration = rng.sample(rest, calibration_count)
    calibration_ids = {episode.episode_id for episode in calibration}
    development = rng.sample(
        [episode for episode in rest if episode.episode_id not in calibration_ids],
        development_count,
    )
    return train, calibration, development


def load_typed_records(episodes, *, csv_paths, projected, zones_path):
    needed = {
        flight_id
        for episode in episodes
        for flight_id in (episode.predecessor_flight_id, episode.successor_flight_id)
    }
    zones = load_timezones(zones_path)
    schedules, outcomes = {}, {}
    for csv_path in csv_paths:
        with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            for raw in csv.DictReader(stream):
                try:
                    schedule, outcome = canonicalize_ontime_row(
                        {key: raw.get(key, "") for key in projected}, zones
                    )
                except Exception:
                    continue
                if schedule.flight_id in needed and schedule.flight_id not in schedules:
                    schedules[schedule.flight_id], outcomes[schedule.flight_id] = schedule, outcome
    missing_ids = needed - set(schedules)
    if missing_ids:
        raise RuntimeError(f"COHORT_FLIGHT_RECORD_MISSING:{sorted(missing_ids)[:5]}")
    return schedules, outcomes


def publish_states(
    item,
    config_hash_value,
    registry_hash_value,
    weather_index=None,
    weather_max_age_minutes=None,
    *,
    publisher: ProductionPREPublisher | None = None,
):
    active_publisher = publisher or ProductionPREPublisher.from_project()
    return publish_episode_states(
        item,
        config_hash_value,
        registry_hash_value,
        weather_index or {},
        weather_max_age_minutes or 0,
        publisher=active_publisher,
    )
