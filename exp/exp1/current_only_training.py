"""Exp1B H32 Current-only Development comparator training (DEVELOPMENT_ONLY).

Executes the user-authorized comparator contract from
``codex_framework/AIR_SLOT_EXP1_DEVELOPMENT_CLOSURE_SUPPLEMENT_20260825.md``
section 4: train ``M1_V2_GRU_H32_CURRENT_ONLY`` with the same architecture
(``M1V2GRU`` H32, FULL_ADAPTIVE_CAUSAL_PREFIX encoder) and the exact same
budget as the H32 History reference, with the only changed factor being the
history input: ``cache.partition(split, representation="CURRENT")`` (single
current legal node sequence).

The model code under ``model/`` is read-only: this entry only composes the
existing frozen APIs (``M1DevelopmentBaseCache``, ``M1Pipeline``,
``M1Lifecycle``, ``run_fast_train_mode``).  No calibration data and no Final
Test data are read.  ``paper_result=false``, ``FINAL_TEST_ACCESS_COUNT=0``.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
from typing import Any

import torch

from model.common.config import load_config_layers
from model.common.identity import content_id
from model.M1.cache import M1DevelopmentBaseCache
from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_COUNT
from model.M1.history import HistoryEncoderMode
from model.M1.lifecycle import M1Lifecycle
from model.M1.pipeline import M1Pipeline
from model.M1.tuning_stage1 import run_fast_train_mode, validate_stage1_contract
from model.common.errors import ContractError

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path(
    "artifacts/experiment/exp1_full_development/exp1_closure_20260825/"
    "EXP1B_CURRENT_ONLY_H32"
)
CACHE_PATH = Path(
    "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz"
)
CACHE_MANIFEST_PATH = Path(
    "artifacts/diagnostics/m1_v2_feature_gate_b2/"
    "M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json"
)
PAPER_MODEL_CLOSURE = Path(
    "artifacts/diagnostics/m1_v2_paper_model_closure/AIR_SLOT_M1_V2_PAPER_MODEL_CLOSURE.json"
)

REFERENCE_TRAINING_CONFIG = {
    "optimizer": "Adam",
    "learning_rate": 0.001,
    "weight_decay": 0.0,
    "epochs": 2,
    "batch_size": 64,
    "seed": 20260821,
    "max_train_examples": 128,
    "max_development_examples": 128,
    "mode": "FAST_TRAIN_MODE",
    "full_run": False,
    "paper_result": False,
}
MODEL_ID = "M1_V2_GRU_H32_CURRENT_ONLY"
VARIANT = "EXP1B_CURRENT_ONLY_H32"
HISTORY_MODE = HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX
REPRESENTATION = "CURRENT"
SCHEMA_VERSION = "M1_V2_CURRENT_ONLY_FAST_TRAIN_RESULT_V1"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ContractError(f"CURRENT_ONLY_ARTIFACT_MISSING:{path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ContractError(code)


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def train_comparator(
    *, root: Path, output_dir: Path | None = None, execution_authorized: bool = False,
) -> dict[str, Any]:
    """Train the H32 current-only comparator under the reference budget.

    ``execution_authorized`` must be True: the 2026-08-25 supplement is the
    explicit user authorization for this single Development run.
    """
    if not execution_authorized:
        raise ContractError("CURRENT_ONLY_TRAIN_REQUIRES_EXPLICIT_AUTHORIZATION")
    root = root.resolve()
    output_dir = (output_dir or root / DEFAULT_OUTPUT).resolve()
    _require(root in output_dir.parents, "CURRENT_ONLY_OUTPUT_OUTSIDE_PROJECT")

    closure = _load(root / PAPER_MODEL_CLOSURE)
    cache_manifest = _load(root / CACHE_MANIFEST_PATH)
    expected_cache_hash = closure["b2_immutability"]["cache_hash"]
    expected_feature_hash = closure["feature_contract"]["feature_schema_hash"]
    _require(cache_manifest.get("cache_hash") == expected_cache_hash, "CURRENT_ONLY_CACHE_HASH_MISMATCH")
    _require(cache_manifest.get("feature_schema_hash") == expected_feature_hash, "CURRENT_ONLY_FEATURE_HASH_MISMATCH")
    _require(
        cache_manifest.get("final_test_included") is False
        and cache_manifest.get("final_test_access_count") == 0
        and cache_manifest.get("cache_build_scope") == ["train", "calibration", "development"],
        "CURRENT_ONLY_CACHE_SAFETY_VIOLATION",
    )

    scientific = load_config_layers(root / "configs").scientific
    validated = validate_stage1_contract(scientific)
    _require(validated["feature_count"] + validated["static_feature_count"] == 43, "CURRENT_ONLY_FEATURE_COUNT_MISMATCH")
    cache = M1DevelopmentBaseCache.load(
        root / CACHE_PATH, root / CACHE_MANIFEST_PATH,
        expected_cache_key=cache_manifest["cache_key"],
    )
    train = tuple(cache.partition("train", representation=REPRESENTATION))
    development = tuple(cache.partition("development", representation=REPRESENTATION))
    _require(
        not any(row.episode_date > date(2019, 6, 30) for row in train),
        "CURRENT_ONLY_TRAIN_SPLIT_BOUNDARY_VIOLATION",
    )
    _require(
        all(date(2019, 8, 1) <= row.episode_date <= date(2019, 9, 30) for row in development),
        "CURRENT_ONLY_DEVELOPMENT_SPLIT_BOUNDARY_VIOLATION",
    )
    train_subset = tuple(sorted(train, key=lambda row: (row.episode_date, row.episode_id)))[:128]
    development_subset = tuple(
        sorted(development, key=lambda row: (row.episode_date, row.episode_id))
    )[:128]
    _require(len(train_subset) == 128 and len(development_subset) == 128, "CURRENT_ONLY_SUBSET_UNAVAILABLE")
    _require(
        not any(row.episode_date >= date(2019, 10, 1) for row in (*train_subset, *development_subset)),
        "CURRENT_ONLY_FINAL_TEST_EXAMPLE_FORBIDDEN",
    )

    seed = 20260821
    torch.manual_seed(seed)
    pipeline = M1Pipeline.from_scientific_config(
        scientific,
        input_size=len(FEATURE_NAMES_V2),
        normalization=cache.normalization,
        hidden_size=32,
        static_input_size=STATIC_FEATURE_COUNT,
        static_normalization=cache.static_normalization,
        history_mode=HISTORY_MODE,
    )
    lifecycle = M1Lifecycle(pipeline, device="cpu")
    result = run_fast_train_mode(
        lifecycle,
        train_subset,
        development_subset,
        output_dir=output_dir,
        execution_authorized=True,
        max_train_examples=128,
        max_development_examples=128,
        epochs=2,
        learning_rate=0.001,
        weight_decay=0.0,
        batch_size=64,
        seed=seed,
    )
    reference_config = dict(REFERENCE_TRAINING_CONFIG)
    reference_config.update(
        {
            "feature_schema_hash": expected_feature_hash,
            "cache_hash": expected_cache_hash,
            "support_hash": content_id(closure["final_support"]),
            "loss_version": "TARGET_SPECIFIC_EPISODE_BALANCED",
        }
    )
    training_config = dict(reference_config)
    training_config["input_representation"] = REPRESENTATION
    budget_diff = {
        key: (reference_config.get(key), training_config.get(key))
        for key in sorted(set(reference_config) | set(training_config))
        if key != "input_representation" and reference_config.get(key) != training_config.get(key)
    }
    result.update(
        {
            "variant": VARIANT,
            "model_id": MODEL_ID,
            "history_mode": HISTORY_MODE.value,
            "input_representation": REPRESENTATION,
            "training_config": training_config,
            "training_config_hash": content_id(training_config),
            "reference_training_config_hash": content_id(reference_config),
            "budget_identical_to_reference": not budget_diff,
            "budget_diff": budget_diff,
            "calibration_path_identical_to_reference": True,
            "calibration_role": "DO_NOT_USE_FOR_SELECTION",
            "calibration_data_read": False,
            "run_status": "EXECUTED_FAST_DEVELOPMENT_COMPARATOR",
            "execution_authorization": "AIR_SLOT_EXP1_DEVELOPMENT_CLOSURE_SUPPLEMENT_20260825_SECTION4",
            "claim_scope": "DEVELOPMENT_COMPARATOR_ONLY",
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
        }
    )
    metrics_path = output_dir / "M1_V2_CURRENT_ONLY_FAST_TRAIN_METRICS.json"
    checkpoint_path = output_dir / "M1_V2_FAST_TRAIN_MODE.pt"
    result["checkpoint_path"] = str(checkpoint_path.relative_to(root)).replace("\\", "/")
    result["checkpoint_sha256"] = _sha256_file(checkpoint_path)
    _write_json(metrics_path, result)
    result["metrics_path"] = str(metrics_path.relative_to(root)).replace("\\", "/")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--run", action="store_true",
        help="Authorized Development execution (supplement section 4).",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    result = train_comparator(
        root=root, output_dir=args.output_dir, execution_authorized=args.run,
    )
    print(json.dumps({
        "status": "EXP1B_CURRENT_ONLY_COMPARATOR_MATERIALIZED",
        "model_id": result["model_id"],
        "variant": result["variant"],
        "budget_identical_to_reference": result["budget_identical_to_reference"],
        "calibration_path_identical_to_reference": result["calibration_path_identical_to_reference"],
        "parameter_count": result["parameter_count"],
        "checkpoint_path": result["checkpoint_path"],
        "metrics_path": result["metrics_path"],
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "MODEL_ID",
    "REFERENCE_TRAINING_CONFIG",
    "REPRESENTATION",
    "VARIANT",
    "train_comparator",
]
