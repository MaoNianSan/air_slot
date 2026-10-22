"""M1-only H8/H16/H32 history-capacity Development experiment.

The module intentionally stops at the M1 state model and never imports M2, M3,
or M4. H32 is an experiment-local candidate constructed directly from the
frozen M1 contracts; it is not added to any active model registry or setting.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
import torch

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.contracts import (
    HazardBinContract,
    HurdleQuantileContract,
    M1_V2_HAZARD_COORDINATE,
    M1_V2_HAZARD_COORDINATE_TARGET,
)
from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_COUNT
from model.M1.history import HistoryEncoderMode
from model.M1.lifecycle import M1Lifecycle, M1TrainingExample
from model.M1.loss import hazard_pmf, monotone_positive_quantiles
from model.M1.model_layer.gru import M1V2GRU
from model.M1.pipeline import M1Pipeline
from model.M1.tuning_stage1 import STAGE1_SUPPORT, STAGE1_TRAINING_CONFIG
from model.common.config import load_config_layers
from model.common.identity import content_id


ROOT = Path(__file__).resolve().parents[2]
MODEL_ROOT = ROOT / "artifacts" / "models" / "m1"
CACHE_ROOT = MODEL_ROOT / "M1_FROZEN_H16"
CACHE_PATH = CACHE_ROOT / "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3.npz"
CACHE_MANIFEST_PATH = (
    CACHE_ROOT / "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3_MANIFEST.json"
)
COHORT_PATH = MODEL_ROOT / "M1_FORMAL_TRAINING_COHORT_V1.json"
OUTPUT_ROOT = ROOT / "artifacts" / "diagnostics" / "jatm_section4" / "h_capacity"

H_CAPACITY_GRID: tuple[int, ...] = (8, 16, 32)
H_CAPACITY_ROLE = "EXPERIMENT_LOCAL_CAPACITY_CANDIDATE"
H_CAPACITY_SELECTION_IMPROVEMENT_THRESHOLD = 0.001
H_CAPACITY_GAP_TOLERANCE = 1e-6
H_CAPACITY_CALIBRATION_TOLERANCE = 0.02
COVERAGE_NOMINAL = 0.80


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _require_development_rows(rows: Sequence[M1TrainingExample]) -> None:
    if not rows:
        raise RuntimeError("JATM_SECTION4_EMPTY_COHORT")
    if any(row.episode_date >= pd.Timestamp("2019-10-01").date() for row in rows):
        raise RuntimeError("JATM_SECTION4_FINAL_TEST_FORBIDDEN")


def _load_authorities() -> tuple[M1DevelopmentBaseCache, dict, dict, object]:
    for path in (CACHE_PATH, CACHE_MANIFEST_PATH, COHORT_PATH):
        if not path.is_file():
            raise RuntimeError(f"JATM_SECTION4_REQUIRED_INPUT_MISSING:{path}")
    cache_manifest = _read_json(CACHE_MANIFEST_PATH)
    cohort = _read_json(COHORT_PATH)
    if int(cache_manifest.get("final_test_access_count", -1)) != 0:
        raise RuntimeError("JATM_SECTION4_CACHE_FINAL_TEST_ACCESS")
    if int(cohort.get("final_test_access_count", -1)) != 0:
        raise RuntimeError("JATM_SECTION4_COHORT_FINAL_TEST_ACCESS")
    cache = M1DevelopmentBaseCache.load(
        CACHE_PATH,
        CACHE_MANIFEST_PATH,
        expected_cache_key=cache_manifest["cache_key"],
        allow_legacy_schema=True,
    )
    scientific = load_config_layers(ROOT / "configs").scientific
    return cache, cohort, cache_manifest, scientific


def _cohort_rows(
    cache: M1DevelopmentBaseCache, cohort: Mapping[str, object], split: str
) -> tuple[M1TrainingExample, ...]:
    ids = set(cohort[f"{split}_episode_ids"])
    rows = tuple(
        row
        for row in cache.partition(split, representation="ADAPTIVE_HISTORY")
        if row.episode_id in ids
    )
    if {row.episode_id for row in rows} != ids:
        raise RuntimeError(f"JATM_SECTION4_COHORT_ID_MISMATCH:{split}")
    _require_development_rows(rows)
    return rows


def _contracts_from_scientific(scientific: object) -> dict[str, object]:
    width = int(scientific.parameters["m1_bin_width_minutes"].value)
    ib_max = int(
        scientific.parameters["m1_v2_t_ib_remaining_max_finite_minutes"].value
    )
    d_ob_max = int(scientific.parameters["m1_v2_d_ob_max_finite_minutes"].value)
    d_tx_max = int(scientific.parameters["m1_v2_d_tx_max_finite_minutes"].value)
    levels = tuple(scientific.parameters["m1_v2_quantile_levels"].value)
    tail = scientific.parameters.get("m1_v2_positive_tail_policy")
    policy = "UNRESOLVED" if tail is None else str(tail.value)
    return {
        M1_V2_HAZARD_COORDINATE_TARGET: HazardBinContract(
            bin_width_minutes=width, max_finite_minutes=ib_max
        ),
        "D_OB": HurdleQuantileContract(
            target_name="D_OB",
            bin_width_minutes=width,
            max_finite_minutes=d_ob_max,
            quantile_levels=levels,
            upper_tail_policy=policy,
        ),
        "D_TX": HurdleQuantileContract(
            target_name="D_TX",
            bin_width_minutes=width,
            max_finite_minutes=d_tx_max,
            quantile_levels=levels,
            upper_tail_policy=policy,
        ),
    }


def _shared_training_contract(cohort: Mapping[str, object]) -> dict[str, object]:
    """Return contract hashes shared by every history-capacity candidate."""

    support = dict(STAGE1_SUPPORT)
    return {
        "features": FEATURE_NAMES_V2,
        "feature_hash": content_id({"feature_names": FEATURE_NAMES_V2}),
        "split_hash": content_id(
            {
                "train_episode_ids": list(cohort["train_episode_ids"]),
                "calibration_episode_ids": list(
                    cohort["calibration_episode_ids"]
                ),
                "development_episode_ids": list(
                    cohort["development_episode_ids"]
                ),
            }
        ),
        "support": support,
        "support_hash": content_id(support),
    }


def _build_local_pipeline(
    cache: M1DevelopmentBaseCache, scientific: object, hidden_size: int
) -> M1Pipeline:
    contracts = _contracts_from_scientific(scientific)
    model = M1V2GRU(
        len(FEATURE_NAMES_V2),
        int(hidden_size),
        contracts[M1_V2_HAZARD_COORDINATE_TARGET],
        contracts["D_OB"],
        contracts["D_TX"],
        fast_input_size=len(FEATURE_NAMES_V2),
        static_input_size=STATIC_FEATURE_COUNT,
        history_mode=HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX,
    )
    return M1Pipeline(
        model,
        contracts,
        normalization=cache.normalization,
        static_normalization=cache.static_normalization,
        history_mode=HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX,
    )


def _hazard_expectation(logits: torch.Tensor, contract: HazardBinContract) -> np.ndarray:
    pmf = hazard_pmf(logits, contract)
    representatives = torch.tensor(
        [contract.representative(index)[0] for index in range(contract.class_count)],
        dtype=pmf.dtype,
    )
    return (pmf * representatives).sum(-1).detach().cpu().numpy()


def _target_predictions(
    lifecycle: M1Lifecycle,
    rows: Sequence[M1TrainingExample],
    *,
    batch_size: int,
) -> dict[str, np.ndarray]:
    logits, _, _, _ = lifecycle.batched_logits(
        rows, batch_size=batch_size, teacher_forcing=True
    )
    hazard_contract = lifecycle.pipeline.contracts[M1_V2_HAZARD_COORDINATE_TARGET]
    predictions: dict[str, np.ndarray] = {
        "T_IB_REMAINING_HAZARD": _hazard_expectation(
            logits[M1_V2_HAZARD_COORDINATE], hazard_contract
        )
    }
    for name in ("D_OB", "D_TX"):
        zero = torch.sigmoid(logits[f"{name}_zero"].squeeze(-1))
        quantiles = monotone_positive_quantiles(logits[f"{name}_quantile"])
        predictions[name] = (
            ((1.0 - zero) * quantiles.mean(dim=-1)).detach().cpu().numpy()
        )
    return predictions


def _target_metrics(
    rows: Sequence[M1TrainingExample], predictions: Mapping[str, np.ndarray]
) -> list[dict[str, float | int | str]]:
    output: list[dict[str, float | int | str]] = []
    for target in ("T_IB_REMAINING_HAZARD", "D_OB", "D_TX"):
        actual = np.asarray(
            [
                row.targets.get(target)
                for row in rows
                if row.active.get(target, False) and row.targets.get(target) is not None
            ],
            dtype=float,
        )
        predicted = np.asarray(predictions[target], dtype=float)
        active = np.asarray(
            [
                row.active.get(target, False) and row.targets.get(target) is not None
                for row in rows
            ],
            dtype=bool,
        )
        errors = np.abs(predicted[active] - actual)
        output.append(
            {
                "target": target,
                "N": int(len(errors)),
                "MAE": float(np.mean(errors)) if len(errors) else float("nan"),
                "median_AE": float(np.median(errors))
                if len(errors)
                else float("nan"),
                "P90_AE": float(np.quantile(errors, 0.90))
                if len(errors)
                else float("nan"),
            }
        )
    return output


def _mixture_interval(
    zero_probability: np.ndarray,
    positive_quantiles: np.ndarray,
    levels: Sequence[float],
    *,
    alpha: float = 0.20,
) -> tuple[np.ndarray, np.ndarray]:
    levels_array = np.asarray(levels, dtype=float)
    lower_level = alpha / 2.0
    upper_level = 1.0 - alpha / 2.0
    lower = np.zeros(len(zero_probability), dtype=float)
    upper = np.zeros(len(zero_probability), dtype=float)
    for index, (zero, quantiles) in enumerate(
        zip(zero_probability, positive_quantiles, strict=True)
    ):
        for level, destination in ((lower_level, lower), (upper_level, upper)):
            if level <= zero:
                destination[index] = 0.0
                continue
            positive_level = (level - zero) / max(1.0 - zero, 1e-12)
            destination[index] = float(
                np.interp(positive_level, levels_array, quantiles)
            )
    return lower, upper


def _probabilistic_metrics(
    lifecycle: M1Lifecycle,
    rows: Sequence[M1TrainingExample],
    *,
    batch_size: int,
) -> dict[str, float]:
    logits, _, _, _ = lifecycle.batched_logits(
        rows, batch_size=batch_size, teacher_forcing=True
    )
    coverages: list[np.ndarray] = []
    widths: list[np.ndarray] = []
    hazard_contract = lifecycle.pipeline.contracts[M1_V2_HAZARD_COORDINATE_TARGET]
    hazard_pmf_values = hazard_pmf(
        logits[M1_V2_HAZARD_COORDINATE], hazard_contract
    ).numpy()
    hazard_reps = np.asarray(
        [hazard_contract.representative(index)[0] for index in range(hazard_contract.class_count)],
        dtype=float,
    )
    cumulative = np.cumsum(hazard_pmf_values, axis=-1)
    hazard_lower = hazard_reps[
        np.argmax(cumulative >= 0.10, axis=-1)
    ]
    hazard_upper = hazard_reps[
        np.argmax(cumulative >= 0.90, axis=-1)
    ]
    active = np.asarray(
        [
            row.active.get("T_IB_REMAINING_HAZARD", False)
            and row.targets.get("T_IB_REMAINING_HAZARD") is not None
            for row in rows
        ],
        dtype=bool,
    )
    actual = np.asarray(
        [row.targets.get("T_IB_REMAINING_HAZARD", np.nan) for row in rows],
        dtype=float,
    )
    lower = hazard_lower[active]
    upper = hazard_upper[active]
    values = actual[active]
    coverages.append(((values >= lower) & (values <= upper)).astype(float))
    widths.append(upper - lower)
    for name in ("D_OB", "D_TX"):
        zero = torch.sigmoid(logits[f"{name}_zero"].squeeze(-1)).numpy()
        quantiles = monotone_positive_quantiles(logits[f"{name}_quantile"]).numpy()
        lower, upper = _mixture_interval(
            zero,
            quantiles,
            lifecycle.pipeline.contracts[name].quantile_levels,
        )
        target = name
        active = np.asarray(
            [
                row.active.get(target, False) and row.targets.get(target) is not None
                for row in rows
            ],
            dtype=bool,
        )
        actual = np.asarray([row.targets.get(target, np.nan) for row in rows], dtype=float)
        values = actual[active]
        coverages.append(((values >= lower[active]) & (values <= upper[active])).astype(float))
        widths.append((upper - lower)[active])
    coverage_values = np.concatenate(coverages) if coverages else np.asarray([])
    width_values = np.concatenate(widths) if widths else np.asarray([])
    coverage_80 = float(np.mean(coverage_values)) if coverage_values.size else float("nan")
    mean_width_80 = float(np.mean(width_values)) if width_values.size else float("nan")
    return {
        "coverage_80": coverage_80,
        "coverage_error_80": abs(coverage_80 - COVERAGE_NOMINAL),
        "mean_width_80": mean_width_80,
    }


def _select_capacity(rows: pd.DataFrame) -> dict[str, object]:
    by_capacity = {int(row.history_capacity): row for row in rows.itertuples()}
    current = 8
    decisions: list[dict[str, object]] = []
    for candidate in (16, 32):
        current_row = by_capacity[current]
        candidate_row = by_capacity[candidate]
        improvement = (
            float(current_row.development_joint_loss)
            - float(candidate_row.development_joint_loss)
        ) / float(current_row.development_joint_loss)
        gap_worse = float(candidate_row.generalization_gap) > (
            float(current_row.generalization_gap) + H_CAPACITY_GAP_TOLERANCE
        )
        calibration_worse = float(candidate_row.coverage_error_80) > (
            float(current_row.coverage_error_80) + H_CAPACITY_CALIBRATION_TOLERANCE
        )
        selected = (
            improvement >= H_CAPACITY_SELECTION_IMPROVEMENT_THRESHOLD
            and not gap_worse
            and not calibration_worse
        )
        decisions.append(
            {
                "candidate": candidate,
                "incumbent": current,
                "development_loss_improvement_fraction": improvement,
                "generalization_gap_worse": gap_worse,
                "calibration_worse": calibration_worse,
                "selected": selected,
                "rule": (
                    "SELECT_LARGER_ONLY_IF_DEVELOPMENT_IMPROVEMENT_GE_0.1_PERCENT_"
                    "AND_GAP_AND_CALIBRATION_DO_NOT_WORSEN"
                ),
            }
        )
        if selected:
            current = candidate
    return {
        "selected_history_capacity": current,
        "selection_metric": "development_joint_loss",
        "comparisons": decisions,
        "active_model_mutation": "NONE",
        "downstream_execution": "NONE",
    }


def _render_selection_markdown(payload: Mapping[str, object]) -> str:
    lines = [
        "# Section 4 H-capacity selection",
        "",
        f"- Selected capacity: H{payload['selected_history_capacity']}",
        f"- Selection metric: `{payload['selection_metric']}`",
        "- Downstream execution: NONE",
        "- Active model mutation: NONE",
        "",
        "| candidate | incumbent | dev improvement | gap worse | calibration worse | selected |",
        "|---:|---:|---:|---|---|---|",
    ]
    for item in payload["comparisons"]:
        lines.append(
            "| {candidate} | {incumbent} | {development_loss_improvement_fraction:.6f} | "
            "{generalization_gap_worse} | {calibration_worse} | {selected} |".format(
                **item
            )
        )
    lines.append("")
    return "\n".join(lines)


def run_h_capacity_development(root: Path | None = None) -> dict[str, object]:
    """Train and evaluate H8/H16/H32 on the frozen Development cohort."""

    if root is not None and Path(root).resolve() != ROOT.resolve():
        raise RuntimeError("JATM_SECTION4_ROOT_MUST_BE_REPOSITORY_ROOT")
    cache, cohort, cache_manifest, scientific = _load_authorities()
    config = dict(STAGE1_TRAINING_CONFIG)
    seed = int(config["seed"])
    batch_size = int(config["batch_size"])
    epochs = int(config["epochs"])
    learning_rate = float(config["learning_rate"])
    weight_decay = float(config["weight_decay"])
    train = _cohort_rows(cache, cohort, "train")
    calibration = _cohort_rows(cache, cohort, "calibration")
    development = _cohort_rows(cache, cohort, "development")
    shared_contract = _shared_training_contract(cohort)
    feature_hash = str(shared_contract["feature_hash"])
    split_hash = str(shared_contract["split_hash"])
    support_hash = str(shared_contract["support_hash"])
    model_rows: list[dict[str, object]] = []
    target_rows: list[dict[str, object]] = []
    for hidden_size in H_CAPACITY_GRID:
        torch.manual_seed(seed)
        pipeline = _build_local_pipeline(cache, scientific, hidden_size)
        lifecycle = M1Lifecycle(pipeline, device="cpu")
        training = lifecycle.train(
            train,
            epochs=epochs,
            learning_rate=learning_rate,
            weight_decay=weight_decay,
            batch_size=batch_size,
            seed=seed,
            teacher_forcing=True,
        )
        temperatures = lifecycle.calibrate(calibration, batch_size=batch_size)
        train_metrics = lifecycle.episode_balanced_objective(
            train, batch_size=batch_size, teacher_forcing=True
        )
        development_metrics = lifecycle.episode_balanced_objective(
            development, batch_size=batch_size, teacher_forcing=True
        )
        probabilistic = _probabilistic_metrics(
            lifecycle, development, batch_size=batch_size
        )
        predictions = _target_predictions(
            lifecycle, development, batch_size=batch_size
        )
        target_rows.extend(
            {
                "history_capacity": hidden_size,
                **row,
                "role": H_CAPACITY_ROLE,
            }
            for row in _target_metrics(development, predictions)
        )
        last_epoch_training_loss = float(training[-1]["loss"])
        train_eval_joint_loss = float(
            train_metrics["EPISODE_BALANCED_JOINT_VALIDATION_LOSS"]
        )
        development_joint_loss = float(
            development_metrics["EPISODE_BALANCED_JOINT_VALIDATION_LOSS"]
        )
        model_rows.append(
            {
                "history_capacity": hidden_size,
                "role": H_CAPACITY_ROLE,
                "parameter_count": int(
                    sum(parameter.numel() for parameter in pipeline.model.parameters())
                ),
                "last_epoch_training_loss": last_epoch_training_loss,
                "train_eval_joint_loss": train_eval_joint_loss,
                "development_joint_loss": development_joint_loss,
                "joint_validation_loss": development_joint_loss,
                "train_loss": last_epoch_training_loss,
                "development_loss": development_joint_loss,
                "generalization_gap": development_joint_loss - train_eval_joint_loss,
                "train_development_gap": development_joint_loss - train_eval_joint_loss,
                "T_IB_HAZARD_NLL": float(
                    development_metrics["T_IB_HAZARD_NLL"]
                ),
                **probabilistic,
                "selection_status": "CANDIDATE",
                "features_hash": feature_hash,
                "split_hash": split_hash,
                "support_hash": support_hash,
                "calibration_temperatures": json.dumps(
                    temperatures, sort_keys=True
                ),
                "seed": seed,
                "epochs": epochs,
                "optimizer": config["optimizer"],
                "learning_rate": learning_rate,
                "batch_size": batch_size,
                "source_cache_key": cache_manifest["cache_key"],
                "final_test_access_count": 0,
            }
        )
    model_frame = pd.DataFrame(model_rows).sort_values("history_capacity")
    target_frame = pd.DataFrame(target_rows).sort_values(
        ["history_capacity", "target"]
    )
    selection = _select_capacity(model_frame)
    selection["schema_version"] = "JATM_SECTION4_H_CAPACITY_SELECTION_V1"
    selection["status"] = "COMPLETE"
    selection["h_capacity_grid"] = list(H_CAPACITY_GRID)
    selection["h32_scope"] = H_CAPACITY_ROLE
    selection["section5_primary_model"] = "H16_FROZEN_PRIMARY"
    selection["final_test_access_count"] = 0
    selection["scientific_definition_changed"] = False
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    model_frame.to_csv(OUTPUT_ROOT / "H_CAPACITY_MODEL_PERFORMANCE.csv", index=False)
    target_frame.to_csv(OUTPUT_ROOT / "H_CAPACITY_TARGET_PERFORMANCE.csv", index=False)
    _write_json(OUTPUT_ROOT / "H_CAPACITY_SELECTION.json", selection)
    (OUTPUT_ROOT / "H_CAPACITY_SELECTION.md").write_text(
        _render_selection_markdown(selection), encoding="utf-8"
    )
    return {
        "status": "COMPLETE",
        "model_performance": model_frame.to_dict(orient="records"),
        "target_performance": target_frame.to_dict(orient="records"),
        "selection": selection,
        "output_root": str(OUTPUT_ROOT),
        "final_test_access_count": 0,
    }


__all__ = ["H_CAPACITY_GRID", "run_h_capacity_development"]
