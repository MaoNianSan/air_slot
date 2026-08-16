# -*- coding: utf-8 -*-
"""data2 fast-tier full-year run: D2-10 formal temporal split + H1 references.

Chain (D2-1/D2-2 anchor B) over the full 2019 BTS On-Time year; train-frozen
references fit on 2019-H1 (turnaround / taxi / downstream exposure, fit_period
2019-H1 under the unchanged D2-3/4/5 rules) and the new H1 passenger reference
(D2-PASSENGER-REFERENCE-H1@1.0.0, Q1+Q2 coupon files, x10); PRE publish with
DIRECT NOAA-ISD weather injection (D2-NOAA-ISD); M1 train/calibrate on the
train/calibration partitions and stage-selected inference on the development
and test partitions.

Temporal split (D2-TEMPORAL-SPLIT@1.0.0, D2-10): episodes are partitioned by
the successor (later leg) service_date -- train <= 2019-06-30, calibration
2019-07-01..07-31, development 2019-08-01..09-30, test >= 2019-10-01.  Cohort
per split: 32/16/16/16 (fast tier).  No cross-split leakage: references fit on
train rows only; M1 trains on train episodes only; calibration/dev/test use
frozen artifacts.  Fast tier only: no M2-M4, no paper result.

Weather note: D2-NOAA-ISD current_weather injection with latest legal ISD
observation (age <= weather_max_age=60) for the connection airport; availability =
event_time + data2_weather_replay_lag_minutes (FROZEN, 5 min, D2-6 replay-lag new
decision 2026-08-16); airports
without a legal observation keep legal ABSTAIN semantics.  Weather gates in this fast-tier run only require SUPPORTED slots in the
train/calibration prefixes and in the test inference (H2 evidence); the
development split is reported informationally -- its sampled episodes can
legitimately land on airports outside the 48-station partial coverage
(D2-6 option A, user-approved "部分机场作为主要考虑").
"""
from __future__ import annotations

import csv
import gc
import json
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path

import torch

from model.common.config import load_config_layers
from model.common.enums import OperationalStage, SupportState
from model.common.identity import content_id
from model.M1.coverage import active_node_prefixes
from model.M1.data import FEATURE_NAMES, encode_pre_sequence, fit_train_normalization
from model.M1.lifecycle import M1Lifecycle, M1TrainingExample
from model.M1.pipeline import M1Pipeline
from model.M1.splits import ALL_SPLITS, split_for_date
from model.PRE.adapters.data2 import Data2Adapter
from model.PRE.adapters.registry import RawReadRequest
from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.episode.builder import build_data2_episode_records
from model.PRE.episode.node_builder import build_rolling_decision_nodes
from model.PRE.feature_registry.loader import load_registry_bundle
from model.PRE.pipeline import ProductionPRERequest, publish_production_pre
from model.PRE.reference.exposure_data2 import build_data2_downstream_exposure
from model.PRE.reference.passenger_data2 import H1_RULE_ID, build_data2_passenger_reference
from model.PRE.reference.taxi_data2 import build_data2_taxi_reference
from model.PRE.reference.turnaround_data2 import build_data2_turnaround_reference


ROOT = Path(__file__).resolve().parents[1]
DATA2 = ROOT / "data2"
WEATHER_REPLAY_LAG_PARAM = "data2_weather_replay_lag_minutes"
REPLAY_LAG_PARAM = "replay_lag_minutes"
_SCIENTIFIC = load_config_layers(ROOT / "configs").scientific
WEATHER_REPLAY_LAG_MINUTES = int(_SCIENTIFIC.parameters[WEATHER_REPLAY_LAG_PARAM].value)
OUT = ROOT / "outputs" / "runtime" / f"data2_m1_fast_2019_full_year_wx_v2_rl{WEATHER_REPLAY_LAG_MINUTES}"
SEED = 20260813
TRAIN_COUNT = 32
CALIBRATION_COUNT = 16
DEVELOPMENT_COUNT = 16
TEST_COUNT = 16

PROJECTED = ("FlightDate", "Reporting_Airline", "Tail_Number",
    "Flight_Number_Reporting_Airline", "Origin", "Dest", "CRSDepTime",
    "CRSArrTime", "DepTime", "ArrTime", "WheelsOff", "WheelsOn",
    "TaxiOut", "TaxiIn", "DepDelayMinutes", "ArrDelayMinutes",
    "Cancelled", "Diverted")
ONTIME_CSVS = sorted((DATA2 / "raw" / "bts" / "ontime" / "2019").glob("month=*/*.csv"))
COUPON_CSVS = [DATA2 / "raw" / "bts" / "db1b" / "2019" / "coupon" / name
               for name in ("Origin_and_Destination_Survey_DB1BCoupon_2019_1.csv",
                            "Origin_and_Destination_Survey_DB1BCoupon_2019_2.csv")]
TRAIN_END_ISO = "2019-06-30"
H2_START_ISO = "2019-07-01"
ZONES_PATH = DATA2 / "refs" / "us_airport_timezones.csv"
STATION_MAP_PATH = DATA2 / "refs" / "weather_station_map.csv"


def _timezones() -> dict[str, str]:
    with ZONES_PATH.open(encoding="utf-8-sig", newline="") as stream:
        return {row["iata"]: row["timezone"] for row in csv.DictReader(stream)}


def _config_hash() -> str:
    paths = (ROOT / "configs" / "scientific" / "foundation.yaml",
             ROOT / "configs" / "reproducibility" / "smoke.yaml",
             ROOT / "configs" / "engineering" / "local.example.yaml")
    ids = [{"path": str(path.relative_to(ROOT)),
            "sha256": sha256(path.read_bytes()).hexdigest()} for path in paths]
    return content_id(ids)


def _registry_hash() -> str:
    bundle = load_registry_bundle(ROOT / "registries")
    published = json.loads((ROOT / "registries" / "registry_manifest.json")
                           .read_text(encoding="utf-8"))
    if bundle.manifest.combined_sha256 != published["combined_sha256"]:
        raise RuntimeError("REGISTRY_MANIFEST_MISMATCH")
    return bundle.manifest.combined_sha256


def _stream_flights(zones: dict[str, str]):
    flight_rows: list[dict] = []
    taxi_rows: list[dict] = []
    skipped = 0
    per_month: Counter[str] = Counter()
    for csv_path in ONTIME_CSVS:
        month = csv_path.parent.name.replace("month=", "")
        with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            for raw in csv.DictReader(stream):
                try:
                    schedule, outcome = canonicalize_ontime_row(
                        {key: raw.get(key, "") for key in PROJECTED}, zones)
                except Exception:
                    skipped += 1
                    continue
                if schedule.aircraft_id is None or outcome.cancelled or outcome.diverted:
                    skipped += 1
                    continue
                flight_rows.append({
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
                    "service_date": (schedule.service_date.isoformat()
                                     if schedule.service_date is not None else None),
                })
                per_month[month] += 1
                if outcome.taxi_out_minutes is not None:
                    taxi_rows.append({
                        "dataset_instance_id": schedule.dataset_instance_id,
                        "aircraft_id": schedule.aircraft_id,
                        "flight_id": schedule.flight_id,
                        "origin_airport_id": schedule.origin_airport_id,
                        "taxi_out_minutes": outcome.taxi_out_minutes,
                        "service_date": (schedule.service_date.isoformat()
                                         if schedule.service_date is not None else None),
                    })
    return flight_rows, taxi_rows, skipped, dict(per_month)

def _stream_coupon_routes():
    sums: dict[tuple[str, str], float] = defaultdict(float)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    raw_rows = 0
    missing_passengers = 0
    for csv_path in COUPON_CSVS:
        with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader)
            idx_pax = header.index("Passengers")
            idx_origin = header.index("Origin")
            idx_dest = header.index("Dest")
            for raw in reader:
                if not raw or len(raw) <= max(idx_pax, idx_origin, idx_dest):
                    continue
                raw_rows += 1
                origin = raw[idx_origin].strip()
                dest = raw[idx_dest].strip()
                if not origin or not dest:
                    continue
                try:
                    pax = float(raw[idx_pax])
                except ValueError:
                    missing_passengers += 1
                    continue
                sums[(origin, dest)] += pax
                counts[(origin, dest)] += 1
    rows = [{
        "dataset_instance_id": "data2_2019",
        "canonical_record_id": content_id({"source": "bts_db1b",
                                           "origin": origin, "destination": dest}),
        "join_key": {"origin": origin, "destination": dest},
        "reference_period": "2019",
        "value": total,
        "record_count": counts[(origin, dest)],
        "split": "train",
    } for (origin, dest), total in sorted(sums.items())]
    return rows, raw_rows, missing_passengers


def _weather_index_and_stats(replay_lag_minutes: int):
    request = RawReadRequest(dataset_instance_id="data2_2019", source_family="noaa_isd",
                             raw_root=DATA2, output_root=OUT, year=2019)
    adapter = Data2Adapter()
    index: dict[str, list] = defaultdict(list)
    per_airport: Counter[str] = Counter()
    obs_total = 0
    for obs in adapter.iter_canonical(request, replay_lag_minutes=replay_lag_minutes):
        if obs.event_time is None or obs.event_time.year != 2019:
            continue
        if not obs.airport_id or obs.availability_time is None:
            continue
        obs_total += 1
        per_airport[obs.airport_id] += 1
        index[obs.airport_id].append(obs)
    for airport in index:
        index[airport].sort(key=lambda obs: obs.availability_time)
    stats = {
        "year_observations": obs_total,
        "airports_covered": len(per_airport),
        "top_airports": per_airport.most_common(10),
        "injected": True,
    }
    return dict(index), stats


def _latest_weather(weather_index, airport_id, cutoff, weather_max_age_minutes):
    if not airport_id:
        return None
    observations = weather_index.get(airport_id)
    if not observations:
        return None
    limit = cutoff - timedelta(minutes=weather_max_age_minutes)
    for obs in reversed(observations):
        if obs.availability_time > cutoff:
            continue
        if obs.availability_time < limit:
            break
        return obs
    return None


def _reference_summary(reference, *, cells: list[dict], globals_: dict | None = None) -> dict:
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


def _turnaround_cells(reference) -> list[dict]:
    return [{"airport_id": cell.airport_id, "value_minutes": cell.value_minutes,
             "sample_count": cell.sample_count, "fallback_level": cell.fallback_level,
             "provenance": list(cell.provenance)} for cell in reference.cells]


def _taxi_cells(reference) -> list[dict]:
    return [{"airport_id": cell.airport_id, "value_minutes": cell.value_minutes,
             "sample_count": cell.sample_count, "fallback_level": cell.fallback_level,
             "provenance": list(cell.provenance)} for cell in reference.cells]


def _exposure_cells(reference) -> list[dict]:
    return [{"airport_id": cell.airport_id, "value_legs": cell.value_legs,
             "sample_count": cell.sample_count, "fallback_level": cell.fallback_level,
             "provenance": list(cell.provenance)} for cell in reference.cells]


def _passenger_cells(reference) -> list[dict]:
    return [{"origin": cell.origin_airport_id, "destination": cell.destination_airport_id,
             "value_passengers": cell.value_passengers, "sample_count": cell.sample_count,
             "provenance": list(cell.provenance)} for cell in reference.cells]


def _gap_stats(gaps: list[float]) -> dict:
    ordered = sorted(gaps)
    n = len(ordered)
    percentiles = {q: ordered[min(n - 1, int(q * n / 100.0))] for q in (5, 25, 50, 75, 95, 99)}
    return {"count": n, "percentiles": percentiles, "max": ordered[-1]}




SAMPLE_COUNTS = {"train": TRAIN_COUNT, "calibration": CALIBRATION_COUNT,
                 "development": DEVELOPMENT_COUNT, "test": TEST_COUNT}


def _build_episode_reservoirs(flight_rows: list[dict], by_id: dict[str, dict]):
    """Build the full-year episode set in month chunks with per-split reservoirs.

    Chunk (m-1, m) covers every chain whose successor service_date is in month
    m (gap <= 360 min => predecessor is never older than the previous month).
    Episodes are streamed into a deterministic uniform k-subset reservoir per
    split (Algorithm R, fixed seed), so the 32/16/16/16 cohort is sampled
    without materialising the ~5M episode pool (memory-bounded, D2-10).
    """
    by_month: dict[str, list[dict]] = defaultdict(list)
    for row in flight_rows:
        if row.get("service_date"):
            by_month[row["service_date"][:7]].append(row)
    reservoirs: dict[str, list] = {split: [] for split in ALL_SPLITS}
    pool_sizes: dict[str, int] = {split: 0 for split in ALL_SPLITS}
    total = 0
    gaps: list[float] = []
    rng = random.Random(SEED)
    for month_index in range(1, 13):
        key = f"2019-{month_index:02d}"
        prev = f"2019-{month_index - 1:02d}" if month_index > 1 else None
        chunk = list(by_month.get(key, ()))
        if prev:
            chunk.extend(by_month.get(prev, ()))
        for episode in sorted(build_data2_episode_records(chunk),
                              key=lambda e: e.episode_id):
            service_date = by_id[episode.successor_flight_id]["service_date"]
            if service_date is None or service_date[:7] != key:
                continue
            split = split_for_date(date.fromisoformat(service_date))
            pool_sizes[split] += 1
            total += 1
            gaps.append(
                (by_id[episode.successor_flight_id]["actual_departure_utc"]
                 - by_id[episode.predecessor_flight_id]["actual_arrival_utc"])
                .total_seconds() / 60)
            reservoir = reservoirs[split]
            count = pool_sizes[split]
            if len(reservoir) < SAMPLE_COUNTS[split]:
                reservoir.append(episode)
            else:
                index = rng.randrange(count)
                if index < SAMPLE_COUNTS[split]:
                    reservoir[index] = episode
    return reservoirs, pool_sizes, total, gaps


def _cohort(reservoirs: dict[str, list]):
    key = lambda episode: (episode.episode_id, episode.predecessor_flight_id)
    return (sorted(reservoirs["train"], key=key),
            sorted(reservoirs["calibration"], key=key),
            sorted(reservoirs["development"], key=key),
            sorted(reservoirs["test"], key=key))


def _typed_records(episodes) -> tuple[dict[str, object], dict[str, object]]:
    needed = {flight_id for episode in episodes
              for flight_id in (episode.predecessor_flight_id, episode.successor_flight_id)}
    zones = _timezones()
    schedules: dict[str, object] = {}
    outcomes: dict[str, object] = {}
    for csv_path in ONTIME_CSVS:
        with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            for raw in csv.DictReader(stream):
                try:
                    schedule, outcome = canonicalize_ontime_row(
                        {key: raw.get(key, "") for key in PROJECTED}, zones)
                except Exception:
                    continue
                if schedule.flight_id in needed and schedule.flight_id not in schedules:
                    schedules[schedule.flight_id] = schedule
                    outcomes[schedule.flight_id] = outcome
    missing = needed - set(schedules)
    if missing:
        raise RuntimeError(f"COHORT_FLIGHT_RECORD_MISSING:{sorted(missing)[:5]}")
    return schedules, outcomes


def _states(item, config_hash: str, registry_hash: str, weather_index,
              weather_max_age_minutes: int):
    episode, successor_schedule, predecessor_outcome, successor_outcome = item
    nodes = build_rolling_decision_nodes(episode=episode,
        predecessor_outcome=predecessor_outcome, successor_outcome=successor_outcome,
        config_hash=config_hash, registry_hash=registry_hash)
    states = []
    for node in nodes:
        weather = _latest_weather(weather_index, episode.connection_airport_id,
                                  node.information_cutoff, weather_max_age_minutes)
        records = (successor_schedule,) if weather is None else (successor_schedule, weather)
        states.append(publish_production_pre(ProductionPRERequest(
            episode_id=episode.episode_id, predecessor_id=episode.predecessor_flight_id,
            successor_id=episode.successor_flight_id, dataset_instance_id="data2_2019",
            decision_time=node.decision_time, information_cutoff=node.information_cutoff,
            records=records, config_hash=config_hash,
            registry_hash=registry_hash, connection_airport_id=episode.connection_airport_id,
            operational_stage=node.operational_stage, node_index=node.node_index,
            roll_minutes=node.roll_minutes)).pre_state)
    return nodes, states


def _normalization_rows(prefixes):
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


def _pick_prefix(item, stage: OperationalStage, config_hash: str, registry_hash: str,
                   weather_index, weather_max_age_minutes: int):
    nodes, states = _states(item, config_hash, registry_hash, weather_index,
                            weather_max_age_minutes)
    candidates = [index for index, node in enumerate(nodes) if node.operational_stage is stage]
    if not candidates:
        return None
    index = candidates[-1] if stage is OperationalStage.PRE_IB else candidates[0]
    return item, nodes[index], states[:index + 1]

def _source_stats(paths):
    return {str(path.relative_to(ROOT)): (path.stat().st_size, path.stat().st_mtime_ns)
            for path in paths}


def _raw_paths() -> list[Path]:
    paths = list(ONTIME_CSVS) + list(COUPON_CSVS) + [ZONES_PATH, STATION_MAP_PATH]
    paths.extend(sorted((DATA2 / "raw" / "weather" / "noaa" / "2019").glob("*.csv")))
    return paths


def _weather_state_stats(prefixes) -> dict:
    total = 0
    supported = 0
    supported_with_values = 0
    abstain_reasons: Counter[str] = Counter()
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


def _stage_inference(episodes, items, normalization, loaded, *,
                     config_hash, registry_hash, weather_index, weather_max_age):
    stage_selected = []
    used = set()
    for stage in OperationalStage:
        for episode in episodes:
            if episode.episode_id in used:
                continue
            match = _pick_prefix(items[episode.episode_id], stage, config_hash,
                                 registry_hash, weather_index, weather_max_age)
            if match is None:
                continue
            stage_selected.append(match)
            used.add(match[0][0].episode_id)
            break
    numerical, deterministic = True, True
    probability_shapes = {}
    scenarios = []
    stage_counts: Counter[str] = Counter()
    for selected in stage_selected:
        item, node, states = selected
        episode, schedule, predecessor_outcome, successor_outcome = item
        values = encode_pre_sequence(states, normalization).unsqueeze(0)
        lengths = torch.tensor([len(states)])
        distributions = loaded.infer(values, lengths)
        probability_shapes[node.operational_stage.value] = {
            name: list(distribution.shape) for name, distribution in distributions.items()}
        numerical &= all(torch.isfinite(distribution).all().item()
                         and abs(float(distribution.sum()) - 1.0) < 1e-5
                         for distribution in distributions.values())
        observed = {}
        if node.operational_stage in {OperationalStage.POST_IB_PRE_OB,
                                      OperationalStage.POST_OB_PRE_TO,
                                      OperationalStage.COMPLETED}:
            observed["R_IB"] = 0.0
        if node.operational_stage in {OperationalStage.POST_OB_PRE_TO,
                                      OperationalStage.COMPLETED}:
            observed["R_OB"] = max(0.0, (successor_outcome.actual_departure_utc -
                schedule.scheduled_departure_utc).total_seconds() / 60)
        if node.operational_stage is OperationalStage.COMPLETED:
            observed["T_TX"] = float(successor_outcome.taxi_out_minutes)
        created = loaded.sample(states[-1], values, lengths, observed=observed,
                                count=16, seed=SEED)
        repeated = loaded.sample(states[-1], values, lengths, observed=observed,
                                 count=16, seed=SEED)
        deterministic &= created == repeated
        scenarios.extend(created)
        stage_counts[node.operational_stage.value] += len(created)
    return (stage_selected, scenarios, dict(stage_counts), numerical, deterministic,
            probability_shapes)

def main() -> None:
    torch.manual_seed(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    config_hash = _config_hash()
    registry_hash = _registry_hash()
    scientific = load_config_layers(ROOT / "configs").scientific
    replay_lag = int(scientific.parameters[REPLAY_LAG_PARAM].value)
    weather_replay_lag = int(scientific.parameters[WEATHER_REPLAY_LAG_PARAM].value)
    weather_max_age = int(scientific.parameters["weather_max_age_minutes"].value)

    before = _source_stats(_raw_paths())

    zones = _timezones()
    flight_rows, taxi_rows, skipped_ontime, per_month = _stream_flights(zones)
    flight_rows_count = len(flight_rows)
    unique_aircraft = len({row["aircraft_id"] for row in flight_rows})
    print("PHASE streams done:", flight_rows_count, "flights", flush=True)
    flight_routes = {(row["origin_airport_id"], row["destination_airport_id"])
                     for row in flight_rows}
    h2_routes = {(row["origin_airport_id"], row["destination_airport_id"])
                 for row in flight_rows
                 if row.get("service_date") and row["service_date"] >= H2_START_ISO}
    by_id = {row["flight_id"]: row for row in flight_rows}
    reservoirs, pool_sizes, total_episodes, gaps = _build_episode_reservoirs(
        flight_rows, by_id)
    chain_stats = _gap_stats(gaps)
    print("PHASE episodes done:", total_episodes, "episodes", flush=True)
    train_episodes, calibration_episodes, development_episodes, test_episodes = (
        _cohort(reservoirs))
    del reservoirs

    train_rows = [row for row in flight_rows
                  if row.get("service_date") and row["service_date"] <= TRAIN_END_ISO]
    train_taxi_rows = [row for row in taxi_rows
                       if row.get("service_date") and row["service_date"] <= TRAIN_END_ISO]
    del flight_rows, by_id, taxi_rows
    gc.collect()
    print("PHASE memory released; train rows:", len(train_rows), flush=True)

    turnaround = build_data2_turnaround_reference(
        [{**row, "split": "train"} for row in train_rows], fit_period="2019-H1")
    print("PHASE turnaround reference done", flush=True)
    taxi = build_data2_taxi_reference(
        [{**row, "split": "train"} for row in train_taxi_rows], fit_period="2019-H1")
    print("PHASE taxi reference done", flush=True)
    exposure = build_data2_downstream_exposure(
        [{**row, "split": "train"} for row in train_rows], fit_period="2019-H1")
    print("PHASE exposure reference done", flush=True)
    del train_rows, train_taxi_rows
    gc.collect()
    passenger_rows, coupon_rows, coupon_missing = _stream_coupon_routes()
    print("PHASE coupon stream done:", coupon_rows, "rows", flush=True)
    passenger = build_data2_passenger_reference(passenger_rows, fit_period="2019-H1",
                                                rule_id=H1_RULE_ID)
    print("PHASE passenger reference done", flush=True)

    passenger_covered = {route for route in flight_routes
                         if passenger.lookup(*route).support_state is SupportState.SUPPORTED}
    h2_covered = passenger_covered & h2_routes

    weather_index, weather_stats = _weather_index_and_stats(weather_replay_lag)

    all_cohort = train_episodes + calibration_episodes + development_episodes + test_episodes
    schedules, outcomes = _typed_records(all_cohort)
    items = {episode.episode_id: (episode, schedules[episode.successor_flight_id],
                                  outcomes[episode.predecessor_flight_id],
                                  outcomes[episode.successor_flight_id])
             for episode in all_cohort}

    train_active = []
    train_stage_counts: Counter[str] = Counter()
    for episode in train_episodes:
        item = items[episode.episode_id]
        nodes, states = _states(item, config_hash, registry_hash, weather_index, weather_max_age)
        for _, prefix, labels in active_node_prefixes(
                episode=episode, nodes=nodes, states=states,
                successor_schedule=item[1], predecessor_outcome=item[2],
                successor_outcome=item[3]):
            train_active.append((episode, prefix, labels))
            train_stage_counts[prefix[-1].decision_node.operational_stage.value] += 1
    calibration_active = []
    calibration_stage_counts: Counter[str] = Counter()
    for episode in calibration_episodes:
        item = items[episode.episode_id]
        nodes, states = _states(item, config_hash, registry_hash, weather_index, weather_max_age)
        for _, prefix, labels in active_node_prefixes(
                episode=episode, nodes=nodes, states=states,
                successor_schedule=item[1], predecessor_outcome=item[2],
                successor_outcome=item[3]):
            calibration_active.append((episode, prefix, labels))
            calibration_stage_counts[prefix[-1].decision_node.operational_stage.value] += 1
    train_prefixes = [prefix for _, prefix, _ in train_active]
    calibration_prefixes = [prefix for _, prefix, _ in calibration_active]

    normalization = fit_train_normalization(_normalization_rows(train_prefixes), split="train")
    pipeline = M1Pipeline.from_scientific_config(scientific, input_size=len(FEATURE_NAMES),
                                                  normalization=normalization)
    train_examples = [M1TrainingExample.from_target_labels(
                          values=encode_pre_sequence(prefix, normalization),
                          labels=labels, bins=pipeline.bins)
                      for _, prefix, labels in train_active]
    calibration_examples = [M1TrainingExample.from_target_labels(
                                values=encode_pre_sequence(prefix, normalization),
                                labels=labels, bins=pipeline.bins)
                            for _, prefix, labels in calibration_active]
    lifecycle = M1Lifecycle(pipeline)
    history = lifecycle.train(train_examples, epochs=8, learning_rate=0.01)
    temperatures = lifecycle.calibrate(calibration_examples)

    artifact = OUT / "m1.pt"
    lifecycle.save(artifact)
    loaded = M1Lifecycle.load(artifact)

    dev_selected, dev_scenarios, dev_stage_counts, dev_numerical, dev_deterministic, dev_shapes = (
        _stage_inference(development_episodes, items, normalization, loaded,
                         config_hash=config_hash, registry_hash=registry_hash,
                         weather_index=weather_index, weather_max_age=weather_max_age))
    test_selected, test_scenarios, test_stage_counts, test_numerical, test_deterministic, test_shapes = (
        _stage_inference(test_episodes, items, normalization, loaded,
                         config_hash=config_hash, registry_hash=registry_hash,
                         weather_index=weather_index, weather_max_age=weather_max_age))
    scenarios = dev_scenarios + test_scenarios
    numerical = dev_numerical and test_numerical
    deterministic = dev_deterministic and test_deterministic
    probability_shapes = {**dev_shapes, **test_shapes}

    train_dates = sorted({str(example.episode_date) for example in train_examples})
    calibration_dates = sorted({str(example.episode_date) for example in calibration_examples})
    development_dates = sorted({str(item[0][1].service_date) for item in dev_selected})
    test_dates = sorted({str(item[0][1].service_date) for item in test_selected})

    isolation = {
        "train_max": max(train_dates),
        "calibration_max": max(calibration_dates),
        "development_min": min(development_dates),
        "development_max": max(development_dates),
        "test_min": min(test_dates),
        "train_within_window": max(train_dates) <= TRAIN_END_ISO,
        "calibration_within_window": max(calibration_dates) <= "2019-07-31",
        "development_within_window": min(development_dates) >= H2_START_ISO
                                     and max(development_dates) <= "2019-09-30",
        "test_after_window": min(test_dates) >= "2019-10-01",
    }

    supports = {name: {"max_finite_minutes": bins.max_finite_minutes,
        "finite_last_index": bins.encode(bins.max_finite_minutes),
        "overflow_start_minutes": bins.max_finite_minutes + bins.bin_width_minutes,
        "overflow_index": bins.encode(bins.max_finite_minutes + bins.bin_width_minutes),
        "class_count": bins.class_count} for name, bins in pipeline.bins.items()}
    weather_state_stats = _weather_state_stats(train_prefixes + calibration_prefixes)
    dev_weather_stats = _weather_state_stats(
        [states for _, _, states in dev_selected])
    test_weather_stats = _weather_state_stats(
        [states for _, _, states in test_selected])
    expected_scenarios = (len(dev_selected) + len(test_selected)) * 16

    del gaps
    gc.collect()
    result = {
        "status": "PASS", "paper_result": False, "experiment": False,
        "tier": "fast", "dataset_instance_id": "data2_2019", "period": "2019",
        "config_hash": config_hash, "registry_hash": registry_hash,
        "cohort": {
            "train_episodes_sampled": len(train_episodes),
            "train_examples": len(train_examples),
            "train_example_stage_counts": dict(train_stage_counts),
            "calibration_episodes_sampled": len(calibration_episodes),
            "calibration_examples": len(calibration_examples),
            "calibration_example_stage_counts": dict(calibration_stage_counts),
            "development_stage_examples": len(dev_selected),
            "test_stage_examples": len(test_selected),
            "pool_sizes": pool_sizes,
            "total_episodes": total_episodes,
            "train_dates": train_dates,
            "calibration_dates": calibration_dates,
            "development_dates": development_dates,
            "test_dates": test_dates,
            "split_semantics": "formal_temporal_by_successor_service_date",
            "split_rule": "D2-TEMPORAL-SPLIT@1.0.0",
            "coverage_rule": "D2-M1-TRAINING-COVERAGE@1.0.0",
            "sampling_method": "per_split_uniform_k_subset_reservoir_seeded",
            "selection_seed": SEED,
            "temporal_isolation": isolation,
        },
        "chain": {
            "ontime_rows_processed": flight_rows_count + skipped_ontime,
            "completed_eligible_flights": flight_rows_count,
            "skipped_canonical_or_incomplete": skipped_ontime,
            "per_month_completed": per_month,
            "unique_aircraft": unique_aircraft,
            **chain_stats,
        },
        "references": {
            "turnaround": _reference_summary(turnaround, cells=_turnaround_cells(turnaround),
                globals_={"global_value_minutes": turnaround.global_value_minutes,
                          "global_sample_count": turnaround.global_sample_count}),
            "taxi": _reference_summary(taxi, cells=_taxi_cells(taxi),
                globals_={"global_value_minutes": taxi.global_value_minutes,
                          "global_sample_count": taxi.global_sample_count}),
            "downstream_exposure": _reference_summary(exposure, cells=_exposure_cells(exposure),
                globals_={"global_value_legs": exposure.global_value_legs,
                          "global_sample_count": exposure.global_sample_count}),
            "passenger": {
                **_reference_summary(passenger, cells=_passenger_cells(passenger),
                    globals_={"total_passengers": passenger.total_passengers,
                              "total_sample_count": passenger.total_sample_count,
                              "route_count": passenger.route_count}),
                "coupon_raw_rows": coupon_rows,
                "coupon_missing_passengers": coupon_missing,
                "full_year_flight_routes": len(flight_routes),
                "full_year_route_coverage": len(passenger_covered),
                "full_year_route_coverage_share": round(len(passenger_covered) / len(flight_routes), 4),
                "h2_flight_routes": len(h2_routes),
                "h2_route_coverage": len(h2_covered),
                "h2_route_coverage_share": round(len(h2_covered) / len(h2_routes), 4),
            },
        },
        "weather": weather_stats,
        "weather_injection": weather_state_stats,
        "weather_development": dev_weather_stats,
        "weather_test": test_weather_stats,
        "config_parameters": {"replay_lag_minutes": replay_lag,
                              "data2_weather_replay_lag_minutes": weather_replay_lag,
                              "weather_max_age_minutes": weather_max_age},
        "history": {"earliest_node_index": 0,
                    "min_length": min(example.values.shape[0] for example in train_examples),
                    "max_length": max(example.values.shape[0] for example in train_examples),
                    "grid_minutes": 5, "lookback_parameter": None, "truncation": False,
                    "padding_only_in_batch": True},
        "supports": supports,
        "head_dimensions": {name: bins.class_count for name, bins in pipeline.bins.items()},
        "optimization": {"epochs": 8, "initial_loss": history[0]["loss"],
                         "final_loss": history[-1]["loss"],
                         "active_counts": history[-1]["active_counts"]},
        "temperatures": temperatures, "artifact": str(artifact.relative_to(ROOT)),
        "probability_shapes": probability_shapes,
        "numerical_valid": numerical,
        "scenarios": {"count": len(scenarios),
                      "development_stage_counts": dev_stage_counts,
                      "test_stage_counts": test_stage_counts,
                      "deterministic_lineage": deterministic,
                      "unique_seed_keys": len({row.scenario_seed_key for row in scenarios})},
        "raw_read_only": before == _source_stats(_raw_paths()),
        "source_files": sorted(before),
    }
    if (len(scenarios) != expected_scenarios or not numerical or not deterministic
            or not result["raw_read_only"]
            or len(train_examples) == 0 or len(calibration_examples) == 0
            or len(dev_selected) == 0 or len(test_selected) == 0
            or not all(isolation.values())
            or weather_state_stats["supported"] == 0
            or weather_state_stats["supported_with_temperature_values"] == 0
            or test_weather_stats["supported"] == 0
            or len(h2_covered) == 0):
        result["status"] = "FAIL"
    references_out = {
        "turnaround": _reference_summary(turnaround, cells=_turnaround_cells(turnaround),
            globals_={"global_value_minutes": turnaround.global_value_minutes,
                      "global_sample_count": turnaround.global_sample_count}),
        "taxi": _reference_summary(taxi, cells=_taxi_cells(taxi),
            globals_={"global_value_minutes": taxi.global_value_minutes,
                      "global_sample_count": taxi.global_sample_count}),
        "downstream_exposure": _reference_summary(exposure, cells=_exposure_cells(exposure),
            globals_={"global_value_legs": exposure.global_value_legs,
                      "global_sample_count": exposure.global_sample_count}),
        "passenger": {
            **_reference_summary(passenger, cells=_passenger_cells(passenger),
                globals_={"total_passengers": passenger.total_passengers,
                          "total_sample_count": passenger.total_sample_count,
                          "route_count": passenger.route_count}),
            "coupon_raw_rows": coupon_rows,
            "coupon_missing_passengers": coupon_missing,
        },
    }
    (OUT / "metrics.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    (OUT / "references.json").write_text(
        json.dumps(references_out, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "status", "tier", "config_hash", "registry_hash", "cohort", "chain", "weather",
        "weather_injection", "optimization", "scenarios", "raw_read_only",
        "references")}, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
