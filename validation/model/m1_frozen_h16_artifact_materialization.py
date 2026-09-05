"""Materialize the fixed-contract H16 M1 primary artifact.

The active H16 model is materialized once from the existing frozen Train and
July 2019 calibration partitions.  This is not a tuning runner: optimizer,
epoch count, seed, target support, quantile grid, and calibration procedure
come from the existing frozen contracts.  Development is retained only for
the bounded diagnostic emitted by the shared materializer; it cannot select
any parameter.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from hashlib import sha256
from pathlib import Path

from model.M1.development_diagnostics import require_training_target_coverage, target_coverage
from model.M1.development_training import (
    CACHE_MANIFEST_NAME,
    CACHE_NAME,
    _build_or_load_cache,
    _load_fast_config,
    _load_references,
)
from model.M1.history import HistoryEncoderMode
from model.M1.lifecycle import M1Lifecycle
from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_COUNT
from model.M1.pipeline import M1Pipeline
from model.common.config import load_config_layers
from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT


OUTPUT = PROJECT_ROOT / "artifacts" / "models" / "m1" / "M1_FROZEN_H16"
HIDDEN_SIZE = 16
MODEL_VERSION = "M1_STATE_ESTIMATOR_V2_H16"
SUPPORT = {
    "T_IB_REMAINING_HAZARD": 360,
    "D_OB": 180,
    "D_TX": 60,
}


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def materialize(output: Path = OUTPUT) -> dict:
    output = Path(output).resolve()
    if output == PROJECT_ROOT or PROJECT_ROOT not in output.parents:
        raise ValueError("M1_H16_OUTPUT_OUTSIDE_PROJECT_FORBIDDEN")

    scientific = load_config_layers(PROJECT_ROOT / "configs").scientific
    if int(scientific.parameters["m1_hidden_size"].value) != HIDDEN_SIZE:
        raise ValueError("M1_H16_PRIMARY_SCIENTIFIC_CONTRACT_MISMATCH")
    if int(scientific.parameters["m1_sensitivity_hidden_size"].value) != 8:
        raise ValueError("M1_H8_LOWER_CAPACITY_SENSITIVITY_CONTRACT_MISMATCH")
    if int(scientific.parameters["scenario_count"].value) != 64:
        raise ValueError("M1_SCENARIO_COUNT_CONTRACT_MISMATCH")

    config, fast_config_hash = _load_fast_config(PROJECT_ROOT)
    taxi, turnaround, references = _load_references(PROJECT_ROOT)
    cache, _, cache_status = _build_or_load_cache(
        PROJECT_ROOT, output, config, scientific, taxi, turnaround
    )
    train = tuple(cache.partition("train"))
    calibration = tuple(cache.partition("calibration"))
    train_coverage = target_coverage(train)
    calibration_coverage = target_coverage(calibration)
    require_training_target_coverage(train_coverage)
    pipeline = M1Pipeline.from_scientific_config(
        scientific,
        input_size=len(FEATURE_NAMES_V2),
        normalization=cache.normalization,
        hidden_size=HIDDEN_SIZE,
        static_input_size=STATIC_FEATURE_COUNT,
        static_normalization=cache.static_normalization,
    )
    lifecycle = M1Lifecycle(pipeline, device=str(config["training"]["device"]))
    batch_size = int(config["training"]["batch_size"])
    history = lifecycle.train(
        train,
        epochs=int(config["training"]["epochs"]),
        learning_rate=float(config["training"]["learning_rate"]),
        batch_size=batch_size,
        bucketed=True,
        seed=int(config["training"]["seed"]),
        teacher_forcing=True,
    )
    temperatures = lifecycle.calibrate(calibration, batch_size=batch_size)
    checkpoint = output / "DATA2_M1_V2_DEVELOPMENT_FAST.pt"
    lifecycle.save(checkpoint)
    training_manifest = {
        "schema_version": "M1_FROZEN_H16_TRAINING_MANIFEST_V1",
        "dataset": "DATA2_2019",
        "train_split": config["partitions"]["train"],
        "calibration_split": config["partitions"]["calibration"],
        "development_split": config["partitions"]["development"],
        "seed": int(config["training"]["seed"]),
        "epochs": int(config["training"]["epochs"]),
        "batch_size": batch_size,
        "hidden_size": HIDDEN_SIZE,
        "input_schema_hash": content_id({"feature_names": FEATURE_NAMES_V2}),
        "normalization_fitted_split": cache.normalization.fitted_split,
        "train_counts": train_coverage,
        "calibration_counts": calibration_coverage,
        "cache": {**cache_status, "path": str(output / CACHE_NAME), "manifest": str(output / CACHE_MANIFEST_NAME)},
        "training": history,
        "calibration": {"temperatures": temperatures},
        "final_test_access_count": 0,
        "development_used_for_parameter_selection": False,
        "development_diagnostics": "NOT_RUN",
        "scenario_generation": "NOT_RUN",
        "fast_config_hash": fast_config_hash,
        "references": references,
    }
    training_manifest_path = output / "M1_FROZEN_H16_TRAINING_MANIFEST.json"
    _write_json(training_manifest_path, training_manifest)
    training_manifest = json.loads(training_manifest_path.read_text(encoding="utf-8"))
    pipeline = M1Pipeline.load(checkpoint)
    actual_support = {
        name: int(contract.max_finite_minutes)
        for name, contract in pipeline.contracts.items()
    }
    if pipeline.model.hidden_size != HIDDEN_SIZE:
        raise RuntimeError("M1_H16_PRIMARY_HIDDEN_SIZE_MISMATCH_AFTER_MATERIALIZATION")
    if pipeline.history_mode is not HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX:
        raise RuntimeError("M1_H16_PRIMARY_HISTORY_MODE_MISMATCH")
    if actual_support != SUPPORT:
        raise RuntimeError("M1_H16_PRIMARY_SUPPORT_MISMATCH_AFTER_MATERIALIZATION")
    if pipeline.normalization is None or pipeline.normalization.fitted_split != "train":
        raise RuntimeError("M1_H16_NORMALIZATION_NOT_TRAIN_FITTED")
    if training_manifest.get("calibration_split") != {
        "start": "2019-07-01",
        "end": "2019-07-31",
    }:
        raise RuntimeError("M1_H16_CALIBRATION_SPLIT_MISMATCH")
    if training_manifest.get("final_test_access_count") != 0:
        raise RuntimeError("M1_H16_FINAL_TEST_ACCESS_NONZERO")

    contracts_json = {
        name: contract.model_dump(mode="json")
        for name, contract in pipeline.contracts.items()
    }
    calibration_payload = {
        "schema_version": "M1_FROZEN_H16_CALIBRATION_ARTIFACT_V1",
        "model_version": MODEL_VERSION,
        "model_role": "PRIMARY",
        "support": SUPPORT,
        "calibration_contract": pipeline.calibration_contract.model_dump(
            mode="json"
        ),
        "temperatures": temperatures,
        "diagnostics": pipeline.calibration_diagnostics,
        "calibration_partition": training_manifest["calibration_split"],
        "calibration_source": "FROZEN_JULY_2019_CALIBRATION_SPLIT",
        "reused_h32_temperature": False,
        "final_test_access_count": 0,
    }
    calibration_payload["calibration_hash"] = content_id(calibration_payload)
    calibration_path = output / "M1_FROZEN_H16_CALIBRATION.json"
    _write_json(calibration_path, calibration_payload)

    target_manifest = {
        "schema_version": "M1_FROZEN_H16_TARGET_SUPPORT_MANIFEST_V1",
        "model_version": MODEL_VERSION,
        "primitive_targets": ["T_IB_A00", "D_OB", "D_TX"],
        "conditional_order": ["T_IB_A00", "D_OB", "D_TX"],
        "derived_targets": ["R_IB", "D_TO"],
        "support": SUPPORT,
        "overflow": {"T_IB_A00": 365, "D_OB": 185, "D_TX": 65},
        "bin_width_minutes": 5,
        "target_contract_hash": content_id(contracts_json),
        "final_test_access_count": 0,
    }
    target_manifest["target_manifest_hash"] = content_id(target_manifest)
    target_path = output / "M1_FROZEN_H16_TARGET_SUPPORT_MANIFEST.json"
    _write_json(target_path, target_manifest)

    checkpoint_hash = _file_hash(checkpoint)
    registry_hash = _file_hash(
        PROJECT_ROOT / "registries" / "MODEL_PARAMETER_REGISTRY.json"
    )
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
    ).strip()
    frozen_manifest = {
        "schema_version": "M1_FROZEN_H16_RUNTIME_ARTIFACT_MANIFEST_V1",
        "artifact_status": "FROZEN_MODEL_RUNTIME_ARTIFACT_READY",
        "model_family": "M1_STATE_ESTIMATOR_V2",
        "model_version": MODEL_VERSION,
        "model_role": "PRIMARY",
        "hidden_dim": HIDDEN_SIZE,
        "lower_capacity_sensitivity_hidden_dim": 8,
        "layers": 1,
        "causal": True,
        "history": "FULL_ADAPTIVE_CAUSAL_PREFIX",
        "roll_minutes": int(scientific.parameters["roll_minutes"].value),
        "support": SUPPORT,
        "overflow": {"T_IB_A00": 365, "D_OB": 185, "D_TX": 65},
        "scenario_count": int(scientific.parameters["scenario_count"].value),
        "feature_contract_hash": training_manifest.get("input_schema_hash"),
        "target_contract_hash": target_manifest["target_contract_hash"],
        "parameter_registry_hash": registry_hash,
        "code_commit": commit,
        "train_partition": training_manifest.get("train_split"),
        "calibration_partition": training_manifest.get("calibration_split"),
        "development_partition": training_manifest.get("development_split"),
        "training_seed": training_manifest.get("seed"),
        "checkpoint_path": str(checkpoint),
        "checkpoint_hash": checkpoint_hash,
        "calibration_path": str(calibration_path),
        "calibration_hash": calibration_payload["calibration_hash"],
        "target_manifest_path": str(target_path),
        "final_test_access_count": 0,
        "paper_result": False,
        "selection_or_tuning": False,
        "development_used_for_parameter_selection": False,
    }
    frozen_manifest["artifact_hash"] = content_id(frozen_manifest)
    frozen_path = output / "M1_FROZEN_H16_MANIFEST.json"
    _write_json(frozen_path, frozen_manifest)
    return {
        "status": "M1_H16_PRIMARY_MATERIALIZED",
        "checkpoint": str(checkpoint),
        "calibration": str(calibration_path),
        "manifest": str(frozen_path),
        "checkpoint_hash": checkpoint_hash,
        "calibration_hash": calibration_payload["calibration_hash"],
        "target_manifest_hash": target_manifest["target_manifest_hash"],
        "final_test_access_count": 0,
        "development_used_for_parameter_selection": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(materialize(args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
