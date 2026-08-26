"""T-cal: M1 V2 shared calibration artifact (2026-08-26).

Fits ONLY the two pieces declared in ``M1_CALIBRATION_CONTRACT_V1``
(``configs/scientific/foundation.yaml`` L234-245) on the calibration split
(2019-07-01..2019-07-31, 64 episodes, ``configs/evaluation/common.yaml``):

- predecessor probability calibration ``DISCRETE_HAZARD_EVENT_TIME_NLL``
  (temperature on hazard logits, event-time NLL; multiclass softmax
  forbidden);
- successor zero-mass calibration ``HURDLE_ZERO_BINARY_CE_TEMPERATURE``
  (binary-CE temperature on the hurdle zero logits for D_OB and D_TX).

Positive-quantile calibration stays ``QUANTILE_CALIBRATION_NOT_APPLIED``
(coverage recorded as provenance only).  One-shot fit; no selection loop; no
hyperparameter search; Train / Development / Final Test splits are not read
and not written.  ONE shared artifact is written under
``artifacts/calibration/m1_v2_calibration_20260826/`` and is applied
IDENTICALLY (same file, same procedure) to the frozen STATE_AWARE H32
checkpoint and the CURRENT-only comparator checkpoint.  Frozen checkpoints
are loaded read-only; their weights are never modified (hashes before/after
recorded).  ``paper_result=false``, ``FINAL_TEST_ACCESS_COUNT=0``.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any

import torch

from model.common.config import load_config_layers
from model.common.identity import content_id
from model.M1.cache import M1DevelopmentBaseCache
from model.M1.calibration import (
    fit_hazard_temperature,
    fit_zero_mass_temperature,
    quantile_coverage_diagnostic,
    require_calibration_split,
)
from model.M1.contracts import M1_TEMPERATURE_D_OB_ZERO, M1_TEMPERATURE_D_TX_ZERO, M1_TEMPERATURE_HAZARD
from model.M1.lifecycle import M1Lifecycle
from model.M1.loss import hazard_interval_nll, monotone_positive_quantiles
from model.M1.semantics import M1_V2_HAZARD_COORDINATE_TARGET

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path("artifacts/calibration/m1_v2_calibration_20260826")
CACHE_PATH = Path(
    "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz"
)
CACHE_MANIFEST_PATH = Path(
    "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json"
)
STATE_AWARE_CHECKPOINT = Path(
    "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt"
)
CURRENT_ONLY_CHECKPOINT = Path(
    "artifacts/experiment/exp1_full_development/exp1_closure_20260825/"
    "EXP1B_CURRENT_ONLY_H32/M1_V2_FAST_TRAIN_MODE.pt"
)
STATE_AWARE_MODEL_ID = "M1_V2_GRU_H32"
CURRENT_ONLY_MODEL_ID = "M1_V2_GRU_H32_CURRENT_ONLY"
CALIBRATION_SPLIT = (date(2019, 7, 1), date(2019, 7, 31))
EXPECTED_CALIBRATION_EPISODES = 64
SAFETY = {
    "FINAL_TEST_ACCESS_COUNT": 0,
    "M1_TRAINING_RUNS": 0,
    "TUNING_RUNS": 0,
    "PAPER_FULL_RUN": False,
}
SCHEMA_VERSION = "AIR_SLOT_M1_V2_CALIBRATION_ARTIFACT_V1"

HAZARD_COORDINATE = M1_V2_HAZARD_COORDINATE_TARGET


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _hazard_nll_at(
    logits: torch.Tensor,
    labels: torch.Tensor,
    active: torch.Tensor,
    contract,
    temperature: float,
) -> float:
    """Event-time NLL of the discrete-hazard head at a given temperature."""
    labels = torch.as_tensor(labels, dtype=torch.long)
    active = torch.as_tensor(active, dtype=torch.bool)
    lower = torch.full((logits.shape[0],), -1.0, dtype=torch.float32)
    upper = torch.full((logits.shape[0],), -1.0, dtype=torch.float32)
    for index in active.nonzero(as_tuple=False).reshape(-1).tolist():
        bin_index = int(labels[index])
        _require(bin_index >= 0, "M1_CALIBRATION_ACTIVE_LABEL_INVALID")
        lower[index] = contract.bin_start(bin_index)
        upper[index] = contract.bin_end(bin_index)
    if not bool(active.any()):
        return float("nan")
    return float(
        hazard_interval_nll(
            logits / temperature,
            contract,
            lower=lower,
            upper=upper,
            active=active,
        ).item()
    )


def _zero_bce_at(
    logits: torch.Tensor, zero: torch.Tensor, active: torch.Tensor, temperature: float,
) -> float:
    logits = torch.as_tensor(logits, dtype=torch.float32).reshape(-1)
    zero = torch.as_tensor(zero, dtype=torch.float32).reshape(-1)
    active = torch.as_tensor(active, dtype=torch.bool).reshape(-1)
    if not bool(active.any()):
        return float("nan")
    return float(
        torch.nn.functional.binary_cross_entropy_with_logits(
            logits[active] / temperature, zero[active]
        ).item()
    )


def _fit_one_model(
    *,
    checkpoint_path: Path,
    examples: tuple,
    model_id: str,
) -> dict[str, Any]:
    """One-shot fit of the two contracted pieces for one frozen checkpoint.

    Read-only on the checkpoint (hash recorded before/after); the pipeline is
    mutated only in memory and never saved.
    """
    hash_before = _sha256(checkpoint_path)
    lifecycle = M1Lifecycle.load(checkpoint_path)
    logits, labels, active, zero = lifecycle.batched_logits(
        examples, teacher_forcing=True,
    )
    hazard = lifecycle.pipeline.contracts[HAZARD_COORDINATE]
    hazard_active = active[HAZARD_COORDINATE]
    hazard_logits = logits[HAZARD_COORDINATE]

    # before metrics (provenance only): temperatures 1.0
    nll_before = _hazard_nll_at(
        hazard_logits, labels[HAZARD_COORDINATE], hazard_active, hazard, 1.0,
    )
    bce_before: dict[str, float | None] = {}
    for name, key in (("D_OB", M1_TEMPERATURE_D_OB_ZERO), ("D_TX", M1_TEMPERATURE_D_TX_ZERO)):
        target_active = active[name]
        bce_before[name] = _zero_bce_at(
            logits[f"{name}_zero"], zero[name], target_active, 1.0,
        )

    # fit (calibration split only; no selection loop)
    temperature_hazard = fit_hazard_temperature(
        hazard_logits, labels[HAZARD_COORDINATE], hazard_active, hazard,
        split="calibration",
    )
    temperatures = {M1_TEMPERATURE_HAZARD: temperature_hazard}
    bce_after: dict[str, float | None] = {}
    for name, key in (("D_OB", M1_TEMPERATURE_D_OB_ZERO), ("D_TX", M1_TEMPERATURE_D_TX_ZERO)):
        target_active = active[name]
        fitted = fit_zero_mass_temperature(
            logits[f"{name}_zero"], zero[name], target_active, split="calibration",
        )
        temperatures[key] = fitted
        bce_after[name] = _zero_bce_at(
            logits[f"{name}_zero"], zero[name], target_active, fitted,
        )

    nll_after = _hazard_nll_at(
        hazard_logits, labels[HAZARD_COORDINATE], hazard_active, hazard,
        temperature_hazard,
    )
    coverage: dict[str, dict[str, float | None] | None] = {}
    for name in ("D_OB", "D_TX"):
        actual = torch.tensor(
            [
                (
                    float(row.targets[name])
                    if row.targets.get(name) is not None
                    else float("nan")
                )
                for row in examples
            ],
            dtype=torch.float32,
        )
        positive_active = active[name] & ~zero[name] & torch.isfinite(actual)
        predicted = monotone_positive_quantiles(logits[f"{name}_quantile"])
        coverage[name] = quantile_coverage_diagnostic(
            predicted, actual, tuple(lifecycle.pipeline.contracts[name].quantile_levels),
            positive_active, split="calibration",
        )
    hash_after = _sha256(checkpoint_path)
    _require(hash_before == hash_after, "M1_CALIBRATION_CHECKPOINT_MODIFIED")
    return {
        "model_id": model_id,
        "checkpoint_path": str(checkpoint_path.relative_to(ROOT)).replace("\\", "/"),
        "checkpoint_sha256_before": hash_before,
        "checkpoint_sha256_after": hash_after,
        "n_episodes": len({row.episode_id for row in examples}),
        "n_nodes": len(examples),
        "active_counts": {
            "hazard": int(hazard_active.sum()),
            "d_ob_zero": int((active["D_OB"]).sum()),
            "d_tx_zero": int((active["D_TX"]).sum()),
        },
        "temperatures": {
            "hazard": temperature_hazard,
            "d_ob_zero": temperatures[M1_TEMPERATURE_D_OB_ZERO],
            "d_tx_zero": temperatures[M1_TEMPERATURE_D_TX_ZERO],
        },
        "before_metrics": {"hazard_event_time_nll": nll_before, "zero_bce": bce_before},
        "after_metrics": {"hazard_event_time_nll": nll_after, "zero_bce": bce_after},
        "quantile_coverage_diagnostics": coverage,
        "positive_quantile_calibration": "QUANTILE_CALIBRATION_NOT_APPLIED",
    }


def materialize(*, root: Path | None = None, output_root: Path | None = None) -> dict[str, Any]:
    """Fit and write the shared calibration artifact (one-shot, calibration split only)."""
    root = (root or ROOT).resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    _require(root in output_root.parents, "CALIBRATION_OUTPUT_OUTSIDE_PROJECT")

    cache_manifest = json.loads((root / CACHE_MANIFEST_PATH).read_text(encoding="utf-8"))
    _require(cache_manifest.get("final_test_included") is False, "M1_CALIBRATION_CACHE_FINAL_TEST_GUARD_FAILED")
    _require(cache_manifest.get("final_test_access_count") == 0, "M1_CALIBRATION_CACHE_FINAL_TEST_ACCESS")
    _require(
        cache_manifest.get("cache_build_scope") == ["train", "calibration", "development"],
        "M1_CALIBRATION_CACHE_SCOPE_INVALID",
    )
    _require(
        int(cache_manifest.get("calibration_episode_count", -1)) == EXPECTED_CALIBRATION_EPISODES,
        "M1_CALIBRATION_CALIBRATION_EPISODE_COUNT_INVALID",
    )
    cache = M1DevelopmentBaseCache.load(
        root / CACHE_PATH,
        root / CACHE_MANIFEST_PATH,
        expected_cache_key=cache_manifest["cache_key"],
    )
    history_examples = tuple(cache.partition("calibration"))
    current_examples = tuple(cache.partition("calibration", representation="CURRENT"))
    for examples in (history_examples, current_examples):
        _require(len(examples) > 0, "M1_CALIBRATION_SPLIT_EMPTY")
        episode_dates = {row.episode_date for row in examples}
        _require(
            all(CALIBRATION_SPLIT[0] <= d <= CALIBRATION_SPLIT[1] for d in episode_dates),
            "M1_CALIBRATION_SPLIT_BOUNDARY_VIOLATION",
        )
        _require(
            len({row.episode_id for row in examples}) == EXPECTED_CALIBRATION_EPISODES,
            "M1_CALIBRATION_EPISODE_COUNT_DRIFT",
        )

    state_aware = _fit_one_model(
        checkpoint_path=root / STATE_AWARE_CHECKPOINT,
        examples=history_examples,
        model_id=STATE_AWARE_MODEL_ID,
    )
    current_only = _fit_one_model(
        checkpoint_path=root / CURRENT_ONLY_CHECKPOINT,
        examples=current_examples,
        model_id=CURRENT_ONLY_MODEL_ID,
    )

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "status": "FROZEN_SHARED_CALIBRATION_ARTIFACT",
        "decision_id": "AIR_SLOT_HUMAN_GATES_ALL_APPROVED_20260826 (D7=B, D7a-D7d=A)",
        "policy": "M1_CALIBRATION_CONTRACT_V1",
        "predecessor_probability_calibration": "DISCRETE_HAZARD_EVENT_TIME_NLL",
        "predecessor_calibration_method": "TEMPERATURE_ON_HAZARD_LOGITS",
        "successor_zero_mass_calibration": "HURDLE_ZERO_BINARY_CE_TEMPERATURE",
        "positive_quantile_calibration": "QUANTILE_CALIBRATION_NOT_APPLIED",
        "calibration_split": {"start": "2019-07-01", "end": "2019-07-31", "n_episodes": EXPECTED_CALIBRATION_EPISODES},
        "fitting_procedure": {
            "one_shot": True,
            "selection_loop": "NONE",
            "hyperparameter_search": "NONE",
            "optimizer": "LBFGS",
            "steps": 50,
            "temperature_clamp": [0.05, 20.0],
            "train_split_read": False,
            "development_split_read": False,
            "final_test_split_read": False,
        },
        "shared_by": [STATE_AWARE_MODEL_ID, CURRENT_ONLY_MODEL_ID],
        "application": "IDENTICAL_SHARED_ARTIFACT_FILE_EACH_MODEL_USES_ITS_FITTED_TEMPERATURE_SET",
        "models": {"STATE_AWARE_H32": state_aware, "CURRENT_ONLY": current_only},
        "safety": dict(SAFETY),
        "paper_result": False,
    }
    artifact["artifact_hash"] = content_id(artifact)
    _write_json(output_root / "M1_V2_CALIBRATION_ARTIFACT.json", artifact)
    manifest = {
        "schema_version": SCHEMA_VERSION + "_MANIFEST",
        "status": "M1_V2_CALIBRATION_ARTIFACT_MATERIALIZED",
        "scope": "CALIBRATION_SPLIT_ONLY_DEVELOPMENT_SAFE",
        "artifact": str((output_root / "M1_V2_CALIBRATION_ARTIFACT.json").relative_to(root)).replace("\\", "/"),
        "artifact_hash": artifact["artifact_hash"],
        "calibration_split": artifact["calibration_split"],
        "checkpoint_hashes_unchanged": {
            STATE_AWARE_MODEL_ID: state_aware["checkpoint_sha256_before"] == state_aware["checkpoint_sha256_after"],
            CURRENT_ONLY_MODEL_ID: current_only["checkpoint_sha256_before"] == current_only["checkpoint_sha256_after"],
        },
        "input_hashes": {
            "cache": cache_manifest["cache_hash"],
            "feature_schema_hash": cache_manifest["feature_schema_hash"],
            "state_aware_checkpoint": state_aware["checkpoint_sha256_before"],
            "current_only_checkpoint": current_only["checkpoint_sha256_before"],
        },
        "shared_by": artifact["shared_by"],
        "quantile_calibration": "QUANTILE_CALIBRATION_NOT_APPLIED",
        "safety": dict(SAFETY),
    }
    manifest["manifest_hash"] = content_id(manifest)
    _write_json(output_root / "M1_V2_CALIBRATION_MANIFEST.json", manifest)
    return {"artifact": output_root / "M1_V2_CALIBRATION_ARTIFACT.json", "manifest": output_root / "M1_V2_CALIBRATION_MANIFEST.json"}


def apply_calibration_artifact(pipeline, artifact_payload: dict[str, Any], model_id: str) -> dict[str, float]:
    """Apply the shared artifact to a loaded (frozen) pipeline in memory only.

    Sets ``pipeline.temperatures`` for the given model from the shared
    artifact.  Never saves the pipeline; the checkpoint file is untouched.
    """
    models = artifact_payload.get("models", {})
    for record in models.values():
        if record.get("model_id") == model_id:
            temps = record["temperatures"]
            result = {
                M1_TEMPERATURE_HAZARD: float(temps["hazard"]),
                M1_TEMPERATURE_D_OB_ZERO: float(temps["d_ob_zero"]),
                M1_TEMPERATURE_D_TX_ZERO: float(temps["d_tx_zero"]),
            }
            pipeline.temperatures = dict(result)
            return result
    raise KeyError(f"M1_CALIBRATION_ARTIFACT_MODEL_NOT_FOUND:{model_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    result = materialize(output_root=args.output_root)
    print(json.dumps({k: str(v.relative_to(ROOT)).replace("\\", "/") for k, v in result.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

