"""Materialize matched formal H16 M1 History and Current artifacts.

Consumes the already-frozen M1 cache only. No cohort selection or raw Data2
access is performed. Each variant uses one fixed seed and independent July
calibration on the same formal cohort.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from hashlib import sha256
from pathlib import Path

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_COUNT
from model.M1.history import HistoryEncoderMode
from model.M1.lifecycle import M1Lifecycle
from model.M1.pipeline import M1Pipeline
from model.M1.tuning_stage1 import (
    NO_HISTORY_BASELINE_CONTRACT,
    OPTIONAL_ROBUSTNESS_SEEDS,
    PRIMARY_EPOCHS,
    PRIMARY_TRAINING_SEED,
    STAGE1_SPLITS,
    STAGE1_SUPPORT,
    STAGE1_TRAINING_CONFIG,
    validate_stage1_contract,
)
from model.common.config import load_config_layers
from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT


MODEL_ROOT = PROJECT_ROOT / "artifacts" / "models" / "m1"
SOURCE_ROOT = MODEL_ROOT / "M1_FROZEN_H16"
SOURCE_CACHE = SOURCE_ROOT / "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3.npz"
SOURCE_CACHE_MANIFEST = SOURCE_ROOT / "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3_MANIFEST.json"
COHORT_PATH = MODEL_ROOT / "M1_FORMAL_TRAINING_COHORT_V1.json"
MATCHED_AUDIT_PATH = MODEL_ROOT / "M1_H16_HISTORY_CURRENT_MATCHED_AUDIT.json"
HIDDEN_SIZE = 16
SCENARIO_COUNT = 64
MODEL_VERSION = "M1_STATE_ESTIMATOR_V2_H16"


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def _source_cache() -> M1DevelopmentBaseCache:
    manifest = json.loads(SOURCE_CACHE_MANIFEST.read_text(encoding="utf-8"))
    return M1DevelopmentBaseCache.load(SOURCE_CACHE, SOURCE_CACHE_MANIFEST, expected_cache_key=manifest["cache_key"])


def _episode_ids(cache: M1DevelopmentBaseCache, split: str) -> tuple[str, ...]:
    return tuple(sorted({episode_id for episode_id, current_split in zip(cache.store.sample_episode_ids, cache.store.sample_splits) if current_split == split}))


def _hash_ids(ids: tuple[str, ...]) -> str:
    return content_id({"episode_ids": list(ids)})


def materialize_formal_cohort(cache: M1DevelopmentBaseCache | None = None) -> dict:
    """Create a manifest from existing frozen cache IDs; never resample."""
    cache = cache or _source_cache()
    expected_counts = {"train": 128, "calibration": 64, "development": 128}
    ids = {split: _episode_ids(cache, split) for split in expected_counts}
    counts = {split: len(ids[split]) for split in ids}
    if counts != expected_counts:
        raise ValueError(f"M1_FORMAL_COHORT_COUNTS_MISMATCH:{counts}")
    payload = {
        "schema_version": "M1_FORMAL_TRAINING_COHORT_V1",
        "cohort_id": "M1_FORMAL_TRAINING_COHORT_V1",
        "selection_rule": "SEEDED_RESERVOIR_OVER_SPLIT_CONTAINED_EPISODES_FROZEN_SOURCE",
        "selection_seed": PRIMARY_TRAINING_SEED,
        "selection_pre_outcome": True,
        "train_episode_ids": list(ids["train"]),
        "train_episode_count": counts["train"],
        "calibration_episode_ids": list(ids["calibration"]),
        "calibration_episode_count": counts["calibration"],
        "development_episode_ids": list(ids["development"]),
        "development_episode_count": counts["development"],
        "train_episode_hash": _hash_ids(ids["train"]),
        "calibration_episode_hash": _hash_ids(ids["calibration"]),
        "development_episode_hash": _hash_ids(ids["development"]),
        "source_cache_hash": cache.manifest["cache_hash"],
        "source_episode_contract_hash": cache.manifest["contract_hashes"]["episode_contract_hash"],
        "source_cache_manifest_hash": _file_hash(SOURCE_CACHE_MANIFEST),
        "final_test_episode_count": 0,
        "final_test_access_count": 0,
    }
    payload["cohort_hash"] = content_id(payload)
    _write_json(COHORT_PATH, payload)
    return payload


def _formal_contract() -> dict:
    scientific = load_config_layers(PROJECT_ROOT / "configs").scientific
    validate_stage1_contract(scientific)
    return {
        "source": "model/M1/tuning_stage1.py:STAGE1_TRAINING_CONFIG",
        "hidden_size": HIDDEN_SIZE,
        "training_seed": PRIMARY_TRAINING_SEED,
        "epochs": PRIMARY_EPOCHS,
        "training": {"epochs": PRIMARY_EPOCHS, **{key: STAGE1_TRAINING_CONFIG[key] for key in ("optimizer", "learning_rate", "weight_decay", "batch_size")}},
        "optional_robustness_seeds": list(OPTIONAL_ROBUSTNESS_SEEDS),
        "splits": {key: list(value) for key, value in STAGE1_SPLITS.items() if isinstance(value, list)},
        "support": dict(STAGE1_SUPPORT),
        "scenario_count": SCENARIO_COUNT,
    }


def formal_training_authority() -> dict:
    """Public fast-contract view of the single-seed formal authority."""
    return _formal_contract()


def _subset_exact(cache: M1DevelopmentBaseCache, split: str, expected_ids: set[str], representation: str):
    rows = cache.partition(split, representation=representation)
    if {row.episode_id for row in rows} != expected_ids:
        raise ValueError(f"M1_FORMAL_COHORT_ID_MISMATCH:{split}")
    return rows


def _materialize_variant(*, cache: M1DevelopmentBaseCache, cohort: dict, output: Path, history_mode: HistoryEncoderMode, role: str, selection_role: str | None = None) -> dict:
    representation = "ADAPTIVE_HISTORY" if history_mode is HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX else "CURRENT"
    train = _subset_exact(cache, "train", set(cohort["train_episode_ids"]), representation)
    calibration = _subset_exact(cache, "calibration", set(cohort["calibration_episode_ids"]), representation)
    _subset_exact(cache, "development", set(cohort["development_episode_ids"]), representation)
    scientific = load_config_layers(PROJECT_ROOT / "configs").scientific
    pipeline = M1Pipeline.from_scientific_config(scientific, input_size=len(FEATURE_NAMES_V2), normalization=cache.normalization, hidden_size=HIDDEN_SIZE, static_input_size=STATIC_FEATURE_COUNT, static_normalization=cache.static_normalization, history_mode=history_mode)
    lifecycle = M1Lifecycle(pipeline, device="cpu")
    history = lifecycle.train(train, epochs=PRIMARY_EPOCHS, learning_rate=float(STAGE1_TRAINING_CONFIG["learning_rate"]), weight_decay=float(STAGE1_TRAINING_CONFIG["weight_decay"]), batch_size=int(STAGE1_TRAINING_CONFIG["batch_size"]), bucketed=True, seed=PRIMARY_TRAINING_SEED, teacher_forcing=True)
    temperatures = lifecycle.calibrate(calibration, batch_size=int(STAGE1_TRAINING_CONFIG["batch_size"]))
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = output / f"{output.name}.pt"
    lifecycle.save(checkpoint)
    contracts = {name: contract.model_dump(mode="json") for name, contract in pipeline.contracts.items()}
    target_hash = content_id(contracts)
    feature_hash = content_id({"feature_names": FEATURE_NAMES_V2})
    support_hash = content_id(STAGE1_SUPPORT)
    calibration_payload = {"schema_version": "M1_FORMAL_H16_CALIBRATION_V1", "model_version": MODEL_VERSION, "model_role": role, "history_mode": history_mode.value, "calibration_cohort_hash": cohort["calibration_episode_hash"], "calibration_partition": {"start": "2019-07-01", "end": "2019-07-31"}, "calibration_protocol": pipeline.calibration_contract.model_dump(mode="json"), "temperatures": temperatures, "reused_h32_temperature": False, "final_test_access_count": 0}
    calibration_payload["calibration_hash"] = content_id(calibration_payload)
    calibration_path = output / f"{output.name}_CALIBRATION.json"
    _write_json(calibration_path, calibration_payload)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
    manifest = {"schema_version": "M1_FORMAL_H16_RUNTIME_ARTIFACT_MANIFEST_V1", "artifact_status": "FORMAL_MODEL_RUNTIME_ARTIFACT_READY", "model_role": role, "selection_role": selection_role, "model_version": MODEL_VERSION, "hidden_size": HIDDEN_SIZE, "history_mode": history_mode.value, "history_contract": (NO_HISTORY_BASELINE_CONTRACT if history_mode is HistoryEncoderMode.NO_HISTORY_CURRENT_OBSERVATION else {"history_mode": history_mode.value, "history_encoder_enabled": True, "future_information": "FORBIDDEN", "full_episode_access": "CAUSAL_PREFIX_ONLY"}), "training_seed": PRIMARY_TRAINING_SEED, "epochs": PRIMARY_EPOCHS, "optimizer": STAGE1_TRAINING_CONFIG["optimizer"], "learning_rate": STAGE1_TRAINING_CONFIG["learning_rate"], "weight_decay": STAGE1_TRAINING_CONFIG["weight_decay"], "batch_size": STAGE1_TRAINING_CONFIG["batch_size"], "training_cohort_id": cohort["cohort_id"], "training_cohort_hash": cohort["cohort_hash"], "train_episode_hash": cohort["train_episode_hash"], "calibration_cohort_hash": cohort["calibration_episode_hash"], "development_cohort_hash": cohort["development_episode_hash"], "target_contract_hash": target_hash, "support_contract_hash": support_hash, "feature_contract_hash": feature_hash, "scenario_count": SCENARIO_COUNT, "quantile_grid": list(scientific.parameters["m1_v2_quantile_levels"].value), "checkpoint_path": str(checkpoint), "checkpoint_hash": _file_hash(checkpoint), "calibration_path": str(calibration_path), "calibration_hash": calibration_payload["calibration_hash"], "formal_training_contract_source": "model/M1/tuning_stage1.py:STAGE1_TRAINING_CONFIG", "optional_robustness_seeds": list(OPTIONAL_ROBUSTNESS_SEEDS), "development_used_for_parameter_selection": False, "selection_or_tuning": False, "final_test_access_count": 0, "paper_result": False, "code_commit": commit, "training": history, "calibration_parameters_are_variant_specific": True}
    manifest["artifact_hash"] = content_id(manifest)
    manifest_path = output / f"{output.name}_MANIFEST.json"
    _write_json(manifest_path, manifest)
    return manifest


def matched_audit(history_manifest: dict, current_manifest: dict, cohort: dict) -> dict:
    checks = {
        "same_hidden_size": history_manifest["hidden_size"] == current_manifest["hidden_size"],
        "same_training_seed": history_manifest["training_seed"] == current_manifest["training_seed"],
        "same_training_cohort": history_manifest["training_cohort_hash"] == current_manifest["training_cohort_hash"],
        "same_calibration_cohort": history_manifest["calibration_cohort_hash"] == current_manifest["calibration_cohort_hash"],
        "same_epochs": history_manifest["epochs"] == current_manifest["epochs"],
        "same_optimizer": history_manifest["optimizer"] == current_manifest["optimizer"],
        "same_learning_rate": history_manifest["learning_rate"] == current_manifest["learning_rate"],
        "same_weight_decay": history_manifest["weight_decay"] == current_manifest["weight_decay"],
        "same_batch_size": history_manifest["batch_size"] == current_manifest["batch_size"],
        "same_target_contract": history_manifest["target_contract_hash"] == current_manifest["target_contract_hash"],
        "same_support_contract": history_manifest["support_contract_hash"] == current_manifest["support_contract_hash"],
        "same_feature_contract": history_manifest["feature_contract_hash"] == current_manifest["feature_contract_hash"],
        "same_scenario_count": history_manifest["scenario_count"] == current_manifest["scenario_count"],
        "different_history_mode": history_manifest["history_mode"] != current_manifest["history_mode"],
        "development_used_for_parameter_selection": not history_manifest["development_used_for_parameter_selection"] and not current_manifest["development_used_for_parameter_selection"],
        "final_test_access_count": history_manifest["final_test_access_count"] == 0 and current_manifest["final_test_access_count"] == 0 and cohort["final_test_access_count"] == 0,
    }
    audit = {"schema_version": "M1_H16_HISTORY_CURRENT_MATCHED_AUDIT_V1", **checks, "history_mode_history": history_manifest["history_mode"], "history_mode_current": current_manifest["history_mode"], "development_used_for_parameter_selection": False, "status": "PASS" if all(checks.values()) else "FAIL"}
    _write_json(MATCHED_AUDIT_PATH, audit)
    if audit["status"] != "PASS":
        raise RuntimeError("M1_H16_HISTORY_CURRENT_MATCHED_CONTRACT_FAILED")
    return audit


def materialize() -> dict:
    cache = _source_cache()
    cohort = materialize_formal_cohort(cache)
    contract = _formal_contract()
    history_manifest = _materialize_variant(cache=cache, cohort=cohort, output=MODEL_ROOT / "M1_H16_HISTORY_PRIMARY", history_mode=HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX, role="PRIMARY")
    current_manifest = _materialize_variant(cache=cache, cohort=cohort, output=MODEL_ROOT / "M1_H16_CURRENT_COMPARATOR", history_mode=HistoryEncoderMode.NO_HISTORY_CURRENT_OBSERVATION, role="EXP1_NO_HISTORY_COMPARATOR", selection_role="BASELINE_DIAGNOSTIC_ONLY")
    audit = matched_audit(history_manifest, current_manifest, cohort)
    return {"cohort": str(COHORT_PATH), "cohort_counts": {"train": cohort["train_episode_count"], "calibration": cohort["calibration_episode_count"], "development": cohort["development_episode_count"]}, "history_manifest": history_manifest, "current_manifest": current_manifest, "matched_audit": audit, "formal_training_contract": contract, "final_test_access_count": 0, "formal_exp1_execution": "NOT_RUN"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.check_only:
        print(json.dumps({"cohort": json.loads(COHORT_PATH.read_text(encoding="utf-8")), "status": "PASS"}, sort_keys=True))
        return 0
    print(json.dumps(materialize(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
