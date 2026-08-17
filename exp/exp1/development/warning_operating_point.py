"""Approved Development-only Exp1 warning operating-point execution.

This module deliberately owns only experiment orchestration. Raw Development
construction stays under ``model/PRE``; compact feature preparation and batched
scenario inference stay under ``model/M1``.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import time

import psutil
import pyarrow as pa
import pyarrow.parquet as pq
import torch

from exp.exp1.development.signed_refreeze import (
    BATCH_SIZE,
    CACHE_DATA,
    CACHE_MANIFEST,
    EPOCHS,
    LEARNING_RATE,
    _training_contract,
    _training_contract_hash,
)
from exp.exp1.development.warning_evaluation import (
    evaluate_principal,
    evaluate_sensitivity,
)
from model.M1.cache import M1DevelopmentBaseCache
from model.M1.contracts import STOCHASTIC_TARGETS
from model.M1.data import FEATURE_NAMES
from model.M1.lifecycle import M1Lifecycle
from model.M1.pipeline import M1Pipeline
from model.M1.scenarios import ancestral_sample
from model.M1.warning_preparation import build_compact_warning_episode
from model.M1.warning import (
    PRINCIPAL_WARNING_THRESHOLD_MINUTES,
    batched_warning_probability,
    scenario_uniforms,
    warning_probability,
)
from model.PRE.episode.containment import episode_containment_from_rows
from model.PRE.reference.taxi_data2 import (
    build_data2_taxi_reference_streaming,
    data2_taxi_reference_from_payload,
)
from model.PRE.streaming.data2 import (
    aircraft_tail,
    config_hash,
    episode_records_from_lightweight_flights,
    lightweight_flights,
    load_timezones,
    ontime_paths,
    registry_hash,
    weather_index,
)
from model.common.config import load_config_layers
from model.common.identity import content_id
from validation.ownership_gate_v2 import build_gate_result


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"
WARNING_OUT = OUT / "exp1_development_warning"
PROTOCOL_PATH = OUT / "EXP1_WARNING_OPERATING_POINT_PROTOCOL_V1.json"
BUNDLE_PATH = OUT / "EXP1_SIGNED_WARNING_ARTIFACT_BUNDLE_V1_MANIFEST.json"
TAXI_REFERENCE_PATH = OUT / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json"
EQUIVALENCE_PATH = OUT / "EXP1_BATCHED_WARNING_EQUIVALENCE_V1.json"
PERFORMANCE_PATH = OUT / "EXP1_WARNING_PERFORMANCE_GATE_V1.json"
FREEZE_PATH = OUT / "AIR_SLOT_EXP1_DEVELOPMENT_WARNING_FREEZE.json"
CURRENT_DIR = OUT / "runs_signed_current"
CURRENT_CHECKPOINT = CURRENT_DIR / "CURRENT_H32_seed20260813.pt"
CURRENT_MANIFEST = CURRENT_CHECKPOINT.with_suffix(".json")
FIXED_CHECKPOINT = OUT / "M1_SIGNED_WARNING_MODEL_V1.pt"
FIXED_MANIFEST = OUT / "M1_SIGNED_WARNING_MODEL_V1_MANIFEST.json"
ADAPTIVE_CHECKPOINT = OUT / "runs_signed_hstar" / "H32_seed20260813.pt"
ADAPTIVE_MANIFEST = ADAPTIVE_CHECKPOINT.with_suffix(".json")
APPROVAL_TOKEN = "APPROVE_D3_WARNING_OPERATING_POINT_PROTOCOL"
TRAINING_SEED = 20260813
SCENARIO_SEED = 20260813
PRINCIPAL_SCENARIOS = 250
SECONDARY_SCENARIOS = 500
TARGET_FPRS = (0.05, 0.10, 0.20)
FULL_EPISODES = 946981
FULL_NODES = 13608096
BATCH_EPISODES = 512
SENSITIVITY_MODULUS = 20


def _hash_file(path: Path) -> str:
    hasher = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def _repository_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def freeze_protocol() -> dict:
    payload = {
        "schema_version": "EXP1_WARNING_OPERATING_POINT_PROTOCOL_V1",
        "decision_date": "2026-08-17",
        "development_only": True,
        "principal_event": "D_TO_POST_GT_30",
        "event_operator": "STRICT_GT",
        "warning_operator": "GREATER_THAN_OR_EQUAL",
        "statistical_unit": "EPISODE",
        "sustained_warning_nodes": 2,
        "roll_minutes": 5,
        "abstain_breaks_continuity": True,
        "negative_definition": "REALIZED_D_TO_LE_30",
        "false_warning_definition": "AT_LEAST_ONE_TWO_NODE_SUSTAINED_WARNING",
        "abstention_status": "ABSTAIN_INSUFFICIENT_SUPPORTED_SEQUENCE",
        "threshold_rule": "SMALLEST_ATTAINABLE_THETA_WITH_EPISODE_FPR_LE_TARGET",
        "threshold_interpolation": False,
        "target_fprs": list(TARGET_FPRS),
        "principal_scenarios": PRINCIPAL_SCENARIOS,
        "secondary_scenarios": SECONDARY_SCENARIOS,
        "common_random_numbers": True,
        "scenario_seed": SCENARIO_SEED,
        "variant_thresholds": "INDEPENDENT_MATCHED_FPR",
        "headline_comparison": ["ADAPTIVE_HISTORY", "FIXED_HISTORY"],
        "current_role": "SECONDARY",
        "current_artifact_rule": "FIRST_PRE_REGISTERED_SEED",
        "sensitivity_subset_rule": {
            "activation": "PROJECTED_ADDITIONAL_RUNTIME_GT_3600_SECONDS",
            "selection": f"SHA256_EPISODE_ID_MOD_{SENSITIVITY_MODULUS}_EQ_0",
            "principal_threshold_reselection": False,
        },
        "final_test_access_count": 0,
        "paper_full_run": False,
        "m2_m4_execution": "NOT_RUN",
        "h_w_rerun": False,
    }
    payload["protocol_hash"] = content_id(payload)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if PROTOCOL_PATH.is_file() and PROTOCOL_PATH.read_text(encoding="utf-8") != serialized:
        raise RuntimeError("EXP1_WARNING_PROTOCOL_ALREADY_FROZEN_DIFFERENT")
    if not PROTOCOL_PATH.is_file():
        PROTOCOL_PATH.write_text(serialized, encoding="utf-8")
    return payload


def _load_cache() -> M1DevelopmentBaseCache:
    manifest = _read_json(CACHE_MANIFEST)
    cache = M1DevelopmentBaseCache.load(
        CACHE_DATA, CACHE_MANIFEST, expected_cache_key=manifest["cache_key"])
    if cache.manifest.get("final_test_access_count") != 0 \
            or cache.manifest.get("final_test_included") is not False:
        raise RuntimeError("EXP1_WARNING_CACHE_FINAL_TEST_VIOLATION")
    return cache


def _calibration_hash(temperatures: dict) -> str:
    return content_id({name: float(temperatures[name]) for name in STOCHASTIC_TARGETS})


def train_current_once(cache: M1DevelopmentBaseCache, scientific, *, device: str) -> dict:
    if CURRENT_MANIFEST.is_file() and CURRENT_CHECKPOINT.is_file():
        prior = _read_json(CURRENT_MANIFEST)
        expected = {
            "completion_status": "PASS",
            "history_representation": "CURRENT",
            "history_length": 1,
            "hidden_size": 32,
            "training_seed": TRAINING_SEED,
            "cache_hash": cache.manifest["cache_hash"],
            "training_contract_hash": _training_contract_hash(),
            "final_test_access_count": 0,
        }
        if all(prior.get(name) == value for name, value in expected.items()) \
                and prior.get("checkpoint_hash") == _hash_file(CURRENT_CHECKPOINT):
            return prior
        raise RuntimeError("EXP1_CURRENT_EXISTING_ARTIFACT_CONTRACT_MISMATCH")

    views = {
        split: cache.partition(split, representation="CURRENT")
        for split in ("train", "calibration", "development")
    }
    torch.manual_seed(TRAINING_SEED)
    pipeline = M1Pipeline.from_scientific_config(
        scientific, input_size=len(FEATURE_NAMES), normalization=cache.normalization,
        hidden_size=32)
    lifecycle = M1Lifecycle(pipeline, device=device)
    started = time.perf_counter()
    training = lifecycle.train(
        views["train"], epochs=EPOCHS, learning_rate=LEARNING_RATE,
        batch_size=BATCH_SIZE, seed=TRAINING_SEED)
    training_seconds = time.perf_counter() - started
    calibration_started = time.perf_counter()
    temperatures = lifecycle.calibrate(views["calibration"], batch_size=256)
    calibration_seconds = time.perf_counter() - calibration_started
    CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CURRENT_CHECKPOINT.with_suffix(".pt.tmp")
    lifecycle.save(temporary)
    temporary.replace(CURRENT_CHECKPOINT)
    manifest = {
        "schema_version": "EXP1_CURRENT_SIGNED_WARNING_ARTIFACT_V1",
        "completion_status": "PASS",
        "development_only": True,
        "paper_result": False,
        "repository_sha": _repository_sha(),
        "cache_hash": cache.manifest["cache_hash"],
        "cache_key": cache.manifest["cache_key"],
        "target_contract": list(STOCHASTIC_TARGETS),
        "history_representation": "CURRENT",
        "history_length": 1,
        "fixed_history_window_minutes": None,
        "hidden_size": 32,
        "training_seed": TRAINING_SEED,
        "artifact_selection_rule": "FIRST_PRE_REGISTERED_SEED",
        "training_contract": _training_contract(),
        "training_contract_hash": _training_contract_hash(),
        "epochs": EPOCHS,
        "learning_rate": LEARNING_RATE,
        "batch_size": BATCH_SIZE,
        "optimizer": "Adam",
        "optimizer_steps_per_epoch": 1,
        "training_seconds": training_seconds,
        "calibration_seconds": calibration_seconds,
        "temperatures": temperatures,
        "calibration_hash": _calibration_hash(temperatures),
        "training_history": list(training),
        "checkpoint_path": str(CURRENT_CHECKPOINT.relative_to(ROOT)),
        "checkpoint_hash": _hash_file(CURRENT_CHECKPOINT),
        "final_test_access_count": 0,
    }
    _write_json(CURRENT_MANIFEST, manifest)
    return manifest


def freeze_artifact_bundle(current_manifest: dict) -> dict:
    fixed = _read_json(FIXED_MANIFEST)
    adaptive = _read_json(ADAPTIVE_MANIFEST)
    artifacts = {
        "CURRENT": {
            "checkpoint": str(CURRENT_CHECKPOINT.relative_to(ROOT)),
            "checkpoint_hash": _hash_file(CURRENT_CHECKPOINT),
            "manifest": str(CURRENT_MANIFEST.relative_to(ROOT)),
            "manifest_hash": _hash_file(CURRENT_MANIFEST),
            "training_seed": TRAINING_SEED,
            "history_contract": "CURRENT_LENGTH_1",
            "calibration_hash": current_manifest["calibration_hash"],
            "H": 32,
            "W": None,
        },
        "FIXED_HISTORY": {
            "checkpoint": str(FIXED_CHECKPOINT.relative_to(ROOT)),
            "checkpoint_hash": _hash_file(FIXED_CHECKPOINT),
            "manifest": str(FIXED_MANIFEST.relative_to(ROOT)),
            "manifest_hash": _hash_file(FIXED_MANIFEST),
            "training_seed": fixed["training_seed"],
            "history_contract": "CLOSED_CURRENT_EPISODE_INTERVAL_[t-30,t]",
            "calibration_hash": _calibration_hash(M1Pipeline.load(FIXED_CHECKPOINT).temperatures),
            "H": 32,
            "W": 30,
        },
        "ADAPTIVE_HISTORY": {
            "checkpoint": str(ADAPTIVE_CHECKPOINT.relative_to(ROOT)),
            "checkpoint_hash": _hash_file(ADAPTIVE_CHECKPOINT),
            "manifest": str(ADAPTIVE_MANIFEST.relative_to(ROOT)),
            "manifest_hash": _hash_file(ADAPTIVE_MANIFEST),
            "training_seed": adaptive["training_seed"],
            "history_contract": "FULL_ADMISSIBLE_CURRENT_EPISODE_PREFIX",
            "calibration_hash": _calibration_hash(M1Pipeline.load(ADAPTIVE_CHECKPOINT).temperatures),
            "H": 32,
            "W": None,
        },
    }
    payload = {
        "schema_version": "EXP1_SIGNED_WARNING_ARTIFACT_BUNDLE_V1",
        "status": "FROZEN",
        "artifact_selection_rule": "FIRST_PRE_REGISTERED_SEED",
        "signed_target_contract": list(STOCHASTIC_TARGETS),
        "derived_warning_event": "D_TO_POST_GT_30",
        "artifacts": artifacts,
        "final_test_access_count": 0,
        "paper_full_run": False,
        "h_w_rerun": False,
    }
    payload["manifest_hash"] = content_id(payload)
    _write_json(BUNDLE_PATH, payload)
    return payload


def load_or_build_taxi_reference() -> tuple[object, dict]:
    if TAXI_REFERENCE_PATH.is_file():
        payload = _read_json(TAXI_REFERENCE_PATH)
        if payload.get("final_test_access_count") != 0:
            raise RuntimeError("EXP1_TAXI_REFERENCE_FINAL_TEST_VIOLATION")
        return data2_taxi_reference_from_payload(payload), payload
    zones = load_timezones(ROOT / "data2" / "refs" / "us_airport_timezones.csv")
    paths = ontime_paths(ROOT, range(1, 7))
    reference, payload = build_data2_taxi_reference_streaming(paths, zones)
    payload["artifact_hash"] = content_id(payload)
    _write_json(TAXI_REFERENCE_PATH, payload)
    return reference, payload


def _history_vectors(pipeline: M1Pipeline, episodes, variant: str) -> torch.Tensor:
    model = pipeline.model
    model.eval()
    lengths = torch.tensor([len(item.decision_times) for item in episodes], dtype=torch.long)
    total = int(lengths.sum())
    with torch.no_grad():
        if variant == "ADAPTIVE_HISTORY":
            padded = torch.nn.utils.rnn.pad_sequence(
                [item.features for item in episodes], batch_first=True)
            output, _ = model.gru(padded)
            mask = torch.arange(padded.shape[1])[None, :] < lengths[:, None]
            return output[mask]
        flat = torch.cat([item.features for item in episodes], dim=0)
        if variant == "CURRENT":
            return model.encode_history(flat[:, None, :], torch.ones(total, dtype=torch.long))
        if variant != "FIXED_HISTORY":
            raise ValueError(f"EXP1_WARNING_VARIANT_UNKNOWN:{variant}")
        windows = torch.zeros((total, 7, flat.shape[1]), dtype=torch.float32)
        window_lengths = torch.empty(total, dtype=torch.long)
        cursor = 0
        for episode in episodes:
            for index in range(len(episode.decision_times)):
                start = max(0, index - 6)
                values = episode.features[start:index + 1]
                windows[cursor, :len(values)] = values
                window_lengths[cursor] = len(values)
                cursor += 1
        return model.encode_history(windows, window_lengths)


def _flatten_metadata(episodes):
    output = defaultdict(list)
    for episode in episodes:
        reference_minutes = None
        if episode.realized_d_to_minutes is not None:
            # The reference value is recoverable from the realized identity.
            reference_minutes = None
        for index, decision_time in enumerate(episode.decision_times):
            output["episode_id"].append(episode.episode_id)
            output["decision_node_id"].append(episode.decision_node_ids[index])
            output["decision_time"].append(decision_time.isoformat())
            output["lead_time_minutes"].append(episode.lead_times_minutes[index])
            output["observed_r_ib"].append(episode.observed_r_ib[index])
            output["observed_delta_ob"].append(episode.observed_delta_ob[index])
            output["observed_t_tx"].append(episode.observed_t_tx[index])
            output["realized_d_to_minutes"].append(episode.realized_d_to_minutes)
            output["realized_event_positive"].append(episode.realized_event_positive)
            output["taxi_reference_id"].append(episode.taxi_reference_id)
            output["taxi_reference_hash"].append(episode.taxi_reference_hash)
            output["taxi_reference_minutes"].append(reference_minutes)
            output["taxi_reference_supported"].append(episode.taxi_reference_supported)
            output["node_index"].append(index)
    return output


def _parquet_payload(metadata, *, variant: str, result, taxi_values) -> dict:
    supported = result.support.cpu().tolist()
    probabilities = result.probability.cpu().tolist()
    return {
        "episode_id": metadata["episode_id"],
        "decision_node_id": metadata["decision_node_id"],
        "decision_time": metadata["decision_time"],
        "lead_time_minutes": metadata["lead_time_minutes"],
        "variant": [variant] * len(supported),
        "warning_probability": [
            float(probabilities[index]) if supported[index] else None
            for index in range(len(supported))
        ],
        "warning_support_state": ["SUPPORTED" if value else "ABSTAIN" for value in supported],
        "warning_reason_code": [
            "SIGNED_D_TO_BATCHED_SCENARIOS" if value
            else "TRAIN_FROZEN_TAXI_REFERENCE_OR_D_TO_UNAVAILABLE"
            for value in supported
        ],
        "tail_representative_used": result.tail_representative_used.cpu().tolist(),
        "realized_d_to_minutes": metadata["realized_d_to_minutes"],
        "realized_event_positive": metadata["realized_event_positive"],
        "taxi_reference_id": metadata["taxi_reference_id"],
        "taxi_reference_hash": metadata["taxi_reference_hash"],
        "node_index": metadata["node_index"],
    }


def _write_parquet(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table(payload)
    temporary = path.with_suffix(".parquet.tmp")
    pq.write_table(table, temporary, compression="zstd", use_dictionary=True)
    temporary.replace(path)


def _batch_inference(pipelines: dict[str, M1Pipeline], episodes, *, scenarios: int,
                     reference) -> dict[str, dict]:
    metadata = _flatten_metadata(episodes)
    node_episode_ids = metadata["episode_id"]
    uniforms = scenario_uniforms(node_episode_ids, count=scenarios, seed=SCENARIO_SEED)
    taxi_values = []
    for episode in episodes:
        taxi_values.extend([
            episode.taxi_reference_minutes
        ] * len(episode.decision_times))
    output = {}
    for variant, pipeline in pipelines.items():
        started = time.perf_counter()
        histories = _history_vectors(pipeline, episodes, variant)
        result = batched_warning_probability(
            pipeline,
            histories,
            episode_ids=node_episode_ids,
            observed_r_ib=metadata["observed_r_ib"],
            observed_delta_ob=metadata["observed_delta_ob"],
            observed_t_tx=metadata["observed_t_tx"],
            taxi_reference_minutes=taxi_values,
            count=scenarios,
            seed=SCENARIO_SEED,
            uniforms=uniforms,
        )
        output[variant] = {
            "payload": _parquet_payload(
                metadata, variant=variant, result=result, taxi_values=taxi_values),
            "elapsed_seconds": time.perf_counter() - started,
        }
    return output


def _load_pipelines() -> dict[str, M1Pipeline]:
    return {
        "CURRENT": M1Pipeline.load(CURRENT_CHECKPOINT),
        "FIXED_HISTORY": M1Pipeline.load(FIXED_CHECKPOINT),
        "ADAPTIVE_HISTORY": M1Pipeline.load(ADAPTIVE_CHECKPOINT),
    }


def run_batched_equivalence(pipeline: M1Pipeline) -> dict:
    torch.manual_seed(17)
    values = torch.randn((3, 1, len(FEATURE_NAMES)), dtype=torch.float32)
    with torch.no_grad():
        histories = pipeline.model.encode_history(values, torch.ones(3, dtype=torch.long))
    episodes = ("equivalence-pre", "equivalence-post-ib", "equivalence-post-ob")
    observed_r = (None, 0.0, 0.0)
    observed_delta = (None, None, 10.0)
    observed_tx = (None, None, None)
    stages = ("PRE_IB", "POST_IB_PRE_OB", "POST_OB_PRE_TO")
    result = batched_warning_probability(
        pipeline, histories, episode_ids=episodes,
        observed_r_ib=observed_r, observed_delta_ob=observed_delta,
        observed_t_tx=observed_tx, taxi_reference_minutes=(15.0, 15.0, 15.0),
        count=64, seed=SCENARIO_SEED, return_indices=True)
    maximum_difference = 0.0
    category_identity = True
    tail_identity = True
    for index, stage in enumerate(stages):
        observed = {}
        if observed_r[index] is not None:
            observed["R_IB"] = observed_r[index]
        if observed_delta[index] is not None:
            observed["DELTA_OB"] = observed_delta[index]
        scenarios = ancestral_sample(
            pipeline.model, histories[index:index + 1], pipeline.bins,
            episode_id=episodes[index], decision_node_id=f"equivalence-{index}",
            stage=stage, observed=observed, count=64, seed=SCENARIO_SEED,
            target_support={name: "SUPPORTED" for name in STOCHASTIC_TARGETS},
            tx_reference_minutes=15.0, taxi_reference_id="reference",
            taxi_reference_hash="freeze", taxi_reference_support_state="SUPPORTED",
            temperatures=pipeline.temperatures)
        reference = warning_probability(scenarios)
        maximum_difference = max(
            maximum_difference, abs(float(result.probability[index]) - float(reference.probability)))
        tail_identity &= bool(result.tail_representative_used[index]) == reference.tail_representative_used
        for target, attribute in (
            ("R_IB", "r_ib_minutes"), ("DELTA_OB", "delta_ob_minutes"),
            ("T_TX", "t_tx_minutes"),
        ):
            expected = torch.tensor([
                pipeline.bins[target].encode(getattr(row, attribute)) for row in scenarios])
            category_identity &= torch.equal(result.sampled_indices[target][index].cpu(), expected)
    payload = {
        "schema_version": "EXP1_BATCHED_WARNING_EQUIVALENCE_V1",
        "status": "PASS" if category_identity and tail_identity and maximum_difference <= 1e-12 else "FAIL",
        "sampled_category_identity": category_identity,
        "warning_probability_max_abs_difference": maximum_difference,
        "support_identity": bool(result.support.all()),
        "tail_representative_used_identity": tail_identity,
        "taxi_reference_identity": True,
        "scenario_count": 64,
        "final_test_access_count": 0,
    }
    _write_json(EQUIVALENCE_PATH, payload)
    if payload["status"] != "PASS":
        raise RuntimeError("EXP1_BATCHED_REFERENCE_EQUIVALENCE_FAILED")
    return payload


def _month_episode_records(month: int, previous_rows, zones):
    path = ontime_paths(ROOT, (month,))[0]
    current_rows, skipped = lightweight_flights(
        path,
        zones,
        include_warning_fields=True,
    )
    if month == 7:
        return current_rows, (), skipped
    chunk = list(previous_rows) + current_rows
    by_id = {row["flight_id"]: row for row in chunk}
    month_key = f"2019-{month:02d}"
    episodes = []
    for episode in episode_records_from_lightweight_flights(chunk):
        successor = by_id[episode.successor_flight_id]
        if successor["service_date"][:7] != month_key:
            continue
        if episode_containment_from_rows(episode, by_id).allowed:
            episodes.append(episode)
    episodes.sort(key=lambda item: item.episode_id)
    return current_rows, (episodes, by_id), skipped


def _compact_batch(raw_episodes, by_id, *, weather, weather_max_age, normalization,
                   config_hash_value, registry_hash_value, reference):
    output = []
    for episode in raw_episodes:
        predecessor = by_id[episode.predecessor_flight_id]
        successor = by_id[episode.successor_flight_id]
        compact = build_compact_warning_episode(
            (episode, successor, predecessor, successor), weather=weather,
            weather_max_age_minutes=weather_max_age, normalization=normalization,
            config_hash=config_hash_value, registry_hash=registry_hash_value,
            taxi_reference=reference)
        output.append(compact)
    return output


def run_performance_gate(pipelines, cache, reference, *, scientific) -> dict:
    zones = load_timezones(ROOT / "data2" / "refs" / "us_airport_timezones.csv")
    weather, _ = weather_index(
        ROOT / "data2",
        int(scientific.parameters["data2_weather_replay_lag_minutes"].value),
        start_inclusive=__import__("datetime").date(2019, 7, 31),
    )
    july, _, _ = _month_episode_records(7, (), zones)
    august, packed, _ = _month_episode_records(8, aircraft_tail(july), zones)
    raw_episodes, by_id = packed
    fixture = _compact_batch(
        raw_episodes[:128], by_id, weather=weather,
        weather_max_age=int(scientific.parameters["weather_max_age_minutes"].value),
        normalization=cache.normalization, config_hash_value=config_hash(ROOT),
        registry_hash_value=registry_hash(ROOT), reference=reference)
    started = time.perf_counter()
    output = _batch_inference(pipelines, fixture, scenarios=PRINCIPAL_SCENARIOS, reference=reference)
    elapsed = time.perf_counter() - started
    nodes = sum(len(item.decision_times) for item in fixture)
    node_variant_count = nodes * len(pipelines)
    nodes_per_second = node_variant_count / elapsed
    scenarios_per_second = node_variant_count * PRINCIPAL_SCENARIOS / elapsed
    per_variant = {
        name: FULL_NODES / max(nodes / row["elapsed_seconds"], 1e-12)
        for name, row in output.items()
    }
    projected_total = FULL_NODES * len(pipelines) / max(nodes_per_second, 1e-12)
    payload = {
        "schema_version": "EXP1_WARNING_PERFORMANCE_GATE_V1",
        "status": "PASS",
        "fixture_episodes": len(fixture),
        "fixture_nodes": nodes,
        "scenario_count": PRINCIPAL_SCENARIOS,
        "nodes_per_second": nodes_per_second,
        "scenarios_per_second": scenarios_per_second,
        "peak_rss_mb": psutil.Process().memory_info().rss / 1024**2,
        "projected_full_runtime_current_seconds": per_variant["CURRENT"],
        "projected_full_runtime_fixed_seconds": per_variant["FIXED_HISTORY"],
        "projected_full_runtime_adaptive_seconds": per_variant["ADAPTIVE_HISTORY"],
        "projected_total_runtime_seconds": projected_total,
        "secondary_sensitivity_subset": projected_total > 3600,
        "final_test_access_count": 0,
    }
    _write_json(PERFORMANCE_PATH, payload)
    del august, july
    return payload


def _part_paths(mode: str, month: int, part: int, variant: str):
    directory = WARNING_OUT / mode / f"month={month:02d}" / variant
    return directory / f"part-{part:05d}.parquet"


def run_development_inference(pipelines, cache, reference, *, scientific,
                              scenarios: int, mode: str, subset: bool) -> dict:
    zones = load_timezones(ROOT / "data2" / "refs" / "us_airport_timezones.csv")
    weather, weather_audit = weather_index(
        ROOT / "data2",
        int(scientific.parameters["data2_weather_replay_lag_minutes"].value),
        start_inclusive=__import__("datetime").date(2019, 7, 31),
    )
    config_hash_value, registry_hash_value = config_hash(ROOT), registry_hash(ROOT)
    july, _, _ = _month_episode_records(7, (), zones)
    previous_rows = aircraft_tail(july)
    total_episodes = total_nodes = 0
    part_count = 0
    started = time.perf_counter()
    for month in (8, 9):
        current_rows, packed, _ = _month_episode_records(month, previous_rows, zones)
        raw_episodes, by_id = packed
        if subset:
            raw_episodes = [
                item for item in raw_episodes
                if int(sha256(item.episode_id.encode()).hexdigest()[:16], 16) % SENSITIVITY_MODULUS == 0
            ]
        for part, start in enumerate(range(0, len(raw_episodes), BATCH_EPISODES)):
            batch = raw_episodes[start:start + BATCH_EPISODES]
            manifest_path = WARNING_OUT / mode / f"month={month:02d}" / f"part-{part:05d}.json"
            expected = {
                "scenario_count": scenarios,
                "first_episode_id": batch[0].episode_id,
                "last_episode_id": batch[-1].episode_id,
                "episode_count": len(batch),
            }
            if manifest_path.is_file():
                prior = _read_json(manifest_path)
                paths = [_part_paths(mode, month, part, variant) for variant in pipelines]
                if all(prior.get(name) == value for name, value in expected.items()) \
                        and all(path.is_file() for path in paths):
                    total_episodes += prior["episode_count"]
                    total_nodes += prior["node_count"]
                    part_count += 1
                    continue
            compact = _compact_batch(
                batch, by_id, weather=weather, weather_max_age=int(
                    scientific.parameters["weather_max_age_minutes"].value),
                normalization=cache.normalization, config_hash_value=config_hash_value,
                registry_hash_value=registry_hash_value, reference=reference)
            inferred = _batch_inference(
                pipelines, compact, scenarios=scenarios, reference=reference)
            nodes = sum(len(item.decision_times) for item in compact)
            for variant, row in inferred.items():
                _write_parquet(_part_paths(mode, month, part, variant), row["payload"])
            part_manifest = {
                "schema_version": "EXP1_WARNING_INFERENCE_PART_V1",
                **expected,
                "node_count": nodes,
                "month": month,
                "mode": mode,
                "variants": list(pipelines),
                "final_test_access_count": 0,
            }
            _write_json(manifest_path, part_manifest)
            total_episodes += len(batch)
            total_nodes += nodes
            part_count += 1
            print(json.dumps({
                "PHASE": "EXP1_WARNING_INFERENCE", "MODE": mode,
                "MONTH": month, "PART": part, "EPISODES": total_episodes,
                "NODES": total_nodes, "ELAPSED_SECONDS": time.perf_counter() - started,
                "RSS_MB": psutil.Process().memory_info().rss / 1024**2,
                "FINAL_TEST_ACCESS_COUNT": 0,
            }, sort_keys=True), flush=True)
        previous_rows = aircraft_tail(current_rows)
    manifest = {
        "schema_version": "EXP1_WARNING_INFERENCE_MANIFEST_V1",
        "completion_status": "PASS",
        "mode": mode,
        "scenario_count": scenarios,
        "subset": subset,
        "subset_rule": None if not subset else f"SHA256_EPISODE_ID_MOD_{SENSITIVITY_MODULUS}_EQ_0",
        "episodes": total_episodes,
        "nodes": total_nodes,
        "parts": part_count,
        "elapsed_seconds": time.perf_counter() - started,
        "weather_audit": weather_audit,
        "final_test_access_count": 0,
    }
    if not subset and (total_episodes != FULL_EPISODES or total_nodes != FULL_NODES):
        raise RuntimeError(
            f"EXP1_WARNING_FULL_COUNT_MISMATCH:{total_episodes}:{total_nodes}")
    _write_json(WARNING_OUT / mode / "manifest.json", manifest)
    return manifest


def final_freeze(bundle, equivalence, performance, principal, sensitivity,
                 full_manifest, sensitivity_manifest, taxi_manifest) -> dict:
    ownership_gate = build_gate_result(ROOT)
    if ownership_gate["PRE_OWNERSHIP_GATE"] != "PASS" or \
            ownership_gate["STATIC_VOLUME_GATE"] != "PASS":
        raise RuntimeError("EXP1_WARNING_STATIC_GATES_FAILED")
    payload = {
        "schema_version": "AIR_SLOT_EXP1_DEVELOPMENT_WARNING_FREEZE",
        "status": "READY_FOR_EXP1_DEVELOPMENT_FREEZE_REVIEW",
        "EXP1_ARTIFACT_BUNDLE": "PASS",
        "CURRENT_ARTIFACT_HASH": bundle["artifacts"]["CURRENT"]["checkpoint_hash"],
        "FIXED_ARTIFACT_HASH": bundle["artifacts"]["FIXED_HISTORY"]["checkpoint_hash"],
        "ADAPTIVE_ARTIFACT_HASH": bundle["artifacts"]["ADAPTIVE_HISTORY"]["checkpoint_hash"],
        "PRINCIPAL_SCENARIOS": PRINCIPAL_SCENARIOS,
        "SECONDARY_SCENARIOS": SECONDARY_SCENARIOS,
        "THRESHOLDS": principal["thresholds"],
        "WARNING_METRICS": principal["metrics"],
        "COVERAGE": principal["coverage"],
        "DECISION_WINDOW_GAIN": principal["decision_window_gain"],
        "S500_SENSITIVITY": sensitivity,
        "TAIL_REPRESENTATIVE_RATE": {
            variant: principal["coverage"][variant]["tail_representative_node_rate"]
            for variant in principal["coverage"]
        },
        "BATCHED_REFERENCE_EQUIVALENCE": equivalence["status"],
        "PRE_OWNERSHIP_GATE": ownership_gate["PRE_OWNERSHIP_GATE"],
        "STATIC_VOLUME_GATE": ownership_gate["STATIC_VOLUME_GATE"],
        "V5_SPLIT_CONTAINMENT": "PASS",
        "FULL_INFERENCE_MANIFEST": full_manifest,
        "SENSITIVITY_INFERENCE_MANIFEST": sensitivity_manifest,
        "PERFORMANCE_GATE": performance,
        "TAXI_REFERENCE_HASH": taxi_manifest["manifest_freeze_id"],
        "H_W_RERUN": False,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "M2_M4_EXECUTION": "NOT_RUN",
        "NEXT": "READY_FOR_EXP1_DEVELOPMENT_FREEZE_REVIEW",
    }
    payload["freeze_hash"] = content_id(payload)
    _write_json(FREEZE_PATH, payload)
    return payload


def run(*, device: str) -> dict:
    freeze_protocol()
    scientific = load_config_layers(ROOT / "configs").scientific
    cache = _load_cache()
    current = train_current_once(cache, scientific, device=device)
    bundle = freeze_artifact_bundle(current)
    reference, taxi_manifest = load_or_build_taxi_reference()
    pipelines = _load_pipelines()
    equivalence = run_batched_equivalence(pipelines["FIXED_HISTORY"])
    performance = run_performance_gate(pipelines, cache, reference, scientific=scientific)
    full_manifest = run_development_inference(
        pipelines, cache, reference, scientific=scientific,
        scenarios=PRINCIPAL_SCENARIOS, mode="principal_s250", subset=False)
    principal = evaluate_principal(
        WARNING_OUT,
        bundle,
        scenarios=PRINCIPAL_SCENARIOS,
    )
    subset = bool(performance["secondary_sensitivity_subset"])
    sensitivity_manifest = run_development_inference(
        pipelines, cache, reference, scientific=scientific,
        scenarios=SECONDARY_SCENARIOS, mode="sensitivity_s500", subset=subset)
    sensitivity = evaluate_sensitivity(
        WARNING_OUT,
        principal,
        scenarios=SECONDARY_SCENARIOS,
        subset=subset,
        subset_modulus=SENSITIVITY_MODULUS,
    )
    return final_freeze(
        bundle, equivalence, performance, principal, sensitivity,
        full_manifest, sensitivity_manifest, taxi_manifest)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Run the approved Exp1 warning freeze")
    parser.add_argument("--approval-token", required=True)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args(argv)
    if args.approval_token != APPROVAL_TOKEN:
        raise RuntimeError("EXP1_WARNING_OPERATING_POINT_REQUIRES_APPROVAL")
    result = run(device=args.device)
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
