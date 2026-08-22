"""Read-only preparation and evaluation contracts for M1 V2 Stage 1.

This module performs no automatic training. It defines the narrow H sensitivity
manifest, the no-history baseline contract, the Development metric projection,
and a separately guarded FAST entry point used only after authorization.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
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
    lifecycle.save(checkpoint)
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
        "paper_result": False,
        "full_run": False,
        "training_counter_semantics": "INCREMENT_ONLY_FOR_THIS_EXPLICITLY_AUTHORIZED_FAST_EXECUTION",
        "TUNING_RUNS": 0,
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


__all__ = [
    "NO_HISTORY_BASELINE_CONTRACT",
    "STAGE1_H_CANDIDATES",
    "STAGE1_METRICS",
    "STAGE1_TRAINING_CONFIG",
    "exp1_interface_contract",
    "fast_train_mode",
    "fast_train_mode_contract",
    "stage1_development_metrics",
    "stage1_manifest",
    "stage1_training_config_hash",
    "validate_stage1_contract",
]
