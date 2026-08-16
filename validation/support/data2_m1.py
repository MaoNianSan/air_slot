from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import random

from model.common.enums import SupportState
from model.common.identity import content_id
from model.PRE.adapters.data2 import Data2Adapter
from model.PRE.adapters.registry import RawReadRequest
from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.episode.node_builder import build_rolling_decision_nodes
from model.PRE.feature_registry.loader import load_registry_bundle
from model.PRE.pipeline import ProductionPRERequest, publish_production_pre


def load_timezones(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {row["iata"]: row["timezone"] for row in csv.DictReader(stream)}


def config_hash(root: Path) -> str:
    paths = (root / "configs" / "scientific" / "foundation.yaml",
             root / "configs" / "reproducibility" / "smoke.yaml",
             root / "configs" / "engineering" / "local.example.yaml")
    ids = [{"path": str(path.relative_to(root)),
            "sha256": sha256(path.read_bytes()).hexdigest()} for path in paths]
    return content_id(ids)


def registry_hash(root: Path) -> str:
    bundle = load_registry_bundle(root / "registries")
    published = json.loads((root / "registries" / "registry_manifest.json").read_text(encoding="utf-8"))
    if bundle.manifest.combined_sha256 != published["combined_sha256"]:
        raise RuntimeError("REGISTRY_MANIFEST_MISMATCH")
    return bundle.manifest.combined_sha256


def stream_completed_flights(csv_paths, projected, zones, *, include_service_date=False):
    flight_rows, taxi_rows = [], []
    skipped = 0
    per_month = Counter()
    for csv_path in csv_paths:
        month = csv_path.parent.name.replace("month=", "")
        with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            for raw in csv.DictReader(stream):
                try:
                    schedule, outcome = canonicalize_ontime_row(
                        {key: raw.get(key, "") for key in projected}, zones)
                except Exception:
                    skipped += 1
                    continue
                if schedule.aircraft_id is None or outcome.cancelled or outcome.diverted:
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
                    row["service_date"] = schedule.service_date.isoformat() if schedule.service_date else None
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


def stream_january_flights(csv_path, projected, zones):
    flight_rows, taxi_rows, skipped, _ = stream_completed_flights(
        (csv_path,), projected, zones, include_service_date=False)
    return flight_rows, taxi_rows, skipped


def stream_coupon_routes(csv_paths):
    sums, counts = defaultdict(float), defaultdict(int)
    raw_rows = missing_passengers = 0
    for csv_path in csv_paths:
        with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader)
            idx_pax, idx_origin, idx_dest = (header.index("Passengers"), header.index("Origin"), header.index("Dest"))
            for raw in reader:
                if not raw or len(raw) <= max(idx_pax, idx_origin, idx_dest):
                    continue
                raw_rows += 1
                origin, dest = raw[idx_origin].strip(), raw[idx_dest].strip()
                if not origin or not dest:
                    continue
                try:
                    passengers = float(raw[idx_pax])
                except ValueError:
                    missing_passengers += 1
                    continue
                sums[(origin, dest)] += passengers
                counts[(origin, dest)] += 1
    rows = [{
        "dataset_instance_id": "data2_2019",
        "canonical_record_id": content_id({"source": "bts_db1b", "origin": origin, "destination": dest}),
        "join_key": {"origin": origin, "destination": dest},
        "reference_period": "2019",
        "value": total,
        "record_count": counts[(origin, dest)],
        "split": "train",
    } for (origin, dest), total in sorted(sums.items())]
    return rows, raw_rows, missing_passengers


def weather_index_and_stats(data2_root: Path, output: Path, replay_lag_minutes: int,
                            *, period: str | None):
    request = RawReadRequest(dataset_instance_id="data2_2019", source_family="noaa_isd",
                             raw_root=data2_root, output_root=output, year=2019)
    index, per_airport = defaultdict(list), Counter()
    total = 0
    for observation in Data2Adapter().iter_canonical(request, replay_lag_minutes=replay_lag_minutes):
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
    return dict(index), {label: total, "airports_covered": len(per_airport),
                         "top_airports": per_airport.most_common(10), "injected": True}


def latest_weather(weather_index, airport_id, cutoff, weather_max_age_minutes):
    if not airport_id or not weather_index.get(airport_id):
        return None
    limit = cutoff - timedelta(minutes=weather_max_age_minutes)
    for observation in reversed(weather_index[airport_id]):
        if observation.availability_time > cutoff:
            continue
        if observation.availability_time < limit:
            break
        return observation
    return None


def reference_summary(reference, *, cells: list[dict], globals_: dict | None = None) -> dict:
    return {"rule_id": reference.rule_id, "rule_version": reference.rule_version,
            "reference_id": reference.reference_id, "fit_period": reference.fit_period,
            "manifest_freeze_id": reference.manifest_freeze_id,
            "support_state": reference.support_state.value, "cells_count": len(reference.cells),
            **(globals_ or {}), "cells": cells}


def turnaround_cells(reference):
    return [{"airport_id": cell.airport_id, "value_minutes": cell.value_minutes,
             "sample_count": cell.sample_count, "fallback_level": cell.fallback_level,
             "provenance": list(cell.provenance)} for cell in reference.cells]


def taxi_cells(reference):
    return turnaround_cells(reference)


def exposure_cells(reference):
    return [{"airport_id": cell.airport_id, "value_legs": cell.value_legs,
             "sample_count": cell.sample_count, "fallback_level": cell.fallback_level,
             "provenance": list(cell.provenance)} for cell in reference.cells]


def passenger_cells(reference):
    return [{"origin": cell.origin_airport_id, "destination": cell.destination_airport_id,
             "value_passengers": cell.value_passengers, "sample_count": cell.sample_count,
             "provenance": list(cell.provenance)} for cell in reference.cells]


def chain_stats(episodes, by_id):
    gaps = [(by_id[episode.successor_flight_id]["actual_departure_utc"]
             - by_id[episode.predecessor_flight_id]["actual_arrival_utc"]).total_seconds() / 60
            for episode in episodes]
    ordered, count = sorted(gaps), len(gaps)
    return {"count": count,
            "percentiles": {q: ordered[min(count - 1, int(q * count / 100.0))]
                            for q in (5, 25, 50, 75, 95, 99)},
            "max": ordered[-1]}


def sample_three_way_cohort(episodes, *, seed, train_count, calibration_count, development_count):
    rng = random.Random(seed)
    pool = sorted(episodes, key=lambda episode: (episode.episode_id, episode.predecessor_flight_id))
    train = rng.sample(pool, train_count)
    train_ids = {episode.episode_id for episode in train}
    rest = [episode for episode in pool if episode.episode_id not in train_ids]
    calibration = rng.sample(rest, calibration_count)
    calibration_ids = {episode.episode_id for episode in calibration}
    development = rng.sample([episode for episode in rest if episode.episode_id not in calibration_ids],
                             development_count)
    return train, calibration, development


def load_typed_records(episodes, *, csv_paths, projected, zones_path):
    needed = {flight_id for episode in episodes
              for flight_id in (episode.predecessor_flight_id, episode.successor_flight_id)}
    zones = load_timezones(zones_path)
    schedules, outcomes = {}, {}
    for csv_path in csv_paths:
        with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            for raw in csv.DictReader(stream):
                try:
                    schedule, outcome = canonicalize_ontime_row(
                        {key: raw.get(key, "") for key in projected}, zones)
                except Exception:
                    continue
                if schedule.flight_id in needed and schedule.flight_id not in schedules:
                    schedules[schedule.flight_id], outcomes[schedule.flight_id] = schedule, outcome
    missing = needed - set(schedules)
    if missing:
        raise RuntimeError(f"COHORT_FLIGHT_RECORD_MISSING:{sorted(missing)[:5]}")
    return schedules, outcomes


def publish_states(item, config_hash_value, registry_hash_value, weather_index=None,
                   weather_max_age_minutes=None):
    episode, successor_schedule, predecessor_outcome, successor_outcome = item
    nodes = build_rolling_decision_nodes(episode=episode, predecessor_outcome=predecessor_outcome,
        successor_outcome=successor_outcome, config_hash=config_hash_value,
        registry_hash=registry_hash_value)
    states = []
    for node in nodes:
        weather = None if weather_index is None else latest_weather(
            weather_index, episode.connection_airport_id, node.information_cutoff,
            weather_max_age_minutes)
        records = (successor_schedule,) if weather is None else (successor_schedule, weather)
        states.append(publish_production_pre(ProductionPRERequest(
            episode_id=episode.episode_id, predecessor_id=episode.predecessor_flight_id,
            successor_id=episode.successor_flight_id, dataset_instance_id="data2_2019",
            decision_time=node.decision_time, information_cutoff=node.information_cutoff,
            records=records, config_hash=config_hash_value, registry_hash=registry_hash_value,
            connection_airport_id=episode.connection_airport_id,
            operational_stage=node.operational_stage, node_index=node.node_index,
            roll_minutes=node.roll_minutes)).pre_state)
    return nodes, states


def normalization_rows(prefixes):
    rows = []
    for states in prefixes:
        previous = None
        for state in states:
            row = {}
            schedule = state.successor_state.get("schedule_reference")
            if schedule and isinstance(schedule.value, dict):
                departure = schedule.value.get("scheduled_departure_utc")
                if departure is not None:
                    row["schedule.signed_minutes_to_crs_departure"] = (
                        departure - state.decision_node.decision_time).total_seconds() / 60
            for variable, name in (("predecessor_motion", "motion.observation_age_minutes"),
                                   ("current_weather", "weather.observation_age_minutes")):
                lineage = next((entry for entry in state.variable_lineage
                                if entry.scientific_variable == variable), None)
                if lineage and lineage.age_seconds is not None:
                    row[name] = lineage.age_seconds / 60
            row["node.spacing_minutes"] = 0.0 if previous is None else (
                state.decision_node.decision_time - previous).total_seconds() / 60
            previous = state.decision_node.decision_time
            rows.append(row)
    return rows


def source_stats(paths, *, root: Path):
    return {str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
            for path in paths}


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
                if isinstance(weather.value, dict) and weather.value.get("temperature_c") is not None:
                    supported_with_values += 1
            else:
                abstain_reasons[weather.reason_code] += 1
    return {"states_with_weather_slot": total, "supported": supported,
            "abstain": total - supported, "abstain_reasons": dict(abstain_reasons),
            "supported_with_temperature_values": supported_with_values}
