"""Read-only preparation and evaluation contracts for M1 V2 Stage 1.

This module performs no automatic training. It defines the narrow H sensitivity
manifest, the no-history baseline contract, the Development metric projection,
and a separately guarded FAST entry point used only after authorization.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
import subprocess
from typing import Sequence

import torch

from model.common.identity import content_id

from .contracts import (
    HazardBinContract,
    HurdleQuantileContract,
)
from .data import FEATURE_NAMES_V2, STATIC_FEATURE_COUNT
from .history import HistoryEncoderMode
from .lifecycle import M1Lifecycle
from .pipeline import M1Pipeline
from .network import M1V2GRU
from .semantics import EVALUATION_ONLY_FORECAST_HORIZONS_MINUTES


STAGE1_H_CANDIDATES: tuple[int, ...] = (8, 16, 32)
STAGE1_METRICS: tuple[str, ...] = (
    "EPISODE_BALANCED_JOINT_VALIDATION_LOSS",
    "T_IB_HAZARD_NLL",
    "D_OB_ZERO_BCE",
    "D_OB_POSITIVE_QUANTILE_LOSS",
    "D_TX_ZERO_BCE",
    "D_TX_POSITIVE_QUANTILE_LOSS",
)
STAGE1_TRAINING_CONFIG = {
    "optimizer": "Adam",
    "learning_rate": 0.001,
    "weight_decay": 0.0,
    "epochs": 8,
    "batch_size": 64,
    "paired_training_seeds": [20260813, 20260814, 20260815, 20260816, 20260817],
    "selection_aggregation": "MEAN_ACROSS_PAIRED_SEEDS",
}
STAGE1_SPLITS = {
    "train": ["2019-01-01", "2019-06-30"],
    "calibration": ["2019-07-01", "2019-07-31"],
    "development": ["2019-08-01", "2019-09-30"],
    "final_test": "LOCKED_NOT_ACCESSED",
}
STAGE1_SUPPORT = {
    "T_IB_REMAINING_HAZARD": 360,
    "D_OB": 210,
    "D_TX": 60,
    "bin_width_minutes": 5,
}
NO_HISTORY_BASELINE_CONTRACT = {
    "history_mode": HistoryEncoderMode.NO_HISTORY_CURRENT_OBSERVATION.value,
    "history_encoder_enabled": False,
    "input_contract": "CURRENT_ADMISSIBLE_OBSERVATION_ONLY",
    "future_information": "FORBIDDEN",
    "full_episode_access": "FORBIDDEN",
    "selection_role": "BASELINE_DIAGNOSTIC_ONLY",
}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    temporary.replace(path)


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _checkpoint_roundtrip(
    lifecycle: M1Lifecycle,
    development_examples: Sequence,
    *,
    checkpoint_path: Path,
    batch_size: int,
) -> dict[str, object]:
    """Prove that the saved FAST candidate reproduces its held-out logits."""

    probe = tuple(development_examples[: min(16, len(development_examples))])
    lifecycle.pipeline.model.eval()
    before, _, _, _ = lifecycle.batched_logits(
        probe, batch_size=batch_size, teacher_forcing=True,
    )
    lifecycle.save(checkpoint_path)
    loaded = M1Lifecycle.load(checkpoint_path, device=str(lifecycle.device))
    loaded.pipeline.model.eval()
    after, _, _, _ = loaded.batched_logits(
        probe, batch_size=batch_size, teacher_forcing=True,
    )
    differences = {
        name: float((before[name] - after[name]).abs().max())
        for name in before
    }
    passed = all(value <= 1e-5 for value in differences.values())
    if not passed:
        raise ValueError("M1_V2_STAGE1_FAST_CHECKPOINT_ROUNDTRIP_FAILED")
    return {
        "status": "PASS",
        "probe_example_count": len(probe),
        "max_abs_difference": max(differences.values(), default=0.0),
        "per_head_max_abs_difference": differences,
        "checkpoint_sha256": _file_hash(checkpoint_path),
    }


def stage1_development_metrics(
    lifecycle,
    examples: Sequence,
    *,
    batch_size: int | None = None,
) -> dict[str, float]:
    """Project the existing episode-balanced objective into the Stage 1 schema."""

    raw = lifecycle.episode_balanced_objective(
        examples, batch_size=batch_size, teacher_forcing=True,
    )
    aliases = {
        "EPISODE_BALANCED_JOINT_VALIDATION_LOSS":
            "EPISODE_BALANCED_JOINT_VALIDATION_LOSS",
        "T_IB_HAZARD_NLL": "T_IB_HAZARD_NLL",
        "D_OB_ZERO_BCE": "D_OB_ZERO_BCE",
        "D_OB_POSITIVE_QUANTILE_LOSS": "D_OB_POSITIVE_PINBALL",
        "D_TX_ZERO_BCE": "D_TX_ZERO_BCE",
        "D_TX_POSITIVE_QUANTILE_LOSS": "D_TX_POSITIVE_PINBALL",
    }
    missing = [name for name, source in aliases.items() if source not in raw]
    if missing:
        raise ValueError(f"M1_V2_STAGE1_METRICS_MISSING:{','.join(missing)}")
    return {name: float(raw[source]) for name, source in aliases.items()}


def validate_stage1_contract(scientific) -> dict[str, object]:
    """Validate only the frozen contracts required by Stage 1 preparation."""

    candidates = tuple(
        int(value) for value in scientific.parameters[
            "m1_hidden_size_candidates"
        ].value
    )
    if candidates != STAGE1_H_CANDIDATES:
        raise ValueError(f"M1_V2_STAGE1_H_CANDIDATES_MISMATCH:{candidates}")
    support = {
        "T_IB_REMAINING_HAZARD": scientific.parameters[
            "m1_v2_t_ib_remaining_max_finite_minutes"
        ].value,
        "D_OB": scientific.parameters["m1_v2_d_ob_max_finite_minutes"].value,
        "D_TX": scientific.parameters["m1_v2_d_tx_max_finite_minutes"].value,
        "bin_width_minutes": scientific.parameters["m1_bin_width_minutes"].value,
    }
    if support != STAGE1_SUPPORT:
        raise ValueError(f"M1_V2_STAGE1_SUPPORT_MISMATCH:{support}")
    return {
        "feature_count": len(FEATURE_NAMES_V2),
        "static_feature_count": STATIC_FEATURE_COUNT,
        "support": support,
        "candidate_hidden_sizes": list(candidates),
        "split_roles": dict(STAGE1_SPLITS),
        "final_test_access_count": 0,
    }


def exp1_interface_contract() -> dict[str, object]:
    """Describe the existing M1 -> Exp1 artifact boundary without executing it."""

    return {
        "joint_state_distribution_artifact": {
            "producer": "M1Pipeline.sample_from_pre",
            "scenario_identity": ["episode_id", "decision_node_id", "scenario_id", "scenario_seed_key"],
            "status": "READY",
        },
        "marginal_distribution_artifact": {
            "producer": "model.M1.summaries.scenario_marginal_summary",
            "status": "READY",
        },
        "history_lineage": {
            "field": "history_mode",
            "principal": HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX.value,
            "baseline": HistoryEncoderMode.NO_HISTORY_CURRENT_OBSERVATION.value,
            "status": "READY",
        },
        "forecast_horizons_minutes": list(EVALUATION_ONLY_FORECAST_HORIZONS_MINUTES),
        "exp1_mutation": False,
    }


def fast_train_mode_contract() -> dict[str, object]:
    """Return the bounded deterministic-subset execution contract."""

    return {
        "mode": "FAST_TRAIN_MODE",
        "scope": "SMALL_DETERMINISTIC_DEVELOPMENT_SUBSET",
        "purpose": ["pipeline", "checkpoint", "evaluation", "artifact_lineage"],
        "max_train_examples": 128,
        "max_development_examples": 128,
        "max_epochs": 2,
        "paper_result": False,
        "full_run": False,
        "final_test_access_count": 0,
        "tuning_runs": 0,
    }


def stage1_parameter_count(
    hidden_size: int | None,
    *,
    history_mode: HistoryEncoderMode | str = HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX,
) -> int:
    """Count parameters without initializing an optimizer or running training."""

    mode = HistoryEncoderMode(history_mode)
    if mode is HistoryEncoderMode.NO_HISTORY_CURRENT_OBSERVATION:
        hidden = 16 if hidden_size is None else int(hidden_size)
    else:
        if hidden_size not in STAGE1_H_CANDIDATES:
            raise ValueError(f"M1_V2_STAGE1_H_INVALID:{hidden_size}")
        hidden = int(hidden_size)
    hazard = HazardBinContract(bin_width_minutes=5, max_finite_minutes=360)
    d_ob = HurdleQuantileContract(
        target_name="D_OB", bin_width_minutes=5, max_finite_minutes=210,
        quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
        upper_tail_policy="UNRESOLVED",
    )
    d_tx = HurdleQuantileContract(
        target_name="D_TX", bin_width_minutes=5, max_finite_minutes=60,
        quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
        upper_tail_policy="UNRESOLVED",
    )
    model = M1V2GRU(
        len(FEATURE_NAMES_V2), hidden, hazard, d_ob, d_tx,
        fast_input_size=len(FEATURE_NAMES_V2),
        static_input_size=STATIC_FEATURE_COUNT,
        history_mode=mode,
    )
    return sum(parameter.numel() for parameter in model.parameters())


def run_fast_train_mode(
    lifecycle: M1Lifecycle,
    train_examples: Sequence,
    development_examples: Sequence,
    *,
    output_dir: Path,
    execution_authorized: bool = False,
    max_train_examples: int = 32,
    max_development_examples: int = 32,
    epochs: int = 2,
    learning_rate: float = 0.001,
    weight_decay: float = 0.0,
    batch_size: int = 16,
    seed: int = 20260821,
) -> dict[str, object]:
    """Run only an explicitly authorized deterministic Development smoke.

    The default is preparation-only and raises before touching the lifecycle.
    Final-Test dated examples are rejected; no caller can turn this into a
    paper/full run through this bounded helper.
    """

    if not execution_authorized:
        raise RuntimeError("M1_V2_FAST_TRAIN_REQUIRES_EXPLICIT_AUTHORIZATION")
    if (
        max_train_examples <= 0 or max_development_examples <= 0
        or max_train_examples > 128 or max_development_examples > 128
    ):
        raise ValueError("M1_V2_FAST_TRAIN_SUBSET_SIZE_INVALID")
    if epochs <= 0 or epochs > 2:
        raise ValueError("M1_V2_FAST_TRAIN_EPOCH_BOUND_INVALID")
    train = tuple(sorted(train_examples, key=lambda row: (row.episode_date, row.episode_id)))[
        :max_train_examples
    ]
    development = tuple(sorted(
        development_examples, key=lambda row: (row.episode_date, row.episode_id),
    ))[:max_development_examples]
    if not train or not development:
        raise ValueError("M1_V2_FAST_TRAIN_SUBSET_EMPTY")
    if any(row.episode_date >= date(2019, 10, 1)
           for row in (*train, *development)):
        raise ValueError("M1_V2_FAST_FINAL_TEST_EXAMPLE_FORBIDDEN")
    torch.manual_seed(seed)
    training = lifecycle.train(
        train, epochs=epochs, learning_rate=learning_rate,
        weight_decay=weight_decay, batch_size=batch_size,
        seed=seed, teacher_forcing=True,
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / "M1_V2_FAST_TRAIN_MODE.pt"
    roundtrip = _checkpoint_roundtrip(
        lifecycle, development, checkpoint_path=checkpoint, batch_size=batch_size,
    )
    return {
        "schema_version": "M1_V2_FAST_TRAIN_MODE_RESULT_V1",
        "model_id": f"M1_V2_{lifecycle.pipeline.history_mode.value}",
        "hidden_size": lifecycle.pipeline.model.hidden_size,
        "parameter_count": sum(
            parameter.numel() for parameter in lifecycle.pipeline.model.parameters()
        ),
        "training_config_hash": content_id({
            "epochs": epochs, "learning_rate": learning_rate,
            "weight_decay": weight_decay, "batch_size": batch_size,
            "seed": seed,
        }),
        "training_history": training,
        "validation_result": stage1_development_metrics(
            lifecycle, development, batch_size=batch_size,
        ),
        "checkpoint_path": str(checkpoint),
        "checkpoint_roundtrip": roundtrip,
        "paper_result": False,
        "full_run": False,
        "training_counter_semantics": "INCREMENT_ONLY_FOR_THIS_EXPLICITLY_AUTHORIZED_FAST_EXECUTION",
        "M1_TRAINING_RUNS": 1,
        "TUNING_RUNS": 1,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }


def fast_train_mode(*args, **kwargs) -> dict[str, object]:
    """Named Stage 1 FAST execution entry point; authorization remains required."""

    return run_fast_train_mode(*args, **kwargs)


def stage1_training_config_hash() -> str:
    return content_id({
        "training": STAGE1_TRAINING_CONFIG,
        "objective": "TARGET_SPECIFIC_EPISODE_BALANCED",
        "splits": STAGE1_SPLITS,
        "support": STAGE1_SUPPORT,
        "metrics": STAGE1_METRICS,
    })


def stage1_manifest(root: Path) -> dict[str, object]:
    """Build a no-run manifest from the already frozen closure artifacts."""

    root = Path(root)
    from model.common.config import load_config_layers

    scientific = load_config_layers(root / "configs").scientific
    contract = validate_stage1_contract(scientific)
    closure_path = root / (
        "artifacts/diagnostics/m1_v2_paper_model_closure/"
        "AIR_SLOT_M1_V2_PAPER_MODEL_CLOSURE.json"
    )
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    training_hash = stage1_training_config_hash()
    candidates = []
    for hidden_size in STAGE1_H_CANDIDATES:
        candidates.append({
            "model_id": f"M1_V2_STATE_AWARE_H{hidden_size}",
            "hidden_size": hidden_size,
            "history_mode": HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX.value,
            "parameter_count": stage1_parameter_count(hidden_size),
            "training_config_hash": training_hash,
            "validation_result": None,
            "run_status": "NOT_RUN",
        })
    candidates.append({
        "model_id": "M1_V2_NO_HISTORY_BASELINE",
        "hidden_size": 16,
        "history_mode": HistoryEncoderMode.NO_HISTORY_CURRENT_OBSERVATION.value,
        "parameter_count": stage1_parameter_count(
            16, history_mode=HistoryEncoderMode.NO_HISTORY_CURRENT_OBSERVATION,
        ),
        "baseline_reference_hidden_size": 16,
        "training_config_hash": training_hash,
        "validation_result": None,
        "run_status": "NOT_RUN",
    })
    fixed_contract = {
        **contract,
        "total_feature_count": len(FEATURE_NAMES_V2) + STATIC_FEATURE_COUNT,
        "feature_schema_hash": closure["feature_contract"]["feature_schema_hash"],
        "cache_hash": closure["b2_immutability"]["cache_hash"],
        "support_hash": content_id(closure["final_support"]),
        "loss_version": "TARGET_SPECIFIC_EPISODE_BALANCED",
    }
    return {
        "schema_version": "M1_V2_TUNING_STAGE1_MANIFEST_V1",
        "status": "M1_V2_TUNING_STAGE1_READY",
        "execution_authorized": False,
        "decision_id": "AIR_SLOT_M1_V2_TUNING_STAGE1_IMPLEMENTATION",
        "repository_head": "UNSET_UNTIL_EXECUTION",
        "dataset": "DATA2_2019",
        "fixed_contract": fixed_contract,
        "total_feature_count": len(FEATURE_NAMES_V2) + STATIC_FEATURE_COUNT,
        "feature_schema_hash": closure["feature_contract"]["feature_schema_hash"],
        "cache_hash": closure["b2_immutability"]["cache_hash"],
        "support_hash": content_id(closure["final_support"]),
        "loss_version": "TARGET_SPECIFIC_EPISODE_BALANCED",
        "training_config": STAGE1_TRAINING_CONFIG,
        "training_config_hash": training_hash,
        "candidate_list": ["NO_HISTORY", "H8", "H16", "H32"],
        "candidates": candidates,
        "development_evaluation": {
            "principal": STAGE1_METRICS[0],
            "secondary": list(STAGE1_METRICS[1:]),
            "calibration_used_for_selection": False,
            "metric_source": "M1Lifecycle.episode_balanced_objective",
        },
        "no_history_baseline": NO_HISTORY_BASELINE_CONTRACT,
        "exp1_interface": exp1_interface_contract(),
        "fast_train_mode": fast_train_mode_contract(),
        "safety": {
            "M1_TRAINING_RUNS": 0,
            "TUNING_RUNS": 0,
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
        },
    }


def run_fast_stage1_tuning(
    root: Path,
    *,
    output_dir: Path | None = None,
    execution_authorized: bool = False,
) -> dict[str, object]:
    """Execute the authorized four-variant, Development-only FAST comparison.

    This entry point intentionally consumes the B2 frozen cache directly.  It
    neither rebuilds features nor reads calibration or Final Test records, so
    all candidates receive the exact same 128/128 deterministic subset.
    """

    if not execution_authorized:
        raise RuntimeError("M1_V2_STAGE1_FAST_REQUIRES_EXPLICIT_AUTHORIZATION")

    root = Path(root).resolve()
    closure_path = root / (
        "artifacts/diagnostics/m1_v2_paper_model_closure/"
        "AIR_SLOT_M1_V2_PAPER_MODEL_CLOSURE.json"
    )
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    frozen_cache_dir = root / "artifacts/diagnostics/m1_v2_feature_gate_b2"
    cache_path = frozen_cache_dir / "M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz"
    cache_manifest_path = (
        frozen_cache_dir / "M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json"
    )
    cache_manifest = json.loads(cache_manifest_path.read_text(encoding="utf-8"))
    expected_cache_hash = closure["b2_immutability"]["cache_hash"]
    expected_feature_hash = closure["feature_contract"]["feature_schema_hash"]
    if cache_manifest.get("cache_hash") != expected_cache_hash:
        raise ValueError("M1_V2_STAGE1_FAST_CACHE_HASH_MISMATCH")
    if cache_manifest.get("feature_schema_hash") != expected_feature_hash:
        raise ValueError("M1_V2_STAGE1_FAST_FEATURE_HASH_MISMATCH")
    if (
        cache_manifest.get("final_test_included") is not False
        or cache_manifest.get("final_test_access_count") != 0
        or cache_manifest.get("cache_build_scope") != [
            "train", "calibration", "development",
        ]
    ):
        raise ValueError("M1_V2_STAGE1_FAST_CACHE_SAFETY_VIOLATION")

    from model.common.config import load_config_layers

    from .cache import M1DevelopmentBaseCache

    scientific = load_config_layers(root / "configs").scientific
    validated = validate_stage1_contract(scientific)
    if validated["feature_count"] + validated["static_feature_count"] != 43:
        raise ValueError("M1_V2_STAGE1_FAST_FEATURE_COUNT_MISMATCH")
    cache = M1DevelopmentBaseCache.load(
        cache_path,
        cache_manifest_path,
        expected_cache_key=cache_manifest["cache_key"],
    )
    train = tuple(cache.partition("train"))
    development = tuple(cache.partition("development"))
    if any(
        row.episode_date > date(2019, 6, 30) for row in train
    ) or any(
        not date(2019, 8, 1) <= row.episode_date <= date(2019, 9, 30)
        for row in development
    ):
        raise ValueError("M1_V2_STAGE1_FAST_SPLIT_BOUNDARY_VIOLATION")
    train_subset = tuple(sorted(
        train, key=lambda row: (row.episode_date, row.episode_id),
    ))[:128]
    development_subset = tuple(sorted(
        development, key=lambda row: (row.episode_date, row.episode_id),
    ))[:128]
    if len(train_subset) != 128 or len(development_subset) != 128:
        raise ValueError("M1_V2_STAGE1_FAST_SUBSET_UNAVAILABLE")
    if any(
        row.episode_date >= date(2019, 10, 1)
        for row in (*train_subset, *development_subset)
    ):
        raise ValueError("M1_V2_STAGE1_FAST_FINAL_TEST_EXAMPLE_FORBIDDEN")

    output_dir = Path(output_dir or (
        root / "artifacts/experiment/m1_v2_tuning_stage1_fast"
    )).resolve()
    if output_dir == root or root not in output_dir.parents:
        raise ValueError("M1_V2_STAGE1_FAST_OUTPUT_OUTSIDE_PROJECT_FORBIDDEN")
    output_dir.mkdir(parents=True, exist_ok=True)

    seed = 20260821
    training_config = {
        "optimizer": "Adam",
        "learning_rate": 0.001,
        "weight_decay": 0.0,
        "epochs": 2,
        "batch_size": 64,
        "seed": seed,
        "max_train_examples": 128,
        "max_development_examples": 128,
        "mode": "FAST_TRAIN_MODE",
        "full_run": False,
        "paper_result": False,
        "feature_schema_hash": expected_feature_hash,
        "cache_hash": expected_cache_hash,
        "support_hash": content_id(closure["final_support"]),
        "loss_version": "TARGET_SPECIFIC_EPISODE_BALANCED",
    }
    candidate_specs = (
        (
            "NO_HISTORY",
            "M1_V2_NO_HISTORY_BASELINE",
            16,
            HistoryEncoderMode.NO_HISTORY_CURRENT_OBSERVATION,
        ),
        (
            "GRU_H8",
            "M1_V2_GRU_H8",
            8,
            HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX,
        ),
        (
            "GRU_H16",
            "M1_V2_GRU_H16",
            16,
            HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX,
        ),
        (
            "GRU_H32",
            "M1_V2_GRU_H32",
            32,
            HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX,
        ),
    )
    records = []
    for variant, model_id, hidden_size, history_mode in candidate_specs:
        # Paired initialization and optimization randomness are intentionally
        # reset per candidate; H/history are the only changing factors.
        torch.manual_seed(seed)
        pipeline = M1Pipeline.from_scientific_config(
            scientific,
            input_size=len(FEATURE_NAMES_V2),
            normalization=cache.normalization,
            hidden_size=hidden_size,
            static_input_size=STATIC_FEATURE_COUNT,
            static_normalization=cache.static_normalization,
            history_mode=history_mode,
        )
        lifecycle = M1Lifecycle(pipeline, device="cpu")
        result = run_fast_train_mode(
            lifecycle,
            train_subset,
            development_subset,
            output_dir=output_dir / variant,
            execution_authorized=True,
            max_train_examples=128,
            max_development_examples=128,
            epochs=2,
            learning_rate=0.001,
            weight_decay=0.0,
            batch_size=64,
            seed=seed,
        )
        result.update({
            "variant": variant,
            "model_id": model_id,
            "history_mode": history_mode.value,
            "training_config": training_config,
            "training_config_hash": content_id(training_config),
            "run_status": "EXECUTED_FAST_NOT_SELECTED",
            "calibration_used_for_selection": False,
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
        })
        metrics_path = output_dir / variant / "M1_V2_FAST_TUNING_METRICS.json"
        _write_json(metrics_path, result)
        result["metrics_path"] = str(metrics_path)
        records.append(result)

    ranked = sorted(
        records,
        key=lambda item: (
            item["validation_result"]["EPISODE_BALANCED_JOINT_VALIDATION_LOSS"],
            item["variant"],
        ),
    )
    ranking = [
        {
            "rank": index,
            "variant": item["variant"],
            "model_id": item["model_id"],
            "principal_loss": item["validation_result"][
                "EPISODE_BALANCED_JOINT_VALIDATION_LOSS"
            ],
        }
        for index, item in enumerate(ranked, start=1)
    ]
    best_second_difference = (
        ranking[1]["principal_loss"] - ranking[0]["principal_loss"]
    )
    sample_identity = {
        "train": [
            [row.episode_id, row.decision_node_id, row.episode_date.isoformat()]
            for row in train_subset
        ],
        "development": [
            [row.episode_id, row.decision_node_id, row.episode_date.isoformat()]
            for row in development_subset
        ],
    }
    lineage = {
        "schema_version": "M1_V2_FAST_TUNING_STAGE1_LINEAGE_V1",
        "input_cache_path": str(cache_path),
        "input_cache_hash": expected_cache_hash,
        "feature_schema_hash": expected_feature_hash,
        "support_hash": content_id(closure["final_support"]),
        "loss_version": "TARGET_SPECIFIC_EPISODE_BALANCED",
        "selection_split": "development",
        "calibration_used_for_selection": False,
        "sample_identity_hash": content_id(sample_identity),
        "sample_counts": {
            "train": len(train_subset),
            "development": len(development_subset),
        },
        "split_date_ranges": {
            "train": ["2019-01-01", "2019-06-30"],
            "development": ["2019-08-01", "2019-09-30"],
        },
        "history_lineage": {
            "NO_HISTORY": NO_HISTORY_BASELINE_CONTRACT,
            "GRU_H8": HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX.value,
            "GRU_H16": HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX.value,
            "GRU_H32": HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX.value,
        },
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }
    lineage["lineage_hash"] = content_id(lineage)
    lineage_path = output_dir / "M1_V2_FAST_TUNING_LINEAGE.json"
    _write_json(lineage_path, lineage)
    repository_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True,
    ).strip()
    manifest = {
        "schema_version": "M1_V2_FAST_TUNING_STAGE1_MANIFEST_V1",
        "status": "M1_V2_FAST_TUNING_COMPLETE",
        "repository_head": repository_head,
        "execution_authorized": True,
        "execution_scope": "FAST_DEVELOPMENT_ONLY",
        "fixed_contract": {
            "feature_schema_hash": expected_feature_hash,
            "cache_hash": expected_cache_hash,
            "support": STAGE1_SUPPORT,
            "loss_version": "TARGET_SPECIFIC_EPISODE_BALANCED",
            "train_split": ["2019-01-01", "2019-06-30"],
            "development_split": ["2019-08-01", "2019-09-30"],
            "calibration_role": "DO_NOT_USE_FOR_SELECTION",
        },
        "training_config": training_config,
        "training_config_hash": content_id(training_config),
        "variants": records,
        "ranking": ranking,
        "best_second_principal_loss_difference": best_second_difference,
        "selection": {
            "automatic_freeze": False,
            "status": "HUMAN_SELECTION_REQUIRED",
            "principal_metric": "EPISODE_BALANCED_JOINT_VALIDATION_LOSS",
        },
        "lineage_path": str(lineage_path),
        "lineage_hash": lineage["lineage_hash"],
        "safety": {
            "M1_TRAINING_RUNS": len(records),
            "TUNING_RUNS": len(records),
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
            "FULL": False,
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest["artifact_hash"] = content_id(manifest)
    manifest_path = output_dir / "M1_V2_FAST_TUNING_MANIFEST.json"
    _write_json(manifest_path, manifest)
    return {
        "status": manifest["status"],
        "manifest_path": str(manifest_path),
        "lineage_path": str(lineage_path),
        "ranking": ranking,
        "best_second_principal_loss_difference": best_second_difference,
        "safety": manifest["safety"],
    }


__all__ = [
    "NO_HISTORY_BASELINE_CONTRACT",
    "STAGE1_H_CANDIDATES",
    "STAGE1_METRICS",
    "STAGE1_TRAINING_CONFIG",
    "exp1_interface_contract",
    "fast_train_mode",
    "fast_train_mode_contract",
    "run_fast_stage1_tuning",
    "stage1_development_metrics",
    "stage1_manifest",
    "stage1_training_config_hash",
    "validate_stage1_contract",
]
