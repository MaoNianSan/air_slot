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


from functools import partial
from validation.support.data2_m1 import (
    chain_stats as shared_chain_stats,
    config_hash as shared_config_hash,
    exposure_cells as shared_exposure_cells,
    latest_weather as shared_latest_weather,
    load_timezones as shared_load_timezones,
    load_typed_records as shared_load_typed_records,
    normalization_rows as shared_normalization_rows,
    passenger_cells as shared_passenger_cells,
    publish_states as shared_publish_states,
    reference_summary as shared_reference_summary,
    registry_hash as shared_registry_hash,
    sample_three_way_cohort as shared_sample_three_way_cohort,
    source_stats as shared_source_stats,
    stream_completed_flights as shared_stream_completed_flights,
    stream_coupon_routes as shared_stream_coupon_routes,
    stream_january_flights as shared_stream_january_flights,
    taxi_cells as shared_taxi_cells,
    turnaround_cells as shared_turnaround_cells,
    weather_index_and_stats as shared_weather_index_and_stats,
    weather_state_stats as shared_weather_state_stats,
)

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



_timezones = partial(shared_load_timezones, ZONES_PATH)
_config_hash = partial(shared_config_hash, ROOT)
_registry_hash = partial(shared_registry_hash, ROOT)
_stream_january_flights = partial(shared_stream_january_flights, ONTIME_CSV, PROJECTED)
_stream_coupon_routes = partial(shared_stream_coupon_routes, (COUPON_CSV,))
_reference_summary = shared_reference_summary
_turnaround_cells = shared_turnaround_cells
_taxi_cells = shared_taxi_cells
_exposure_cells = shared_exposure_cells
_passenger_cells = shared_passenger_cells
_chain_stats = shared_chain_stats
_cohort = partial(shared_sample_three_way_cohort, seed=SEED, train_count=TRAIN_COUNT,
                  calibration_count=CALIBRATION_COUNT, development_count=DEVELOPMENT_COUNT)
_typed_records = partial(shared_load_typed_records, csv_paths=(ONTIME_CSV,),
                         projected=PROJECTED, zones_path=ZONES_PATH)
_states = shared_publish_states
_normalization_rows = shared_normalization_rows
_source_stats = partial(shared_source_stats, root=ROOT)

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
                                                  normalization=normalization, hidden_size=16)
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
