"""M1 history-encoder capacity selection: H8 / H16 / H32.

Development-only.  Trains each candidate width on the frozen Stage-1 contract
(cache, cohort, features, support, loss, optimizer, 8 epochs, paired seeds) and
selects a capacity with the predeclared one-standard-error rule plus
calibration, tail-error and core-target guardrails.  No Final-Test path is read,
no downstream decision metric is used, and no frozen artifact is modified.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from statistics import mean, pstdev, stdev
from typing import Any, Mapping, Sequence

import torch

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.contracts import (
    HazardBinContract,
    HurdleQuantileContract,
    M1_V2_HAZARD_COORDINATE,
)
from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_COUNT
from model.M1.history import HistoryEncoderMode
from model.M1.lifecycle import M1Lifecycle
from model.M1.model_layer.gru import M1V2GRU
from model.M1.pipeline import M1Pipeline
from model.M1.tuning_stage1 import (
    PRIMARY_EPOCHS,
    STAGE1_SPLITS,
    STAGE1_SUPPORT,
    STAGE1_TRAINING_CONFIG,
    validate_stage1_contract,
)
from model.common.config import load_config_layers
from model.common.errors import ContractError
from model.common.identity import content_id

from . import horizon, metrics

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_HIDDEN_SIZES: tuple[int, ...] = (8, 16, 32)
PAIRED_SEEDS: tuple[int, ...] = (20260813, 20260814, 20260815, 20260816, 20260817)
# Declared by the frozen closure manifest.  The materialized count of the
# frozen architecture is recomputed from the model definition and reported
# next to the declaration rather than overwriting it.
DECLARED_PARAMETER_COUNTS = {8: 4708, 16: 9716, 32: 20884}
DECLARED_PARAMETER_COUNT_SOURCE = (
    "artifacts/diagnostics/model/m1_v2_model_closure/"
    "M1_V2_TUNING_STAGE1_MANIFEST.json:candidates[].parameter_count"
)
PARAMETER_COUNT_NOTE = (
    "candidate_parameter_counts are materialized from the frozen "
    "architecture definition (M1V2GRU at the given hidden size) and are "
    "proven signature-equal to the frozen H16 runtime artifact; "
    "declared_parameter_counts preserve the closure-manifest declarations "
    "unchanged"
)
H16_CHECKPOINT_RELATIVE = Path(
    "artifacts/models/m1/M1_H16_HISTORY_PRIMARY/M1_H16_HISTORY_PRIMARY.pt"
)
OUTPUT_RELATIVE = Path("artifacts/diagnostics/model/m1_h_capacity_selection")
CACHE_DIR = Path("artifacts/models/m1/M1_FROZEN_H16")
CACHE_NAME = "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3.npz"
CACHE_MANIFEST_NAME = "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3_MANIFEST.json"
COHORT_PATH = Path("artifacts/models/m1/M1_FORMAL_TRAINING_COHORT_V1.json")
H16_MANIFEST_PATH = Path(
    "artifacts/models/m1/M1_H16_HISTORY_PRIMARY/M1_H16_HISTORY_PRIMARY_MANIFEST.json"
)
NODE_INPUT_PATH = Path(
    "artifacts/experiment/exp2/development/data/EXP2_H16_M2_V4_NODE_INPUT.parquet"
)
BATCH_SIZE = int(STAGE1_TRAINING_CONFIG["batch_size"])
ARTIFACT_SCOPE = "M1_DEVELOPMENT_CAPACITY_SELECTION_ONLY"
COMPONENT_KEYS = (
    "T_IB_HAZARD_NLL",
    "D_OB_ZERO_BCE",
    "D_OB_POSITIVE_QUANTILE_LOSS",
    "D_TX_ZERO_BCE",
    "D_TX_POSITIVE_QUANTILE_LOSS",
)
OUTPUT_NAMES = (
    "M1_H_CAPACITY_BY_SEED.csv",
    "M1_H_CAPACITY_TARGET_METRICS.csv",
    "M1_H_CAPACITY_BY_HORIZON.csv",
    "M1_H_CAPACITY_BY_STAGE.csv",
    "M1_H_CAPACITY_CALIBRATION.csv",
    "M1_H_CAPACITY_GENERALIZATION.csv",
    "M1_H_CAPACITY_SELECTION_SUMMARY.csv",
    "M1_H_CAPACITY_SELECTION_REPORT.md",
)


# --------------------------------------------------------------------------- io
def file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    temporary.replace(path)


def _state_hash(model: torch.nn.Module) -> str:
    digest = sha256()
    for name, tensor in sorted(model.state_dict().items()):
        digest.update(name.encode("utf-8"))
        digest.update(
            tensor.detach().to(torch.float32).cpu().numpy().tobytes()
        )
    return f"sha256:{digest.hexdigest()}"


def _git_head(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:  # pragma: no cover - provenance only
        return "UNRESOLVED"


# ------------------------------------------------------------------- statistics
def _stats(values: Sequence[float]) -> dict[str, Any]:
    finite = [
        float(value)
        for value in values
        if value is not None and math.isfinite(float(value))
    ]
    if not finite:
        return {
            "mean": None,
            "sd": None,
            "se": None,
            "cv": None,
            "worst": None,
            "n": 0,
        }
    sd = float(stdev(finite)) if len(finite) > 1 else 0.0
    mean_value = float(mean(finite))
    return {
        "mean": mean_value,
        "sd": sd,
        "se": sd / math.sqrt(len(finite)),
        "cv": None if mean_value == 0 else sd / abs(mean_value),
        "worst": float(max(finite)),
        "n": len(finite),
    }


def _round(value: Any, digits: int = 6) -> Any:
    if isinstance(value, float) and math.isfinite(value):
        return round(value, digits)
    return value


# ----------------------------------------------------------------------- splits
def _split_examples(
    cache: M1DevelopmentBaseCache, cohort: Mapping[str, Any], split: str
):
    ids = set(cohort[f"{split}_episode_ids"])
    rows = tuple(
        row
        for row in cache.partition(split, representation="ADAPTIVE_HISTORY")
        if row.episode_id in ids
    )
    if {row.episode_id for row in rows} != ids:
        raise ContractError(f"M1_CAPACITY_COHORT_ID_MISMATCH:{split}")
    return rows


# ------------------------------------------------------------------- evaluation
def _lead_grouped(
    records: Sequence[Mapping[str, Any]], target: str
) -> dict[int, list[Mapping[str, Any]]]:
    """Active nodes by realized lead bin (hurdle zeros kept)."""
    grouped: dict[int, list[Mapping[str, Any]]] = {}
    for record in records:
        if not record["active"].get(target, False):
            continue
        if record["targets"].get(target) is None:
            continue
        lead_bin = record["lead_bins"].get(target)
        if lead_bin is None:
            continue
        grouped.setdefault(int(lead_bin), []).append(record)
    return grouped


def _positive_lead_grouped(
    records: Sequence[Mapping[str, Any]], target: str
) -> dict[int, list[Mapping[str, Any]]]:
    """Positive active nodes by lead bin (frozen coverage population).

    Hurdle coverage and sharpness are defined on positive outcomes, matching
    the target-level coverage convention.
    """
    grouped: dict[int, list[Mapping[str, Any]]] = {}
    for record in records:
        if not record["active"].get(target, False):
            continue
        if record["targets"].get(target) is None:
            continue
        if (
            target != metrics.TARGET_HAZARD
            and float(record["targets"][target]) <= 0.0
        ):
            continue
        lead_bin = record["lead_bins"].get(target)
        if lead_bin is None:
            continue
        grouped.setdefault(int(lead_bin), []).append(record)
    return grouped


def _coverage_by_lead(
    records: Sequence[Mapping[str, Any]], target: str
) -> dict[str, Any]:
    rows: dict[int, dict[str, Any]] = {}
    positive = _positive_lead_grouped(records, target)
    for lead_bin, subset in sorted(positive.items()):
        if len(subset) < 5:
            continue
        rows[lead_bin] = metrics.coverage_metrics(subset, target)
    volatility: dict[str, Any] = {}
    for level in metrics.COVERAGE_LEVELS:
        key = f"Cov{int(round(level * 100))}"
        values = [
            row[key] for row in rows.values() if row.get(key) is not None
        ]
        volatility[f"{key}_sd"] = (
            float(pstdev(values)) if len(values) > 1 else (0.0 if values else None)
        )
        volatility[f"{key}_max_abs_deviation"] = (
            None if not values else max(abs(value - level) for value in values)
        )
    deviations = [
        value
        for value in (
            volatility.get(f"Cov{int(round(level * 100))}_max_abs_deviation")
            for level in metrics.COVERAGE_LEVELS
        )
        if value is not None
    ]
    volatility["max_absolute_coverage_deviation"] = (
        None if not deviations else float(max(deviations))
    )
    volatility["lead_bin_count"] = len(rows)
    return {"rows": rows, "volatility": volatility}


def _target_rows(
    hidden_size: int, seed: int, records: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for target in metrics.TARGETS:
        point = metrics.point_metrics(records, target)
        coverage = metrics.coverage_metrics(records, target)
        crps = metrics.crps_metrics(records, target)
        zero = (
            metrics.zero_calibration(records, target)
            if target != metrics.TARGET_HAZARD
            else {"n": 0, "zero_probability_gap": None, "brier_zero": None}
        )
        volatility = _coverage_by_lead(records, target)["volatility"]
        rows.append(
            {
                "H": hidden_size,
                "seed": seed,
                "target": target,
                "n_active": point["n"],
                "n_coverage": coverage.get("n"),
                "mae": _round(point["mae"]),
                "median_ae": _round(point["median_ae"]),
                "p90_ae": _round(point["p90_ae"]),
                "crps": _round(crps["crps"]),
                "crps_status": crps["status"],
                "crps_n": crps["n"],
                "zero_probability_gap": _round(zero["zero_probability_gap"]),
                "brier_zero": _round(zero["brier_zero"]),
                "cov50": _round(coverage.get("Cov50")),
                "cov80": _round(coverage.get("Cov80")),
                "cov90": _round(coverage.get("Cov90")),
                "cov90_status": coverage.get("level_status", {}).get("Cov90"),
                "w50": _round(coverage.get("W50")),
                "w80": _round(coverage.get("W80")),
                "w90": _round(coverage.get("W90")),
                "ace50": _round(coverage.get("ACE50")),
                "ace80": _round(coverage.get("ACE80")),
                "ace90": _round(coverage.get("ACE90")),
                "mean_ace": _round(coverage.get("mean_ace")),
                "coverage_volatility_sd50": _round(volatility.get("Cov50_sd")),
                "coverage_volatility_sd80": _round(volatility.get("Cov80_sd")),
                "coverage_volatility_sd90": _round(volatility.get("Cov90_sd")),
                "coverage_max_abs_deviation": _round(
                    volatility.get("max_absolute_coverage_deviation")
                ),
            }
        )
    return rows


def _horizon_rows(
    hidden_size: int, seed: int, records: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for target in metrics.TARGETS:
        positive = _positive_lead_grouped(records, target)
        for lead_bin, subset in sorted(_lead_grouped(records, target).items()):
            # Point metrics keep every active label (hurdle zeros included) so
            # the lead rows are comparable with the overall target row; the
            # coverage columns use the frozen positive-outcome population.
            point = metrics.point_metrics(subset, target)
            coverage = metrics.coverage_metrics(
                positive.get(lead_bin, []), target
            )
            rows.append(
                {
                    "H": hidden_size,
                    "seed": seed,
                    "target": target,
                    "lead_minutes": lead_bin,
                    "n": point["n"],
                    "n_coverage": coverage.get("n"),
                    "mae": _round(point["mae"]),
                    "median_ae": _round(point["median_ae"]),
                    "p90_ae": _round(point["p90_ae"]),
                    "cov50": _round(coverage.get("Cov50")),
                    "cov80": _round(coverage.get("Cov80")),
                    "cov90": _round(coverage.get("Cov90")),
                    "cov90_status": coverage.get("level_status", {}).get("Cov90"),
                    "w50": _round(coverage.get("W50")),
                    "w80": _round(coverage.get("W80")),
                    "w90": _round(coverage.get("W90")),
                }
            )
    return rows


def _stage_rows(
    hidden_size: int, seed: int, records: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for stage in horizon.STAGE_ORDER:
        subset = [row for row in records if row["operational_stage"] == stage]
        if not subset:
            continue
        for target in metrics.TARGETS:
            point = metrics.point_metrics(subset, target)
            if point["n"] == 0:
                continue
            rows.append(
                {
                    "H": hidden_size,
                    "seed": seed,
                    "operational_stage": stage,
                    "target": target,
                    "n_active": point["n"],
                    "mae": _round(point["mae"]),
                    "median_ae": _round(point["median_ae"]),
                    "p90_ae": _round(point["p90_ae"]),
                }
            )
    return rows


def _calibration_rows(
    hidden_size: int, seed: int, records: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for target in metrics.TARGETS:
        overall = metrics.coverage_metrics(records, target)
        by_lead = _coverage_by_lead(records, target)
        for lead_bin, coverage in sorted(by_lead["rows"].items()):
            for level in metrics.COVERAGE_LEVELS:
                label = int(round(level * 100))
                key = f"Cov{label}"
                rows.append(
                    {
                        "H": hidden_size,
                        "seed": seed,
                        "target": target,
                        "scope": "LEAD",
                        "lead_minutes": lead_bin,
                        "nominal": level,
                        "empirical_coverage": _round(coverage.get(key)),
                        "ace": _round(coverage.get(f"ACE{label}")),
                        "width": _round(coverage.get(f"W{label}")),
                        "n": coverage.get("n"),
                        "status": coverage.get("level_status", {}).get(
                            key, "DEFINED"
                        ),
                    }
                )
        for level in metrics.COVERAGE_LEVELS:
            label = int(round(level * 100))
            key = f"Cov{label}"
            rows.append(
                {
                    "H": hidden_size,
                    "seed": seed,
                    "target": target,
                    "scope": "OVERALL",
                    "lead_minutes": None,
                    "nominal": level,
                    "empirical_coverage": _round(overall.get(key)),
                    "ace": _round(overall.get(f"ACE{label}")),
                    "width": _round(overall.get(f"W{label}")),
                    "n": overall.get("n"),
                    "status": overall.get("level_status", {}).get(
                        key, "DEFINED"
                    ),
                }
            )
    return rows


# --------------------------------------------------------------------- training
def _component_map(objective: Mapping[str, Any]) -> dict[str, float]:
    return {
        "T_IB_HAZARD_NLL": float(objective["T_IB_HAZARD_NLL"]),
        "D_OB_ZERO_BCE": float(objective["D_OB_ZERO_BCE"]),
        "D_OB_POSITIVE_QUANTILE_LOSS": float(
            objective["D_OB_POSITIVE_PINBALL"]
        ),
        "D_TX_ZERO_BCE": float(objective["D_TX_ZERO_BCE"]),
        "D_TX_POSITIVE_QUANTILE_LOSS": float(
            objective["D_TX_POSITIVE_PINBALL"]
        ),
    }


def _build_pipeline(
    *, scientific: Any, cache: M1DevelopmentBaseCache, hidden_size: int
) -> M1Pipeline:
    """Frozen ``M1Pipeline.from_scientific_config`` recipe at any width.

    ``from_scientific_config`` keeps ``hidden_size`` inside the frozen model
    settings (H16 principal / H8 sensitivity).  This capacity-selection
    experiment must also train H32, so the identical construction is repeated
    here from the same frozen scientific parameters.  No scientific value is
    defined locally and no frozen module is modified.
    """
    width = scientific.parameters["m1_bin_width_minutes"].value
    ib_max = scientific.parameters[
        "m1_v2_t_ib_remaining_max_finite_minutes"
    ].value
    d_ob_max = scientific.parameters[
        "m1_v2_d_ob_max_finite_minutes"
    ].value
    d_tx_max = scientific.parameters[
        "m1_v2_d_tx_max_finite_minutes"
    ].value
    quantile_levels = scientific.parameters["m1_v2_quantile_levels"].value
    if None in (ib_max, d_ob_max, d_tx_max) or not quantile_levels:
        raise ContractError("M1_CAPACITY_FINITE_SUPPORT_UNFROZEN")
    tail_param = scientific.parameters.get("m1_v2_positive_tail_policy")
    tail_policy = "UNRESOLVED" if tail_param is None else tail_param.value
    contracts = {
        M1_V2_HAZARD_COORDINATE: HazardBinContract(
            bin_width_minutes=width, max_finite_minutes=ib_max
        ),
        "D_OB": HurdleQuantileContract(
            target_name="D_OB",
            bin_width_minutes=width,
            max_finite_minutes=d_ob_max,
            quantile_levels=tuple(quantile_levels),
            upper_tail_policy=tail_policy,
        ),
        "D_TX": HurdleQuantileContract(
            target_name="D_TX",
            bin_width_minutes=width,
            max_finite_minutes=d_tx_max,
            quantile_levels=tuple(quantile_levels),
            upper_tail_policy=tail_policy,
        ),
    }
    return M1Pipeline(
        M1V2GRU(
            len(FEATURE_NAMES_V2),
            int(hidden_size),
            contracts[M1_V2_HAZARD_COORDINATE],
            contracts["D_OB"],
            contracts["D_TX"],
            fast_input_size=len(FEATURE_NAMES_V2),
            static_input_size=STATIC_FEATURE_COUNT,
            history_mode=HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX,
        ),
        contracts,
        normalization=cache.normalization,
        static_normalization=cache.static_normalization,
        history_mode=HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX,
    )


def _parameter_count(pipeline: M1Pipeline) -> int:
    return sum(int(value.numel()) for value in pipeline.model.parameters())


def _architecture_signature(
    model: torch.nn.Module,
) -> list[tuple[str, tuple[int, ...]]]:
    return sorted(
        (name, tuple(int(item) for item in tensor.shape))
        for name, tensor in model.state_dict().items()
    )


def _frozen_architecture_check(
    *,
    root: Path,
    scientific: Any,
    cache: M1DevelopmentBaseCache,
    h16_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Prove the local construction equals the frozen H16 runtime artifact.

    The frozen H16 checkpoint anchors the architecture recipe: matching its
    parameter-name/shape signature shows that H8/H16/H32 candidates differ
    from the frozen model only in hidden width.
    """
    expected_hash = str(h16_manifest.get("checkpoint_hash", ""))
    declared_path = Path(str(h16_manifest.get("checkpoint_path", "")))
    checkpoint: Path | None = None
    for candidate in (root / H16_CHECKPOINT_RELATIVE, declared_path):
        if not candidate.is_file():
            continue
        if expected_hash and file_hash(candidate) != expected_hash:
            continue
        checkpoint = candidate
        break
    if checkpoint is None:
        raise ContractError("M1_CAPACITY_FROZEN_H16_CHECKPOINT_UNRESOLVED")
    frozen = M1Pipeline.load(checkpoint)
    local = _build_pipeline(scientific=scientific, cache=cache, hidden_size=16)
    frozen_signature = _architecture_signature(frozen.model)
    if frozen_signature != _architecture_signature(local.model):
        raise ContractError("M1_CAPACITY_FROZEN_H16_ARCHITECTURE_MISMATCH")
    return {
        "checkpoint_path": str(checkpoint),
        "checkpoint_hash": file_hash(checkpoint),
        "architecture_signature_hash": content_id(
            [[name, list(shape)] for name, shape in frozen_signature]
        ),
        "frozen_parameter_count": _parameter_count(frozen),
        "materialized_h16_parameter_count": _parameter_count(local),
        "status": "FROZEN_H16_ARCHITECTURE_EQUIVALENT",
    }


def _train_single(
    *,
    scientific: Any,
    cache: M1DevelopmentBaseCache,
    train: Sequence[Any],
    calibration: Sequence[Any],
    development: Sequence[Any],
    hidden_size: int,
    seed: int,
    device: str,
) -> dict[str, Any]:
    # Reproducibility control: seed the ambient generator before the candidate
    # is constructed so every (H, seed) run is reproducible and independent
    # of run order.  ``M1Lifecycle.train(seed=...)`` (unchanged) re-seeds for
    # batching/optimization, but it runs after construction, so without this
    # control the initial weights would depend on ambient RNG state.
    torch.manual_seed(int(seed))
    pipeline = _build_pipeline(
        scientific=scientific, cache=cache, hidden_size=hidden_size
    )
    parameter_count = _parameter_count(pipeline)
    if int(pipeline.model.hidden_size) != int(hidden_size):
        raise ContractError(
            "M1_CAPACITY_WIDTH_MISMATCH:"
            f"H{hidden_size}:{pipeline.model.hidden_size}"
        )
    lifecycle = M1Lifecycle(pipeline, device=device)
    started = time.time()
    history = lifecycle.train(
        train,
        epochs=PRIMARY_EPOCHS,
        learning_rate=float(STAGE1_TRAINING_CONFIG["learning_rate"]),
        weight_decay=float(STAGE1_TRAINING_CONFIG["weight_decay"]),
        batch_size=BATCH_SIZE,
        bucketed=True,
        seed=seed,
        teacher_forcing=True,
    )
    temperatures = lifecycle.calibrate(calibration, batch_size=BATCH_SIZE)
    train_objective = lifecycle.episode_balanced_objective(
        train, batch_size=BATCH_SIZE, bucketed=True, teacher_forcing=True
    )
    development_objective = lifecycle.episode_balanced_objective(
        development, batch_size=BATCH_SIZE, bucketed=True, teacher_forcing=True
    )
    return {
        "lifecycle": lifecycle,
        "parameter_count": parameter_count,
        "history": history,
        "temperatures": temperatures,
        "train_objective": train_objective,
        "development_objective": development_objective,
        "state_hash": _state_hash(pipeline.model),
        "runtime_seconds": time.time() - started,
    }


# -------------------------------------------------------------------- selection
def _guardrails(
    joint: Mapping[int, Mapping[str, Any]], candidate: int, best: int
) -> list[str]:
    if candidate == best:
        return []
    reasons: list[str] = []
    reference = joint[best]
    row = joint[candidate]
    for mean_key, sd_key in (
        ("mean_absolute_coverage_error", "mean_absolute_coverage_error_sd"),
        ("p90_ae_summary", "p90_ae_summary_sd"),
    ):
        value = row.get(mean_key)
        reference_value = reference.get(mean_key)
        if value is None or reference_value is None:
            continue
        margin = float(reference.get(sd_key) or 0.0) / math.sqrt(len(PAIRED_SEEDS))
        if float(value) > float(reference_value) + margin:
            reasons.append(
                f"{mean_key} {float(value):.6f} > "
                f"{float(reference_value):.6f} + SE {margin:.6f}"
            )
    for component in COMPONENT_KEYS:
        value = row.get(f"development_{component}_mean")
        reference_value = reference.get(f"development_{component}_mean")
        if value is None or reference_value is None:
            continue
        margin = float(reference.get(f"development_{component}_se") or 0.0)
        if float(value) > float(reference_value) + margin:
            reasons.append(
                f"{component} {float(value):.6f} > "
                f"{float(reference_value):.6f} + SE {margin:.6f}"
            )
    return reasons


def _select(summary_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    joint = {int(row["H"]): row for row in summary_rows}
    best_h = min(
        joint, key=lambda h: float(joint[h]["development_joint_loss_mean"])
    )
    best_se = float(joint[best_h]["development_joint_loss_se"])
    threshold = float(joint[best_h]["development_joint_loss_mean"]) + best_se
    eligible = sorted(
        h
        for h in joint
        if float(joint[h]["development_joint_loss_mean"]) <= threshold
    )
    guardrail_reasons: list[str] = []
    selected = None
    for candidate in eligible:
        reasons = _guardrails(joint, candidate, best_h)
        if not reasons:
            selected = candidate
            break
        guardrail_reasons.append(
            f"H{candidate} rejected by guardrail: " + "; ".join(reasons)
        )
    if selected is None:
        selected = best_h
        guardrail_reasons.append(
            "all eligible candidates failed guardrails; best-mean candidate retained"
        )
    return {
        "best_mean_h": best_h,
        "best_mean_loss": float(joint[best_h]["development_joint_loss_mean"]),
        "best_se": best_se,
        "eligibility_threshold": threshold,
        "eligible": eligible,
        "selected_h": selected,
        "guardrail_notes": guardrail_reasons,
        "selection_rule": (
            "ONE_SE_THEN_SMALLEST_ELIGIBLE_WITH_CALIBRATION_TAIL_CORE_TARGET_GUARDRAILS"
        ),
    }


# -------------------------------------------------------------------------- run
def run_capacity_selection(
    *,
    root: Path = PROJECT_ROOT,
    output_root: Path | None = None,
    candidates: Sequence[int] = CANDIDATE_HIDDEN_SIZES,
    seeds: Sequence[int] = PAIRED_SEEDS,
    device: str = "cpu",
) -> dict[str, Any]:
    root = Path(root)
    output_root = Path(output_root or (root / OUTPUT_RELATIVE))
    if "final_test" in str(output_root).lower():
        raise ContractError("M1_CAPACITY_OUTPUT_MUST_NOT_BE_FINAL_TEST")

    torch.set_num_threads(8)
    scientific = load_config_layers(root / "configs").scientific
    contract = validate_stage1_contract(scientific)

    cache_path = root / CACHE_DIR / CACHE_NAME
    cache_manifest_path = root / CACHE_DIR / CACHE_MANIFEST_NAME
    cache_manifest = json.loads(cache_manifest_path.read_text(encoding="utf-8"))
    cohort_path = root / COHORT_PATH
    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    if int(cohort.get("final_test_access_count", 0)) != 0:
        raise ContractError("M1_CAPACITY_COHORT_FINAL_TEST_ACCESS_VIOLATION")
    if int(cache_manifest["audit"].get("final_test_access_count", 0)) != 0:
        raise ContractError("M1_CAPACITY_CACHE_FINAL_TEST_ACCESS_VIOLATION")

    cache = M1DevelopmentBaseCache.load(
        cache_path,
        cache_manifest_path,
        expected_cache_key=cache_manifest["cache_key"],
        allow_legacy_schema=True,
    )
    train = _split_examples(cache, cohort, "train")
    calibration = _split_examples(cache, cohort, "calibration")
    development = _split_examples(cache, cohort, "development")
    node_input_path = root / NODE_INPUT_PATH
    development_meta = horizon.load_development_metadata(
        node_input_path=node_input_path,
        cache_manifest=cache_manifest,
        examples=development,
    )

    h16_manifest = json.loads(
        (root / H16_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    feature_hash = content_id({"feature_names": FEATURE_NAMES_V2})
    support_hash = content_id(STAGE1_SUPPORT)
    for name, value in (
        ("feature_contract_hash", feature_hash),
        ("support_contract_hash", support_hash),
    ):
        if h16_manifest.get(name) != value:
            raise ContractError(f"M1_CAPACITY_FROZEN_CONTRACT_MISMATCH:{name}")

    frozen_h16_check = _frozen_architecture_check(
        root=root, scientific=scientific, cache=cache, h16_manifest=h16_manifest
    )
    materialized_counts = {
        int(hidden_size): _parameter_count(
            _build_pipeline(
                scientific=scientific,
                cache=cache,
                hidden_size=int(hidden_size),
            )
        )
        for hidden_size in candidates
    }
    declared_counts = {
        int(hidden_size): DECLARED_PARAMETER_COUNTS.get(int(hidden_size))
        for hidden_size in candidates
    }

    by_seed_rows: list[dict[str, Any]] = []
    target_rows: list[dict[str, Any]] = []
    horizon_rows: list[dict[str, Any]] = []
    stage_rows: list[dict[str, Any]] = []
    calibration_rows: list[dict[str, Any]] = []
    generalization_rows: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []

    for hidden_size in candidates:
        for seed in seeds:
            print(f"[capacity] train H{hidden_size} seed={seed}", flush=True)
            result = _train_single(
                scientific=scientific,
                cache=cache,
                train=train,
                calibration=calibration,
                development=development,
                hidden_size=hidden_size,
                seed=seed,
                device=device,
            )
            lifecycle = result["lifecycle"]
            records = metrics.predict_nodes(
                lifecycle,
                development,
                development_meta,
                batch_size=BATCH_SIZE,
            )
            train_components = _component_map(result["train_objective"])
            development_components = _component_map(
                result["development_objective"]
            )
            train_joint = float(
                result["train_objective"][
                    "EPISODE_BALANCED_JOINT_VALIDATION_LOSS"
                ]
            )
            development_joint = float(
                result["development_objective"][
                    "EPISODE_BALANCED_JOINT_VALIDATION_LOSS"
                ]
            )
            epoch_losses = [float(item["loss"]) for item in result["history"]]
            best_epoch = int(
                min(range(len(epoch_losses)), key=lambda index: epoch_losses[index])
                + 1
            )
            target_seed_rows = _target_rows(hidden_size, seed, records)
            target_rows.extend(target_seed_rows)
            horizon_rows.extend(_horizon_rows(hidden_size, seed, records))
            stage_rows.extend(_stage_rows(hidden_size, seed, records))
            calibration_rows.extend(
                _calibration_rows(hidden_size, seed, records)
            )
            per_target_mae = {
                row["target"]: row["mae"] for row in target_seed_rows
            }
            mean_ace = [
                row["mean_ace"]
                for row in target_seed_rows
                if row["mean_ace"] is not None
            ]
            p90_values = [
                row["p90_ae"]
                for row in target_seed_rows
                if row["p90_ae"] is not None
            ]
            coverage_volatility = [
                row["coverage_max_abs_deviation"]
                for row in target_seed_rows
                if row["coverage_max_abs_deviation"] is not None
            ]
            by_seed_rows.append(
                {
                    "H": hidden_size,
                    "seed": seed,
                    "parameter_count": result["parameter_count"],
                    "epochs": PRIMARY_EPOCHS,
                    "best_epoch": best_epoch,
                    "stopping_epoch": PRIMARY_EPOCHS,
                    "early_stopping": "NOT_USED_BY_FROZEN_CONTRACT",
                    "final_train_loss": _round(epoch_losses[-1]),
                    "best_train_loss": _round(min(epoch_losses)),
                    "train_joint_loss": _round(train_joint),
                    "development_joint_loss": _round(development_joint),
                    "absolute_generalization_gap": _round(
                        development_joint - train_joint
                    ),
                    "relative_generalization_gap": _round(
                        (development_joint - train_joint) / abs(train_joint)
                        if train_joint != 0
                        else None
                    ),
                    "mean_absolute_coverage_error": _round(
                        mean(mean_ace) if mean_ace else None
                    ),
                    "coverage_volatility": _round(
                        max(coverage_volatility) if coverage_volatility else None
                    ),
                    "p90_ae_summary": _round(
                        mean(p90_values) if p90_values else None
                    ),
                    "mae_T_IB": _round(per_target_mae.get(metrics.TARGET_HAZARD)),
                    "mae_D_OB": _round(per_target_mae.get("D_OB")),
                    "mae_D_TX": _round(per_target_mae.get("D_TX")),
                    "temperatures": json.dumps(
                        result["temperatures"], sort_keys=True
                    ),
                    "model_state_hash": result["state_hash"],
                    "runtime_seconds": _round(result["runtime_seconds"], 3),
                }
            )
            for name, value in train_components.items():
                generalization_rows.append(
                    {
                        "H": hidden_size,
                        "seed": seed,
                        "scope": "COMPONENT",
                        "metric": name,
                        "train_value": _round(value),
                        "development_value": _round(
                            development_components[name]
                        ),
                        "absolute_gap": _round(
                            development_components[name] - value
                        ),
                        "relative_gap": _round(
                            (development_components[name] - value) / abs(value)
                            if value != 0
                            else None
                        ),
                    }
                )
            generalization_rows.append(
                {
                    "H": hidden_size,
                    "seed": seed,
                    "scope": "JOINT",
                    "metric": "EPISODE_BALANCED_JOINT_VALIDATION_LOSS",
                    "train_value": _round(train_joint),
                    "development_value": _round(development_joint),
                    "absolute_gap": _round(development_joint - train_joint),
                    "relative_gap": _round(
                        (development_joint - train_joint) / abs(train_joint)
                        if train_joint != 0
                        else None
                    ),
                }
            )
            runs.append(
                {
                    "H": hidden_size,
                    "seed": seed,
                    "train_joint_loss": train_joint,
                    "development_joint_loss": development_joint,
                    "components": development_components,
                    "train_components": train_components,
                    "parameter_count": result["parameter_count"],
                    "model_state_hash": result["state_hash"],
                }
            )

    summary_rows = []
    for hidden_size in candidates:
        subset = [run for run in runs if run["H"] == hidden_size]
        joint_stats = _stats([run["development_joint_loss"] for run in subset])
        train_stats = _stats([run["train_joint_loss"] for run in subset])
        seed_rows = [row for row in by_seed_rows if row["H"] == hidden_size]
        ace_stats = _stats(
            [
                row["mean_absolute_coverage_error"]
                for row in seed_rows
                if row["mean_absolute_coverage_error"] is not None
            ]
        )
        p90_stats = _stats(
            [
                row["p90_ae_summary"]
                for row in seed_rows
                if row["p90_ae_summary"] is not None
            ]
        )
        volatility_stats = _stats(
            [
                row["coverage_volatility"]
                for row in seed_rows
                if row["coverage_volatility"] is not None
            ]
        )
        row: dict[str, Any] = {
            "H": hidden_size,
            "parameter_count": subset[0]["parameter_count"],
            "development_joint_loss_mean": _round(joint_stats["mean"]),
            "development_joint_loss_sd": _round(joint_stats["sd"]),
            "development_joint_loss_se": _round(joint_stats["se"]),
            "train_joint_loss_mean": _round(train_stats["mean"]),
            "relative_generalization_gap": _round(
                (joint_stats["mean"] - train_stats["mean"])
                / abs(train_stats["mean"])
                if train_stats["mean"]
                else None
            ),
            "mean_absolute_coverage_error": _round(ace_stats["mean"]),
            "mean_absolute_coverage_error_sd": _round(ace_stats["sd"]),
            "coverage_volatility": _round(volatility_stats["mean"]),
            "p90_ae_summary": _round(p90_stats["mean"]),
            "p90_ae_summary_sd": _round(p90_stats["sd"]),
            "across_seed_cv": _round(joint_stats["cv"]),
            "across_seed_worst": _round(joint_stats["worst"]),
            "across_seed_n": joint_stats["n"],
        }
        for component in COMPONENT_KEYS:
            stats = _stats([run["components"][component] for run in subset])
            row[f"development_{component}_mean"] = _round(stats["mean"])
            row[f"development_{component}_sd"] = _round(stats["sd"])
            row[f"development_{component}_se"] = _round(stats["se"])
        summary_rows.append(row)

    selection = _select(summary_rows)
    for row in summary_rows:
        row["selection_eligible"] = int(row["H"]) in selection["eligible"]
        row["selected"] = int(row["H"]) == selection["selected_h"]
        row["selection_reason"] = selection["selection_rule"]
    frozen_h = int(scientific.parameters["m1_hidden_size"].value)
    if selection["selected_h"] != frozen_h:
        selection["scientific_reconciliation_required"] = True
        selection["status"] = "SCIENTIFIC_RECONCILIATION_REQUIRED"
    else:
        selection["scientific_reconciliation_required"] = False
        selection["status"] = "SELECTION_CONSISTENT_WITH_H16_AUTHORITY"

    manifest: dict[str, Any] = {
        "schema_version": "M1_H_CAPACITY_SELECTION_MANIFEST_V1",
        "artifact_scope": ARTIFACT_SCOPE,
        "repository_head": _git_head(root),
        "dataset": "DATA2_2019",
        "candidate_hidden_sizes": list(candidates),
        "candidate_parameter_counts": {
            str(h): materialized_counts[int(h)] for h in candidates
        },
        "declared_parameter_counts": {
            str(h): declared_counts[int(h)] for h in candidates
        },
        "declared_parameter_count_source": DECLARED_PARAMETER_COUNT_SOURCE,
        "parameter_count_declaration_match": {
            str(h): declared_counts[int(h)] == materialized_counts[int(h)]
            for h in candidates
        },
        "parameter_count_note": PARAMETER_COUNT_NOTE,
        "frozen_h16_architecture_check": frozen_h16_check,
        "paired_training_seeds": list(seeds),
        "training_config_source": (
            "model/M1/tuning_stage1.py:STAGE1_TRAINING_CONFIG"
        ),
        "training_config": {
            key: STAGE1_TRAINING_CONFIG[key]
            for key in (
                "optimizer",
                "learning_rate",
                "weight_decay",
                "epochs",
                "batch_size",
            )
        },
        "early_stopping": "NOT_USED_BY_FROZEN_CONTRACT",
        "initialization_control": (
            "torch.manual_seed(run_seed) applied before candidate "
            "construction; identical for every candidate and seed"
        ),
        "split_roles": dict(STAGE1_SPLITS),
        "inputs": {
            "cache_path": str(cache_path.relative_to(root)),
            "cache_file_hash": file_hash(cache_path),
            "cache_hash": cache_manifest.get("cache_hash"),
            "cache_key": cache_manifest.get("cache_key"),
            "cache_manifest_hash": file_hash(cache_manifest_path),
            "cohort_path": str(cohort_path.relative_to(root)),
            "cohort_file_hash": file_hash(cohort_path),
            "train_episode_hash": cohort.get("train_episode_hash"),
            "calibration_episode_hash": cohort.get("calibration_episode_hash"),
            "development_episode_hash": cohort.get("development_episode_hash"),
            "node_metadata_path": str(node_input_path.relative_to(root)),
            "node_metadata_file_hash": file_hash(node_input_path),
            "h16_manifest_path": str(
                (root / H16_MANIFEST_PATH).relative_to(root)
            ),
            "h16_manifest_hash": file_hash(root / H16_MANIFEST_PATH),
        },
        "contracts": {
            "feature_contract_hash": feature_hash,
            "support_contract_hash": support_hash,
            "support": contract["support"],
            "target_contract_hash": h16_manifest.get("target_contract_hash"),
            "quantile_grid": h16_manifest.get("quantile_grid"),
            "history_mode": "FULL_ADAPTIVE_CAUSAL_PREFIX",
        },
        "runs": [
            {
                "H": run["H"],
                "seed": run["seed"],
                "parameter_count": run["parameter_count"],
                "model_state_hash": run["model_state_hash"],
                "train_joint_loss": _round(run["train_joint_loss"]),
                "development_joint_loss": _round(
                    run["development_joint_loss"]
                ),
            }
            for run in runs
        ],
        "selection": selection,
        "final_test_access_count": 0,
        "downstream_decision_metrics_used": False,
        "frozen_artifacts_modified": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    write_csv(output_root / OUTPUT_NAMES[0], by_seed_rows)
    write_csv(output_root / OUTPUT_NAMES[1], target_rows)
    write_csv(output_root / OUTPUT_NAMES[2], horizon_rows)
    write_csv(output_root / OUTPUT_NAMES[3], stage_rows)
    write_csv(output_root / OUTPUT_NAMES[4], calibration_rows)
    write_csv(output_root / OUTPUT_NAMES[5], generalization_rows)
    write_csv(output_root / OUTPUT_NAMES[6], summary_rows)
    (output_root / OUTPUT_NAMES[7]).write_text(
        _render_report(
            manifest=manifest,
            summary_rows=summary_rows,
            target_rows=target_rows,
            stage_rows=stage_rows,
            selection=selection,
        ),
        encoding="utf-8",
    )
    manifest["outputs"] = {
        name: file_hash(output_root / name) for name in OUTPUT_NAMES
    }
    write_json(
        output_root / "M1_H_CAPACITY_SELECTION_MANIFEST.json", manifest
    )
    return {
        "status": "PASS",
        "output_root": str(output_root),
        "selection": selection,
        "summary_rows": summary_rows,
        "manifest_path": str(
            output_root / "M1_H_CAPACITY_SELECTION_MANIFEST.json"
        ),
    }


def _render_report(
    *,
    manifest: Mapping[str, Any],
    summary_rows: Sequence[Mapping[str, Any]],
    target_rows: Sequence[Mapping[str, Any]],
    stage_rows: Sequence[Mapping[str, Any]],
    selection: Mapping[str, Any],
) -> str:
    lines = [
        "# M1 history-encoder capacity selection (H8 / H16 / H32)",
        "",
        "Development-only state-prediction experiment. No consequence, ranking,",
        "attention, recovery or decision-value metric participates in this report,",
        "and no Final-Test path is read.",
        "",
        "## Run contract",
        "",
        f"- repository HEAD: `{manifest['repository_head']}`",
        f"- candidates: {manifest['candidate_hidden_sizes']} "
        f"(parameters {manifest['candidate_parameter_counts']})",
        f"- declared parameter counts (closure manifest, kept unchanged): "
        f"{manifest['declared_parameter_counts']}",
        "- frozen H16 architecture check: "
        f"`{manifest['frozen_h16_architecture_check']['status']}` "
        f"({manifest['frozen_h16_architecture_check']['frozen_parameter_count']} "
        "parameters, signature "
        f"`{manifest['frozen_h16_architecture_check']['architecture_signature_hash']}`),",
        f"- paired seeds: {manifest['paired_training_seeds']}",
        f"- training config: {manifest['training_config']}",
        f"- early stopping: `{manifest['early_stopping']}`",
        f"- splits: {manifest['split_roles']}",
        f"- cache hash: `{manifest['inputs']['cache_hash']}`",
        f"- feature contract hash: `{manifest['contracts']['feature_contract_hash']}`",
        f"- support contract hash: `{manifest['contracts']['support_contract_hash']}`",
        f"- Final-Test access count: {manifest['final_test_access_count']}",
        "- downstream decision metrics used: false",
        "",
        "## Primary selection metric by capacity",
        "",
        "| H | parameters | dev joint mean | SD | SE | train joint mean | rel. gap |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['H']} | {row['parameter_count']} | "
            f"{row['development_joint_loss_mean']} | "
            f"{row['development_joint_loss_sd']} | "
            f"{row['development_joint_loss_se']} | "
            f"{row['train_joint_loss_mean']} | "
            f"{row['relative_generalization_gap']} |"
        )
    lines.extend(
        [
            "",
            "## Selection",
            "",
            f"- rule: `{selection['selection_rule']}`",
            f"- best mean capacity: H{selection['best_mean_h']} "
            f"(mean {selection['best_mean_loss']:.6f}, "
            f"SE {selection['best_se']:.6f})",
            f"- eligible (mean <= best + SE): {selection['eligible']}",
            f"- selected: H{selection['selected_h']}",
            f"- status: `{selection['status']}`",
        ]
    )
    for note in selection["guardrail_notes"]:
        lines.append(f"- guardrail: {note}")
    lines.extend(
        [
            "",
            "## Per-target Development metrics (mean over seeds)",
            "",
            "| H | target | MAE | median AE | P90AE | Cov50 | Cov80 | Cov90 | mean ACE |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )
    grouped: dict[tuple[int, str], list[Mapping[str, Any]]] = {}
    for row in target_rows:
        grouped.setdefault((int(row["H"]), row["target"]), []).append(row)
    for (hidden_size, target), rows in sorted(grouped.items()):
        def _average(key: str) -> Any:
            values = [row[key] for row in rows if row.get(key) is not None]
            if not values:
                return "N/A_NOT_DEFINED"
            return round(mean(values), 6)

        lines.append(
            f"| H{hidden_size} | {target} | {_average('mae')} | "
            f"{_average('median_ae')} | {_average('p90_ae')} | "
            f"{_average('cov50')} | {_average('cov80')} | "
            f"{_average('cov90')} | {_average('mean_ace')} |"
        )
    lines.extend(
        [
            "",
            "## Operating-stage robustness (mean over seeds)",
            "",
            "| H | stage | target | n | MAE | P90AE |",
            "|---|---|---|---|---|---|",
        ]
    )
    stage_grouped: dict[tuple[int, str, str], list[Mapping[str, Any]]] = {}
    for row in stage_rows:
        key = (int(row["H"]), row["operational_stage"], row["target"])
        stage_grouped.setdefault(key, []).append(row)
    for (hidden_size, stage, target), rows in sorted(stage_grouped.items()):
        counts = int(round(mean([row["n_active"] for row in rows])))
        mae_values = [
            row["mae"] for row in rows if row["mae"] is not None
        ]
        p90_values = [
            row["p90_ae"] for row in rows if row["p90_ae"] is not None
        ]
        lines.append(
            f"| H{hidden_size} | {stage} | {target} | {counts} | "
            f"{round(mean(mae_values), 6)} | {round(mean(p90_values), 6)} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- The frozen training contract has no early stopping; every candidate",
            "  runs the identical 8-epoch budget with the identical optimizer,",
            "  learning rate, batch size, cohort, seeds, support and quantile grid.",
            "- Cov90 for D_OB / D_TX is reported as",
            "  `NOT_DEFINED_FROZEN_QUANTILE_GRID` because the frozen grid is",
            "  (0.1, 0.3, 0.5, 0.7, 0.9) and 90 percent coverage would need q05/q95.",
            "- Per-lead tables use the realized-lead definitions of the frozen",
            "  M1 horizon diagnostic; leads outside the capture window are excluded",
            "  rather than re-binned.",
            "- CRPS is reported only for T_IB finite support, where the frozen",
            "  representation defines it; the hurdle targets report pinball and",
            "  zero-mass calibration instead.",
            "- Point metrics (MAE / median AE / P90AE) use every active label,",
            "  hurdle zeros included; coverage, width and calibration",
            "  diagnostics use the frozen positive-outcome population for",
            "  D_OB / D_TX (``n_coverage`` in the target and lead tables).",
            "- Declared candidate parameter counts from the closure manifest",
            "  differ from the counts materialized by the current frozen",
            "  architecture definition; materialized counts are reported, the",
            "  declarations are preserved unchanged, and the H16 recipe is",
            "  proven signature-equal to the frozen H16 runtime artifact.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--candidates", default=",".join(map(str, CANDIDATE_HIDDEN_SIZES))
    )
    parser.add_argument("--seeds", default=",".join(map(str, PAIRED_SEEDS)))
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args(argv)
    result = run_capacity_selection(
        root=args.root,
        output_root=args.output,
        candidates=tuple(
            int(value) for value in args.candidates.split(",") if value
        ),
        seeds=tuple(int(value) for value in args.seeds.split(",") if value),
        device=args.device,
    )
    print(json.dumps(result["selection"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
