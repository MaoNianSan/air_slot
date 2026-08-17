from __future__ import annotations

import argparse
import csv
import gc
import json
import math
import random
import statistics
import subprocess
import time
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path

import torch
import psutil

from exp.exp1.history import adaptive_history
from model.common.config import load_config_layers
from model.common.identity import content_id
from model.M1.coverage import active_node_prefixes
from model.M1.cache import M1DevelopmentBaseCache, cache_key as development_cache_key
from model.M1.data import FEATURE_NAMES, encode_pre_sequence, fit_train_normalization
from model.M1.lifecycle import M1Lifecycle, M1TrainingExample
from model.M1.pipeline import M1Pipeline
from model.M1.splits import split_for_date
from model.PRE.adapters.data2 import _normalize_isd_station_id
from model.PRE.canonical.normalization import canonicalize_isd_row, canonicalize_ontime_row
from model.PRE.canonical.normalization_common import deterministic_id, missing, number
from model.PRE.canonical.timezone import infer_rollover, local_hhmm_to_utc
from model.PRE.episode.builder import build_data2_episode_records
from model.PRE.episode.node_builder import build_rolling_decision_nodes
from model.PRE.pipeline import ProductionPREPublisher, ProductionPRERequest
from validation.support.data2_m1 import (
    config_hash, load_timezones, normalization_rows, registry_hash,
)


ROOT = Path(__file__).resolve().parents[1]
DATA2 = ROOT / "data2"
OUT = ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"
EVIDENCE_PATH = OUT / "m1_hstar_evidence.json"
BASE_CACHE_DATA = OUT / "M1_BASE_CACHE.npz"
BASE_CACHE_MANIFEST = OUT / "M1_BASE_CACHE_MANIFEST.json"
RUNS_DIR = OUT / "runs"
PREPARATION_STATE = OUT / "M1_BASE_CACHE_PREPARATION_STATE.pt"
PREPARATION_MANIFEST = OUT / "M1_BASE_CACHE_PREPARATION_PROGRESS.json"
PROJECTED = (
    "FlightDate", "Reporting_Airline", "Tail_Number",
    "Flight_Number_Reporting_Airline", "Origin", "Dest", "CRSDepTime",
    "CRSArrTime", "DepTime", "ArrTime", "WheelsOff", "WheelsOn",
    "TaxiOut", "TaxiIn", "DepDelayMinutes", "ArrDelayMinutes",
    "Cancelled", "Diverted",
)
COHORT_COUNTS = {"train": 128, "calibration": 64, "development": 128, "test": 0}
COHORT_SEED = 20260813
TRAINING_SEEDS = (20260813, 20260814, 20260815, 20260816, 20260817)
HIDDEN_SIZES = (16, 32)
EPOCHS = 8
LEARNING_RATE = 0.01
BATCH_SIZE = 128
FINAL_TEST_START = "2019-10-01"
FULL_H_APPROVAL_TOKEN = "APPROVE_H_SELECTION_RUN"
APPROVED_CACHE_HASH = (
    "sha256:9c647c03a4bb59d8cc6568e14a34f431f5da84b6d179e55d2e416fe7e7ed180a")


def _heartbeat(phase: str, *, started: float, rows: int = 0, episodes: int = 0,
               decision_nodes: int = 0, current_month: str | None = None,
               current_file: str | None = None,
               candidate: int | None = None, seed: int | None = None,
               progress: float | None = None, cache: str = "MISS") -> None:
    elapsed = time.perf_counter() - started
    eta = None if not progress or progress <= 0 else max(elapsed / progress - elapsed, 0.0)
    payload = {
        "TIMESTAMP": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "PHASE": phase,
        "CURRENT_MONTH": current_month,
        "CURRENT_FILE_OR_CHUNK": current_file,
        "ROWS_PROCESSED": rows,
        "EPISODES_PROCESSED": episodes,
        "DECISION_NODES_PROCESSED": decision_nodes,
        "ELAPSED_SECONDS": round(elapsed, 3),
        "ETA_SECONDS": None if eta is None else round(eta, 3),
        "RSS_MB": round(psutil.Process().memory_info().rss / 1024 ** 2, 3),
        "CACHE": cache,
    }
    if candidate is not None:
        payload["H"] = candidate
    if seed is not None:
        payload["SEED"] = seed
    print(json.dumps(payload, sort_keys=True), flush=True)


@dataclass(frozen=True)
class PreparedData:
    normalization: object
    train_examples: tuple[M1TrainingExample, ...]
    calibration_examples: tuple[M1TrainingExample, ...]
    development_examples: tuple[M1TrainingExample, ...]
    audit: dict


def _ontime_paths() -> tuple[Path, ...]:
    paths = tuple(next((DATA2 / "raw" / "bts" / "ontime" / "2019" /
                        f"month={month:02d}").glob("*.csv")) for month in range(1, 10))
    if any("month=10" in str(path) or "month=11" in str(path) or "month=12" in str(path)
           for path in paths):
        raise RuntimeError("FINAL_TEST_ONTIME_PATH_SELECTED")
    return paths


def _aircraft_tail(rows):
    tail = {}
    for row in rows:
        key = (row["dataset_instance_id"], row["aircraft_id_namespace"],
               row["aircraft_id"])
        order = (row["actual_departure_utc"], row["actual_arrival_utc"], row["flight_id"])
        previous = tail.get(key)
        if previous is None or order > (
                previous["actual_departure_utc"], previous["actual_arrival_utc"],
                previous["flight_id"]):
            tail[key] = row
    return tuple(tail.values())


def _preparation_state_key(paths):
    return content_id({
        "sources": {str(path.relative_to(ROOT)): [path.stat().st_size, path.stat().st_mtime_ns]
                    for path in paths},
        "cohort_counts": COHORT_COUNTS,
        "cohort_seed": COHORT_SEED,
        "carry_rule": "LAST_ACTUAL_DEPARTURE_ROW_PER_AIRCRAFT",
    })


def _save_preparation_state(*, key, next_month, reservoirs, pool_sizes, rng,
                            previous_rows, per_month, skipped_total, total_episodes):
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
    temporary = PREPARATION_STATE.with_suffix(".pt.tmp")
    torch.save(payload, temporary)
    temporary.replace(PREPARATION_STATE)
    manifest = {
        "schema_version": "M1_BASE_CACHE_PREPARATION_PROGRESS_V1",
        "state_key": key,
        "completed_months": [f"2019-{month:02d}" for month in range(1, next_month)],
        "next_month": None if next_month > 9 else f"2019-{next_month:02d}",
        "completion_status": "PASS" if next_month > 9 else "RUNNING",
        "pool_sizes": dict(pool_sizes),
        "sampled_counts": {name: len(values) for name, values in reservoirs.items()},
        "cross_month_carry_rows": len(previous_rows),
        "final_test_access_count": 0,
    }
    temporary_manifest = PREPARATION_MANIFEST.with_suffix(".json.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    temporary_manifest.replace(PREPARATION_MANIFEST)


def _episode_reservoirs(paths, zones, *, resume=True):
    reservoirs = {name: [] for name in COHORT_COUNTS}
    pool_sizes = {name: 0 for name in COHORT_COUNTS}
    rng = random.Random(COHORT_SEED)
    previous_rows = ()
    per_month = {}
    skipped_total = 0
    total_episodes = 0
    start_month = 1
    state_key = _preparation_state_key(paths)
    if resume and PREPARATION_STATE.is_file():
        payload = torch.load(PREPARATION_STATE, map_location="cpu", weights_only=False)
        if payload.get("state_key") == state_key:
            reservoirs = payload["reservoirs"]
            pool_sizes = payload["pool_sizes"]
            rng.setstate(payload["rng_state"])
            previous_rows = tuple(payload["previous_rows"])
            per_month = payload["per_month"]
            skipped_total = payload["skipped_total"]
            total_episodes = payload["total_episodes"]
            start_month = int(payload["next_month"])
            print(json.dumps({"PHASE": "DATA_PREPARATION_RESUME",
                              "CACHE": "HIT", "NEXT_MONTH": start_month,
                              "CARRY_ROWS": len(previous_rows)},
                             sort_keys=True), flush=True)
    for month, path in enumerate(paths, start=1):
        if month < start_month:
            continue
        month_started = time.perf_counter()
        current_rows, skipped = _lightweight_flights(path, zones, month=month)
        skipped_total += skipped
        per_month[f"{month:02d}"] = len(current_rows)
        chunk = list(previous_rows) + current_rows
        by_id = {row["flight_id"]: row for row in chunk}
        key = f"2019-{month:02d}"
        month_episodes = 0
        for episode in sorted(build_data2_episode_records(chunk), key=lambda item: item.episode_id):
            service_date = by_id[episode.successor_flight_id].get("service_date")
            if not service_date or service_date[:7] != key:
                continue
            split = split_for_date(date.fromisoformat(service_date))
            if split == "test":
                raise RuntimeError("FINAL_TEST_EPISODE_MATERIALIZED")
            pool_sizes[split] += 1
            total_episodes += 1
            month_episodes += 1
            reservoir = reservoirs[split]
            seen = pool_sizes[split]
            target = COHORT_COUNTS[split]
            if len(reservoir) < target:
                reservoir.append(episode)
            else:
                index = rng.randrange(seen)
                if index < target:
                    reservoir[index] = episode
        previous_rows = _aircraft_tail(current_rows)
        _save_preparation_state(
            key=state_key, next_month=month + 1, reservoirs=reservoirs,
            pool_sizes=pool_sizes, rng=rng, previous_rows=previous_rows,
            per_month=per_month, skipped_total=skipped_total,
            total_episodes=total_episodes)
        _heartbeat(
            "DATA_PREPARATION_MONTH_COMPLETE", started=month_started,
            rows=len(current_rows), episodes=month_episodes,
            current_month=f"2019-{month:02d}", current_file=path.name,
            progress=month / len(paths))
        gc.collect()
    return reservoirs, pool_sizes, total_episodes, per_month, skipped_total


def _lightweight_flights(path, zones, *, month):
    rows = []
    skipped = 0
    started = last_heartbeat = time.perf_counter()
    input_rows = 0
    total_bytes = path.stat().st_size
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        positions = {name: header.index(name) for name in PROJECTED}
        for raw in reader:
            input_rows += 1
            def value(name):
                position = positions[name]
                return raw[position] if position < len(raw) else ""
            try:
                day = date.fromisoformat(value("FlightDate")[:10])
                origin, dest = value("Origin"), value("Dest")
                if origin not in zones or dest not in zones or missing(value("Tail_Number")):
                    raise ValueError
                schedule_dep = local_hhmm_to_utc(day, value("CRSDepTime"), zones[origin])
                schedule_arr = local_hhmm_to_utc(day, value("CRSArrTime"), zones[dest])
                if schedule_dep is None or schedule_arr is None:
                    raise ValueError
                schedule_arr = infer_rollover(schedule_dep, schedule_arr)
                cancelled = bool(number(value("Cancelled")) or 0)
                diverted = bool(number(value("Diverted")) or 0)
                if cancelled or diverted:
                    raise ValueError
                actual_dep = local_hhmm_to_utc(day, value("DepTime"), zones[origin])
                actual_arr = local_hhmm_to_utc(day, value("ArrTime"), zones[dest])
                if actual_dep is not None: actual_dep = infer_rollover(schedule_dep, actual_dep)
                if actual_arr is not None: actual_arr = infer_rollover(schedule_arr, actual_arr)
                dep_delay = number(value("DepDelayMinutes"))
                arr_delay = number(value("ArrDelayMinutes"))
                if dep_delay is not None: actual_dep = schedule_dep + timedelta(minutes=dep_delay)
                if arr_delay is not None: actual_arr = schedule_arr + timedelta(minutes=arr_delay)
                if actual_dep is None or actual_arr is None:
                    raise ValueError
                flight_parts = {name: value(name) for name in (
                    "FlightDate", "Reporting_Airline",
                    "Flight_Number_Reporting_Airline", "Origin", "Dest")}
                rows.append({
                    "flight_id": deterministic_id("flight", flight_parts),
                    "aircraft_id": value("Tail_Number").strip(),
                    "aircraft_id_namespace": "REGISTRATION",
                    "origin_airport_id": origin, "destination_airport_id": dest,
                    "event_start_time": schedule_dep, "event_end_time": schedule_arr,
                    "actual_arrival_utc": actual_arr, "actual_departure_utc": actual_dep,
                    "dataset_instance_id": "data2_2019", "service_date": day.isoformat(),
                })
            except Exception:
                skipped += 1
            now = time.perf_counter()
            if now - last_heartbeat >= 45:
                position = stream.buffer.tell()
                _heartbeat(
                    f"DATA_PREPARATION_ONTIME_2019_{month:02d}", started=started,
                    rows=input_rows, current_month=f"2019-{month:02d}",
                    current_file=path.name,
                    progress=min(position / max(total_bytes, 1), 1.0))
                last_heartbeat = now
    return rows, skipped


def _load_selected_typed_records(episodes, paths, zones):
    needed = {flight_id for episode in episodes for flight_id in (
        episode.predecessor_flight_id, episode.successor_flight_id)}
    schedules, outcomes = {}, {}
    started = last_heartbeat = time.perf_counter()
    input_rows = 0
    for path in paths:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            for raw in csv.DictReader(stream):
                input_rows += 1
                flight_parts = {name: raw.get(name) for name in (
                    "FlightDate", "Reporting_Airline",
                    "Flight_Number_Reporting_Airline", "Origin", "Dest")}
                flight_id = deterministic_id("flight", flight_parts)
                if flight_id not in needed or flight_id in schedules:
                    continue
                try:
                    schedule, outcome = canonicalize_ontime_row(
                        {name: raw.get(name, "") for name in PROJECTED}, zones)
                except Exception:
                    continue
                schedules[flight_id], outcomes[flight_id] = schedule, outcome
                now = time.perf_counter()
                if now - last_heartbeat >= 45:
                    _heartbeat("DATA_PREPARATION_TYPED_RECORDS", started=started,
                               rows=input_rows, episodes=len(schedules) // 2,
                               current_month=path.parent.name.replace("month=", "2019-"),
                               current_file=path.name)
                    last_heartbeat = now
        print(f"PREP typed records through={path.parent.name} found={len(schedules)}/{len(needed)}", flush=True)
    missing_ids = needed - set(schedules)
    if missing_ids:
        raise RuntimeError(f"COHORT_FLIGHT_RECORD_MISSING:{sorted(missing_ids)[:5]}")
    return schedules, outcomes


def _weather_index(replay_lag_minutes: int):
    with (DATA2 / "refs" / "weather_station_map.csv").open(
            encoding="utf-8-sig", newline="") as stream:
        station_map = {_normalize_isd_station_id(row["station"]): row["airport"]
                       for row in csv.DictReader(stream)}
    index = defaultdict(list)
    accepted = 0
    input_rows = 0
    started = last_heartbeat = time.perf_counter()
    paths = tuple(sorted((DATA2 / "raw" / "weather" / "noaa" / "2019").glob("*.csv")))
    for path_index, path in enumerate(paths, start=1):
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            for row in csv.DictReader(stream):
                input_rows += 1
                stamp = str(row.get("DATE", ""))
                if stamp >= FINAL_TEST_START:
                    break
                if not stamp.startswith("2019-"):
                    continue
                try:
                    observation = canonicalize_isd_row(
                        row, station_map=station_map,
                        replay_lag_minutes=replay_lag_minutes)
                except Exception:
                    continue
                index[observation.airport_id].append(observation)
                accepted += 1
                now = time.perf_counter()
                if now - last_heartbeat >= 45:
                    _heartbeat(
                        "DATA_PREPARATION_WEATHER", started=started, rows=input_rows,
                        current_file=path.name,
                        progress=path_index / max(len(paths), 1))
                    last_heartbeat = now
        if len(index) % 8 == 0:
            print(f"PREP weather files through={path.name} accepted={accepted}", flush=True)
    packed = {}
    for airport, observations in index.items():
        ordered = tuple(sorted(observations, key=lambda item: item.availability_time))
        packed[airport] = (tuple(item.availability_time for item in ordered), ordered)
    return packed, {"accepted_train_calibration_development_observations": accepted,
                    "airports": len(packed), "final_test_access_count": 0}


def _latest_weather(index, airport_id, cutoff, max_age_minutes):
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


def _publish_states(item, cfg_hash, reg_hash, weather, max_age, *, publisher):
    episode, schedule, predecessor_outcome, successor_outcome = item
    nodes = build_rolling_decision_nodes(
        episode=episode, predecessor_outcome=predecessor_outcome,
        successor_outcome=successor_outcome, config_hash=cfg_hash,
        registry_hash=reg_hash)
    states = []
    for node in nodes:
        observation = _latest_weather(
            weather, episode.connection_airport_id, node.information_cutoff, max_age)
        records = (schedule,) if observation is None else (schedule, observation)
        states.append(publisher.publish(ProductionPRERequest(
            episode_id=episode.episode_id,
            predecessor_id=episode.predecessor_flight_id,
            successor_id=episode.successor_flight_id,
            dataset_instance_id="data2_2019", decision_time=node.decision_time,
            information_cutoff=node.information_cutoff, records=records,
            config_hash=cfg_hash, registry_hash=reg_hash,
            connection_airport_id=episode.connection_airport_id,
            operational_stage=node.operational_stage, node_index=node.node_index,
            roll_minutes=node.roll_minutes)).pre_state)
    return nodes, tuple(states)


def _active(episodes, items, cfg_hash, reg_hash, weather, max_age, *, publisher):
    output = []
    stage_counts = Counter()
    for episode in episodes:
        item = items[episode.episode_id]
        nodes, states = _publish_states(
            item, cfg_hash, reg_hash, weather, max_age, publisher=publisher)
        for _, prefix, labels in active_node_prefixes(
                episode=episode, nodes=nodes, states=states,
                successor_schedule=item[1], predecessor_outcome=item[2],
                successor_outcome=item[3]):
            prefix = adaptive_history(prefix)
            output.append((episode, prefix, labels))
            stage_counts[prefix[-1].decision_node.operational_stage.value] += 1
    return output, dict(stage_counts)


def _examples(rows, normalization, bins):
    return tuple(M1TrainingExample.from_target_labels(
        values=encode_pre_sequence(prefix, normalization), labels=labels, bins=bins)
        for _, prefix, labels in rows)


def prepare_data(scientific) -> PreparedData:
    paths = _ontime_paths()
    zones_path = DATA2 / "refs" / "us_airport_timezones.csv"
    zones = load_timezones(zones_path)
    reservoirs, pool_sizes, total_episodes, per_month, skipped = _episode_reservoirs(
        paths, zones)
    train_episodes = tuple(sorted(reservoirs["train"], key=lambda item: item.episode_id))
    calibration_episodes = tuple(sorted(reservoirs["calibration"], key=lambda item: item.episode_id))
    development_episodes = tuple(sorted(reservoirs["development"], key=lambda item: item.episode_id))
    if reservoirs["test"]:
        raise RuntimeError("FINAL_TEST_EPISODE_MATERIALIZED")
    selected = train_episodes + calibration_episodes + development_episodes
    del reservoirs
    gc.collect()

    schedules, outcomes = _load_selected_typed_records(selected, paths, zones)
    items = {episode.episode_id: (
        episode, schedules[episode.successor_flight_id],
        outcomes[episode.predecessor_flight_id], outcomes[episode.successor_flight_id])
        for episode in selected}
    replay_lag = int(scientific.parameters["data2_weather_replay_lag_minutes"].value)
    max_age = int(scientific.parameters["weather_max_age_minutes"].value)
    weather, weather_audit = _weather_index(replay_lag)
    print(f"PREP weather complete observations={weather_audit['accepted_train_calibration_development_observations']}", flush=True)
    cfg_hash, reg_hash = config_hash(ROOT), registry_hash(ROOT)
    publisher = ProductionPREPublisher.from_project()
    train_rows, train_stages = _active(
        train_episodes, items, cfg_hash, reg_hash, weather, max_age,
        publisher=publisher)
    print(f"PREP train histories={len(train_rows)}", flush=True)
    calibration_rows, calibration_stages = _active(
        calibration_episodes, items, cfg_hash, reg_hash, weather, max_age,
        publisher=publisher)
    print(f"PREP calibration histories={len(calibration_rows)}", flush=True)
    development_rows, development_stages = _active(
        development_episodes, items, cfg_hash, reg_hash, weather, max_age,
        publisher=publisher)
    print(f"PREP development histories={len(development_rows)}", flush=True)
    normalization = fit_train_normalization(
        normalization_rows([prefix for _, prefix, _ in train_rows]), split="train")
    template = M1Pipeline.from_scientific_config(
        scientific, input_size=len(FEATURE_NAMES), normalization=normalization, hidden_size=16)
    examples = {
        "train": _examples(train_rows, normalization, template.bins),
        "calibration": _examples(calibration_rows, normalization, template.bins),
        "development": _examples(development_rows, normalization, template.bins),
    }
    print("PREP sequence encoding complete", flush=True)
    dates = {name: sorted({str(row.episode_date) for row in values})
             for name, values in examples.items()}
    if dates["development"][-1] >= FINAL_TEST_START:
        raise RuntimeError("FINAL_TEST_DEVELOPMENT_DATE_VIOLATION")
    audit = {
        "cohort_seed": COHORT_SEED, "cohort_counts": COHORT_COUNTS,
        "sampled_episodes": {"train": len(train_episodes),
                             "calibration": len(calibration_episodes),
                             "development": len(development_episodes)},
        "examples": {name: len(values) for name, values in examples.items()},
        "stage_counts": {"train": train_stages, "calibration": calibration_stages,
                         "development": development_stages},
        "dates": dates, "pool_sizes": pool_sizes, "total_episode_pool": total_episodes,
        "ontime_rows_by_month": per_month, "ontime_rows_skipped": skipped,
        "weather": weather_audit, "config_hash": cfg_hash, "registry_hash": reg_hash,
        "partition_hashes": {name: content_id(sorted({row.episode_id for row in values}))
                             for name, values in examples.items()},
        "final_test_access_count": 0,
    }
    return PreparedData(normalization, examples["train"], examples["calibration"],
                        examples["development"], audit)


def _ece(probabilities, labels, bins=10):
    confidence, prediction = probabilities.max(dim=1)
    correct = prediction.eq(labels).float()
    total = max(len(labels), 1)
    value = 0.0
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        mask = (confidence >= lower) & (confidence < upper if index < bins - 1 else confidence <= upper)
        if mask.any():
            value += float(mask.sum()) / total * abs(float(correct[mask].mean()) - float(confidence[mask].mean()))
    return value


def evaluate(lifecycle, examples):
    episode_joint = defaultdict(list)
    target_episode = {name: defaultdict(list) for name in ("R_IB", "R_OB", "T_TX")}
    started = time.perf_counter()
    logits, labels, active = lifecycle.batched_logits(
        examples, batch_size=256, teacher_forcing=True)
    joint = torch.zeros(len(examples))
    calibration = {}
    for name in target_episode:
        scaled = logits[name] / lifecycle.pipeline.temperatures[name]
        losses = torch.nn.functional.cross_entropy(scaled, labels[name], reduction="none")
        probabilities = torch.softmax(scaled, dim=1)
        mask = active[name]
        joint += losses * mask.float()
        calibration[name] = (probabilities[mask], labels[name][mask])
        for index, example in enumerate(examples):
            if bool(mask[index]):
                target_episode[name][example.episode_id].append(float(losses[index]))
    for index, example in enumerate(examples):
        episode_joint[example.episode_id].append(float(joint[index]))
    joint_score = statistics.mean(statistics.mean(values) for values in episode_joint.values())
    target_scores = {name: statistics.mean(statistics.mean(values) for values in episodes.values())
                     for name, episodes in target_episode.items()}
    ece = {}
    for name, (probabilities, target_labels) in calibration.items():
        ece[name] = _ece(probabilities, target_labels)
    return {"episode_balanced_joint_nll": joint_score,
            "episode_balanced_target_nll": target_scores,
            "calibration_ece": ece, "mean_calibration_ece": statistics.mean(ece.values()),
            "development_episode_n": len(episode_joint),
            "inference_seconds": time.perf_counter() - started}


def _repository_sha():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _hash_file(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _source_paths() -> tuple[Path, ...]:
    paths = (_ontime_paths()
             + tuple(sorted((DATA2 / "raw" / "weather" / "noaa" / "2019").glob("*.csv")))
             + (DATA2 / "refs" / "weather_station_map.csv",
                DATA2 / "refs" / "us_airport_timezones.csv"))
    forbidden = [path for path in paths if "month=10" in str(path)
                 or "month=11" in str(path) or "month=12" in str(path)]
    if forbidden:
        raise RuntimeError(f"FINAL_TEST_SOURCE_PATH_SELECTED:{forbidden[0]}")
    return paths


def _source_manifest_hash() -> str:
    return content_id({
        str(path.relative_to(ROOT)): [path.stat().st_size, path.stat().st_mtime_ns]
        for path in _source_paths()
    })


def _contract_hashes(scientific) -> dict[str, str]:
    episode_hash = content_id({
        "builder": _hash_file(ROOT / "model" / "PRE" / "episode" / "builder.py"),
        "node_builder": _hash_file(ROOT / "model" / "PRE" / "episode" / "node_builder.py"),
    })
    return {
        "PRE_contract_hash": content_id({
            "pipeline": _hash_file(ROOT / "model" / "PRE" / "pipeline.py"),
            "mapping": _hash_file(ROOT / "model" / "PRE" / "mapping.py"),
            "registry": registry_hash(ROOT),
        }),
        "episode_contract_hash": episode_hash,
        "episode_construction_hash": episode_hash,
        "feature_contract_hash": content_id({
            "data": _hash_file(ROOT / "model" / "M1" / "data.py"),
            "coverage": _hash_file(ROOT / "model" / "M1" / "coverage.py"),
            "feature_names": FEATURE_NAMES,
        }),
        "split_contract_hash": _hash_file(ROOT / "model" / "M1" / "splits.py"),
        "roll_contract_hash": content_id({
            "roll_minutes": scientific.parameters["roll_minutes"].value,
            "node_builder": _hash_file(ROOT / "model" / "PRE" / "episode" / "node_builder.py"),
        }),
        "normalization_contract_hash": content_id({
            "data_code": _hash_file(ROOT / "model" / "M1" / "data.py"),
            "fitted_split": "train",
        }),
    }


def _expected_cache_key(scientific) -> tuple[str, str, dict[str, str]]:
    source_hash = _source_manifest_hash()
    contracts = _contract_hashes(scientific)
    key = development_cache_key(
        source_manifest_hash=source_hash, contract_hashes=contracts,
        cohort_counts=COHORT_COUNTS, cohort_seed=COHORT_SEED)
    return key, source_hash, contracts


def _scientific_config_hash() -> str:
    return config_hash(ROOT)


def _training_contract_payload() -> dict:
    return {
        "epochs": EPOCHS,
        "learning_rate": LEARNING_RATE,
        "batch_size": BATCH_SIZE,
        "optimizer": "Adam",
        "optimizer_steps_per_epoch": 1,
        "length_bucketed_microbatch": True,
        "gradient_accumulation": True,
    }


def _training_contract_hash() -> str:
    return content_id(_training_contract_payload())


def _validate_cache_for_h(cache, scientific) -> dict:
    manifest = cache.manifest
    if manifest.get("cache_hash") != APPROVED_CACHE_HASH:
        raise RuntimeError(
            f"H_SELECTION_CACHE_HASH_MISMATCH:{manifest.get('cache_hash')}"
            f"!={APPROVED_CACHE_HASH}")
    if manifest.get("feature_count") != len(FEATURE_NAMES):
        raise RuntimeError("H_SELECTION_FEATURE_COUNT_MISMATCH")
    if manifest.get("final_test_included") is not False:
        raise RuntimeError("H_SELECTION_FINAL_TEST_INCLUDED")
    if manifest.get("final_test_access_count", 0) != 0:
        raise RuntimeError("H_SELECTION_FINAL_TEST_ACCESS_NONZERO")
    contracts = _contract_hashes(scientific)
    for name, expected in contracts.items():
        if manifest.get("contract_hashes", {}).get(name) != expected:
            raise RuntimeError(f"H_SELECTION_CONTRACT_HASH_MISMATCH:{name}")
    current_config_hash = _scientific_config_hash()
    if cache.audit.get("config_hash") != current_config_hash:
        raise RuntimeError("H_SELECTION_SCIENTIFIC_CONFIG_HASH_MISMATCH")
    partition_hashes = cache.audit.get("partition_hashes", {})
    for split in ("train", "calibration", "development"):
        dataset = cache.partition(split)
        observed = content_id(sorted({row.episode_id for row in dataset}))
        if partition_hashes.get(split) != observed:
            raise RuntimeError(f"H_SELECTION_EPISODE_IDS_MISMATCH:{split}")
        if any(row.episode_date >= date(2019, 10, 1) for row in dataset):
            raise RuntimeError(f"H_SELECTION_FINAL_TEST_DATE:{split}")
    if set(cache.store.sample_splits) - {"train", "calibration", "development"}:
        raise RuntimeError("H_SELECTION_SPLIT_MISMATCH")
    return {
        "cache_hash": manifest["cache_hash"],
        "feature_count": manifest["feature_count"],
        "scientific_config_hash": current_config_hash,
        "training_contract_hash": _training_contract_hash(),
        "final_test_access_count": 0,
        "cache_rebuilds": 0,
    }


def _validate_manifest_for_resume(manifest: dict, cache, scientific) -> tuple[bool, str]:
    expected = _validate_cache_for_h(cache, scientific)
    required_values = {
        "completion_status": "PASS",
        "cache_hash": expected["cache_hash"],
        "hidden_size": manifest.get("hidden_size"),
        "training_seed": manifest.get("training_seed"),
        "epochs": EPOCHS,
        "learning_rate": LEARNING_RATE,
        "batch_size": BATCH_SIZE,
        "optimizer": "Adam",
        "optimizer_steps_per_epoch": 1,
        "final_test_access_count": 0,
    }
    if manifest.get("hidden_size") not in HIDDEN_SIZES:
        return False, "hidden_size_not_in_candidate_set"
    if manifest.get("training_seed") not in TRAINING_SEEDS:
        return False, "training_seed_not_in_principal_seed_set"
    if any(manifest.get(name) != value for name, value in required_values.items()
           if name not in {"hidden_size", "training_seed"}):
        return False, "explicit_training_contract_field_mismatch"
    if manifest.get("scientific_config_hash") == expected["scientific_config_hash"] \
            and manifest.get("training_contract_hash") == expected["training_contract_hash"]:
        return True, "validated"
    # The first approved H16 seed predates these two metadata fields. Its
    # scientific config is still verified through the immutable cache audit and
    # its explicit training fields above; do not rerun it solely for metadata.
    if "scientific_config_hash" not in manifest and "training_contract_hash" not in manifest:
        return True, "legacy_manifest_verified_from_cache_audit"
    return False, "scientific_or_training_contract_hash_mismatch"


def _peak_rss_mb() -> float:
    info = psutil.Process().memory_info()
    return float(getattr(info, "peak_wset", info.rss)) / 1024 ** 2


def _base_cache(scientific, *, allow_build: bool):
    key, source_hash, contracts = _expected_cache_key(scientific)
    load_started = time.perf_counter()
    if BASE_CACHE_DATA.is_file() and BASE_CACHE_MANIFEST.is_file():
        cache = M1DevelopmentBaseCache.load(
            BASE_CACHE_DATA, BASE_CACHE_MANIFEST, expected_cache_key=key)
        load_seconds = time.perf_counter() - load_started
        print(json.dumps({"PHASE": "M1_BASE_CACHE_LOAD", "CACHE": "HIT",
                          "ELAPSED_SECONDS": load_seconds,
                          "RSS_MB": _peak_rss_mb()}, sort_keys=True), flush=True)
        return cache, {"cache_hit": True, "warm_cache_load_seconds": load_seconds}
    if not allow_build:
        raise RuntimeError("M1_BASE_CACHE_MISSING_BUILD_NOT_AUTHORIZED")
    build_started = time.perf_counter()
    prepared = prepare_data(scientific)
    cache = M1DevelopmentBaseCache.from_partitions(
        partitions={"train": prepared.train_examples,
                    "calibration": prepared.calibration_examples,
                    "development": prepared.development_examples},
        normalization=prepared.normalization, audit=prepared.audit,
        cache_key=key, source_manifest_hash=source_hash,
        contract_hashes=contracts)
    build_seconds = time.perf_counter() - build_started
    cache.manifest.update({
        "repository_sha": _repository_sha(),
        "build_seconds": build_seconds,
        "peak_rss_mb": _peak_rss_mb(),
        "feature_count": int(cache.store.values_flat.shape[1]),
        "total_nodes": cache.store.canonical_node_count,
        "train_episode_count": prepared.audit["sampled_episodes"]["train"],
        "calibration_episode_count": prepared.audit["sampled_episodes"]["calibration"],
        "development_episode_count": prepared.audit["sampled_episodes"]["development"],
    })
    manifest = cache.save(BASE_CACHE_DATA, BASE_CACHE_MANIFEST)
    warm_started = time.perf_counter()
    loaded = M1DevelopmentBaseCache.load(
        BASE_CACHE_DATA, BASE_CACHE_MANIFEST, expected_cache_key=key)
    warm_seconds = time.perf_counter() - warm_started
    manifest.update({
        "warm_cache_load_seconds": warm_seconds,
        "cache_reuse_status": "PASS",
        "raw_parquet_files_read_during_warm_load": 0,
        "pairing_rebuilt_during_warm_load": 0,
        "weather_rebuilt_during_warm_load": 0,
        "pre_sequence_rebuilt_during_warm_load": 0,
    })
    BASE_CACHE_MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"PHASE": "M1_BASE_CACHE_BUILD", "CACHE": "MISS",
                      "BUILD_SECONDS": build_seconds, "WARM_LOAD_SECONDS": warm_seconds,
                      "CACHE_HASH": manifest["cache_hash"],
                      "FINAL_TEST_ACCESS_COUNT": 0}, sort_keys=True), flush=True)
    return loaded, {"cache_hit": False, "build_seconds": build_seconds,
                    "warm_cache_load_seconds": warm_seconds, "manifest": manifest}


def _run_paths(hidden_size: int, seed: int):
    stem = f"H{hidden_size}_seed{seed}"
    return RUNS_DIR / f"{stem}.pt", RUNS_DIR / f"{stem}.json"


def _run_candidate(scientific, cache, *, hidden_size: int, seed: int,
                   device: str, resume: bool):
    cache_validation = _validate_cache_for_h(cache, scientific)
    checkpoint_path, manifest_path = _run_paths(hidden_size, seed)
    if resume and manifest_path.is_file() and checkpoint_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        valid, validation_reason = _validate_manifest_for_resume(
            manifest, cache, scientific)
        if valid:
            print(json.dumps({"PHASE": "M1_TRAIN", "H": hidden_size, "SEED": seed,
                              "CACHE": "HIT", "RESUME": "SKIP_COMPLETED",
                              "VALIDATION": validation_reason},
                             sort_keys=True), flush=True)
            return manifest
    train_examples = cache.partition("train")
    calibration_examples = cache.partition("calibration")
    development_examples = cache.partition("development")
    torch.manual_seed(seed)
    pipeline = M1Pipeline.from_scientific_config(
        scientific, input_size=len(FEATURE_NAMES), normalization=cache.normalization,
        hidden_size=hidden_size)
    lifecycle = M1Lifecycle(pipeline, device=device)
    run_started = time.perf_counter()
    process_cpu_started = time.process_time()
    training_started = time.perf_counter()

    def progress(row):
        elapsed = time.perf_counter() - training_started
        eta = elapsed / row["epoch"] * (EPOCHS - row["epoch"])
        print(json.dumps({
            "TIMESTAMP": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "PHASE": "M1_TRAIN", "H": hidden_size, "SEED": seed,
            "EPOCH": row["epoch"], "LOSS": row["loss"],
            "ELAPSED_SECONDS": elapsed, "ETA_SECONDS": eta,
            "RSS_MB": _peak_rss_mb(), "DEVICE": str(lifecycle.device),
        }, sort_keys=True), flush=True)

    history = lifecycle.train(
        train_examples, epochs=EPOCHS, learning_rate=LEARNING_RATE,
        batch_size=BATCH_SIZE, seed=seed, progress_callback=progress)
    training_seconds = time.perf_counter() - training_started
    calibration_started = time.perf_counter()
    temperatures = lifecycle.calibrate(calibration_examples, batch_size=256)
    calibration_seconds = time.perf_counter() - calibration_started
    metrics = evaluate(lifecycle, development_examples)
    finite_values = list(history)
    finite_values.extend([temperatures, metrics])
    if not all(math.isfinite(float(row["loss"])) for row in history):
        raise RuntimeError(f"H_SELECTION_NONFINITE_LOSS:H{hidden_size}:SEED{seed}")
    if any(not math.isfinite(float(value)) for value in temperatures.values()):
        raise RuntimeError(f"H_SELECTION_NONFINITE_TEMPERATURE:H{hidden_size}:SEED{seed}")
    if not math.isfinite(float(metrics["episode_balanced_joint_nll"])):
        raise RuntimeError(f"H_SELECTION_NONFINITE_METRIC:H{hidden_size}:SEED{seed}")
    process_cpu_seconds = time.process_time() - process_cpu_started
    run_wall_seconds = time.perf_counter() - run_started
    logical_cores = max(psutil.cpu_count(logical=True) or 1, 1)
    average_cpu_utilization = process_cpu_seconds / max(run_wall_seconds, 1e-12) \
        / logical_cores * 100.0
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    temporary_checkpoint = checkpoint_path.with_suffix(".pt.tmp")
    lifecycle.save(temporary_checkpoint)
    temporary_checkpoint.replace(checkpoint_path)
    manifest = {
        "completion_status": "PASS",
        "repository_sha": _repository_sha(),
        "cache_key": cache.manifest["cache_key"],
        "cache_hash": cache.manifest["cache_hash"],
        "scientific_config_hash": cache_validation["scientific_config_hash"],
        "training_contract_hash": cache_validation["training_contract_hash"],
        "training_contract": _training_contract_payload(),
        "hidden_size": hidden_size,
        "training_seed": seed,
        "epochs": EPOCHS,
        "learning_rate": LEARNING_RATE,
        "batch_size": BATCH_SIZE,
        "optimizer": "Adam",
        "optimizer_steps_per_epoch": 1,
        "training_seconds": training_seconds,
        "seconds_per_epoch": training_seconds / EPOCHS,
        "calibration_seconds": calibration_seconds,
        "temperatures": temperatures,
        "training_history": list(history),
        "parameter_count": sum(parameter.numel() for parameter in pipeline.model.parameters()),
        "device": str(lifecycle.device),
        "thread_config": {"torch_intra_op": torch.get_num_threads(),
                          "torch_inter_op": torch.get_num_interop_threads()},
        "peak_rss_mb": _peak_rss_mb(),
        "run_wall_seconds": run_wall_seconds,
        "process_cpu_seconds": process_cpu_seconds,
        "average_cpu_utilization_percent": average_cpu_utilization,
        "cache_rebuilds": 0,
        "final_test_access_count": 0,
        **metrics,
    }
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    temporary_manifest.replace(manifest_path)
    print(json.dumps({
        "PHASE": "M1_TRAIN_COMPLETE", "H": hidden_size, "SEED": seed,
        "TRAIN_SECONDS": training_seconds,
        "CALIBRATION_SECONDS": calibration_seconds,
        "INFERENCE_SECONDS": metrics["inference_seconds"],
        "AVERAGE_CPU_UTILIZATION_PERCENT": average_cpu_utilization,
        "CACHE_REBUILDS": 0, "FINAL_TEST_ACCESS_COUNT": 0,
    }, sort_keys=True), flush=True)
    return manifest


def _write_h_decision(cache, rows):
    candidates = {}
    for hidden_size in HIDDEN_SIZES:
        selected = [row for row in rows if row["hidden_size"] == hidden_size]
        scores = [row["episode_balanced_joint_nll"] for row in selected]
        candidates[str(hidden_size)] = {
            "mean_joint_nll": statistics.mean(scores),
            "sd_joint_nll": statistics.stdev(scores),
            "min_joint_nll": min(scores),
            "max_joint_nll": max(scores),
            "mean_calibration_ece": statistics.mean(
                row["mean_calibration_ece"] for row in selected),
            "mean_training_seconds": statistics.mean(
                row["training_seconds"] for row in selected),
            "mean_inference_seconds": statistics.mean(
                row["inference_seconds"] for row in selected),
        }
    h16_mean = candidates["16"]["mean_joint_nll"]
    h32_mean = candidates["32"]["mean_joint_nll"]
    relative_difference = abs(h16_mean - h32_mean) / min(h16_mean, h32_mean)
    equivalent = relative_difference <= 0.005
    recommendation = 16 if equivalent else (16 if h16_mean < h32_mean else 32)
    evidence = {
        "status": "HUMAN_DECISION_REQUIRED", "decision_id": "D2_H_STAR",
        "paper_result": False, "development_only": True,
        "repository_sha": _repository_sha(), "representation": "ADAPTIVE_HISTORY",
        "history_boundary": "FULL_ADMISSIBLE_CURRENT_EPISODE_PREFIX",
        "hidden_size_candidates": list(HIDDEN_SIZES), "training_seeds": list(TRAINING_SEEDS),
        "training_contract": {"epochs": EPOCHS, "learning_rate": LEARNING_RATE,
                              "batch_size": BATCH_SIZE, "optimizer": "Adam"},
        "selection_metric": "episode-balanced Development joint NLL",
        "tie_rule": "if relative joint-NLL difference <= 0.5%, recommend H=16",
        "candidate_summary": candidates, "per_seed": rows,
        "codex_recommendation": recommendation,
        "within_0_5_percent_equivalence_region": equivalent,
        "relative_nll_difference": relative_difference,
        "cache_rebuilds": 0,
        "data_audit": cache.audit, "final_test_access_count": 0,
        "w_comparison_status": "NOT_RUN_AWAITING_H_STAR_APPROVAL",
    }
    evidence["evidence_hash"] = content_id(evidence)
    EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"status": evidence["status"], "evidence": str(EVIDENCE_PATH),
                      "evidence_hash": evidence["evidence_hash"],
                      "final_test_access_count": 0}, sort_keys=True))


def _parser():
    parser = argparse.ArgumentParser(
        description="Stage-gated M1 Development cache and H-selection runner")
    parser.add_argument("--stage", required=True,
                        choices=("cache", "one-seed", "full-h"))
    parser.add_argument("--approval-token")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda", "auto"))
    return parser


def main(argv=None) -> None:
    args = _parser().parse_args(argv)
    torch.set_num_threads(min(8, torch.get_num_threads()))
    scientific = load_config_layers(ROOT / "configs").scientific
    if tuple(scientific.parameters["m1_hidden_size_candidates"].value) != HIDDEN_SIZES:
        raise RuntimeError("HIDDEN_SIZE_CANDIDATES_CHANGED")
    OUT.mkdir(parents=True, exist_ok=True)
    cache, cache_status = _base_cache(scientific, allow_build=args.stage == "cache")
    if args.stage == "cache":
        print(json.dumps({"status": "CACHE_BUILD_COMPLETE",
                          "cache": str(BASE_CACHE_MANIFEST),
                          "cache_status": cache_status,
                          "final_test_access_count": 0}, sort_keys=True))
        return
    if args.stage == "one-seed":
        row = _run_candidate(
            scientific, cache, hidden_size=16, seed=TRAINING_SEEDS[0],
            device=args.device, resume=args.resume)
        print(json.dumps({
            "status": "HUMAN_DECISION_REQUIRED",
            "decision_id": "PERF_AUTHORIZE_FULL_H_SELECTION",
            "one_seed_manifest": str(_run_paths(16, TRAINING_SEEDS[0])[1]),
            "training_seconds": row["training_seconds"],
            "calibration_seconds": row["calibration_seconds"],
            "development_inference_seconds": row["inference_seconds"],
            "estimated_10_run_seconds": row["training_seconds"] * 10,
            "final_test_access_count": 0,
        }, sort_keys=True))
        return
    if args.approval_token != FULL_H_APPROVAL_TOKEN:
        raise RuntimeError("FULL_H_SELECTION_REQUIRES_APPROVE_H_SELECTION_RUN")
    rows = []
    for hidden_size in HIDDEN_SIZES:
        for seed in TRAINING_SEEDS:
            rows.append(_run_candidate(
                scientific, cache, hidden_size=hidden_size, seed=seed,
                device=args.device, resume=args.resume))
    _write_h_decision(cache, rows)


if __name__ == "__main__":
    main()
