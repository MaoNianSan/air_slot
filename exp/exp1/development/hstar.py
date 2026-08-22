from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path

import psutil
import torch

from model.common.config import load_config_layers
from model.common.identity import content_id
from model.M1.contracts import STOCHASTIC_TARGETS
from model.M1.cache import M1DevelopmentBaseCache, cache_key as development_cache_key
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
from model.PRE.streaming.data2 import (
    PROJECTED_ONTIME_COLUMNS,
    config_hash,
    development_source_manifest_hash,
    registry_hash,
)


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"
EVIDENCE_PATH = OUT / "m1_hstar_evidence.json"
BASE_CACHE_DATA = OUT / "M1_BASE_CACHE.npz"
BASE_CACHE_MANIFEST = OUT / "M1_BASE_CACHE_MANIFEST.json"
RUNS_DIR = OUT / "runs"
PREPARATION_STATE = OUT / "M1_BASE_CACHE_PREPARATION_STATE.pt"
PREPARATION_MANIFEST = OUT / "M1_BASE_CACHE_PREPARATION_PROGRESS.json"
PROJECTED = PROJECTED_ONTIME_COLUMNS
COHORT_COUNTS = {"train": 128, "calibration": 64, "development": 128, "test": 0}
COHORT_SEED = 20260813
TRAINING_SEEDS = (20260813, 20260814, 20260815, 20260816, 20260817)
HIDDEN_SIZES = (16, 32)
EPOCHS = 8
LEARNING_RATE = 0.01
BATCH_SIZE = 128
FINAL_TEST_START = date(2019, 10, 1)
FULL_H_APPROVAL_TOKEN = "APPROVE_H_SELECTION_RUN"
APPROVED_CACHE_HASH = (
    "sha256:9c647c03a4bb59d8cc6568e14a34f431f5da84b6d179e55d2e416fe7e7ed180a"
)


def _heartbeat(
    phase: str,
    *,
    started: float,
    rows: int = 0,
    episodes: int = 0,
    decision_nodes: int = 0,
    current_month: str | None = None,
    current_file: str | None = None,
    candidate: int | None = None,
    seed: int | None = None,
    progress: float | None = None,
    cache: str = "MISS",
) -> None:
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
        "RSS_MB": round(psutil.Process().memory_info().rss / 1024**2, 3),
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


def prepare_data(scientific) -> PreparedData:
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
    rows = {}
    active_stages = {}
    for name in ("train", "calibration", "development"):
        rows[name], active_stages[name] = active_rows(getattr(cohorts, name))
    normalization = fit_train_normalization(
        normalization_rows([prefix for _, prefix, _ in rows["train"]]), split="train"
    )
    static_normalization = fit_static_normalization_from_rows(rows["train"])
    template = M1Pipeline.from_scientific_config(
        scientific,
        input_size=len(FEATURE_NAMES),
        normalization=normalization,
        hidden_size=16,
    )
    examples = {
        name: build_training_examples(
            values, normalization, template.bins,
            static_normalization=static_normalization,
        )
        for name, values in rows.items()
    }
    dates = {
        name: sorted({str(row.episode_date) for row in values})
        for name, values in examples.items()
    }
    if dates["development"][-1] >= FINAL_TEST_START.isoformat():
        raise RuntimeError("FINAL_TEST_DEVELOPMENT_DATE_VIOLATION")
    audit = {
        **cohorts.audit,
        "examples": {name: len(values) for name, values in examples.items()},
        "active_stage_counts": active_stages,
        "dates": dates,
        "partition_hashes": {
            name: content_id(sorted({row.episode_id for row in values}))
            for name, values in examples.items()
        },
        "final_test_access_count": 0,
    }
    return PreparedData(
        normalization,
        examples["train"],
        examples["calibration"],
        examples["development"],
        audit,
    )


def _ece(probabilities, labels, bins=10):
    confidence, prediction = probabilities.max(dim=1)
    correct = prediction.eq(labels).float()
    total = max(len(labels), 1)
    value = 0.0
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        mask = (confidence >= lower) & (
            confidence < upper if index < bins - 1 else confidence <= upper
        )
        if mask.any():
            value += float(mask.sum()) / total * abs(
                float(correct[mask].mean()) - float(confidence[mask].mean())
            )
    return value


def evaluate(lifecycle, examples):
    episode_joint = defaultdict(list)
    target_episode = {name: defaultdict(list) for name in STOCHASTIC_TARGETS}
    started = time.perf_counter()
    logits, labels, active = lifecycle.batched_logits(
        examples, batch_size=256, teacher_forcing=True
    )
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
    joint_score = statistics.mean(
        statistics.mean(values) for values in episode_joint.values()
    )
    target_scores = {
        name: statistics.mean(
            statistics.mean(values) for values in episodes.values()
        )
        for name, episodes in target_episode.items()
    }
    ece = {
        name: _ece(probabilities, target_labels)
        for name, (probabilities, target_labels) in calibration.items()
    }
    return {
        "episode_balanced_joint_nll": joint_score,
        "episode_balanced_target_nll": target_scores,
        "calibration_ece": ece,
        "mean_calibration_ece": statistics.mean(ece.values()),
        "development_episode_n": len(episode_joint),
        "inference_seconds": time.perf_counter() - started,
    }


def _repository_sha():
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _hash_file(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _contract_hashes(scientific) -> dict[str, str]:
    episode_hash = content_id(
        {
            "builder": _hash_file(ROOT / "model" / "PRE" / "episode" / "builder.py"),
            "node_builder": _hash_file(
                ROOT / "model" / "PRE" / "episode" / "node_builder.py"
            ),
        }
    )
    return {
        "PRE_contract_hash": content_id(
            {
                "pipeline": _hash_file(ROOT / "model" / "PRE" / "pipeline.py"),
                "mapping": _hash_file(ROOT / "model" / "PRE" / "mapping.py"),
                "registry": registry_hash(ROOT),
            }
        ),
        "episode_contract_hash": episode_hash,
        "episode_construction_hash": episode_hash,
        "feature_contract_hash": content_id(
            {
                "data": _hash_file(ROOT / "model" / "M1" / "data.py"),
                "coverage": _hash_file(ROOT / "model" / "M1" / "coverage.py"),
                "feature_names": FEATURE_NAMES,
            }
        ),
        "split_contract_hash": _hash_file(ROOT / "model" / "M1" / "splits.py"),
        "roll_contract_hash": content_id(
            {
                "roll_minutes": scientific.parameters["roll_minutes"].value,
                "node_builder": _hash_file(
                    ROOT / "model" / "PRE" / "episode" / "node_builder.py"
                ),
            }
        ),
        "normalization_contract_hash": content_id(
            {
                "data_code": _hash_file(ROOT / "model" / "M1" / "data.py"),
                "fitted_split": "train",
            }
        ),
    }


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


def _expected_cache_key(scientific):
    source_hash = development_source_manifest_hash(ROOT)
    contracts = _contract_hashes(scientific)
    key = development_cache_key(
        source_manifest_hash=source_hash,
        contract_hashes=contracts,
        cohort_counts=COHORT_COUNTS,
        cohort_seed=COHORT_SEED,
    )
    return key, source_hash, contracts


def _validate_cache_for_h(cache, scientific) -> dict:
    manifest = cache.manifest
    if manifest.get("cache_hash") != APPROVED_CACHE_HASH:
        raise RuntimeError("H_SELECTION_CACHE_HASH_MISMATCH")
    if manifest.get("feature_count") != len(FEATURE_NAMES):
        raise RuntimeError("H_SELECTION_FEATURE_COUNT_MISMATCH")
    if manifest.get("final_test_included") is not False:
        raise RuntimeError("H_SELECTION_FINAL_TEST_INCLUDED")
    if manifest.get("final_test_access_count", 0) != 0:
        raise RuntimeError("H_SELECTION_FINAL_TEST_ACCESS_NONZERO")
    current_config_hash = _scientific_config_hash()
    if cache.audit.get("config_hash") != current_config_hash:
        raise RuntimeError("H_SELECTION_SCIENTIFIC_CONFIG_HASH_MISMATCH")
    for split in ("train", "calibration", "development"):
        dataset = cache.partition(split)
        observed = content_id(sorted({row.episode_id for row in dataset}))
        if cache.audit.get("partition_hashes", {}).get(split) != observed:
            raise RuntimeError(f"H_SELECTION_EPISODE_IDS_MISMATCH:{split}")
        if any(row.episode_date >= FINAL_TEST_START for row in dataset):
            raise RuntimeError(f"H_SELECTION_FINAL_TEST_DATE:{split}")
    return {
        "cache_hash": manifest["cache_hash"],
        "feature_count": manifest["feature_count"],
        "scientific_config_hash": current_config_hash,
        "training_contract_hash": _training_contract_hash(),
        "final_test_access_count": 0,
        "cache_rebuilds": 0,
    }


def _validate_manifest_for_resume(manifest, cache, scientific):
    expected = _validate_cache_for_h(cache, scientific)
    if manifest.get("completion_status") != "PASS":
        return False, "completion_status"
    if manifest.get("cache_hash") != expected["cache_hash"]:
        return False, "cache_hash"
    if manifest.get("hidden_size") not in HIDDEN_SIZES:
        return False, "hidden_size"
    if manifest.get("training_seed") not in TRAINING_SEEDS:
        return False, "training_seed"
    explicit = {
        "epochs": EPOCHS,
        "learning_rate": LEARNING_RATE,
        "batch_size": BATCH_SIZE,
        "optimizer": "Adam",
        "optimizer_steps_per_epoch": 1,
        "final_test_access_count": 0,
    }
    if any(manifest.get(name) != value for name, value in explicit.items()):
        return False, "training_contract"
    if manifest.get("scientific_config_hash") == expected["scientific_config_hash"] and manifest.get(
        "training_contract_hash"
    ) == expected["training_contract_hash"]:
        return True, "validated"
    if "scientific_config_hash" not in manifest and "training_contract_hash" not in manifest:
        return True, "legacy_manifest_verified_from_cache_audit"
    return False, "contract_hash"


def _peak_rss_mb() -> float:
    info = psutil.Process().memory_info()
    return float(getattr(info, "peak_wset", info.rss)) / 1024**2


def _base_cache(scientific, *, allow_build: bool):
    key, source_hash, contracts = _expected_cache_key(scientific)
    if BASE_CACHE_DATA.is_file() and BASE_CACHE_MANIFEST.is_file():
        cache = M1DevelopmentBaseCache.load(
            BASE_CACHE_DATA, BASE_CACHE_MANIFEST, expected_cache_key=key
        )
        return cache, {"cache_hit": True}
    if not allow_build:
        raise RuntimeError("M1_BASE_CACHE_MISSING_BUILD_NOT_AUTHORIZED")
    prepared = prepare_data(scientific)
    cache = M1DevelopmentBaseCache.from_partitions(
        partitions={
            "train": prepared.train_examples,
            "calibration": prepared.calibration_examples,
            "development": prepared.development_examples,
        },
        normalization=prepared.normalization,
        audit=prepared.audit,
        cache_key=key,
        source_manifest_hash=source_hash,
        contract_hashes=contracts,
    )
    cache.save(BASE_CACHE_DATA, BASE_CACHE_MANIFEST)
    return cache, {"cache_hit": False}


def _run_paths(hidden_size: int, seed: int):
    stem = f"H{hidden_size}_seed{seed}"
    return RUNS_DIR / f"{stem}.pt", RUNS_DIR / f"{stem}.json"


def _run_candidate(scientific, cache, *, hidden_size, seed, device, resume):
    validation = _validate_cache_for_h(cache, scientific)
    checkpoint_path, manifest_path = _run_paths(hidden_size, seed)
    if resume and manifest_path.is_file() and checkpoint_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        valid, _ = _validate_manifest_for_resume(manifest, cache, scientific)
        if valid:
            return manifest
    train = cache.partition("train")
    calibration = cache.partition("calibration")
    development = cache.partition("development")
    torch.manual_seed(seed)
    pipeline = M1Pipeline.from_scientific_config(
        scientific,
        input_size=len(FEATURE_NAMES),
        normalization=cache.normalization,
        hidden_size=hidden_size,
    )
    lifecycle = M1Lifecycle(pipeline, device=device)
    started = time.perf_counter()
    history = lifecycle.train(
        train,
        epochs=EPOCHS,
        learning_rate=LEARNING_RATE,
        batch_size=BATCH_SIZE,
        seed=seed,
    )
    training_seconds = time.perf_counter() - started
    calibration_started = time.perf_counter()
    temperatures = lifecycle.calibrate(calibration, batch_size=256)
    calibration_seconds = time.perf_counter() - calibration_started
    metrics = evaluate(lifecycle, development)
    if not all(math.isfinite(float(row["loss"])) for row in history):
        raise RuntimeError("H_SELECTION_NONFINITE_LOSS")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    temporary_checkpoint = checkpoint_path.with_suffix(".pt.tmp")
    lifecycle.save(temporary_checkpoint)
    temporary_checkpoint.replace(checkpoint_path)
    manifest = {
        "completion_status": "PASS",
        "repository_sha": _repository_sha(),
        "cache_key": cache.manifest["cache_key"],
        "cache_hash": cache.manifest["cache_hash"],
        "scientific_config_hash": validation["scientific_config_hash"],
        "training_contract_hash": validation["training_contract_hash"],
        "training_contract": _training_contract_payload(),
        "hidden_size": hidden_size,
        "training_seed": seed,
        "epochs": EPOCHS,
        "learning_rate": LEARNING_RATE,
        "batch_size": BATCH_SIZE,
        "optimizer": "Adam",
        "optimizer_steps_per_epoch": 1,
        "training_seconds": training_seconds,
        "calibration_seconds": calibration_seconds,
        "temperatures": temperatures,
        "training_history": list(history),
        "peak_rss_mb": _peak_rss_mb(),
        "cache_rebuilds": 0,
        "final_test_access_count": 0,
        **metrics,
    }
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    temporary_manifest.replace(manifest_path)
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
        }
    left, right = candidates["16"]["mean_joint_nll"], candidates["32"]["mean_joint_nll"]
    relative_difference = abs(left - right) / min(left, right)
    equivalent = relative_difference <= 0.005
    recommendation = 16 if equivalent or left < right else 32
    evidence = {
        "status": "HUMAN_DECISION_REQUIRED",
        "decision_id": "D2_H_STAR",
        "paper_result": False,
        "development_only": True,
        "repository_sha": _repository_sha(),
        "representation": "ADAPTIVE_HISTORY",
        "history_boundary": "FULL_ADMISSIBLE_CURRENT_EPISODE_PREFIX",
        "hidden_size_candidates": list(HIDDEN_SIZES),
        "training_seeds": list(TRAINING_SEEDS),
        "selection_metric": "episode-balanced Development joint NLL",
        "tie_rule": "if relative joint-NLL difference <= 0.5%, recommend H=16",
        "candidate_summary": candidates,
        "per_seed": rows,
        "codex_recommendation": recommendation,
        "within_0_5_percent_equivalence_region": equivalent,
        "relative_nll_difference": relative_difference,
        "cache_rebuilds": 0,
        "data_audit": cache.audit,
        "final_test_access_count": 0,
        "w_comparison_status": "NOT_RUN_AWAITING_H_STAR_APPROVAL",
    }
    evidence["evidence_hash"] = content_id(evidence)
    EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")


def _parser():
    parser = argparse.ArgumentParser(description="Development-only M1 H-selection runner")
    parser.add_argument("--stage", required=True, choices=("cache", "one-seed", "full-h"))
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
    cache, status = _base_cache(scientific, allow_build=args.stage == "cache")
    if args.stage == "cache":
        print(json.dumps({"status": "CACHE_BUILD_COMPLETE", **status}, sort_keys=True))
        return
    if args.stage == "one-seed":
        row = _run_candidate(
            scientific,
            cache,
            hidden_size=16,
            seed=TRAINING_SEEDS[0],
            device=args.device,
            resume=args.resume,
        )
        print(json.dumps({"status": "HUMAN_DECISION_REQUIRED", "run": row}, sort_keys=True))
        return
    if args.approval_token != FULL_H_APPROVAL_TOKEN:
        raise RuntimeError("FULL_H_SELECTION_REQUIRES_APPROVE_H_SELECTION_RUN")
    rows = [
        _run_candidate(
            scientific,
            cache,
            hidden_size=hidden_size,
            seed=seed,
            device=args.device,
            resume=args.resume,
        )
        for hidden_size in HIDDEN_SIZES
        for seed in TRAINING_SEEDS
    ]
    _write_h_decision(cache, rows)


if __name__ == "__main__":
    main()
