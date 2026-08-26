"""Exp4 per-node prediction records (Figure 8A-C and Table 1 material).

Records follow the Exp1B lead-time and CRPS conventions
(exp/exp1/closure.py): T_IB_A00 lead time = realized remaining minutes,
D_OB lead time = planned schedule horizon, D_TX = NA (no planned wheels-off
reference); unavailable values stay NA and are never interpolated.  Lead
bins use the manuscript grid {0,30,...,480} with floor-to-edge semantics.

Schema extends the instructed schema with a ``method`` column so the four
baselines (HISTORICAL, LIGHTGBM, RANDOM_FOREST, STATE_AWARE_H32) can be
distinguished; the extension is recorded in the manifest.

Baselines reuse the frozen fitted Development artifacts where available
(models/HISTORICAL.json, models/RANDOM_FOREST.joblib, models/LIGHTGBM.joblib)
so predictions are numerically identical to the saved Exp4 metrics.  The
STATE_AWARE_H32 baseline uses the official evaluate_lifecycle node
predictions; per-node finite-support CRPS is recomputed in the exp layer
from the M1 hazard PMF (mirror of model/M1/development_diagnostics
``_finite_discrete_crps``; the model module is read-only).  D_OB/D_TX CRPS
is not saved by M1, so those cells are crps=None, crps_supported=False.

Grid cells are summarized with episode-cluster bootstrap (episode is the
resampling unit, 2000 replicates, seed 20260825).
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import torch

from exp.common.official_execution import file_sha256, load_json, write_json
from exp.exp4.global_development import (
    CACHE, CACHE_MANIFEST, CHECKPOINT, INPUT_ROOT,
    _active, _cache, _crps, _features,
)
from exp.exp4.protocol import EVALUATION_LEAD_MINUTES
from model.M1.development_diagnostics import evaluate_lifecycle
from model.M1.lifecycle import M1Lifecycle
from model.common.identity import content_id


DEFAULT_OUTPUT = Path("artifacts/experiment/exp4/exp4_per_node_records_20260825")
EXISTING_EXP4_ROOT = Path("artifacts/experiments/exp4/full_development_v1")
INTERNAL_TARGETS = ("T_IB_REMAINING_HAZARD", "D_OB", "D_TX")
PUBLIC_TARGETS = {"T_IB_REMAINING_HAZARD": "T_IB_A00", "D_OB": "D_OB", "D_TX": "D_TX"}
METHODS = ("HISTORICAL", "LIGHTGBM", "RANDOM_FOREST", "STATE_AWARE_H32")
H32_PREDICTION_KEYS = {
    "T_IB_REMAINING_HAZARD": "T_IB_A00_remaining_minutes_finite_support",
    "D_OB": "D_OB_point_minutes",
    "D_TX": "D_TX_point_minutes",
}
LEAD_TIME_BINS = EVALUATION_LEAD_MINUTES
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20260825
BATCH_SIZE = 256
SAFETY = {
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "EXP4_RUNS": 0,
    "DEVELOPMENT_TUNING": False,
    "DATA1_DATA2_POOLING": False,
}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _iso_minutes(later: str, earlier: str) -> float | None:
    try:
        left = datetime.fromisoformat(str(later).replace("Z", "+00:00"))
        right = datetime.fromisoformat(str(earlier).replace("Z", "+00:00"))
        return (left - right).total_seconds() / 60.0
    except (TypeError, ValueError):
        return None


def _fact_value(entry) -> object:
    if not isinstance(entry, dict):
        return None
    if entry.get("support_state") not in (None, "SUPPORTED"):
        return None
    return entry.get("value")


def _planned_horizon(pre_state, decision_time: str | None) -> float | None:
    if not pre_state or decision_time is None:
        return None
    schedule = _fact_value(pre_state.get("successor_state", {}).get("schedule_reference"))
    if not isinstance(schedule, dict):
        return None
    planned = schedule.get("scheduled_departure_utc")
    if planned is None:
        return None
    return _iso_minutes(planned, decision_time)


def _lead_time_bin(minutes: float | None) -> int | None:
    if minutes is None:
        return None
    value = max(0.0, float(minutes))
    selected = LEAD_TIME_BINS[0]
    for edge in LEAD_TIME_BINS[1:]:
        if value < edge:
            break
        selected = edge
    return int(selected)


def _lead_time_for(
    target: str, observed: float | None,
    pre_state, decision_time: str | None,
) -> tuple[float | None, str]:
    if target == "T_IB_A00":
        if observed is not None:
            return float(observed), "REALIZED_REMAINING_MINUTES"
        return None, "NA_NO_OBSERVED_REMAINING_MINUTES"
    if target == "D_OB":
        planned = _planned_horizon(pre_state, decision_time)
        if planned is not None:
            return planned, "PLANNED_SCHEDULE_HORIZON"
        return None, "NA_NO_PLANNED_HORIZON"
    if target == "D_TX":
        return None, "NA_NO_PLANNED_WHEELS_OFF"
    raise RuntimeError(f"EXP4_RECORDS_UNKNOWN_TARGET:{target}")


def _finite_discrete_crps(values, probabilities, target: float) -> float:
    """Mirror of model/M1/development_diagnostics._finite_discrete_crps."""
    first = sum(
        probability * abs(value - target)
        for value, probability in zip(values, probabilities, strict=True)
    )
    second = sum(
        left_probability * right_probability * abs(left_value - right_value)
        for left_value, left_probability in zip(values, probabilities, strict=True)
        for right_value, right_probability in zip(values, probabilities, strict=True)
    )
    return first - 0.5 * second


def _episode_bootstrap(
    episode_values: dict[str, float], *,
    replicates: int = BOOTSTRAP_REPLICATES, seed: int = BOOTSTRAP_SEED,
) -> dict | None:
    array = np.asarray(list(episode_values.values()), dtype=float)
    array = array[np.isfinite(array)]
    if not len(array):
        return None
    generator = np.random.default_rng(seed)
    indices = generator.integers(0, len(array), size=(replicates, len(array)))
    bootstrap_means = array[indices].mean(axis=1)
    return {
        "estimate": float(array.mean()),
        "ci_lower": float(np.quantile(bootstrap_means, 0.025)),
        "ci_upper": float(np.quantile(bootstrap_means, 0.975)),
        "n_episodes": int(len(array)),
    }


def _historical_payloads(root: Path, development, x_dev) -> dict[str, dict]:
    artifact = load_json(root / EXISTING_EXP4_ROOT / "models" / "HISTORICAL.json")
    payloads = {}
    for target in INTERNAL_TARGETS:
        indexes, observed = _active(development, target)
        samples = np.asarray(artifact["targets"][target]["empirical_samples"], dtype=np.float64)
        matrix = np.repeat(samples[None, :], len(observed), axis=0)
        payloads[target] = {
            "indexes": indexes, "observed": observed,
            "point": np.median(matrix, axis=1), "samples": matrix,
        }
    return payloads


def _random_forest_payloads(root: Path, development, x_dev) -> dict[str, dict]:
    models = joblib.load(root / EXISTING_EXP4_ROOT / "models" / "RANDOM_FOREST.joblib")
    payloads = {}
    for target in INTERNAL_TARGETS:
        indexes, observed = _active(development, target)
        model = models[target]
        matrix = np.column_stack([
            np.clip(tree.predict(x_dev[indexes]), 0.0, None)
            for tree in model.estimators_
        ])
        payloads[target] = {
            "indexes": indexes, "observed": observed,
            "point": np.median(matrix, axis=1), "samples": matrix,
        }
    return payloads


def _lightgbm_payloads(root: Path, development, x_dev) -> dict[str, dict]:
    artifact = joblib.load(root / EXISTING_EXP4_ROOT / "models" / "LIGHTGBM.joblib")
    payloads = {}
    for target in INTERNAL_TARGETS:
        indexes, observed = _active(development, target)
        model = artifact["models"][target]
        residual_samples = np.asarray(
            artifact["calibration_residual_samples"][target], dtype=np.float64
        )
        point = np.clip(model.predict(x_dev[indexes]), 0.0, None)
        matrix = np.clip(point[:, None] + residual_samples[None, :], 0.0, None)
        payloads[target] = {
            "indexes": indexes, "observed": observed,
            "point": np.median(matrix, axis=1), "samples": matrix,
        }
    return payloads


def _h32_payloads(
    root: Path, development, calibration_artifact_path: Path | None = None,
) -> dict[str, dict]:
    lifecycle = M1Lifecycle.load(root / CHECKPOINT, device="cpu")
    if calibration_artifact_path is not None:
        payload = json.loads(calibration_artifact_path.read_text(encoding="utf-8"))
        from exp.reporting.calibration_artifact import apply_calibration_artifact

        apply_calibration_artifact(lifecycle.pipeline, payload, "M1_V2_GRU_H32")
    metrics = evaluate_lifecycle(lifecycle, development, batch_size=BATCH_SIZE)
    nodes_by_id = {row["decision_node_id"]: row for row in metrics["nodes"]}
    _require(len(nodes_by_id) == len(development), "EXP4_RECORDS_H32_NODE_COUNT_INVALID")

    contracts = lifecycle.pipeline.contracts
    hazard = contracts["T_IB_REMAINING_HAZARD"]
    representatives = [
        float(hazard.representative(index)[0])
        for index in range(hazard.finite_class_count)
    ]
    lifecycle.pipeline.model.eval()
    per_node_crps: dict[str, dict] = {}
    for start in range(0, len(development), BATCH_SIZE):
        batch = list(development[start:start + BATCH_SIZE])
        values, lengths, _, static_values = M1Lifecycle._batch(batch, contracts)
        with torch.no_grad():
            distributions = lifecycle.pipeline.predict_distributions(
                values.to(lifecycle.device),
                lengths.to(lifecycle.device),
                static_features=(
                    None if static_values is None else static_values.to(lifecycle.device)
                ),
            )
        hazard_pmf = distributions["T_IB_A00"].detach().cpu()
        for index, example in enumerate(batch):
            probabilities = [float(value) for value in hazard_pmf[index, :-1]]
            finite_mass = sum(probabilities)
            normalized = (
                [value / finite_mass for value in probabilities]
                if finite_mass > 0 else []
            )
            node_row = nodes_by_id[example.decision_node_id]
            stored_point = node_row["predictions"].get(
                "T_IB_A00_remaining_minutes_finite_support"
            )
            hazard_point = (
                sum(
                    value * probability
                    for value, probability in zip(representatives, normalized, strict=True)
                )
                if normalized else None
            )
            if stored_point is None:
                _require(hazard_point is None, "EXP4_RECORDS_H32_POINT_MISMATCH")
            else:
                _require(
                    abs(float(stored_point) - float(hazard_point)) < 1e-9,
                    "EXP4_RECORDS_H32_POINT_MISMATCH",
                )
            target = example.targets.get("T_IB_REMAINING_HAZARD")
            supported = bool(
                example.active.get("T_IB_REMAINING_HAZARD")
                and target is not None
                and float(target) < hazard.max_finite_minutes
                and normalized
            )
            per_node_crps[example.decision_node_id] = {
                "crps": (
                    _finite_discrete_crps(representatives, normalized, float(target))
                    if supported else None
                ),
                "supported": supported,
            }

    payloads = {}
    for target in INTERNAL_TARGETS:
        rows = []
        for example in development:
            node_id = example.decision_node_id
            node_row = nodes_by_id[node_id]
            observed = (
                float(node_row["targets"][target])
                if node_row["active"].get(target)
                and node_row["targets"].get(target) is not None
                else None
            )
            point = node_row["predictions"].get(H32_PREDICTION_KEYS[target])
            if target == "T_IB_REMAINING_HAZARD":
                crps_info = per_node_crps[node_id]
                crps = crps_info["crps"]
                supported = crps_info["supported"]
                finite_scope = bool(
                    observed is not None and supported
                )
                abs_error = (
                    abs(float(point) - observed)
                    if point is not None and finite_scope else None
                )
            else:
                crps = None
                supported = False
                abs_error = (
                    abs(float(point) - observed)
                    if point is not None and observed is not None else None
                )
            rows.append({
                "node_id": node_id,
                "public_target": PUBLIC_TARGETS[target],
                "observed": observed,
                "point": None if point is None else float(point),
                "absolute_error": abs_error,
                "crps": crps,
                "crps_supported": supported,
            })
        payloads[target] = rows
    return payloads


def _row_records(
    *, episode_id: str, node_id: str, method: str, target: str,
    observed, point, absolute_error, crps, crps_supported: bool,
    pre_state, decision_time,
) -> dict:
    lead_time, lead_time_source = _lead_time_for(
        PUBLIC_TARGETS[target], observed, pre_state, decision_time,
    )
    return {
        "episode_id": episode_id,
        "decision_node_id": node_id,
        "method": method,
        "target": PUBLIC_TARGETS[target],
        "observed_minutes": observed,
        "point_prediction": point,
        "absolute_error": absolute_error,
        "crps": crps,
        "crps_supported": bool(crps_supported),
        "lead_time_minutes": lead_time,
        "lead_time_source": lead_time_source,
        "lead_time_bin_minutes": _lead_time_bin(lead_time),
    }


def _ml_row(payload, local_index, example, node_id, method, target, pre_state, decision_time) -> dict:
    positions = np.flatnonzero(payload["indexes"] == local_index)
    if len(positions) == 0:
        return _row_records(
            episode_id=example.episode_id, node_id=node_id, method=method,
            target=target, observed=None, point=None, absolute_error=None,
            crps=None, crps_supported=False, pre_state=pre_state,
            decision_time=decision_time,
        )
    _require(len(positions) == 1, "EXP4_RECORDS_PAYLOAD_INDEX_INVALID")
    position = int(positions[0])
    observed = float(payload["observed"][position])
    point = float(payload["point"][position])
    crps = float(_crps(
        payload["samples"][position:position + 1],
        payload["observed"][position:position + 1],
    )[0])
    return _row_records(
        episode_id=example.episode_id, node_id=node_id, method=method,
        target=target, observed=observed, point=point,
        absolute_error=abs(point - observed), crps=crps,
        crps_supported=True, pre_state=pre_state, decision_time=decision_time,
    )


def run(
    *, root: Path, input_root: Path | None = None,
    output_root: Path | None = None,
    calibration_artifact_path: Path | None = None,
) -> dict[str, Path]:
    root = root.resolve()
    input_root = (input_root or root / INPUT_ROOT).resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    input_manifest_path = input_root / "FULL_DEVELOPMENT_INPUT_MANIFEST.json"
    inputs_path = input_root / "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json"
    _require(all(path.is_file() for path in (
        root / CACHE, root / CACHE_MANIFEST, root / CHECKPOINT,
        input_manifest_path, inputs_path,
        root / EXISTING_EXP4_ROOT / "EXP4_FULL_DEVELOPMENT_METRICS.json",
        root / EXISTING_EXP4_ROOT / "models" / "HISTORICAL.json",
        root / EXISTING_EXP4_ROOT / "models" / "RANDOM_FOREST.joblib",
        root / EXISTING_EXP4_ROOT / "models" / "LIGHTGBM.joblib",
    )), "EXP4_RECORDS_INPUT_MISSING")
    input_manifest = load_json(input_manifest_path)
    inputs = load_json(inputs_path)
    _require(
        input_manifest["episode_count"] == 128 and input_manifest["node_count"] == 1769,
        "EXP4_RECORDS_COHORT_INVALID",
    )
    cache = _cache(root)
    development = tuple(cache.partition("development", representation="ADAPTIVE_HISTORY"))
    _require(len(development) == 1769, "EXP4_RECORDS_CACHE_CARDINALITY_INVALID")
    x_dev = _features(development)

    pre_by_node: dict[str, dict] = {}
    decision_time_by_node: dict[str, str | None] = {}
    historical_to_current: dict[str, str] = {}
    for row in inputs["inference_inputs"]:
        historical_to_current[row["historical_decision_node_id"]] = row["decision_node_id"]
    for states in inputs["pre_states_by_episode"].values():
        for state in states:
            node = state["decision_node"]
            node_id = node["decision_node_id"]
            pre_by_node[node_id] = state
            decision_time_by_node[node_id] = node.get("decision_time")

    historical_payloads = _historical_payloads(root, development, x_dev)
    lightgbm_payloads = _lightgbm_payloads(root, development, x_dev)
    random_forest_payloads = _random_forest_payloads(root, development, x_dev)
    h32_payloads = _h32_payloads(root, development, calibration_artifact_path)

    ml_payloads = {
        "HISTORICAL": historical_payloads,
        "LIGHTGBM": lightgbm_payloads,
        "RANDOM_FOREST": random_forest_payloads,
    }
    records: list[dict] = []
    for local_index, example in enumerate(development):
        node_id = example.decision_node_id
        current_id = historical_to_current.get(node_id, node_id)
        _require(current_id in pre_by_node, "EXP4_RECORDS_PRE_STATE_MISSING")
        pre_state = pre_by_node[current_id]
        decision_time = decision_time_by_node.get(current_id)
        for method, payloads in ml_payloads.items():
            for target in INTERNAL_TARGETS:
                records.append(_ml_row(
                    payloads[target], local_index, example, node_id,
                    method, target, pre_state, decision_time,
                ))
        for target in INTERNAL_TARGETS:
            h32_row = next(
                (row for row in h32_payloads[target] if row["node_id"] == node_id), None
            )
            _require(h32_row is not None, "EXP4_RECORDS_H32_ROW_MISSING")
            records.append(_row_records(
                episode_id=example.episode_id, node_id=node_id,
                method="STATE_AWARE_H32", target=target,
                observed=h32_row["observed"], point=h32_row["point"],
                absolute_error=h32_row["absolute_error"],
                crps=h32_row["crps"], crps_supported=h32_row["crps_supported"],
                pre_state=pre_state, decision_time=decision_time,
            ))

    output_root.mkdir(parents=True, exist_ok=True)
    result_path = output_root / "EXP4_PER_NODE_RECORDS_DEVELOPMENT_ONLY.parquet"
    table = pa.Table.from_pylist(records)
    pq.write_table(table, result_path, compression="zstd")
    csv_path = output_root / "EXP4_PER_NODE_RECORDS_DEVELOPMENT_ONLY.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

    existing_metrics = load_json(
        root / EXISTING_EXP4_ROOT / "EXP4_FULL_DEVELOPMENT_METRICS.json"
    )
    parity = _parity_report(records, existing_metrics)

    grid_rows = _grid_summary(records)
    grid_path = output_root / "EXP4_LEAD_TIME_GRID_DEVELOPMENT_ONLY.csv"
    with grid_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(grid_rows[0]))
        writer.writeheader()
        writer.writerows(grid_rows)

    manifest = {
        "schema_version": "AIR_SLOT_EXP4_PER_NODE_RECORDS_MANIFEST_V1",
        "status": "MATERIALIZED",
        "scope": "DATA2_FULL_DEVELOPMENT_NO_FINAL_TEST",
        "dataset": "DATA2", "split": "DEVELOPMENT",
        "episode_count": 128, "node_count": len(development),
        "methods": list(METHODS),
        "targets": [PUBLIC_TARGETS[name] for name in INTERNAL_TARGETS],
        "lead_time_bins_minutes": list(LEAD_TIME_BINS),
        "na_grid_policy": "EXPLICIT_NA_ROW_FOR_UNSUPPORTED_BINS_NO_INTERPOLATION",
        "lead_time_rule": (
            "T_IB=realized remaining minutes; D_OB=planned schedule horizon; "
            "D_TX=NA_NO_PLANNED_WHEELS_OFF; NA is never interpolated"
        ),
        "crps_rules": {
            "HISTORICAL": "SAMPLE_CRPS_ALL_TARGETS",
            "LIGHTGBM": "SAMPLE_CRPS_ALL_TARGETS",
            "RANDOM_FOREST": "SAMPLE_CRPS_ALL_TARGETS",
            "STATE_AWARE_H32": "T_IB_FINITE_SUPPORT_CRPS_ONLY_D_OB_D_TX_NOT_SAVED_BY_M1",
        },
        "h32_scope_note": (
            "STATE_AWARE_H32 T_IB absolute error and CRPS follow the frozen M1 "
            "finite-support scope (active target below max finite minutes with "
            "positive finite mass)"
        ),
        "schema_extension_note": (
            "method column added to the instructed schema to distinguish the "
            "four baselines; all other columns follow the instructed schema"
        ),
        "bootstrap": {
            "resampling_unit": "EPISODE",
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
        },
        "input_hashes": {
            "cache": file_sha256(root / CACHE),
            "cache_manifest": file_sha256(root / CACHE_MANIFEST),
            "checkpoint": file_sha256(root / CHECKPOINT),
            "inputs": file_sha256(inputs_path),
            "input_manifest": file_sha256(input_manifest_path),
            "existing_metrics": file_sha256(
                root / EXISTING_EXP4_ROOT / "EXP4_FULL_DEVELOPMENT_METRICS.json"
            ),
        },
        "parity_vs_existing_metrics": parity,
        "outputs": {
            "records": "EXP4_PER_NODE_RECORDS_DEVELOPMENT_ONLY.parquet",
            "records_csv": "EXP4_PER_NODE_RECORDS_DEVELOPMENT_ONLY.csv",
            "grid": "EXP4_LEAD_TIME_GRID_DEVELOPMENT_ONLY.csv",
            "manifest": "EXP4_PER_NODE_MANIFEST_DEVELOPMENT_ONLY.json",
        },
        "safety": dict(SAFETY),
        "paper_result": False,
    }
    manifest["artifact_hash"] = content_id(manifest)
    manifest_path = output_root / "EXP4_PER_NODE_MANIFEST_DEVELOPMENT_ONLY.json"
    write_json(manifest_path, manifest)
    return {
        "manifest": manifest_path, "records": result_path,
        "records_csv": csv_path, "grid": grid_path,
    }


def _parity_report(records: list[dict], existing_metrics: dict) -> dict:
    frame = pd.DataFrame(records)
    report: dict[str, dict] = {}
    for method in METHODS:
        method_frame = frame.loc[frame["method"] == method]
        stored = existing_metrics["data2"]["baselines"][method]
        target_report: dict[str, dict] = {}
        max_abs_diff = 0.0
        for internal, public in PUBLIC_TARGETS.items():
            target_frame = method_frame.loc[method_frame["target"] == public]
            mae = target_frame["absolute_error"].dropna().to_numpy(dtype=float)
            crps = target_frame["crps"].dropna().to_numpy(dtype=float)
            stored_target = stored["target_metrics"].get(internal, {})
            stored_mae = stored_target.get("mae_minutes")
            stored_crps = stored_target.get("crps_minutes")
            entry: dict = {"nodes_with_mae": int(len(mae))}
            if stored_mae is not None:
                diff = abs(float(np.mean(mae)) - float(stored_mae))
                entry["mae_mean"] = float(np.mean(mae))
                entry["stored_mae_minutes"] = float(stored_mae)
                entry["mae_abs_diff"] = diff
                max_abs_diff = max(max_abs_diff, diff)
            if stored_crps is not None:
                diff = abs(float(np.mean(crps)) - float(stored_crps))
                entry["crps_mean"] = float(np.mean(crps))
                entry["stored_crps_minutes"] = float(stored_crps)
                entry["crps_abs_diff"] = diff
                max_abs_diff = max(max_abs_diff, diff)
            target_report[public] = entry
        overall_mae = method_frame["absolute_error"].dropna().to_numpy(dtype=float)
        if stored.get("mae_minutes") is not None:
            diff = abs(float(np.mean(overall_mae)) - float(stored["mae_minutes"]))
            max_abs_diff = max(max_abs_diff, diff)
        overall_crps_mean: float | None = None
        if stored.get("crps_minutes") is not None:
            if stored.get("crps_scope") == "T_IB_FINITE_SUPPORT_COMPARISON_SCOPE":
                tib_crps = method_frame.loc[
                    method_frame["target"] == "T_IB_A00", "crps"
                ].dropna().to_numpy(dtype=float)
                overall_crps_mean = float(np.mean(tib_crps))
                diff = abs(overall_crps_mean - float(stored["crps_minutes"]))
            else:
                overall_crps = method_frame["crps"].dropna().to_numpy(dtype=float)
                overall_crps_mean = float(np.mean(overall_crps))
                diff = abs(overall_crps_mean - float(stored["crps_minutes"]))
            max_abs_diff = max(max_abs_diff, diff)
        report[method] = {
            "target_metrics": target_report,
            "overall_mae_mean": float(np.mean(overall_mae)),
            "overall_crps_mean": overall_crps_mean,
            "overall_crps_scope": stored.get("crps_scope"),
            "max_abs_diff_vs_stored": max_abs_diff,
            "status": "PASS" if max_abs_diff < 1e-9 else "DRIFT",
        }
    return report


def _grid_summary(records: list[dict]) -> list[dict]:
    frame = pd.DataFrame(records)
    rows: list[dict] = []
    group_keys = ["method", "target", "lead_time_bin_minutes"]
    for (method, target, lead_bin), group in frame.groupby(group_keys, sort=False):
        group = group.reset_index(drop=True)
        mae_episodes: dict[str, float] = {}
        crps_episodes: dict[str, float] = {}
        mae_nodes = 0
        crps_nodes = 0
        for episode_id, episode_group in group.groupby("episode_id", sort=False):
            mae_values = episode_group["absolute_error"].dropna().to_numpy(dtype=float)
            crps_values = episode_group["crps"].dropna().to_numpy(dtype=float)
            if len(mae_values):
                mae_episodes[episode_id] = float(np.mean(mae_values))
                mae_nodes += int(len(mae_values))
            if len(crps_values):
                crps_episodes[episode_id] = float(np.mean(crps_values))
                crps_nodes += int(len(crps_values))
        mae_estimate = _episode_bootstrap(mae_episodes)
        crps_estimate = _episode_bootstrap(crps_episodes)
        if mae_estimate is not None:
            rows.append({
                "method": method, "target": target,
                "lead_time_bin_minutes": lead_bin,
                "metric": "MAE_MINUTES",
                "estimate": mae_estimate["estimate"],
                "ci_lower": mae_estimate["ci_lower"],
                "ci_upper": mae_estimate["ci_upper"],
                "n_episodes": mae_estimate["n_episodes"],
                "n_nodes": mae_nodes,
            })
        if crps_estimate is not None:
            rows.append({
                "method": method, "target": target,
                "lead_time_bin_minutes": lead_bin,
                "metric": "CRPS_MINUTES",
                "estimate": crps_estimate["estimate"],
                "ci_lower": crps_estimate["ci_lower"],
                "ci_upper": crps_estimate["ci_upper"],
                "n_episodes": crps_estimate["n_episodes"],
                "n_nodes": crps_nodes,
            })
    # Strict grid contract (2026-08-26): every manuscript bin appears
    # explicitly in the grid; bins without node support carry NA estimates
    # (n_episodes=0, n_nodes=0) and are never interpolated.  D_TX has no
    # planned wheels-off reference, so it keeps only OVERALL rows.
    for (method, target), _ in frame.groupby(["method", "target"], sort=False):
        if target == "D_TX":
            continue
        present = {
            int(row["lead_time_bin_minutes"])
            for row in rows
            if row["method"] == method
            and row["target"] == target
            and row["lead_time_bin_minutes"] != "OVERALL"
        }
        for bin_minutes in LEAD_TIME_BINS:
            if bin_minutes in present:
                continue
            for metric in ("MAE_MINUTES", "CRPS_MINUTES"):
                rows.append({
                    "method": method, "target": target,
                    "lead_time_bin_minutes": bin_minutes,
                    "metric": metric,
                    "estimate": None,
                    "ci_lower": None,
                    "ci_upper": None,
                    "n_episodes": 0,
                    "n_nodes": 0,
                })
    for (method, target), group in frame.groupby(["method", "target"], sort=False):
        group = group.reset_index(drop=True)
        mae_episodes: dict[str, float] = {}
        crps_episodes: dict[str, float] = {}
        mae_nodes = 0
        crps_nodes = 0
        for episode_id, episode_group in group.groupby("episode_id", sort=False):
            mae_values = episode_group["absolute_error"].dropna().to_numpy(dtype=float)
            crps_values = episode_group["crps"].dropna().to_numpy(dtype=float)
            if len(mae_values):
                mae_episodes[episode_id] = float(np.mean(mae_values))
                mae_nodes += int(len(mae_values))
            if len(crps_values):
                crps_episodes[episode_id] = float(np.mean(crps_values))
                crps_nodes += int(len(crps_values))
        mae_estimate = _episode_bootstrap(mae_episodes)
        crps_estimate = _episode_bootstrap(crps_episodes)
        if mae_estimate is not None:
            rows.append({
                "method": method, "target": target,
                "lead_time_bin_minutes": "OVERALL",
                "metric": "MAE_MINUTES",
                "estimate": mae_estimate["estimate"],
                "ci_lower": mae_estimate["ci_lower"],
                "ci_upper": mae_estimate["ci_upper"],
                "n_episodes": mae_estimate["n_episodes"],
                "n_nodes": mae_nodes,
            })
        if crps_estimate is not None:
            rows.append({
                "method": method, "target": target,
                "lead_time_bin_minutes": "OVERALL",
                "metric": "CRPS_MINUTES",
                "estimate": crps_estimate["estimate"],
                "ci_lower": crps_estimate["ci_lower"],
                "ci_upper": crps_estimate["ci_upper"],
                "n_episodes": crps_estimate["n_episodes"],
                "n_nodes": crps_nodes,
            })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    run(
        root=Path(__file__).resolve().parents[2],
        input_root=args.input_root, output_root=args.output_root,
    )
    print("EXP4_PER_NODE_RECORDS_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
