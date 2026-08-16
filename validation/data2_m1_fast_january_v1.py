# -*- coding: utf-8 -*-
"""data2 first full-chain fast-tier run: BTS 2019-01 only.

Chain (D2-1/D2-2 anchor B) + four train-frozen references (turnaround /
taxi / downstream exposure / passenger) + PRE publish on a bounded January
cohort + M1 train/calibrate/development-infer.  Fast tier only: no M2-M4,
no paper result, no formal chronology (all January).

Weather note (fast boundary): D2-NOAA-ISD canonical records currently fail
RegistryPREMapper.map_record with UNDECLARED_SCIENTIFIC_VARIABLE:
weather_observation (rule canonical_variable does not match the current_weather
definition), so PRE weather stays ABSTAIN (NO_LEGAL_RECORD_AT_DECISION_TIME),
which is the legal missing semantics.  Reported for approval; nothing here
edits the registry.
"""
from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

import torch

from model.common.config import load_config_layers
from model.common.enums import OperationalStage, SupportState
from model.common.identity import content_id
from model.M1.data import FEATURE_NAMES, encode_pre_sequence, fit_train_normalization
from model.M1.lifecycle import M1Lifecycle, M1TrainingExample
from model.M1.pipeline import M1Pipeline
from model.M1.target_builder import build_data2_target_labels
from model.PRE.adapters.data2 import Data2Adapter
from model.PRE.adapters.registry import RawReadRequest
from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.episode.builder import build_data2_episode_records
from model.PRE.episode.node_builder import build_rolling_decision_nodes
from model.PRE.feature_registry.loader import load_registry_bundle
from model.PRE.pipeline import ProductionPRERequest, publish_production_pre
from model.PRE.reference.exposure_data2 import build_data2_downstream_exposure
from model.PRE.reference.passenger_data2 import build_data2_passenger_reference
from model.PRE.reference.taxi_data2 import build_data2_taxi_reference
from model.PRE.reference.turnaround_data2 import build_data2_turnaround_reference


ROOT = Path(__file__).resolve().parents[1]
DATA2 = ROOT / "data2"
OUT = ROOT / "outputs" / "runtime" / "data2_m1_fast_january"
SEED = 20260813
TRAIN_COUNT = 32
CALIBRATION_COUNT = 16
DEVELOPMENT_COUNT = 16

PROJECTED = ("FlightDate", "Reporting_Airline", "Tail_Number",
    "Flight_Number_Reporting_Airline", "Origin", "Dest", "CRSDepTime",
    "CRSArrTime", "DepTime", "ArrTime", "WheelsOff", "WheelsOn",
    "TaxiOut", "TaxiIn", "DepDelayMinutes", "ArrDelayMinutes",
    "Cancelled", "Diverted")
ONTIME_CSV = next((DATA2 / "raw" / "bts" / "ontime" / "2019" / "month=01").glob("*.csv"))
COUPON_CSV = (DATA2 / "raw" / "bts" / "db1b" / "2019" / "coupon" /
              "Origin_and_Destination_Survey_DB1BCoupon_2019_1.csv")
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


def _stream_january_flights(zones: dict[str, str]):
    flight_rows: list[dict] = []
    taxi_rows: list[dict] = []
    skipped = 0
    with ONTIME_CSV.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
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
            })
            if outcome.taxi_out_minutes is not None:
                taxi_rows.append({
                    "dataset_instance_id": schedule.dataset_instance_id,
                    "aircraft_id": schedule.aircraft_id,
                    "flight_id": schedule.flight_id,
                    "origin_airport_id": schedule.origin_airport_id,
                    "taxi_out_minutes": outcome.taxi_out_minutes,
                })
    return flight_rows, taxi_rows, skipped


def _stream_coupon_routes():
    sums: dict[tuple[str, str], float] = defaultdict(float)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    raw_rows = 0
    missing_passengers = 0
    with COUPON_CSV.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
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


def _weather_january_stats(replay_lag_minutes: int) -> dict:
    request = RawReadRequest(dataset_instance_id="data2_2019", source_family="noaa_isd",
                             raw_root=DATA2, output_root=OUT, year=2019)
    adapter = Data2Adapter()
    per_airport: Counter[str] = Counter()
    obs_total = 0
    for obs in adapter.iter_canonical(request, replay_lag_minutes=replay_lag_minutes):
        if obs.event_time is None or obs.event_time.strftime("%Y-%m") != "2019-01":
            continue
        if not obs.airport_id:
            continue
        obs_total += 1
        per_airport[obs.airport_id] += 1
    return {
        "january_observations": obs_total,
        "airports_covered": len(per_airport),
        "top_airports": per_airport.most_common(10),
        "path": "ABSTAIN_NO_LEGAL_RECORD_AT_DECISION_TIME",
        "blocker": ("D2-NOAA-ISD canonical_variable=weather_observation does not map to "
                    "current_weather canonical_inputs; RegistryPREMapper raises "
                    "UNDECLARED_SCIENTIFIC_VARIABLE. Registry fix pending approval."),
    }


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


def _chain_stats(episodes, by_id: dict[str, dict]) -> dict:
    gaps = [(by_id[episode.successor_flight_id]["actual_departure_utc"]
             - by_id[episode.predecessor_flight_id]["actual_arrival_utc"]).total_seconds() / 60
            for episode in episodes]
    ordered = sorted(gaps)
    n = len(ordered)
    percentiles = {q: ordered[min(n - 1, int(q * n / 100.0))] for q in (5, 25, 50, 75, 95, 99)}
    return {"count": n, "percentiles": percentiles, "max": ordered[-1]}


def _cohort(episodes):
    rng = random.Random(SEED)
    pool = sorted(episodes, key=lambda episode: (episode.episode_id,
                                                 episode.predecessor_flight_id))
    train_episodes = rng.sample(pool, TRAIN_COUNT)
    train_ids = {episode.episode_id for episode in train_episodes}
    rest = [episode for episode in pool if episode.episode_id not in train_ids]
    calibration_episodes = rng.sample(rest, CALIBRATION_COUNT)
    calibration_ids = {episode.episode_id for episode in calibration_episodes}
    rest = [episode for episode in rest if episode.episode_id not in calibration_ids]
    development_episodes = rng.sample(rest, DEVELOPMENT_COUNT)
    return train_episodes, calibration_episodes, development_episodes


def _typed_records(episodes) -> tuple[dict[str, object], dict[str, object]]:
    needed = {flight_id for episode in episodes
              for flight_id in (episode.predecessor_flight_id, episode.successor_flight_id)}
    zones = _timezones()
    schedules: dict[str, object] = {}
    outcomes: dict[str, object] = {}
    with ONTIME_CSV.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
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


def _states(item, config_hash: str, registry_hash: str):
    episode, successor_schedule, predecessor_outcome, successor_outcome = item
    nodes = build_rolling_decision_nodes(episode=episode,
        predecessor_outcome=predecessor_outcome, successor_outcome=successor_outcome,
        config_hash=config_hash, registry_hash=registry_hash)
    states = []
    for node in nodes:
        states.append(publish_production_pre(ProductionPRERequest(
            episode_id=episode.episode_id, predecessor_id=episode.predecessor_flight_id,
            successor_id=episode.successor_flight_id, dataset_instance_id="data2_2019",
            decision_time=node.decision_time, information_cutoff=node.information_cutoff,
            records=(successor_schedule,), config_hash=config_hash,
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


def _pick_prefix(item, stage: OperationalStage, config_hash: str, registry_hash: str):
    nodes, states = _states(item, config_hash, registry_hash)
    candidates = [index for index, node in enumerate(nodes) if node.operational_stage is stage]
    if not candidates:
        return None
    index = candidates[-1] if stage is OperationalStage.PRE_IB else candidates[0]
    return item, nodes[index], states[:index + 1]


def _example(selected, normalization, bins):
    item, node, states = selected
    episode, schedule, predecessor_outcome, successor_outcome = item
    labels = build_data2_target_labels(episode=episode, node=node,
        predecessor_outcome=predecessor_outcome, successor_schedule=schedule,
        successor_outcome=successor_outcome, target_support=states[-1].target_support)
    return M1TrainingExample.from_target_labels(values=encode_pre_sequence(states, normalization),
                                                 labels=labels, bins=bins), labels


def _source_stats(paths):
    return {str(path.relative_to(ROOT)): (path.stat().st_size, path.stat().st_mtime_ns)
            for path in paths}


def _raw_paths() -> list[Path]:
    paths = [ONTIME_CSV, COUPON_CSV, ZONES_PATH, STATION_MAP_PATH]
    paths.extend(sorted((DATA2 / "raw" / "weather" / "noaa" / "2019").glob("*.csv")))
    return paths


def _weather_abstention(prefixes) -> dict:
    total = 0
    legal_abstain = 0
    for states in prefixes:
        for state in states:
            weather = state.current_state.get("current_weather")
            if weather is None:
                continue
            total += 1
            if weather.support_state is SupportState.ABSTAIN and weather.reason_code == \
                    "NO_LEGAL_RECORD_AT_DECISION_TIME":
                legal_abstain += 1
    return {"states_with_weather_slot": total, "legal_abstain": legal_abstain}


def main() -> None:
    torch.manual_seed(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    config_hash = _config_hash()
    registry_hash = _registry_hash()
    scientific = load_config_layers(ROOT / "configs").scientific
    replay_lag = int(scientific.parameters["replay_lag_minutes"].value)
    weather_max_age = int(scientific.parameters["weather_max_age_minutes"].value)

    before = _source_stats(_raw_paths())

    zones = _timezones()
    flight_rows, taxi_rows, skipped_ontime = _stream_january_flights(zones)
    episodes = build_data2_episode_records(flight_rows)
    by_id = {row["flight_id"]: row for row in flight_rows}

    turnaround = build_data2_turnaround_reference(
        [{**row, "split": "train"} for row in flight_rows], fit_period="2019-01")
    taxi = build_data2_taxi_reference(
        [{**row, "split": "train"} for row in taxi_rows], fit_period="2019-01")
    exposure = build_data2_downstream_exposure(
        [{**row, "split": "train"} for row in flight_rows], fit_period="2019-01")
    passenger_rows, coupon_rows, coupon_missing = _stream_coupon_routes()
    passenger = build_data2_passenger_reference(passenger_rows, fit_period="2019-Q1")

    flight_routes = {(row["origin_airport_id"], row["destination_airport_id"])
                     for row in flight_rows}
    passenger_covered = {route for route in flight_routes
                         if passenger.lookup(*route).support_state is SupportState.SUPPORTED}

    weather_stats = _weather_january_stats(replay_lag)

    train_episodes, calibration_episodes, development_episodes = _cohort(episodes)
    all_cohort = train_episodes + calibration_episodes + development_episodes
    schedules, outcomes = _typed_records(all_cohort)
    items = {episode.episode_id: (episode, schedules[episode.successor_flight_id],
                                  outcomes[episode.predecessor_flight_id],
                                  outcomes[episode.successor_flight_id])
             for episode in all_cohort}

    train_selected = []
    for episode in train_episodes:
        match = _pick_prefix(items[episode.episode_id], OperationalStage.PRE_IB,
                             config_hash, registry_hash)
        if match is not None:
            train_selected.append(match)
    calibration_selected = []
    for episode in calibration_episodes:
        match = _pick_prefix(items[episode.episode_id], OperationalStage.PRE_IB,
                             config_hash, registry_hash)
        if match is not None:
            calibration_selected.append(match)
    train_prefixes = [selected[2] for selected in train_selected]
    calibration_prefixes = [selected[2] for selected in calibration_selected]

    normalization = fit_train_normalization(_normalization_rows(train_prefixes), split="train")
    pipeline = M1Pipeline.from_scientific_config(scientific, input_size=len(FEATURE_NAMES),
                                                  normalization=normalization)
    train_pairs = [_example(selected, normalization, pipeline.bins)
                   for selected in train_selected]
    calibration_pairs = [_example(selected, normalization, pipeline.bins)
                         for selected in calibration_selected]
    train_examples = [pair[0] for pair in train_pairs]
    calibration_examples = [pair[0] for pair in calibration_pairs]
    lifecycle = M1Lifecycle(pipeline)
    history = lifecycle.train(train_examples, epochs=8, learning_rate=0.01)
    temperatures = lifecycle.calibrate(calibration_examples)

    artifact = OUT / "m1.pt"
    lifecycle.save(artifact)
    loaded = M1Lifecycle.load(artifact)

    stage_selected = []
    used = set()
    for stage in OperationalStage:
        for episode in development_episodes:
            if items[episode.episode_id][0].episode_id in used:
                continue
            match = _pick_prefix(items[episode.episode_id], stage, config_hash, registry_hash)
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

    supports = {name: {"max_finite_minutes": bins.max_finite_minutes,
        "finite_last_index": bins.encode(bins.max_finite_minutes),
        "overflow_start_minutes": bins.max_finite_minutes + bins.bin_width_minutes,
        "overflow_index": bins.encode(bins.max_finite_minutes + bins.bin_width_minutes),
        "class_count": bins.class_count} for name, bins in pipeline.bins.items()}
    weather_abstention = _weather_abstention(train_prefixes + calibration_prefixes)
    expected_scenarios = len(stage_selected) * 16
    result = {
        "status": "PASS", "paper_result": False, "experiment": False,
        "tier": "fast", "dataset_instance_id": "data2_2019", "period": "2019-01",
        "config_hash": config_hash, "registry_hash": registry_hash,
        "cohort": {
            "train_episodes": len(train_selected),
            "calibration_episodes": len(calibration_selected),
            "development_stage_examples": len(stage_selected),
            "train_dates": sorted({str(pair[0].episode_date) for pair in train_pairs}),
            "calibration_dates": sorted({str(pair[0].episode_date) for pair in calibration_pairs}),
            "development_dates": sorted({str(item[0][1].service_date) for item in stage_selected}),
            "split_semantics": "fast_tier_january_non_chronological",
            "selection_seed": SEED,
        },
        "chain": {
            "ontime_rows_processed": len(flight_rows) + skipped_ontime,
            "completed_eligible_flights": len(flight_rows),
            "skipped_canonical_or_incomplete": skipped_ontime,
            "unique_aircraft": len({row["aircraft_id"] for row in flight_rows}),
            **_chain_stats(episodes, by_id),
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
                "january_flight_routes": len(flight_routes),
                "january_route_coverage": len(passenger_covered),
                "january_route_coverage_share": round(len(passenger_covered) / len(flight_routes), 4),
            },
        },
        "weather": weather_stats,
        "weather_abstention": weather_abstention,
        "config_parameters": {"replay_lag_minutes": replay_lag,
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
        "probability_shapes": probability_shapes, "numerical_valid": numerical,
        "scenarios": {"count": len(scenarios), "stage_counts": dict(stage_counts),
                      "deterministic_lineage": deterministic,
                      "unique_seed_keys": len({row.scenario_seed_key for row in scenarios})},
        "raw_read_only": before == _source_stats(_raw_paths()),
        "source_files": sorted(before),
    }
    if (len(scenarios) != expected_scenarios or not numerical or not deterministic
            or not result["raw_read_only"]
            or weather_abstention["legal_abstain"] != weather_abstention["states_with_weather_slot"]):
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
        "weather_abstention", "optimization", "scenarios", "raw_read_only",
        "references")}, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
