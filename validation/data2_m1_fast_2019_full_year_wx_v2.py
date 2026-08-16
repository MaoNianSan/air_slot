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


from functools import partial
from validation.scenarios.data2_m1_full_year import (
    build_episode_reservoirs as shared_build_episode_reservoirs,
    cohort as shared_full_year_cohort,
    gap_stats as shared_gap_stats,
    raw_paths as shared_full_year_raw_paths,
    stage_inference as shared_stage_inference,
)

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



_timezones = partial(shared_load_timezones, ZONES_PATH)
_config_hash = partial(shared_config_hash, ROOT)
_registry_hash = partial(shared_registry_hash, ROOT)
_stream_flights = partial(shared_stream_completed_flights, ONTIME_CSVS, PROJECTED,
                          include_service_date=True)
_stream_coupon_routes = partial(shared_stream_coupon_routes, COUPON_CSVS)
_weather_index_and_stats = partial(shared_weather_index_and_stats, DATA2, OUT, period=None)
_latest_weather = shared_latest_weather
_reference_summary = shared_reference_summary
_turnaround_cells = shared_turnaround_cells
_taxi_cells = shared_taxi_cells
_exposure_cells = shared_exposure_cells
_passenger_cells = shared_passenger_cells
_typed_records = partial(shared_load_typed_records, csv_paths=ONTIME_CSVS,
                         projected=PROJECTED, zones_path=ZONES_PATH)
_states = shared_publish_states
_normalization_rows = shared_normalization_rows
_source_stats = partial(shared_source_stats, root=ROOT)
_weather_state_stats = shared_weather_state_stats

SAMPLE_COUNTS = {"train": TRAIN_COUNT, "calibration": CALIBRATION_COUNT,
                 "development": DEVELOPMENT_COUNT, "test": TEST_COUNT}

_gap_stats = shared_gap_stats
_build_episode_reservoirs = partial(shared_build_episode_reservoirs,
                                    sample_counts=SAMPLE_COUNTS, seed=SEED)
_cohort = shared_full_year_cohort
_raw_paths = partial(shared_full_year_raw_paths, DATA2, ONTIME_CSVS, COUPON_CSVS,
                     ZONES_PATH, STATION_MAP_PATH)
_stage_inference = partial(shared_stage_inference, states_builder=_states,
                           seed=SEED, scenario_count=16)


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
                                                  normalization=normalization, hidden_size=16)
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
