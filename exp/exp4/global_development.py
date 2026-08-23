"""Data2 Development baselines and bounded Data1 applicability for Exp4."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path
from statistics import mean
import time
from typing import Any

import joblib
import numpy as np
from lightgbm import LGBMRegressor
from sklearn.ensemble import RandomForestRegressor

from codex_framework.air_slot_framework.experiments import build_data1_acceptance_report
from exp.common.official_execution import file_sha256, load_json, write_json
from exp.exp4.protocol import EVALUATION_LEAD_MINUTES
from model.M1.cache import M1DevelopmentBaseCache
from model.M1.development_diagnostics import evaluate_lifecycle
from model.M1.lifecycle import M1Lifecycle
from model.common.identity import content_id


CACHE = Path("artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz")
CACHE_MANIFEST = CACHE.with_name("M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json")
CHECKPOINT = Path("artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt")
INPUT_ROOT = Path("artifacts/experiment/full_development_inputs_v1")
DEFAULT_OUTPUT = Path("artifacts/experiments/exp4/full_development_v1")
TARGETS = ("T_IB_REMAINING_HAZARD", "D_OB", "D_TX")
BASELINES = ("HISTORICAL", "LIGHTGBM", "RANDOM_FOREST", "STATE_AWARE_H32")
SEED = 20260823
SAMPLE_COUNT = 128
SAFETY = {
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "DEVELOPMENT_TUNING": False,
    "DATA1_DATA2_POOLING": False,
}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _cache(root: Path) -> M1DevelopmentBaseCache:
    manifest = load_json(root / CACHE_MANIFEST)
    return M1DevelopmentBaseCache.load(
        root / CACHE, root / CACHE_MANIFEST,
        expected_cache_key=manifest["cache_key"],
    )


def _features(examples) -> np.ndarray:
    rows = []
    for example in examples:
        dynamic = example.values[-1].detach().cpu().numpy().astype(np.float32)
        static = (
            np.zeros(0, dtype=np.float32)
            if example.static_values is None
            else example.static_values.detach().cpu().numpy().astype(np.float32)
        )
        rows.append(np.concatenate((dynamic, static)))
    result = np.stack(rows)
    _require(result.shape[1] == 43, "EXP4_FEATURE_SCHEMA_WIDTH_INVALID")
    _require(np.isfinite(result).all(), "EXP4_FEATURE_NONFINITE")
    return result


def _active(examples, target: str) -> tuple[np.ndarray, np.ndarray]:
    indexes = np.array([
        index for index, example in enumerate(examples)
        if example.active.get(target) and example.targets.get(target) is not None
    ], dtype=np.int64)
    values = np.array([float(examples[index].targets[target]) for index in indexes], dtype=np.float64)
    return indexes, values


def _quantile_samples(values: np.ndarray, count: int = SAMPLE_COUNT) -> np.ndarray:
    levels = (np.arange(count, dtype=np.float64) + 0.5) / count
    return np.quantile(values, levels)


def _crps(samples: np.ndarray, observations: np.ndarray) -> np.ndarray:
    samples = np.asarray(samples, dtype=np.float64)
    observations = np.asarray(observations, dtype=np.float64)
    first = np.mean(np.abs(samples - observations[:, None]), axis=1)
    ordered = np.sort(samples, axis=1)
    n = ordered.shape[1]
    coefficients = 2.0 * np.arange(1, n + 1) - n - 1.0
    half_pairwise = np.sum(ordered * coefficients[None, :], axis=1) / (n * n)
    return first - half_pairwise


def _event(target: str, values: np.ndarray) -> np.ndarray:
    if target == "T_IB_REMAINING_HAZARD":
        return (values > 30.0).astype(np.float64)
    return (values <= 0.5).astype(np.float64)


def _probability(target: str, samples: np.ndarray) -> np.ndarray:
    if target == "T_IB_REMAINING_HAZARD":
        return np.mean(samples > 30.0, axis=1)
    return np.mean(samples <= 0.5, axis=1)


def _calibration(probabilities: np.ndarray, outcomes: np.ndarray) -> dict[str, Any]:
    bins = []
    gap = 0.0
    count = len(probabilities)
    for index in range(10):
        selected = np.minimum((probabilities * 10).astype(int), 9) == index
        n = int(selected.sum())
        if not n:
            bins.append({"bin": index, "count": 0, "forecast": None, "observed": None, "gap": None})
            continue
        forecast = float(probabilities[selected].mean())
        observed = float(outcomes[selected].mean())
        absolute = abs(forecast - observed)
        gap += n / count * absolute
        bins.append({"bin": index, "count": n, "forecast": forecast, "observed": observed, "gap": absolute})
    return {"fixed_bin_calibration_gap": gap, "bins": bins}


def _lead_map(inputs: dict[str, Any]) -> dict[str, int]:
    schedule_by_current: dict[str, datetime] = {}
    for states in inputs["pre_states_by_episode"].values():
        for state in states:
            node = state["decision_node"]
            schedule = state["successor_state"].get("schedule_reference", {}).get("value")
            if isinstance(schedule, dict) and schedule.get("scheduled_departure_utc"):
                schedule_by_current[node["decision_node_id"]] = datetime.fromisoformat(
                    schedule["scheduled_departure_utc"]
                )
    result = {}
    for row in inputs["inference_inputs"]:
        scheduled = schedule_by_current.get(row["decision_node_id"])
        if scheduled is None:
            continue
        decision = datetime.fromisoformat(row["decision_time"])
        minutes = max(0.0, (scheduled - decision).total_seconds() / 60.0)
        lead = min(EVALUATION_LEAD_MINUTES, key=lambda value: abs(value - minutes))
        result[row["historical_decision_node_id"]] = int(lead)
    return result


def _summarize_predictions(
    *, target_payloads: dict[str, dict[str, Any]], examples,
    lead_map: dict[str, int], fit_seconds: float, predict_seconds: float,
) -> dict[str, Any]:
    target_metrics = {}
    all_mae: list[float] = []
    all_crps: list[float] = []
    all_brier: list[float] = []
    all_calibration: list[float] = []
    horizon_errors: dict[int, list[float]] = defaultdict(list)
    for target, payload in target_payloads.items():
        indexes = payload["indexes"]
        observed = payload["observed"]
        point = payload["point"]
        samples = payload["samples"]
        errors = np.abs(point - observed)
        scores = _crps(samples, observed)
        outcomes = _event(target, observed)
        probabilities = _probability(target, samples)
        brier = (probabilities - outcomes) ** 2
        calibration = _calibration(probabilities, outcomes)
        for local_index, example_index in enumerate(indexes):
            node_id = examples[int(example_index)].decision_node_id
            if node_id in lead_map:
                horizon_errors[lead_map[node_id]].append(float(errors[local_index]))
        target_metrics[target] = {
            "active_node_count": int(len(observed)),
            "mae_minutes": float(errors.mean()),
            "crps_minutes": float(scores.mean()),
            "brier": float(brier.mean()),
            "calibration": calibration,
        }
        all_mae.extend(errors.tolist())
        if target == "T_IB_REMAINING_HAZARD":
            all_crps.extend(scores.tolist())
        all_brier.extend(brier.tolist())
        all_calibration.append(calibration["fixed_bin_calibration_gap"])
    return {
        "support_status": "SUPPORTED",
        "target_metrics": target_metrics,
        "mae_minutes": mean(all_mae),
        "crps_minutes": mean(all_crps),
        "crps_scope": "T_IB_FINITE_SUPPORT_COMPARISON_SCOPE",
        "brier": mean(all_brier),
        "calibration_gap": mean(all_calibration),
        "horizon_mae_minutes": {
            str(lead): (None if not horizon_errors[lead] else mean(horizon_errors[lead]))
            for lead in EVALUATION_LEAD_MINUTES
        },
        "runtime": {
            "fit_seconds": fit_seconds,
            "predict_seconds": predict_seconds,
            "development_nodes_per_second": len(examples) / max(predict_seconds, 1e-12),
        },
    }


def _historical(train, development, lead_map) -> tuple[dict[str, Any], dict[str, Any]]:
    payloads = {}
    artifact = {"baseline": "HISTORICAL", "targets": {}}
    for target in TARGETS:
        _, train_y = _active(train, target)
        dev_indexes, dev_y = _active(development, target)
        samples = _quantile_samples(train_y)
        matrix = np.repeat(samples[None, :], len(dev_y), axis=0)
        payloads[target] = {
            "indexes": dev_indexes, "observed": dev_y,
            "point": np.median(matrix, axis=1), "samples": matrix,
        }
        artifact["targets"][target] = {
            "train_count": int(len(train_y)),
            "empirical_samples": samples.tolist(),
        }
    return _summarize_predictions(
        target_payloads=payloads, examples=development, lead_map=lead_map,
        fit_seconds=0.0, predict_seconds=0.0,
    ), artifact


def _random_forest(train, development, x_train, x_dev, lead_map):
    models = {}
    payloads = {}
    fit_started = time.perf_counter()
    for offset, target in enumerate(TARGETS):
        train_indexes, train_y = _active(train, target)
        model = RandomForestRegressor(
            n_estimators=SAMPLE_COUNT, min_samples_leaf=5,
            max_features="sqrt", random_state=SEED + offset, n_jobs=-1,
        )
        model.fit(x_train[train_indexes], train_y)
        models[target] = model
    fit_seconds = time.perf_counter() - fit_started
    predict_started = time.perf_counter()
    for target, model in models.items():
        dev_indexes, dev_y = _active(development, target)
        matrix = np.column_stack([
            np.clip(tree.predict(x_dev[dev_indexes]), 0.0, None)
            for tree in model.estimators_
        ])
        payloads[target] = {
            "indexes": dev_indexes, "observed": dev_y,
            "point": np.median(matrix, axis=1), "samples": matrix,
        }
    predict_seconds = time.perf_counter() - predict_started
    return _summarize_predictions(
        target_payloads=payloads, examples=development, lead_map=lead_map,
        fit_seconds=fit_seconds, predict_seconds=predict_seconds,
    ), models


def _lightgbm(train, calibration, development, x_train, x_cal, x_dev, lead_map):
    models = {}
    residual_samples = {}
    payloads = {}
    fit_started = time.perf_counter()
    for offset, target in enumerate(TARGETS):
        train_indexes, train_y = _active(train, target)
        model = LGBMRegressor(
            objective="regression_l1", n_estimators=200, learning_rate=0.05,
            num_leaves=31, min_child_samples=20, subsample=1.0,
            colsample_bytree=1.0, reg_lambda=0.0,
            random_state=SEED + offset, n_jobs=-1, verbosity=-1,
        )
        model.fit(x_train[train_indexes], train_y)
        cal_indexes, cal_y = _active(calibration, target)
        residuals = cal_y - np.clip(model.predict(x_cal[cal_indexes]), 0.0, None)
        residual_samples[target] = _quantile_samples(residuals)
        models[target] = model
    fit_seconds = time.perf_counter() - fit_started
    predict_started = time.perf_counter()
    for target, model in models.items():
        dev_indexes, dev_y = _active(development, target)
        point = np.clip(model.predict(x_dev[dev_indexes]), 0.0, None)
        matrix = np.clip(point[:, None] + residual_samples[target][None, :], 0.0, None)
        payloads[target] = {
            "indexes": dev_indexes, "observed": dev_y,
            "point": np.median(matrix, axis=1), "samples": matrix,
        }
    predict_seconds = time.perf_counter() - predict_started
    artifact = {"models": models, "calibration_residual_samples": residual_samples}
    return _summarize_predictions(
        target_payloads=payloads, examples=development, lead_map=lead_map,
        fit_seconds=fit_seconds, predict_seconds=predict_seconds,
    ), artifact


def _h32(root: Path, development, lead_map) -> dict[str, Any]:
    started = time.perf_counter()
    metrics = evaluate_lifecycle(
        M1Lifecycle.load(root / CHECKPOINT, device="cpu"),
        development, batch_size=256,
    )
    elapsed = time.perf_counter() - started
    horizon_errors: dict[int, list[float]] = defaultdict(list)
    for row in metrics["nodes"]:
        lead = lead_map.get(row["decision_node_id"])
        if lead is None:
            continue
        for target in TARGETS:
            if not row["active"].get(target) or row["targets"].get(target) is None:
                continue
            key = (
                "T_IB_A00_remaining_minutes_finite_support"
                if target == "T_IB_REMAINING_HAZARD"
                else f"{target}_point_minutes"
            )
            predicted = row["predictions"].get(key)
            if predicted is not None:
                horizon_errors[lead].append(abs(float(predicted) - float(row["targets"][target])))
    return {
        "support_status": "SUPPORTED_WITH_EXISTING_M1_TARGET_SCOPES",
        "target_metrics": {
            "T_IB_REMAINING_HAZARD": {
                "crps_scope": metrics["crps_scope"],
                "coverage": metrics["coverage_by_target"]["T_IB_REMAINING_HAZARD"],
            },
            "D_OB": {"coverage": metrics["coverage_by_target"]["D_OB"]},
            "D_TX": {"coverage": metrics["coverage_by_target"]["D_TX"]},
        },
        "mae_minutes": metrics["mae_minutes"],
        "crps_minutes": metrics["crps_minutes"],
        "brier": metrics["brier"],
        "brier_by_event": metrics["brier_by_event"],
        "calibration_gap": metrics["calibration_absolute_gap"],
        "calibration_by_event": metrics["calibration_by_event"],
        "horizon_mae_minutes": {
            str(lead): (None if not horizon_errors[lead] else mean(horizon_errors[lead]))
            for lead in EVALUATION_LEAD_MINUTES
        },
        "runtime": {
            "fit_seconds": 0.0,
            "predict_seconds": elapsed,
            "development_nodes_per_second": len(development) / max(elapsed, 1e-12),
        },
    }


def run(
    *, root: Path, input_root: Path | None = None,
    output_root: Path | None = None,
) -> dict[str, Path]:
    root = root.resolve()
    input_root = (input_root or root / INPUT_ROOT).resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    input_manifest_path = input_root / "FULL_DEVELOPMENT_INPUT_MANIFEST.json"
    inputs_path = input_root / "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json"
    _require(all(path.is_file() for path in (
        root / CACHE, root / CACHE_MANIFEST, root / CHECKPOINT,
        input_manifest_path, inputs_path,
    )), "EXP4_GLOBAL_INPUT_MISSING")
    input_manifest = load_json(input_manifest_path)
    inputs = load_json(inputs_path)
    _require(input_manifest["episode_count"] == 128 and input_manifest["node_count"] == 1769, "EXP4_GLOBAL_COHORT_INVALID")
    cache = _cache(root)
    train = tuple(cache.partition("train", representation="ADAPTIVE_HISTORY"))
    calibration = tuple(cache.partition("calibration", representation="ADAPTIVE_HISTORY"))
    development = tuple(cache.partition("development", representation="ADAPTIVE_HISTORY"))
    _require((len(train), len(calibration), len(development)) == (1880, 1060, 1769), "EXP4_GLOBAL_CACHE_CARDINALITY_INVALID")
    x_train, x_cal, x_dev = _features(train), _features(calibration), _features(development)
    lead_map = _lead_map(inputs)
    _require(len(lead_map) == 1769, "EXP4_GLOBAL_LEAD_MAP_INCOMPLETE")

    output_root.mkdir(parents=True, exist_ok=True)
    models_root = output_root / "models"
    models_root.mkdir(parents=True, exist_ok=True)
    historical_metrics, historical_artifact = _historical(train, development, lead_map)
    rf_metrics, rf_models = _random_forest(train, development, x_train, x_dev, lead_map)
    lgbm_metrics, lgbm_artifact = _lightgbm(
        train, calibration, development, x_train, x_cal, x_dev, lead_map,
    )
    h32_metrics = _h32(root, development, lead_map)

    historical_path = models_root / "HISTORICAL.json"
    write_json(historical_path, historical_artifact)
    rf_path = models_root / "RANDOM_FOREST.joblib"
    lgbm_path = models_root / "LIGHTGBM.joblib"
    joblib.dump(rf_models, rf_path)
    joblib.dump(lgbm_artifact, lgbm_path)
    data1 = build_data1_acceptance_report()
    data1_path = output_root / "EXP4_DATA1_BOUNDED_ACCEPTANCE.json"
    write_json(data1_path, data1)

    metrics = {
        "schema_version": "EXP4_FULL_DEVELOPMENT_METRICS_V1",
        "status": "DATA2_BASELINES_COMPLETE_DATA1_BOUNDED_PASS",
        "data2": {
            "role": "MAIN_DEVELOPMENT_EVALUATION",
            "split": "DEVELOPMENT",
            "episode_count": 128,
            "node_count": 1769,
            "baselines": {
                "HISTORICAL": historical_metrics,
                "LIGHTGBM": lgbm_metrics,
                "RANDOM_FOREST": rf_metrics,
                "STATE_AWARE_H32": h32_metrics,
            },
        },
        "data1": {
            "role": "BOUNDED_EXTERNAL_APPLICABILITY_SMOKE_ONLY",
            "pooling_with_data2": False,
            "acceptance": data1,
            "predictive_metrics": {
                "support_status": "NOT_RUN",
                "reason": "DATA1_M1_PREDICTIVE_LABEL_PATH_UNAVAILABLE_BY_CONTRACT",
            },
        },
        "scientific_scope": "PREDICTIVE_PERFORMANCE_EFFICIENCY_AND_BOUNDED_GENERALIZATION",
        "safety": dict(SAFETY),
    }
    metrics["artifact_hash"] = content_id(metrics)
    metrics_path = output_root / "EXP4_FULL_DEVELOPMENT_METRICS.json"
    write_json(metrics_path, metrics)

    table_path = output_root / "EXP4_FULL_DEVELOPMENT_TABLE.csv"
    with table_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "baseline", "mae_minutes", "crps_minutes", "brier",
            "calibration_gap", "fit_seconds", "predict_seconds",
        ))
        writer.writeheader()
        for baseline, row in metrics["data2"]["baselines"].items():
            writer.writerow({
                "baseline": baseline,
                "mae_minutes": row["mae_minutes"],
                "crps_minutes": row["crps_minutes"],
                "brier": row["brier"],
                "calibration_gap": row["calibration_gap"],
                "fit_seconds": row["runtime"]["fit_seconds"],
                "predict_seconds": row["runtime"]["predict_seconds"],
            })
    interpretation_path = output_root / "EXP4_FULL_DEVELOPMENT_INTERPRETATION.md"
    interpretation_path.write_text(
        "# Exp4 Development Interpretation\n\n"
        "Data2 is the main predictive evaluation environment for Historical, LightGBM, Random Forest, "
        "and the frozen state-aware H32 model. Data1 is reported only as a bounded adapter and typed "
        "applicability smoke; it is not pooled with Data2 and no Data1 predictive metric is fabricated.\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "EXP4_FULL_DEVELOPMENT_EXECUTION_MANIFEST_V1",
        "status": metrics["status"],
        "data2_role": "MAIN_EVALUATION",
        "data1_role": "BOUNDED_GENERALIZATION_SMOKE_ONLY",
        "data1_data2_pooling": False,
        "episode_count": 128, "node_count": 1769,
        "baselines": list(BASELINES),
        "frozen_hashes": {
            **input_manifest["frozen_hashes"],
            "cohort_hash": input_manifest["cohort_hash"],
        },
        "outputs": {
            "metrics": str(metrics_path.relative_to(root)).replace("\\", "/"),
            "table": str(table_path.relative_to(root)).replace("\\", "/"),
            "interpretation": str(interpretation_path.relative_to(root)).replace("\\", "/"),
            "data1_acceptance": str(data1_path.relative_to(root)).replace("\\", "/"),
        },
        "model_artifacts": {
            "HISTORICAL": {"path": str(historical_path.relative_to(root)).replace("\\", "/"), "sha256": file_sha256(historical_path)},
            "LIGHTGBM": {"path": str(lgbm_path.relative_to(root)).replace("\\", "/"), "sha256": file_sha256(lgbm_path)},
            "RANDOM_FOREST": {"path": str(rf_path.relative_to(root)).replace("\\", "/"), "sha256": file_sha256(rf_path)},
            "STATE_AWARE_H32": {"path": str(CHECKPOINT).replace("\\", "/"), "sha256": file_sha256(root / CHECKPOINT)},
        },
        "artifact_hashes": {"metrics": metrics["artifact_hash"]},
        "safety": dict(SAFETY),
    }
    manifest["artifact_hash"] = content_id(manifest)
    manifest_path = output_root / "EXP4_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json"
    write_json(manifest_path, manifest)
    return {
        "manifest": manifest_path, "metrics": metrics_path,
        "table": table_path, "interpretation": interpretation_path,
        "data1_acceptance": data1_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    run(
        root=Path(__file__).resolve().parents[2],
        input_root=args.input_root, output_root=args.output_root,
    )
    print("EXP4_FULL_DEVELOPMENT_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
