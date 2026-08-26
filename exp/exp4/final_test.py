"""Frozen-model Exp4 predictive benchmark over the materialized Q4 Final Test."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pyarrow.parquet as pq

from exp.common.official_execution import file_sha256, write_json
from exp.exp2.tail_scores import Q_MAX_MINUTES
from exp.exp4.per_node_records import (
    INTERNAL_TARGETS, PUBLIC_TARGETS, _crps, _grid_summary, _row_records,
)
from model.common.identity import content_id


SCOPE = "FINAL_TEST_OUT_OF_TIME_2019_10_12"
MODEL_ROOT = Path("artifacts/experiments/exp4/full_development_v1/models")


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _samples_crps(samples: list[float], observed: float) -> float | None:
    if not samples:
        return None
    return float(_crps(np.asarray([samples], dtype=np.float64), np.asarray([observed], dtype=np.float64))[0])


def _feature_matrix(inputs: list[dict[str, Any]]) -> np.ndarray:
    rows = [np.concatenate((
        np.asarray(item["encoded_adaptive_prefix"][-1], dtype=np.float32),
        np.asarray(item["encoded_static_context"], dtype=np.float32),
    )) for item in inputs]
    matrix = np.stack(rows)
    _require(matrix.shape[1] == 43 and np.isfinite(matrix).all(), "EXP4_FINAL_TEST_FEATURE_SCHEMA_INVALID")
    return matrix


def _episode_bootstrap(frame, column: str, *, replicates: int = 2000,
                       seed: int = 20260825) -> dict[str, Any] | None:
    """Percentile CI over episode-balanced per-node metric means."""
    values = frame[["episode_id", column]].dropna()
    if values.empty:
        return None
    episode_values = values.groupby("episode_id", sort=False)[column].mean().to_numpy(dtype=np.float64)
    episode_values = episode_values[np.isfinite(episode_values)]
    if not len(episode_values):
        return None
    rng = np.random.default_rng(seed)
    indexes = rng.integers(0, len(episode_values), size=(replicates, len(episode_values)))
    draws = episode_values[indexes].mean(axis=1)
    return {
        "estimate": float(episode_values.mean()),
        "ci_lower": float(np.quantile(draws, 0.025)),
        "ci_upper": float(np.quantile(draws, 0.975)),
        "n_episodes": int(len(episode_values)),
        "replicates": replicates,
        "seed": seed,
        "ci": "PERCENTILE_95",
    }


def run(*, root: Path, input_root: Path, scenario_root: Path,
        output_root: Path) -> dict[str, Path]:
    """Evaluate frozen baseline artifacts and held-out H32 scenarios only."""
    root, input_root, scenario_root, output_root = (
        path.resolve() for path in (root, input_root, scenario_root, output_root)
    )
    paths = {
        "manifest": input_root / "FINAL_TEST_INPUT_MANIFEST.json",
        "inputs": input_root / "M1_V2_FINAL_TEST_INFERENCE_INPUTS.json",
        "labels": input_root / "M1_V2_FINAL_TEST_LABELS.json",
        "scenarios": scenario_root / "M1_V2_FINAL_TEST_TYPED_SCENARIOS_HISTORY.parquet",
        "historical": root / MODEL_ROOT / "HISTORICAL.json",
        "random_forest": root / MODEL_ROOT / "RANDOM_FOREST.joblib",
        "lightgbm": root / MODEL_ROOT / "LIGHTGBM.joblib",
    }
    _require(all(path.is_file() for path in paths.values()), "EXP4_FINAL_TEST_INPUT_MISSING")
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    payload = json.loads(paths["inputs"].read_text(encoding="utf-8"))
    labels_payload = json.loads(paths["labels"].read_text(encoding="utf-8"))
    _require(manifest.get("scope") == SCOPE and manifest.get("development_input_used") is False,
             "EXP4_FINAL_TEST_SCOPE_INVALID")
    inputs = payload["inference_inputs"]
    _require(len(inputs) == int(manifest["node_count"]), "EXP4_FINAL_TEST_INPUT_CARDINALITY_INVALID")
    x = _feature_matrix(inputs)
    labels_by_node = {
        (row["decision_node_id"], row["target_name"]): row
        for row in labels_payload["labels"]
    }
    pre_by_node = {
        state["decision_node"]["decision_node_id"]: state
        for states in payload["pre_states_by_episode"].values() for state in states
    }
    _require(len(pre_by_node) == len(inputs), "EXP4_FINAL_TEST_PRE_STATE_CARDINALITY_INVALID")
    historical = json.loads(paths["historical"].read_text(encoding="utf-8"))
    random_forest = joblib.load(paths["random_forest"])
    lightgbm = joblib.load(paths["lightgbm"])
    scenario_samples: dict[tuple[str, str], list[float]] = {}
    scenario_node_ids: set[str] = set()
    scenario_reader = pq.ParquetFile(paths["scenarios"])
    for batch in scenario_reader.iter_batches(batch_size=8192, columns=["decision_node_id", "T_IB_A00", "D_OB", "D_TX"]):
        for row in batch.to_pylist():
            node_id = row["decision_node_id"]
            scenario_node_ids.add(node_id)
            for target in ("T_IB_A00", "D_OB", "D_TX"):
                if row[target] is not None:
                    scenario_samples.setdefault((node_id, target), []).append(float(row[target]))
    _require(len(scenario_node_ids) == len(inputs), "EXP4_FINAL_TEST_SCENARIO_NODE_COUNT_INVALID")

    rf_samples = {
        target: np.column_stack([np.clip(tree.predict(x), 0.0, None) for tree in random_forest[target].estimators_])
        for target in INTERNAL_TARGETS
    }
    lgbm_samples = {}
    for target in INTERNAL_TARGETS:
        point = np.clip(lightgbm["models"][target].predict(x), 0.0, None)
        residuals = np.asarray(lightgbm["calibration_residual_samples"][target], dtype=np.float64)
        lgbm_samples[target] = np.clip(point[:, None] + residuals[None, :], 0.0, None)

    records: list[dict[str, Any]] = []
    target_to_label = {"T_IB_REMAINING_HAZARD": "T_IB_A00", "D_OB": "D_OB", "D_TX": "D_TX"}
    for index, item in enumerate(inputs):
        node_id, episode_id = item["decision_node_id"], item["episode_id"]
        pre, decision_time = pre_by_node[node_id], item.get("decision_time")
        for target in INTERNAL_TARGETS:
            public_target = target_to_label[target]
            label = labels_by_node.get((node_id, public_target), {})
            observed = label.get("exact_minutes") if label.get("active") else None
            observed = None if observed is None else float(observed)
            fixed_samples = np.asarray(historical["targets"][target]["empirical_samples"], dtype=np.float64)
            for method, samples in (
                ("HISTORICAL", fixed_samples),
                ("LIGHTGBM", lgbm_samples[target][index]),
                ("RANDOM_FOREST", rf_samples[target][index]),
            ):
                if observed is None:
                    records.append(_row_records(episode_id=episode_id, node_id=node_id, method=method,
                        target=target, observed=None, point=None, absolute_error=None, crps=None,
                        crps_supported=False, pre_state=pre, decision_time=decision_time))
                    continue
                values = [float(value) for value in samples]
                point = float(np.median(values))
                records.append(_row_records(episode_id=episode_id, node_id=node_id, method=method,
                    target=target, observed=observed, point=point, absolute_error=abs(point - observed),
                    crps=_samples_crps(values, observed), crps_supported=True,
                    pre_state=pre, decision_time=decision_time))
            h32_values = scenario_samples.get((node_id, public_target), [])
            h32_crps_supported = observed is not None and bool(h32_values)
            if target == "T_IB_REMAINING_HAZARD":
                h32_crps_supported = h32_crps_supported and observed < Q_MAX_MINUTES["T_IB_A00"]
            else:
                # M1 did not formally save D_OB/D_TX CRPS.  H32 point/MAE
                # remains evaluable, but CRPS is typed NA and never rebuilt
                # from another experiment track.
                h32_crps_supported = False
            h32_point = None if not h32_values else float(np.median(h32_values))
            h32_mae_supported = observed is not None and h32_point is not None
            records.append(_row_records(episode_id=episode_id, node_id=node_id, method="STATE_AWARE_H32",
                target=target, observed=observed, point=h32_point,
                absolute_error=(None if not h32_mae_supported else abs(h32_point - observed)),
                crps=(None if not h32_crps_supported else _samples_crps(h32_values, observed)),
                crps_supported=h32_crps_supported, pre_state=pre, decision_time=decision_time))

    _require(len(records) == len(inputs) * len(INTERNAL_TARGETS) * 4, "EXP4_FINAL_TEST_RECORD_CARDINALITY_INVALID")
    output_root.mkdir(parents=True, exist_ok=True)
    records_path = output_root / "EXP4_FINAL_TEST_PER_NODE_RECORDS.parquet"
    records_csv = output_root / "EXP4_FINAL_TEST_PER_NODE_RECORDS.csv"
    import pandas as pd
    frame = pd.DataFrame(records)
    frame.to_parquet(records_path, index=False)
    frame.to_csv(records_csv, index=False)
    grid_rows = _grid_summary(records)
    grid_path = output_root / "EXP4_FINAL_TEST_LEAD_TIME_GRID.csv"
    with grid_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(grid_rows[0]))
        writer.writeheader()
        writer.writerows(grid_rows)
    aggregate = {}
    for (method, target), group in frame.groupby(["method", "target"], sort=True):
        mae_bootstrap = _episode_bootstrap(group, "absolute_error")
        crps_bootstrap = _episode_bootstrap(group, "crps")
        aggregate[f"{method}:{target}"] = {
            "mae_minutes": None if mae_bootstrap is None else mae_bootstrap["estimate"],
            "mae_ci_95": None if mae_bootstrap is None else [mae_bootstrap["ci_lower"], mae_bootstrap["ci_upper"]],
            "crps_minutes": None if crps_bootstrap is None else crps_bootstrap["estimate"],
            "crps_ci_95": None if crps_bootstrap is None else [crps_bootstrap["ci_lower"], crps_bootstrap["ci_upper"]],
            "mae_node_count": int(group["absolute_error"].notna().sum()),
            "crps_node_count": int(group["crps"].notna().sum()),
            "mae_episode_count": 0 if mae_bootstrap is None else mae_bootstrap["n_episodes"],
            "crps_episode_count": 0 if crps_bootstrap is None else crps_bootstrap["n_episodes"],
            "crps_status": "NA_NOT_SAVED_BY_M1" if (method == "STATE_AWARE_H32" and target in {"D_OB", "D_TX"}) else ("SUPPORTED" if crps_bootstrap is not None else "NA_NO_VALID_SUPPORT"),
        }
    safety = {"FINAL_TEST_ACCESS_COUNT": sum(1 for name in ("manifest", "inputs", "labels", "scenarios") if paths[name].is_file()),
              "PAPER_FULL_RUN": True, "MODEL_RETRAINED": False, "PARAMETER_RESELECTED": False}
    metrics = {"schema_version": "EXP4_FINAL_TEST_METRICS_V1", "status": "COMPLETE",
               "scope": SCOPE, "dataset": "DATA2", "split": "FINAL_TEST",
               "episode_count": manifest["episode_count"], "node_count": len(inputs), "methods": ["HISTORICAL", "LIGHTGBM", "RANDOM_FOREST", "STATE_AWARE_H32"],
               "aggregate": aggregate, "bootstrap": {"resampling_unit": "EPISODE", "replicates": 2000, "seed": 20260825, "ci": "PERCENTILE_95"}, "safety": safety}
    metrics["artifact_hash"] = content_id(metrics)
    metrics_path = output_root / "EXP4_FINAL_TEST_METRICS.json"
    write_json(metrics_path, metrics)
    manifest_payload = {"schema_version": "EXP4_FINAL_TEST_EXECUTION_MANIFEST_V1", "status": "COMPLETE", "scope": SCOPE,
                        "source_scope": SCOPE, "dataset": "DATA2", "split": "FINAL_TEST", "episode_count": manifest["episode_count"], "node_count": len(inputs),
                        "input_hashes": {name: file_sha256(path) for name, path in paths.items()},
                        "outputs": {"records": str(records_path.relative_to(root)).replace("\\", "/"), "grid": str(grid_path.relative_to(root)).replace("\\", "/"), "metrics": str(metrics_path.relative_to(root)).replace("\\", "/")},
                        "safety": safety, "paper_result": True}
    manifest_payload["artifact_hash"] = content_id(manifest_payload)
    manifest_path = output_root / "EXP4_FINAL_TEST_EXECUTION_MANIFEST.json"
    write_json(manifest_path, manifest_payload)
    return {"manifest": manifest_path, "metrics": metrics_path, "records": records_path, "grid": grid_path}
