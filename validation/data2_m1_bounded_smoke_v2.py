"""Bounded real-data M1 smoke; never a scientific experiment or paper result."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

import torch

from model.common.config import load_config_layers
from model.common.enums import OperationalStage
from model.M1.data import (FEATURE_NAMES, NORMALIZED_NAMES, encode_pre_sequence,
                           fit_train_normalization)
from model.M1.lifecycle import M1Lifecycle, M1TrainingExample
from model.M1.pipeline import M1Pipeline
from model.M1.target_builder import build_data2_target_labels
from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.episode.builder import build_episode_records
from model.PRE.episode.node_builder import build_rolling_decision_nodes
from model.PRE.pipeline import ProductionPRERequest, publish_production_pre


ROOT = Path(__file__).resolve().parents[1]
CONFIG_HASH = "sha256:bounded-real-smoke-config"
REGISTRY_HASH = "sha256:bounded-real-smoke-registry"
PROJECTED = ("FlightDate", "Reporting_Airline", "Tail_Number",
    "Flight_Number_Reporting_Airline", "Origin", "Dest", "CRSDepTime",
    "CRSArrTime", "DepTime", "ArrTime", "WheelsOff", "WheelsOn",
    "TaxiOut", "TaxiIn", "DepDelayMinutes", "ArrDelayMinutes",
    "Cancelled", "Diverted")


def _timezones() -> dict[str, str]:
    path = ROOT / "data2" / "refs" / "us_airport_timezones.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {row["iata"]: row["timezone"] for row in csv.DictReader(stream)}


def _rows(month: int, limit: int = 5000):
    if month == 1:
        path = next((ROOT / "data2" / "raw" / "bts" / "ontime" / "2019" /
                     "month=01").glob("*.csv"))
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            reader = csv.DictReader(stream)
            for index, row in enumerate(reader):
                if index >= limit: break
                yield {key: row.get(key, "") for key in PROJECTED}
        return
    path = ROOT / "data2" / "_download" / "bts" / "ontime" / "2019" / (
        f"On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2019_{month}.zip")
    with zipfile.ZipFile(path) as archive:
        member = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
        with archive.open(member) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig",
                                                           errors="replace", newline="") as stream:
            reader = csv.DictReader(stream)
            for index, row in enumerate(reader):
                if index >= limit: break
                yield {key: row.get(key, "") for key in PROJECTED}


def _cohort(month: int, count: int):
    zones = _timezones()
    schedules, outcomes = {}, {}
    for row in _rows(month):
        try:
            schedule, outcome = canonicalize_ontime_row(row, zones)
        except Exception:
            continue
        if schedule.aircraft_id is None or outcome.cancelled or outcome.diverted:
            continue
        schedules[schedule.flight_id] = schedule
        outcomes[outcome.flight_id] = outcome
    flight_rows = [{
        "flight_id": item.flight_id, "aircraft_id": item.aircraft_id,
        "aircraft_id_namespace": item.aircraft_id_namespace,
        "origin_airport_id": item.origin_airport_id,
        "destination_airport_id": item.destination_airport_id,
        "event_start_time": item.event_start_time, "event_end_time": item.event_end_time,
        "dataset_instance_id": item.dataset_instance_id,
    } for item in schedules.values()]
    episodes = [episode for episode in build_episode_records(flight_rows)
                if episode.predecessor_flight_id in outcomes
                and episode.successor_flight_id in outcomes]
    return [(episode, schedules[episode.successor_flight_id],
             outcomes[episode.predecessor_flight_id], outcomes[episode.successor_flight_id])
            for episode in episodes[:count]]


def _states(item):
    episode, successor_schedule, predecessor_outcome, successor_outcome = item
    nodes = build_rolling_decision_nodes(episode=episode,
        predecessor_outcome=predecessor_outcome, successor_outcome=successor_outcome,
        config_hash=CONFIG_HASH, registry_hash=REGISTRY_HASH)
    states = []
    for node in nodes:
        states.append(publish_production_pre(ProductionPRERequest(
            episode_id=episode.episode_id, predecessor_id=episode.predecessor_flight_id,
            successor_id=episode.successor_flight_id, dataset_instance_id="data2_2019",
            decision_time=node.decision_time, information_cutoff=node.information_cutoff,
            records=(successor_schedule,), config_hash=CONFIG_HASH,
            registry_hash=REGISTRY_HASH, connection_airport_id=episode.connection_airport_id,
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


def _pick_prefix(item, stage: OperationalStage):
    nodes, states = _states(item)
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


def main() -> None:
    torch.manual_seed(20260813)
    raw_paths = [next((ROOT / "data2" / "raw" / "bts" / "ontime" / "2019" /
                       "month=01").glob("*.csv"))]
    raw_paths += [ROOT / "data2" / "_download" / "bts" / "ontime" / "2019" /
                  f"On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2019_{month}.zip"
                  for month in (7, 8)]
    raw_paths.append(ROOT / "data2" / "refs" / "us_airport_timezones.csv")
    before = _source_stats(raw_paths)

    train_items, calibration_items, development_items = _cohort(1, 16), _cohort(7, 8), _cohort(8, 8)
    train_selected = [selected for item in train_items
                      if (selected := _pick_prefix(item, OperationalStage.PRE_IB))]
    calibration_selected = [selected for item in calibration_items
                            if (selected := _pick_prefix(item, OperationalStage.PRE_IB))]
    train_prefixes = [selected[2] for selected in train_selected]
    normalization = fit_train_normalization(_normalization_rows(train_prefixes), split="train")
    scientific = load_config_layers(ROOT / "configs").scientific
    pipeline = M1Pipeline.from_scientific_config(scientific, input_size=len(FEATURE_NAMES),
                                                  normalization=normalization, hidden_size=16)
    train_pairs = [_example(selected, normalization, pipeline.bins) for selected in train_selected]
    calibration_pairs = [_example(selected, normalization, pipeline.bins)
                         for selected in calibration_selected]
    train_examples = [pair[0] for pair in train_pairs]
    calibration_examples = [pair[0] for pair in calibration_pairs]
    lifecycle = M1Lifecycle(pipeline)
    history = lifecycle.train(train_examples, epochs=8, learning_rate=0.01)
    temperatures = lifecycle.calibrate(calibration_examples)

    artifact = ROOT / "outputs" / "real_smoke" / "data2_m1_bounded_smoke_v2" / "m1.pt"
    lifecycle.save(artifact)
    loaded = M1Lifecycle.load(artifact)
    stage_selected = []
    for stage in OperationalStage:
        match = next((_pick_prefix(item, stage) for item in development_items
                      if _pick_prefix(item, stage) is not None), None)
        if match is not None:
            stage_selected.append(match)
    numerical, scenarios, stage_counts = True, [], Counter()
    probability_shapes = {}
    deterministic = True
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
                                count=16, seed=20260813)
        repeated = loaded.sample(states[-1], values, lengths, observed=observed,
                                 count=16, seed=20260813)
        deterministic &= created == repeated
        scenarios.extend(created)
        stage_counts[node.operational_stage.value] += len(created)

    supports = {name: {"max_finite_minutes": bins.max_finite_minutes,
        "finite_last_index": bins.encode(bins.max_finite_minutes),
        "overflow_start_minutes": bins.max_finite_minutes + bins.bin_width_minutes,
        "overflow_index": bins.encode(bins.max_finite_minutes + bins.bin_width_minutes),
        "class_count": bins.class_count} for name, bins in pipeline.bins.items()}
    result = {
        "status": "PASS", "paper_result": False, "experiment": False,
        "cohort": {"train_episodes": len(train_selected),
                   "calibration_episodes": len(calibration_selected),
                   "development_stage_examples": len(stage_selected),
                   "train_dates": sorted({str(pair[0].episode_date) for pair in train_pairs}),
                   "calibration_dates": sorted({str(pair[0].episode_date) for pair in calibration_pairs}),
                   "development_dates": sorted({str(item[0][1].service_date) for item in stage_selected})},
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
        "raw_read_only": before == _source_stats(raw_paths),
        "source_files": list(before),
    }
    if len(scenarios) != 64 or not numerical or not deterministic or not result["raw_read_only"]:
        result["status"] = "FAIL"
    out = ROOT / "outputs" / "real_smoke" / "data2_m1_bounded_smoke_v2" / "metrics.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
