"""Approved Development-only signed M1 H then W refreeze runner.

This runner is deliberately separate from the historical R_OB evidence paths.
It builds a new cache and emits provisional evidence only; it never changes
the permanent foundation freezes or touches Final Test data.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
from hashlib import sha256
import json
import math
from pathlib import Path
import statistics
import subprocess
import time

import psutil
import torch

from model.common.config import load_config_layers
from model.common.identity import content_id
from model.M1.cache import M1DevelopmentBaseCache, cache_key as development_cache_key
from model.M1.contracts import STOCHASTIC_TARGETS
from model.M1.data import FEATURE_NAMES, fit_train_normalization
from model.M1.lifecycle import M1Lifecycle, M1TrainingExample
from model.M1.pipeline import M1Pipeline
from model.M1.preparation import (
    active_rows,
    build_training_examples,
    fit_static_normalization_from_rows,
    normalization_rows,
)
from model.PRE.development import PREDevelopmentCohorts, build_sampled_pre_cohorts
from model.PRE.streaming.data2 import config_hash, development_source_manifest_hash, registry_hash


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"
CACHE_NAME = "M1_SIGNED_OB_DEVELOPMENT_BASE_CACHE_V1"
CACHE_DATA = OUT / f"{CACHE_NAME}.npz"
CACHE_MANIFEST = OUT / f"{CACHE_NAME}_MANIFEST.json"
PREPARATION_STATE = OUT / f"{CACHE_NAME}_PREPARATION_STATE.pt"
PREPARATION_MANIFEST = OUT / f"{CACHE_NAME}_PREPARATION_PROGRESS.json"
H_EVIDENCE_PATH = OUT / "m1_signed_hstar_evidence.json"
W_EVIDENCE_PATH = OUT / "m1_signed_wstar_evidence.json"
H_RUNS_DIR = OUT / "runs_signed_hstar"
W_RUNS_DIR = OUT / "runs_signed_wstar"
OLD_H_EVIDENCE_PATH = OUT / "m1_hstar_evidence.json"
OLD_W_EVIDENCE_PATH = OUT / "m1_wstar_evidence.json"

COHORT_COUNTS = {"train": 128, "calibration": 64, "development": 128, "test": 0}
COHORT_SEED = 20260813
HIDDEN_SIZES = (16, 32)
H_SEEDS = (20260813, 20260814, 20260815, 20260816, 20260817)
WINDOWS = (30, 60, 120, 180)
W_SEEDS = H_SEEDS[:3]
EPOCHS = 8
LEARNING_RATE = 0.01
BATCH_SIZE = 128
FINAL_TEST_START = date(2019, 10, 1)
APPROVAL_TOKEN = "APPROVE_SIGNED_M1_REFREEZE"
SIGNED_BIN_CONTRACT = {
    "target": "DELTA_OB",
    "bin_width_minutes": 5,
    "finite_bin_starts_minutes": [-180, 180],
    "tails": ["UNDERFLOW", "OVERFLOW"],
}


def _hash_file(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _repository_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _peak_rss_mb() -> float:
    info = psutil.Process().memory_info()
    return float(getattr(info, "peak_wset", info.rss)) / 1024**2


def _training_contract() -> dict:
    return {
        "epochs": EPOCHS,
        "learning_rate": LEARNING_RATE,
        "batch_size": BATCH_SIZE,
        "optimizer": "Adam",
        "optimizer_steps_per_epoch": 1,
        "length_bucketed_microbatch": True,
        "gradient_accumulation": True,
        "stochastic_targets": list(STOCHASTIC_TARGETS),
        "signed_bin_contract": SIGNED_BIN_CONTRACT,
    }


def _training_contract_hash() -> str:
    return content_id(_training_contract())


def _contract_hashes(scientific) -> dict[str, str]:
    def code(path: str) -> str:
        return _hash_file(ROOT / path)

    episode_hash = content_id({
        "builder": code("model/PRE/episode/builder.py"),
        "node_builder": code("model/PRE/episode/node_builder.py"),
        "containment": code("model/PRE/episode/containment.py"),
    })
    return {
        "PRE_contract_hash": content_id({
            "pipeline": code("model/PRE/pipeline.py"),
            "mapping": code("model/PRE/mapping.py"),
            "registry": registry_hash(ROOT),
        }),
        "episode_contract_hash": episode_hash,
        "episode_construction_hash": episode_hash,
        "feature_contract_hash": content_id({
            "data": code("model/M1/data.py"),
            "coverage": code("model/M1/coverage.py"),
            "target_builder": code("model/M1/target_builder.py"),
            "feature_names": FEATURE_NAMES,
            "target_contract": list(STOCHASTIC_TARGETS),
            "signed_bins": SIGNED_BIN_CONTRACT,
        }),
        "split_contract_hash": code("model/M1/splits.py"),
        "roll_contract_hash": content_id({
            "roll_minutes": scientific.parameters["roll_minutes"].value,
            "node_builder": code("model/PRE/episode/node_builder.py"),
        }),
        "normalization_contract_hash": content_id({
            "data_code": code("model/M1/data.py"),
            "fitted_split": "train",
        }),
    }


def _heartbeat(phase: str, *, started: float, rows: int = 0, episodes: int = 0,
               decision_nodes: int = 0, current_month: str | None = None,
               current_file: str | None = None, progress: float | None = None, **extra) -> None:
    elapsed = time.perf_counter() - started
    eta = None if not progress else max(elapsed / progress - elapsed, 0.0)
    print(json.dumps({
        "TIMESTAMP": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "PHASE": phase,
        "CURRENT_MONTH": current_month,
        "CURRENT_FILE_OR_CHUNK": current_file,
        "ROWS_PROCESSED": rows,
        "EPISODES_PROCESSED": episodes,
        "DECISION_NODES_PROCESSED": decision_nodes,
        "ELAPSED_SECONDS": round(elapsed, 3),
        "ETA_SECONDS": None if eta is None else round(eta, 3),
        "RSS_MB": round(_peak_rss_mb(), 3),
        "FINAL_TEST_ACCESS_COUNT": 0,
        **extra,
    }, sort_keys=True), flush=True)


def _tail_counts(examples: tuple[M1TrainingExample, ...], bins) -> dict[str, int]:
    underflow = overflow = finite = 0
    for example in examples:
        if not example.active["DELTA_OB"]:
            continue
        tail = bins["DELTA_OB"].tail_state(example.labels["DELTA_OB"])
        if tail == "UNDERFLOW":
            underflow += 1
        elif tail == "OVERFLOW":
            overflow += 1
        else:
            finite += 1
    return {"underflow": underflow, "finite": finite, "overflow": overflow}


def _prepare_data(scientific) -> tuple[dict[str, tuple[M1TrainingExample, ...]], object, dict]:
    cohorts: PREDevelopmentCohorts = build_sampled_pre_cohorts(
        scientific,
        root=ROOT,
        cohort_counts=COHORT_COUNTS,
        cohort_seed=COHORT_SEED,
        preparation_state=PREPARATION_STATE,
        preparation_manifest=PREPARATION_MANIFEST,
        resume=True,
        heartbeat=_heartbeat,
    )
    rows, active_stages = {}, {}
    for split in ("train", "calibration", "development"):
        rows[split], active_stages[split] = active_rows(getattr(cohorts, split))
    normalization = fit_train_normalization(
        normalization_rows([prefix for _, prefix, _ in rows["train"]]), split="train"
    )
    static_normalization = fit_static_normalization_from_rows(rows["train"])
    template = M1Pipeline.from_scientific_config(
        scientific, input_size=len(FEATURE_NAMES), normalization=normalization, hidden_size=16
    )
    examples = {
        split: build_training_examples(
            values, normalization, template.bins,
            static_normalization=static_normalization,
        )
        for split, values in rows.items()
    }
    memberships: dict[str, set[str]] = defaultdict(set)
    for split, values in examples.items():
        for item in values:
            memberships[item.episode_id].add(split)
    cross_split = sorted(key for key, values in memberships.items() if len(values) != 1)
    if cross_split:
        raise RuntimeError(f"SIGNED_CACHE_CROSS_SPLIT_EPISODES:{cross_split[:3]}")
    if any(item.episode_date >= FINAL_TEST_START for values in examples.values() for item in values):
        raise RuntimeError("SIGNED_CACHE_FINAL_TEST_DATE")
    audit = {
        **cohorts.audit,
        "target_contract": list(STOCHASTIC_TARGETS),
        "signed_bin_contract": SIGNED_BIN_CONTRACT,
        "feature_count": len(FEATURE_NAMES),
        "examples": {split: len(values) for split, values in examples.items()},
        "active_stage_counts": active_stages,
        "partition_hashes": {
            split: content_id(sorted({item.episode_id for item in values}))
            for split, values in examples.items()
        },
        "delta_ob_tail_counts": {
            split: _tail_counts(values, template.bins) for split, values in examples.items()
        },
        "cross_split_episodes_in_new_cache": 0,
        "final_test_access_count": 0,
    }
    return examples, normalization, audit


def _expected_cache_key(scientific) -> tuple[str, str, dict[str, str]]:
    source_hash = development_source_manifest_hash(ROOT)
    contracts = _contract_hashes(scientific)
    return development_cache_key(
        source_manifest_hash=source_hash,
        contract_hashes=contracts,
        cohort_counts=COHORT_COUNTS,
        cohort_seed=COHORT_SEED,
    ), source_hash, contracts


def _cache(scientific) -> M1DevelopmentBaseCache:
    cache_key, source_hash, contracts = _expected_cache_key(scientific)
    if CACHE_DATA.is_file() and CACHE_MANIFEST.is_file():
        cache = M1DevelopmentBaseCache.load(CACHE_DATA, CACHE_MANIFEST, expected_cache_key=cache_key)
        _validate_cache(cache, scientific)
        print(json.dumps({"PHASE": "SIGNED_M1_CACHE", "CACHE": "HIT", "FINAL_TEST_ACCESS_COUNT": 0}, sort_keys=True), flush=True)
        return cache
    examples, normalization, audit = _prepare_data(scientific)
    cache = M1DevelopmentBaseCache.from_partitions(
        partitions=examples,
        normalization=normalization,
        audit=audit,
        cache_key=cache_key,
        source_manifest_hash=source_hash,
        contract_hashes=contracts,
    )
    cache.save(CACHE_DATA, CACHE_MANIFEST)
    cache = M1DevelopmentBaseCache.load(
        CACHE_DATA, CACHE_MANIFEST, expected_cache_key=cache_key
    )
    _validate_cache(cache, scientific)
    print(json.dumps({"PHASE": "SIGNED_M1_CACHE", "CACHE": "MISS", "FINAL_TEST_ACCESS_COUNT": 0}, sort_keys=True), flush=True)
    return cache


def _validate_cache(cache: M1DevelopmentBaseCache, scientific) -> None:
    manifest = cache.manifest
    if manifest.get("cache_schema_version") != "M1_SIGNED_OB_DEVELOPMENT_BASE_CACHE_V1":
        raise RuntimeError("SIGNED_CACHE_SCHEMA_MISMATCH")
    if manifest.get("final_test_included") is not False or manifest.get("final_test_access_count") != 0:
        raise RuntimeError("SIGNED_CACHE_FINAL_TEST_GUARD")
    if cache.audit.get("cross_split_episodes_in_new_cache") != 0:
        raise RuntimeError("SIGNED_CACHE_CROSS_SPLIT_GUARD")
    if cache.normalization.fitted_split != "train":
        raise RuntimeError("SIGNED_CACHE_NORMALIZATION_LEAKAGE")
    if manifest.get("feature_count") != len(FEATURE_NAMES):
        raise RuntimeError("SIGNED_CACHE_FEATURE_COUNT_MISMATCH")
    if manifest.get("contract_hashes") != _contract_hashes(scientific):
        raise RuntimeError("SIGNED_CACHE_CONTRACT_HASH_MISMATCH")
    for split in ("train", "calibration", "development"):
        values = cache.partition(split)
        if any(item.episode_date >= FINAL_TEST_START for item in values):
            raise RuntimeError(f"SIGNED_CACHE_FINAL_TEST_DATE:{split}")
        observed = content_id(sorted({item.episode_id for item in values}))
        if observed != cache.audit["partition_hashes"][split]:
            raise RuntimeError(f"SIGNED_CACHE_EPISODE_IDENTITY_MISMATCH:{split}")


def _evaluate(lifecycle: M1Lifecycle, examples) -> dict:
    episode_joint = defaultdict(list)
    target_episode = {name: defaultdict(list) for name in STOCHASTIC_TARGETS}
    started = time.perf_counter()
    logits, labels, active = lifecycle.batched_logits(examples, batch_size=256, teacher_forcing=True)
    joint = torch.zeros(len(examples))
    for name in STOCHASTIC_TARGETS:
        scaled = logits[name] / lifecycle.pipeline.temperatures[name]
        losses = torch.nn.functional.cross_entropy(scaled, labels[name], reduction="none")
        mask = active[name]
        joint += losses * mask.float()
        for index, example in enumerate(examples):
            if bool(mask[index]):
                target_episode[name][example.episode_id].append(float(losses[index]))
    for index, example in enumerate(examples):
        episode_joint[example.episode_id].append(float(joint[index]))
    return {
        "episode_balanced_joint_nll": statistics.mean(statistics.mean(values) for values in episode_joint.values()),
        "episode_balanced_target_nll": {
            name: statistics.mean(statistics.mean(values) for values in episodes.values())
            for name, episodes in target_episode.items()
        },
        "development_episode_n": len(episode_joint),
        "inference_seconds": time.perf_counter() - started,
    }


def _view_summary(dataset) -> dict:
    lengths = [int(item.values.shape[0]) for item in dataset]
    return {
        "sample_count": len(lengths),
        "min_nodes": min(lengths),
        "max_nodes": max(lengths),
        "mean_nodes": statistics.mean(lengths),
        "identity_and_length_hash": content_id([
            [item.episode_id, item.decision_node_id, length]
            for item, length in zip(dataset, lengths)
        ]),
    }


def _run_candidate(cache: M1DevelopmentBaseCache, scientific, *, hidden_size: int,
                   window_minutes: int | None, seed: int, device: str, resume: bool) -> dict:
    run_dir = H_RUNS_DIR if window_minutes is None else W_RUNS_DIR
    prefix = f"H{hidden_size}_seed{seed}" if window_minutes is None else f"W{window_minutes}_H{hidden_size}_seed{seed}"
    checkpoint = run_dir / f"{prefix}.pt"
    manifest_path = run_dir / f"{prefix}.json"
    contract_hash = _training_contract_hash()
    if resume and checkpoint.is_file() and manifest_path.is_file():
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            prior.get("completion_status") == "PASS"
            and prior.get("cache_hash") == cache.manifest.get("cache_hash")
            and prior.get("training_contract_hash") == contract_hash
            and prior.get("hidden_size") == hidden_size
            and prior.get("fixed_history_window_minutes") == window_minutes
            and prior.get("training_seed") == seed
            and prior.get("checkpoint_hash") == _hash_file(checkpoint)
        ):
            return prior
    views = {
        split: cache.partition(split, representation="ADAPTIVE_HISTORY" if window_minutes is None else "FIXED_HISTORY",
                               window_minutes=window_minutes)
        for split in ("train", "calibration", "development")
    }
    torch.manual_seed(seed)
    pipeline = M1Pipeline.from_scientific_config(
        scientific, input_size=len(FEATURE_NAMES), normalization=cache.normalization, hidden_size=hidden_size
    )
    lifecycle = M1Lifecycle(pipeline, device=device)
    started = time.perf_counter()

    def progress(row):
        _heartbeat(
            "SIGNED_M1_TRAIN",
            started=started,
            progress=row["epoch"] / EPOCHS,
            H=hidden_size,
            W=window_minutes,
            SEED=seed,
            EPOCH=row["epoch"],
            TRAIN_LOSS=row["loss"],
        )

    training = lifecycle.train(
        views["train"], epochs=EPOCHS, learning_rate=LEARNING_RATE,
        batch_size=BATCH_SIZE, seed=seed, progress_callback=progress,
    )
    training_seconds = time.perf_counter() - started
    calibration_started = time.perf_counter()
    temperatures = lifecycle.calibrate(views["calibration"], batch_size=256)
    calibration_seconds = time.perf_counter() - calibration_started
    metrics = _evaluate(lifecycle, views["development"])
    if not all(math.isfinite(float(row["loss"])) for row in training):
        raise RuntimeError("SIGNED_M1_NONFINITE_LOSS")
    if not all(math.isfinite(float(value)) for value in temperatures.values()):
        raise RuntimeError("SIGNED_M1_NONFINITE_TEMPERATURE")
    if not math.isfinite(float(metrics["episode_balanced_joint_nll"])):
        raise RuntimeError("SIGNED_M1_NONFINITE_DEVELOPMENT_NLL")
    run_dir.mkdir(parents=True, exist_ok=True)
    temporary = checkpoint.with_suffix(".pt.tmp")
    lifecycle.save(temporary)
    temporary.replace(checkpoint)
    result = {
        "completion_status": "PASS",
        "development_only": True,
        "paper_result": False,
        "repository_sha": _repository_sha(),
        "cache_hash": cache.manifest["cache_hash"],
        "cache_key": cache.manifest["cache_key"],
        "target_contract": list(STOCHASTIC_TARGETS),
        "signed_bin_contract": SIGNED_BIN_CONTRACT,
        "training_contract_hash": contract_hash,
        "training_contract": _training_contract(),
        "hidden_size": hidden_size,
        "fixed_history_window_minutes": window_minutes,
        "training_seed": seed,
        "epochs": EPOCHS,
        "learning_rate": LEARNING_RATE,
        "batch_size": BATCH_SIZE,
        "optimizer": "Adam",
        "optimizer_steps_per_epoch": 1,
        "training_seconds": training_seconds,
        "calibration_seconds": calibration_seconds,
        "temperatures": temperatures,
        "training_history": list(training),
        "view_summaries": {split: _view_summary(view) for split, view in views.items()},
        "checkpoint_hash": _hash_file(checkpoint),
        "checkpoint_path": str(checkpoint.relative_to(ROOT)),
        "peak_rss_mb": _peak_rss_mb(),
        "cache_rebuilds": 0,
        "final_test_access_count": 0,
        **metrics,
    }
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    temporary_manifest.replace(manifest_path)
    return result


def _h_summary(rows: list[dict]) -> tuple[dict, int, float, bool]:
    candidates = {}
    for hidden_size in HIDDEN_SIZES:
        scores = [row["episode_balanced_joint_nll"] for row in rows if row["hidden_size"] == hidden_size]
        candidates[str(hidden_size)] = {
            "mean_joint_nll": statistics.mean(scores),
            "sd_joint_nll": statistics.stdev(scores),
            "min_joint_nll": min(scores),
            "max_joint_nll": max(scores),
        }
    h16, h32 = candidates["16"]["mean_joint_nll"], candidates["32"]["mean_joint_nll"]
    relative = abs(h16 - h32) / min(h16, h32)
    equivalent = relative <= 0.005
    return candidates, (16 if equivalent or h16 < h32 else 32), relative, equivalent


def _w_summary(rows: list[dict]) -> tuple[dict, int, dict[str, float], dict[str, bool]]:
    candidates, means = {}, {}
    for window in WINDOWS:
        scores = [row["episode_balanced_joint_nll"] for row in rows if row["fixed_history_window_minutes"] == window]
        means[window] = statistics.mean(scores)
        candidates[str(window)] = {
            "mean_joint_nll": means[window],
            "sd_joint_nll": statistics.stdev(scores),
            "min_joint_nll": min(scores),
            "max_joint_nll": max(scores),
        }
    raw_best = min(means, key=lambda item: (means[item], item))
    relative_raw = {window: (score - means[raw_best]) / means[raw_best] for window, score in means.items()}
    equivalent = {window: value <= 0.005 for window, value in relative_raw.items()}
    return (
        candidates,
        min(window for window, value in equivalent.items() if value),
        {str(key): value for key, value in relative_raw.items()},
        {str(key): value for key, value in equivalent.items()},
    )


def _write_evidence(path: Path, payload: dict) -> dict:
    evidence = {**payload}
    evidence["evidence_hash"] = content_id(evidence)
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    return evidence


def run(*, device: str, resume: bool) -> dict:
    before = {"h": _hash_file(OLD_H_EVIDENCE_PATH), "w": _hash_file(OLD_W_EVIDENCE_PATH)}
    scientific = load_config_layers(ROOT / "configs").scientific
    cache = _cache(scientific)
    h_rows = [
        _run_candidate(cache, scientific, hidden_size=hidden_size, window_minutes=None,
                       seed=seed, device=device, resume=resume)
        for hidden_size in HIDDEN_SIZES
        for seed in H_SEEDS
    ]
    h_candidates, provisional_h, h_relative, h_equivalent = _h_summary(h_rows)
    h_evidence = _write_evidence(H_EVIDENCE_PATH, {
        "status": "PROVISIONAL_SIGNED_H_STAR",
        "decision_id": "D3_SIGNED_M1_H_W_REFREEZE",
        "development_only": True,
        "paper_result": False,
        "repository_sha": _repository_sha(),
        "stochastic_targets": list(STOCHASTIC_TARGETS),
        "derived_targets": ["R_OB", "T_OB", "T_TO", "D_TO"],
        "signed_bin_contract": SIGNED_BIN_CONTRACT,
        "candidate_hidden_sizes": list(HIDDEN_SIZES),
        "seed_list": list(H_SEEDS),
        "selection_metric": "episode-balanced Development joint NLL",
        "tie_rule": "if relative joint-NLL difference <= 0.5%, choose H=16",
        "per_run": h_rows,
        "per_candidate": h_candidates,
        "relative_nll_difference": h_relative,
        "within_0_5_percent_equivalence_region": h_equivalent,
        "provisional_signed_h_star": provisional_h,
        "H_RULE_APPLIED_BEFORE_W": True,
        "H_REVISED_AFTER_W": False,
        "cache_manifest": str(CACHE_MANIFEST.relative_to(ROOT)),
        "cache_hash": cache.manifest["cache_hash"],
        "data_audit": cache.audit,
        "final_test_access_count": 0,
        "warning_threshold_status": "NOT_RUN",
    })
    w_rows = [
        _run_candidate(cache, scientific, hidden_size=provisional_h, window_minutes=window,
                       seed=seed, device=device, resume=resume)
        for window in WINDOWS
        for seed in W_SEEDS
    ]
    w_candidates, provisional_w, w_relative, w_equivalent = _w_summary(w_rows)
    unchanged = {
        "h": _hash_file(OLD_H_EVIDENCE_PATH) == before["h"],
        "w": _hash_file(OLD_W_EVIDENCE_PATH) == before["w"],
    }
    if not all(unchanged.values()):
        raise RuntimeError("HISTORICAL_EVIDENCE_MUTATED")
    final = _write_evidence(W_EVIDENCE_PATH, {
        "status": "HUMAN_DECISION_REQUIRED",
        "decision_id": "D3_SIGNED_M1_H_W_REFREEZE",
        "development_only": True,
        "paper_result": False,
        "repository_sha": _repository_sha(),
        "stochastic_targets": list(STOCHASTIC_TARGETS),
        "derived_targets": ["R_OB", "T_OB", "T_TO", "D_TO"],
        "signed_bin_contract": SIGNED_BIN_CONTRACT,
        "cache_manifest": str(CACHE_MANIFEST.relative_to(ROOT)),
        "cache_hash": cache.manifest["cache_hash"],
        "new_cache_episodes": cache.manifest["episode_count"],
        "new_cache_nodes": cache.manifest["canonical_node_count"],
        "cross_split_episodes_in_new_cache": 0,
        "delta_ob_tail_counts": cache.audit["delta_ob_tail_counts"],
        "h_evidence_path": str(H_EVIDENCE_PATH.relative_to(ROOT)),
        "h_evidence_hash": h_evidence["evidence_hash"],
        "h_results": h_candidates,
        "h_relative_nll_difference": h_relative,
        "provisional_signed_h_star": provisional_h,
        "w_results": w_candidates,
        "w_relative_difference_to_best": w_relative,
        "w_equivalence_set": w_equivalent,
        "provisional_signed_w_star": provisional_w,
        "per_w_run": w_rows,
        "H_RULE_APPLIED_BEFORE_W": True,
        "H_REVISED_AFTER_W": False,
        "old_h_evidence_byte_hash": before["h"],
        "old_w_evidence_byte_hash": before["w"],
        "old_h_evidence_byte_hash_unchanged": unchanged["h"],
        "old_w_evidence_byte_hash_unchanged": unchanged["w"],
        "pre_ownership_gate": "PENDING_VERIFICATION",
        "static_volume_gate": "PENDING_VERIFICATION",
        "v5_split_containment": "PASS",
        "final_test_access_count": 0,
        "warning_threshold_status": "NOT_RUN",
        "m2_m4_execution": "NOT_RUN",
        "paper_full_run": False,
    })
    return final


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Approved signed M1 Development H then W refreeze")
    parser.add_argument("--approval-token", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda", "auto"))
    args = parser.parse_args(argv)
    if args.approval_token != APPROVAL_TOKEN:
        raise RuntimeError("SIGNED_M1_REFREEZE_REQUIRES_APPROVAL")
    torch.set_num_threads(min(8, torch.get_num_threads()))
    OUT.mkdir(parents=True, exist_ok=True)
    evidence = run(device=args.device, resume=args.resume)
    print(json.dumps({
        "status": evidence["status"],
        "decision_id": evidence["decision_id"],
        "provisional_signed_h_star": evidence["provisional_signed_h_star"],
        "provisional_signed_w_star": evidence["provisional_signed_w_star"],
        "final_test_access_count": 0,
    }, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
