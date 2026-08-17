from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from datetime import date
from pathlib import Path

import psutil
import torch
import yaml

from model.common.config import load_config_layers
from model.common.identity import content_id
from model.M1.cache import M1DevelopmentBaseCache
from model.M1.data import FEATURE_NAMES
from model.M1.lifecycle import M1Lifecycle
from model.M1.pipeline import M1Pipeline
from exp.exp1.development.hstar import (
    APPROVED_CACHE_HASH,
    BASE_CACHE_DATA,
    BASE_CACHE_MANIFEST,
    BATCH_SIZE,
    EPOCHS,
    LEARNING_RATE,
    OUT,
    ROOT,
    TRAINING_SEEDS,
    _contract_hashes,
    _hash_file,
    _peak_rss_mb,
    _repository_sha,
    _scientific_config_hash,
    _training_contract_hash,
    _training_contract_payload,
    evaluate,
)


H_STAR = 32
CANDIDATE_WINDOWS = (30, 60, 120, 180)
SECONDARY_TRAINING_SEEDS = TRAINING_SEEDS[:3]
SEED_DERIVATION = "first three seeds from the frozen V5 principal training-seed sequence"
APPROVAL_TOKEN = "APPROVE_H_STAR_32"
H_EVIDENCE_PATH = OUT / "m1_hstar_evidence.json"
W_EVIDENCE_PATH = OUT / "m1_wstar_evidence.json"
W_RUNS_DIR = OUT / "runs_wstar"
FINAL_TEST_START = date(2019, 10, 1)


def _load_exp1_config() -> dict:
    path = ROOT / "configs" / "evaluation" / "exp1.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _validate_h_freeze(scientific) -> dict:
    selected = scientific.parameters["m1_hidden_size"]
    if selected.freeze_state.value != "FROZEN" or selected.value != H_STAR:
        raise RuntimeError("W_SELECTION_H_STAR_NOT_FROZEN_AT_32")
    provenance = selected.provenance or {}
    if provenance.get("decision_id") != "D2_H_STAR":
        raise RuntimeError("W_SELECTION_H_STAR_DECISION_PROVENANCE_MISMATCH")
    if provenance.get("final_test_access_count") != 0:
        raise RuntimeError("W_SELECTION_H_STAR_FINAL_TEST_ACCESS_NONZERO")

    exp1 = _load_exp1_config()
    if tuple(exp1.get("fixed_history_windows_minutes", ())) != CANDIDATE_WINDOWS:
        raise RuntimeError("W_SELECTION_CANDIDATE_WINDOWS_CHANGED")
    if tuple(scientific.parameters["m1_hidden_size_candidates"].value) != (16, 32):
        raise RuntimeError("W_SELECTION_H_CANDIDATE_CONTRACT_CHANGED")

    evidence = json.loads(H_EVIDENCE_PATH.read_text(encoding="utf-8"))
    expected_evidence_hash = evidence.get("evidence_hash")
    unhashed = {name: value for name, value in evidence.items() if name != "evidence_hash"}
    if expected_evidence_hash != content_id(unhashed):
        raise RuntimeError("W_SELECTION_H_EVIDENCE_HASH_MISMATCH")
    required = {
        "decision_id": "D2_H_STAR",
        "codex_recommendation": H_STAR,
        "cache_rebuilds": 0,
        "final_test_access_count": 0,
    }
    if any(evidence.get(name) != value for name, value in required.items()):
        raise RuntimeError("W_SELECTION_H_EVIDENCE_CONTRACT_MISMATCH")
    if any(row.get("cache_hash") != APPROVED_CACHE_HASH for row in evidence["per_seed"]):
        raise RuntimeError("W_SELECTION_H_EVIDENCE_CACHE_MISMATCH")
    return evidence


def _load_immutable_cache() -> M1DevelopmentBaseCache:
    if not BASE_CACHE_DATA.is_file() or not BASE_CACHE_MANIFEST.is_file():
        raise RuntimeError("W_SELECTION_BASE_CACHE_MISSING_REBUILD_NOT_AUTHORIZED")
    manifest = json.loads(BASE_CACHE_MANIFEST.read_text(encoding="utf-8"))
    started = time.perf_counter()
    cache = M1DevelopmentBaseCache.load(
        BASE_CACHE_DATA, BASE_CACHE_MANIFEST,
        expected_cache_key=manifest["cache_key"],
    )
    print(json.dumps({
        "PHASE": "M1_BASE_CACHE_LOAD",
        "CACHE": "HIT",
        "ELAPSED_SECONDS": time.perf_counter() - started,
        "RAW_DATA_READS": 0,
        "CACHE_REBUILDS": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
    }, sort_keys=True), flush=True)
    return cache


def _model_code_hashes() -> dict[str, str]:
    relative_paths = (
        "exp/exp1/history.py",
        "model/M1/cache.py",
        "model/M1/lifecycle.py",
        "model/M1/pipeline.py",
        "model/M1/network.py",
        "model/M1/loss.py",
        "model/M1/calibration.py",
    )
    return {name: _hash_file(ROOT / name) for name in relative_paths}


def _w_selection_contract_hash(scientific_config_hash: str, h_evidence: dict) -> str:
    return content_id({
        "scientific_config_hash": scientific_config_hash,
        "exp1_config_hash": _hash_file(ROOT / "configs" / "evaluation" / "exp1.yaml"),
        "model_code_hashes": _model_code_hashes(),
        "h_decision_id": "D2_H_STAR",
        "h_star": H_STAR,
        "h_evidence_hash": h_evidence["evidence_hash"],
        "candidate_windows_minutes": CANDIDATE_WINDOWS,
        "secondary_training_seeds": SECONDARY_TRAINING_SEEDS,
        "seed_derivation": SEED_DERIVATION,
        "history_representation": "FIXED_HISTORY",
        "history_boundary": "CLOSED_CURRENT_EPISODE_INTERVAL_[t-W,t]",
        "training_contract_hash": _training_contract_hash(),
        "selection_metric": "episode-balanced Development joint NLL",
        "practical_equivalence_threshold": 0.005,
    })


def _validate_cache_for_w(cache, scientific, h_evidence: dict) -> dict:
    manifest = cache.manifest
    if manifest.get("cache_hash") != APPROVED_CACHE_HASH:
        raise RuntimeError("W_SELECTION_CACHE_HASH_MISMATCH")
    if manifest.get("feature_count") != len(FEATURE_NAMES):
        raise RuntimeError("W_SELECTION_FEATURE_COUNT_MISMATCH")
    if manifest.get("final_test_included") is not False:
        raise RuntimeError("W_SELECTION_FINAL_TEST_INCLUDED")
    if manifest.get("final_test_access_count") != 0:
        raise RuntimeError("W_SELECTION_FINAL_TEST_ACCESS_NONZERO")
    if cache.normalization.fitted_split != "train":
        raise RuntimeError("W_SELECTION_NORMALIZATION_SPLIT_MISMATCH")
    if cache.audit.get("config_hash") != h_evidence["data_audit"].get("config_hash"):
        raise RuntimeError("W_SELECTION_CACHE_BUILD_CONFIG_LINEAGE_MISMATCH")

    contracts = _contract_hashes(scientific)
    for name, expected in contracts.items():
        if manifest.get("contract_hashes", {}).get(name) != expected:
            raise RuntimeError(f"W_SELECTION_CONTRACT_HASH_MISMATCH:{name}")

    partition_hashes = cache.audit.get("partition_hashes", {})
    for split in ("train", "calibration", "development"):
        dataset = cache.partition(split)
        observed = content_id(sorted({row.episode_id for row in dataset}))
        if partition_hashes.get(split) != observed:
            raise RuntimeError(f"W_SELECTION_EPISODE_IDS_MISMATCH:{split}")
        if any(row.episode_date >= FINAL_TEST_START for row in dataset):
            raise RuntimeError(f"W_SELECTION_FINAL_TEST_DATE:{split}")
    if set(cache.store.sample_splits) - {"train", "calibration", "development"}:
        raise RuntimeError("W_SELECTION_SPLIT_MISMATCH")

    scientific_config_hash = _scientific_config_hash()
    return {
        "cache_hash": manifest["cache_hash"],
        "cache_key": manifest["cache_key"],
        "feature_count": manifest["feature_count"],
        "base_cache_build_config_hash": cache.audit["config_hash"],
        "scientific_config_hash": scientific_config_hash,
        "training_contract_hash": _training_contract_hash(),
        "w_selection_contract_hash": _w_selection_contract_hash(
            scientific_config_hash, h_evidence),
        "final_test_access_count": 0,
        "cache_rebuilds": 0,
    }


def _view_summary(dataset) -> dict:
    lengths = [int(row.values.shape[0]) for row in dataset]
    return {
        "sample_count": len(lengths),
        "min_nodes": min(lengths),
        "max_nodes": max(lengths),
        "mean_nodes": statistics.mean(lengths),
        "identity_and_length_hash": content_id([
            [row.episode_id, row.decision_node_id, length]
            for row, length in zip(dataset, lengths)
        ]),
    }


def _fixed_views(cache, window_minutes: int):
    views = {
        split: cache.partition(
            split, representation="FIXED_HISTORY", window_minutes=window_minutes)
        for split in ("train", "calibration", "development")
    }
    maximum_nodes = window_minutes // 5 + 1
    for split, dataset in views.items():
        if any(not 1 <= row.values.shape[0] <= maximum_nodes for row in dataset):
            raise RuntimeError(f"W_SELECTION_FIXED_HISTORY_BOUNDARY_FAILED:{split}")
    return views


def _run_paths(window_minutes: int, seed: int) -> tuple[Path, Path]:
    stem = f"W{window_minutes}_H{H_STAR}_seed{seed}"
    return W_RUNS_DIR / f"{stem}.pt", W_RUNS_DIR / f"{stem}.json"


def _validate_resume(manifest: dict, checkpoint_path: Path, validation: dict,
                     window_minutes: int, seed: int) -> tuple[bool, str]:
    required = {
        "completion_status": "PASS",
        "cache_hash": validation["cache_hash"],
        "scientific_config_hash": validation["scientific_config_hash"],
        "training_contract_hash": validation["training_contract_hash"],
        "w_selection_contract_hash": validation["w_selection_contract_hash"],
        "history_representation": "FIXED_HISTORY",
        "fixed_history_window_minutes": window_minutes,
        "hidden_size": H_STAR,
        "training_seed": seed,
        "epochs": EPOCHS,
        "learning_rate": LEARNING_RATE,
        "batch_size": BATCH_SIZE,
        "optimizer": "Adam",
        "optimizer_steps_per_epoch": 1,
        "cache_rebuilds": 0,
        "final_test_access_count": 0,
    }
    if any(manifest.get(name) != value for name, value in required.items()):
        return False, "manifest_contract_mismatch"
    if not checkpoint_path.is_file():
        return False, "checkpoint_missing"
    if manifest.get("checkpoint_hash") != _hash_file(checkpoint_path):
        return False, "checkpoint_hash_mismatch"
    return True, "validated"


def _run_candidate(scientific, cache, h_evidence: dict, *, window_minutes: int,
                   seed: int, device: str, resume: bool) -> dict:
    validation = _validate_cache_for_w(cache, scientific, h_evidence)
    checkpoint_path, manifest_path = _run_paths(window_minutes, seed)
    if resume and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        valid, reason = _validate_resume(
            manifest, checkpoint_path, validation, window_minutes, seed)
        if valid:
            print(json.dumps({
                "PHASE": "M1_W_TRAIN",
                "W": window_minutes,
                "H": H_STAR,
                "SEED": seed,
                "CACHE": "HIT",
                "RESUME": "SKIP_COMPLETED",
                "VALIDATION": reason,
            }, sort_keys=True), flush=True)
            return manifest

    views = _fixed_views(cache, window_minutes)
    view_summaries = {name: _view_summary(dataset) for name, dataset in views.items()}
    torch.manual_seed(seed)
    pipeline = M1Pipeline.from_scientific_config(
        scientific, input_size=len(FEATURE_NAMES), normalization=cache.normalization,
        hidden_size=H_STAR)
    lifecycle = M1Lifecycle(pipeline, device=device)
    run_started = time.perf_counter()
    process_cpu_started = time.process_time()
    training_started = time.perf_counter()

    def progress(row):
        elapsed = time.perf_counter() - training_started
        eta = elapsed / row["epoch"] * (EPOCHS - row["epoch"])
        print(json.dumps({
            "TIMESTAMP": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "PHASE": "M1_W_TRAIN",
            "W": window_minutes,
            "H": H_STAR,
            "SEED": seed,
            "EPOCH": row["epoch"],
            "TRAIN_LOSS": row["loss"],
            "ELAPSED_SECONDS": elapsed,
            "ETA_SECONDS": eta,
            "RSS_MB": _peak_rss_mb(),
            "DEVICE": str(lifecycle.device),
        }, sort_keys=True), flush=True)

    history = lifecycle.train(
        views["train"], epochs=EPOCHS, learning_rate=LEARNING_RATE,
        batch_size=BATCH_SIZE, seed=seed, progress_callback=progress)
    training_seconds = time.perf_counter() - training_started
    calibration_started = time.perf_counter()
    temperatures = lifecycle.calibrate(views["calibration"], batch_size=256)
    calibration_seconds = time.perf_counter() - calibration_started
    metrics = evaluate(lifecycle, views["development"])

    if not all(math.isfinite(float(row["loss"])) for row in history):
        raise RuntimeError(f"W_SELECTION_NONFINITE_LOSS:W{window_minutes}:SEED{seed}")
    if any(not math.isfinite(float(value)) for value in temperatures.values()):
        raise RuntimeError(f"W_SELECTION_NONFINITE_TEMPERATURE:W{window_minutes}:SEED{seed}")
    if not math.isfinite(float(metrics["episode_balanced_joint_nll"])):
        raise RuntimeError(f"W_SELECTION_NONFINITE_METRIC:W{window_minutes}:SEED{seed}")

    process_cpu_seconds = time.process_time() - process_cpu_started
    run_wall_seconds = time.perf_counter() - run_started
    logical_cores = max(psutil.cpu_count(logical=True) or 1, 1)
    average_cpu = process_cpu_seconds / max(run_wall_seconds, 1e-12) \
        / logical_cores * 100.0
    W_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    temporary_checkpoint = checkpoint_path.with_suffix(".pt.tmp")
    lifecycle.save(temporary_checkpoint)
    temporary_checkpoint.replace(checkpoint_path)
    checkpoint_hash = _hash_file(checkpoint_path)
    manifest = {
        "completion_status": "PASS",
        "development_only": True,
        "paper_result": False,
        "repository_sha": _repository_sha(),
        **validation,
        "h_decision_id": "D2_H_STAR",
        "h_evidence_hash": h_evidence["evidence_hash"],
        "history_representation": "FIXED_HISTORY",
        "history_boundary": "CLOSED_CURRENT_EPISODE_INTERVAL_[t-W,t]",
        "fixed_history_window_minutes": window_minutes,
        "hidden_size": H_STAR,
        "training_seed": seed,
        "seed_derivation": SEED_DERIVATION,
        "epochs": EPOCHS,
        "learning_rate": LEARNING_RATE,
        "batch_size": BATCH_SIZE,
        "optimizer": "Adam",
        "optimizer_steps_per_epoch": 1,
        "training_contract": _training_contract_payload(),
        "training_seconds": training_seconds,
        "seconds_per_epoch": training_seconds / EPOCHS,
        "calibration_status": "PASS",
        "calibration_seconds": calibration_seconds,
        "temperatures": temperatures,
        "training_history": list(history),
        "view_summaries": view_summaries,
        "parameter_count": sum(parameter.numel() for parameter in pipeline.model.parameters()),
        "device": str(lifecycle.device),
        "thread_config": {
            "torch_intra_op": torch.get_num_threads(),
            "torch_inter_op": torch.get_num_interop_threads(),
        },
        "peak_rss_mb": _peak_rss_mb(),
        "run_wall_seconds": run_wall_seconds,
        "process_cpu_seconds": process_cpu_seconds,
        "average_cpu_utilization_percent": average_cpu,
        "checkpoint_hash": checkpoint_hash,
        "checkpoint_path": str(checkpoint_path.relative_to(ROOT)),
        "raw_data_reads": 0,
        "cache_rebuilds": 0,
        "final_test_access_count": 0,
        **metrics,
    }
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    temporary_manifest.replace(manifest_path)
    print(json.dumps({
        "PHASE": "M1_W_TRAIN_COMPLETE",
        "W": window_minutes,
        "H": H_STAR,
        "SEED": seed,
        "DEVELOPMENT_JOINT_NLL": metrics["episode_balanced_joint_nll"],
        "TRAIN_SECONDS": training_seconds,
        "CALIBRATION_SECONDS": calibration_seconds,
        "INFERENCE_SECONDS": metrics["inference_seconds"],
        "CACHE_REBUILDS": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
    }, sort_keys=True), flush=True)
    return manifest


def recommend_window(candidate_means: dict[int, float]) -> tuple[int, int, dict[int, float], dict[int, bool]]:
    best_raw = min(candidate_means, key=lambda window: (candidate_means[window], window))
    best_score = candidate_means[best_raw]
    relative = {
        window: (score - best_score) / best_score
        for window, score in candidate_means.items()
    }
    equivalent = {window: difference <= 0.005 for window, difference in relative.items()}
    recommendation = min(window for window, value in equivalent.items() if value)
    return best_raw, recommendation, relative, equivalent


def _write_w_evidence(cache, h_evidence: dict, rows: list[dict]) -> dict:
    candidates = {}
    means = {}
    for window in CANDIDATE_WINDOWS:
        selected = [row for row in rows if row["fixed_history_window_minutes"] == window]
        scores = [row["episode_balanced_joint_nll"] for row in selected]
        means[window] = statistics.mean(scores)
        candidates[str(window)] = {
            "mean_joint_nll": means[window],
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
    best_raw, recommendation, relative, equivalent = recommend_window(means)
    per_run = [{
        "W": row["fixed_history_window_minutes"],
        "H": row["hidden_size"],
        "seed": row["training_seed"],
        "joint_nll": row["episode_balanced_joint_nll"],
        "target_nll": row["episode_balanced_target_nll"],
        "calibration_status": row["calibration_status"],
        "calibration_temperatures": row["temperatures"],
        "calibration_ece": row["calibration_ece"],
        "train_seconds": row["training_seconds"],
        "inference_seconds": row["inference_seconds"],
        "checkpoint_hash": row["checkpoint_hash"],
        "manifest_path": str(_run_paths(
            row["fixed_history_window_minutes"], row["training_seed"])[1].relative_to(ROOT)),
    } for row in rows]
    validation = _validate_cache_for_w(cache, load_config_layers(ROOT / "configs").scientific,
                                       h_evidence)
    evidence = {
        "status": "HUMAN_DECISION_REQUIRED",
        "decision_id": "D1_W_STAR",
        "development_only": True,
        "paper_result": False,
        "repository_sha": _repository_sha(),
        "h_star": H_STAR,
        "h_decision_id": "D2_H_STAR",
        "h_evidence_hash": h_evidence["evidence_hash"],
        "candidate_windows": list(CANDIDATE_WINDOWS),
        "seed_list": list(SECONDARY_TRAINING_SEEDS),
        "seed_derivation": SEED_DERIVATION,
        "history_representation": "FIXED_HISTORY",
        "history_boundary": "CLOSED_CURRENT_EPISODE_INTERVAL_[t-W,t]",
        "selection_metric": "episode-balanced Development joint NLL",
        "practical_equivalence_threshold": 0.005,
        "per_run": per_run,
        "per_candidate": candidates,
        "best_raw_W": best_raw,
        "relative_difference_to_best": {str(key): value for key, value in relative.items()},
        "within_0_5_percent_equivalence": {
            str(key): value for key, value in equivalent.items()},
        "codex_recommendation": recommendation,
        "scientific_reason": (
            "Recommend the shortest fixed-history horizon within 0.5% relative "
            "Development joint NLL of the raw best candidate."),
        "computational_reason": (
            "Shorter equivalent histories reduce retained stale context and sequence length; "
            "runtime does not override the Development predictive rule."),
        **validation,
        "raw_data_reads": 0,
        "raw_data_rebuilds": 0,
        "pairing_rebuilds": 0,
        "weather_rebuilds": 0,
        "pre_sequence_rebuilds": 0,
        "cache_rebuilds": 0,
        "final_test_access_count": 0,
        "warning_threshold_status": "NOT_RUN_AWAITING_W_STAR_APPROVAL",
    }
    evidence["evidence_hash"] = content_id(evidence)
    W_EVIDENCE_PATH.write_text(
        json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "status": evidence["status"],
        "decision_id": evidence["decision_id"],
        "evidence": str(W_EVIDENCE_PATH),
        "evidence_hash": evidence["evidence_hash"],
        "codex_recommendation": recommendation,
        "cache_rebuilds": 0,
        "final_test_access_count": 0,
    }, sort_keys=True), flush=True)
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage-gated M1 Development-only fixed-history W selection")
    parser.add_argument("--approval-token", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda", "auto"))
    return parser


def main(argv=None) -> None:
    args = _parser().parse_args(argv)
    if args.approval_token != APPROVAL_TOKEN:
        raise RuntimeError("W_SELECTION_REQUIRES_APPROVE_H_STAR_32")
    torch.set_num_threads(min(8, torch.get_num_threads()))
    scientific = load_config_layers(ROOT / "configs").scientific
    h_evidence = _validate_h_freeze(scientific)
    cache = _load_immutable_cache()
    _validate_cache_for_w(cache, scientific, h_evidence)
    rows = []
    for window_minutes in CANDIDATE_WINDOWS:
        for seed in SECONDARY_TRAINING_SEEDS:
            rows.append(_run_candidate(
                scientific, cache, h_evidence, window_minutes=window_minutes,
                seed=seed, device=args.device, resume=args.resume))
    _write_w_evidence(cache, h_evidence, rows)


if __name__ == "__main__":
    main()
