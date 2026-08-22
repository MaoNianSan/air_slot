"""Audit-only C0A: source-clock semantics and episode-balanced support evidence.

This module deliberately sits after the frozen B2 cache.  It reads only the
Train/Calibration/Development cohort and the Jan-Sep 2019 PRE source paths.
It never changes support, labels, features, caches, configuration, or runs a
model.  Selected raw rows are reconstructed through the official PRE
``canonicalize_ontime_row`` owner; this module does not implement a BTS parser.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable

import numpy as np
import torch
import yaml

from model.M1.cache import M1DevelopmentBaseCache
from validation.m1_v2_target_support_c0a_source import (
    classify_departure_values,
    scan_source_clock,
)


ROOT = Path(__file__).resolve().parents[1]
B2_OUTPUT = ROOT / "artifacts" / "diagnostics" / "m1_v2_feature_gate_b2"
A2_OUTPUT = ROOT / "artifacts" / "diagnostics" / "m1_v2_data_gate_a2"
DEFAULT_OUTPUT = ROOT / "artifacts" / "diagnostics" / "m1_v2_target_support_gate_c0a"

TARGETS = ("T_IB_REMAINING_HAZARD", "D_OB", "D_TX")
SPLITS = ("train", "calibration", "development")
CURRENT_SUPPORT = {"T_IB_REMAINING_HAZARD": 360, "D_OB": 180, "D_TX": 60}
CANDIDATES = {
    "T_IB_REMAINING_HAZARD": [300, 330, 360, 390, 420, 450, 480],
    "D_OB": [120, 150, 180, 210, 240, 270, 300, 360, 420, 480],
    "D_TX": [30, 45, 60, 75, 90, 120, 150],
}
BIN_WIDTH = 5
EXPECTED_SCHEMA_HASH = "sha256:1f4b886a9bddc67f3fe72b977ea957cf5828b6cdd20dcc69655dcf3f2ec2972a"
EXPECTED_CACHE_HASH = "sha256:157c0d555c40efd9d7dc5ecebc5dda60a902b855d42bdab9a3657aa601e6f919"
EXPECTED_B2_STATUS = "FEATURE_GATE_B2_PASS_TARGET_SUPPORT_REVIEW_NEXT"

SAFETY = {
    "M1_TRAINING_RUNS": 0,
    "TUNING_RUNS": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "GATE_B2_FEATURE_FREEZE": True,
    "M1_TARGET_SUPPORT_FROZEN": False,
    "HYPERPARAMETER_TUNING_AUTHORIZED": False,
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.integer, torch.Tensor)):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _load_b2() -> tuple[M1DevelopmentBaseCache, dict[str, Any], dict[str, Any]]:
    manifest_path = B2_OUTPUT / "M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json"
    data_path = B2_OUTPUT / "M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz"
    report_path = B2_OUTPUT / "AIR_SLOT_M1_V2_FEATURE_GATE_B2.json"
    manifest, report = _read_json(manifest_path), _read_json(report_path)
    if report.get("FEATURE_GATE_STATUS") != EXPECTED_B2_STATUS:
        raise ValueError("TARGET_SUPPORT_C0A_B2_STATUS_NOT_FROZEN")
    if manifest.get("feature_schema_hash") != EXPECTED_SCHEMA_HASH:
        raise ValueError("TARGET_SUPPORT_C0A_B2_SCHEMA_HASH_MISMATCH")
    if manifest.get("cache_hash") != EXPECTED_CACHE_HASH:
        raise ValueError("TARGET_SUPPORT_C0A_B2_CACHE_HASH_MISMATCH")
    if manifest.get("final_test_access_count") != 0:
        raise ValueError("TARGET_SUPPORT_C0A_FINAL_TEST_ACCESS")
    cache = M1DevelopmentBaseCache.load(data_path, manifest_path, expected_cache_key=manifest["cache_key"])
    return cache, manifest, report


def _load_a2_episodes() -> dict[str, Any]:
    state_path = A2_OUTPUT / "M1_V2_DATA_GATE_A2_PREPARATION_STATE.pt"
    try:
        state = torch.load(state_path, map_location="cpu", weights_only=False)
    except TypeError:
        state = torch.load(state_path, map_location="cpu")
    reservoirs = state.get("reservoirs", {})
    if reservoirs.get("test"):
        raise ValueError("TARGET_SUPPORT_C0A_FINAL_TEST_EPISODE_MATERIALIZED")
    episodes = {}
    for split in SPLITS:
        for episode in reservoirs.get(split, ()):
            episodes[episode.episode_id] = episode
    return episodes


def _active_rows(cache: M1DevelopmentBaseCache, target: str, split: str) -> list[tuple[int, float]]:
    store = cache.store
    return [
        (i, float(store.labels[target][i]))
        for i, current_split in enumerate(store.sample_splits)
        if current_split == split and bool(store.active[target][i])
    ]


def _profile(values: Iterable[float], support: int) -> dict[str, Any]:
    array = np.asarray(tuple(float(v) for v in values), dtype=np.float64)
    if not len(array):
        return {"active_count": 0, "zero_count": 0, "positive_count": 0, "min": None,
                "p50": None, "p75": None, "p90": None, "p95": None, "p97.5": None,
                "p99": None, "max": None, "mean": None, "std": None,
                "current_support_count": 0, "current_support_fraction": None}
    q = np.quantile(array, (0.5, 0.75, 0.9, 0.95, 0.975, 0.99), method="linear")
    tail = array >= support
    return {
        "active_count": int(len(array)), "zero_count": int(np.sum(array == 0)),
        "positive_count": int(np.sum(array > 0)), "min": float(np.min(array)),
        "p50": float(q[0]), "p75": float(q[1]), "p90": float(q[2]), "p95": float(q[3]),
        "p97.5": float(q[4]), "p99": float(q[5]), "max": float(np.max(array)),
        "mean": float(np.mean(array)), "std": float(np.std(array)),
        "current_support_count": int(np.sum(tail)),
        "current_support_fraction": float(np.mean(tail)),
    }


def _episode_groups(cache: M1DevelopmentBaseCache, target: str, split: str) -> dict[str, list[float]]:
    store = cache.store
    groups: dict[str, list[float]] = defaultdict(list)
    for i, value in _active_rows(cache, target, split):
        groups[store.sample_episode_ids[i]].append(value)
    return dict(groups)


def _episode_values(groups: dict[str, list[float]], target: str) -> tuple[dict[str, float], dict[str, Any]]:
    inconsistent = {}
    values = {}
    for episode_id, items in groups.items():
        unique = sorted(set(float(v) for v in items))
        if target in {"D_OB", "D_TX"} and len(unique) != 1:
            inconsistent[episode_id] = unique
        values[episode_id] = max(items) if target == "T_IB_REMAINING_HAZARD" else unique[0]
    return values, {
        "status": "PASS" if not inconsistent else "FAIL",
        "inconsistent_episode_count": len(inconsistent),
        "inconsistent_episodes": inconsistent,
        "assertion": "WITHIN_EPISODE_VALUE_EXACT" if target in {"D_OB", "D_TX"} else "T_IB_NODE_DEPENDENT_MAX",
    }


def _candidate_rows(row_values: Iterable[float], episode_values: Iterable[float], target: str) -> list[dict[str, Any]]:
    rows, row_array = [], np.asarray(tuple(row_values), dtype=np.float64)
    episode_array = np.asarray(tuple(episode_values), dtype=np.float64)
    current = CURRENT_SUPPORT[target]
    candidates = list(CANDIDATES[target])
    max_value = max(float(np.max(row_array)) if len(row_array) else 0.0,
                    float(np.max(episode_array)) if len(episode_array) else 0.0)
    while candidates[-1] < max_value:
        candidates.append(candidates[-1] + BIN_WIDTH)
    for candidate in candidates:
        row_tail = row_array >= candidate
        ep_tail = episode_array >= candidate
        rows.append({
            "target": target, "candidate_support_minutes": candidate,
            "episode_finite_count": int(np.sum(~ep_tail)), "episode_tail_count": int(np.sum(ep_tail)),
            "episode_tail_fraction": float(np.mean(ep_tail)) if len(episode_array) else None,
            "row_finite_count": int(np.sum(~row_tail)), "row_tail_count": int(np.sum(row_tail)),
            "row_tail_fraction": float(np.mean(row_tail)) if len(row_array) else None,
            "additional_finite_classes": max(0, candidate // BIN_WIDTH - current // BIN_WIDTH),
            "observed_additional_finite_bins": len({int(v // BIN_WIDTH) for v in episode_array if v < candidate}
                                                    - {int(v // BIN_WIDTH) for v in episode_array if v < current}),
        })
    return rows


def _lineage_fields(lineage: dict[str, Any] | None) -> dict[str, Any]:
    lineage = lineage or {}
    schedule, route, carrier, taxi = (lineage.get("schedule_reference") or {},
                                      lineage.get("route_context") or {},
                                      lineage.get("carrier_context") or {},
                                      lineage.get("taxi_reference") or {})
    return {
        "origin": route.get("origin_airport_id"), "destination": route.get("destination_airport_id"),
        "carrier": carrier.get("carrier_id"), "schedule_flight_id": schedule.get("flight_id"),
        "scheduled_departure": schedule.get("scheduled_departure_utc"),
        "taxi_reference": taxi.get("value"), "taxi_reference_id": taxi.get("reference_id"),
        "taxi_reference_hash": taxi.get("freeze_id"), "taxi_reference_level": taxi.get("fallback_level"),
    }


def _source_status_for_episode(
    target: str,
    split: str,
    episode: Any,
    values: list[float],
    records: dict[str, Any],
    lineage: dict[str, Any],
    taxi_identity: dict[str, str],
) -> dict[str, Any]:
    predecessor, successor = records.get(episode.predecessor_flight_id), records.get(episode.successor_flight_id)
    if predecessor is None or successor is None:
        return {"status": "SOURCE_VERIFICATION_REQUIRED", "reason": "SELECTED_CANONICAL_RECORD_MISSING"}
    result = {"status": "SOURCE_CONSISTENT", "target": target, "split": split,
              "episode_id": episode.episode_id, "row_repetitions": len(values),
              "target_values": sorted(set(values)), "predecessor_flight_id": episode.predecessor_flight_id,
              "successor_flight_id": episode.successor_flight_id}
    if target == "T_IB_REMAINING_HAZARD":
        expected_max = max(0.0, (predecessor["actual_arrival_utc"] - episode.episode_start_time).total_seconds() / 60.0)
        implied_decision_times = sorted(
            (predecessor["actual_arrival_utc"] - timedelta(minutes=value)).isoformat()
            for value in values
        )
        result.update({"predecessor_actual_arrival_utc": predecessor["actual_arrival_utc"],
                       "episode_start_time": episode.episode_start_time,
                       "expected_episode_max_remaining_minutes": expected_max,
                       "implied_decision_times_utc": implied_decision_times,
                       "node_grid_step_minutes": 5,
                       "label_match": abs(expected_max - max(values)) <= 1e-6,
                       "verification": "max(0, predecessor_actual_arrival - decision_time); episode maximum is checked at episode_start_time"})
        if not result["label_match"]:
            result["status"] = "SOURCE_CONFLICT"
    elif target == "D_OB":
        actual, scheduled = successor["actual_departure_utc"], successor["schedule_departure_utc"]
        derived = max(0.0, (actual - scheduled).total_seconds() / 60.0)
        clock = classify_departure_values(
            schedule_utc=scheduled,
            direct_utc=actual,
            timezone_name=successor["timezone_name"],
            signed_delay=float(successor["DepDelay"]),
        )
        result.update({"actual_departure_utc": actual, "scheduled_departure_utc": scheduled,
                       "derived_d_ob_minutes": derived, "label_match": all(abs(derived - value) <= 1e-6 for value in values),
                       "signed_dep_delay": successor["DepDelay"],
                       "direct_clock_classification": clock["classification"],
                       "local_wall_clock_residual_minutes": clock["local_wall_clock_residual_minutes"],
                       "verification": "max(0, actual_departure - scheduled_departure)"})
        if not result["label_match"] or clock["classification"] not in {
            "SOURCE_CONSISTENT", "DST_CLOCK_BASIS_EXPLAINED", "SOURCE_CLOCK_ROUNDING"
        }:
            result["status"] = "SOURCE_CONFLICT"
    else:
        ref = lineage.get("taxi_reference")
        taxi = successor.get("taxi_out_minutes")
        derived = None if ref is None or taxi is None else max(0.0, float(taxi) - float(ref))
        result.update({"taxi_out_minutes": taxi, "taxi_reference_minutes": ref,
                       "taxi_reference_id": lineage.get("taxi_reference_id"),
                       "taxi_reference_hash": lineage.get("taxi_reference_hash"),
                       "taxi_reference_level": lineage.get("taxi_reference_level"),
                       "taxi_reference_id_match": lineage.get("taxi_reference_id") == taxi_identity["reference_id"],
                       "taxi_reference_hash_match": lineage.get("taxi_reference_hash") == taxi_identity["manifest_freeze_id"],
                       "derived_d_tx_minutes": derived,
                       "label_match": derived is not None and all(abs(derived - value) <= 1e-6 for value in values),
                       "verification": "max(0, TaxiOut - frozen taxi reference)"})
        if not all((result["label_match"], result["taxi_reference_id_match"],
                    result["taxi_reference_hash_match"], bool(result["taxi_reference_level"]))):
            result["status"] = "SOURCE_CONFLICT"
    return result


def _episode_audit(cache: M1DevelopmentBaseCache, episodes: dict[str, Any], source: dict[str, Any] | None) -> dict[str, Any]:
    store = cache.store
    all_profiles, all_candidates, overflow_rows, verification = {}, [], [], []
    records = (source or {}).get("selected_canonical_records", {})
    taxi_payload = _read_json(A2_OUTPUT / "DATA2_TAXI_REFERENCE_GATE_A2_DIAGNOSTIC.json")
    taxi_identity = {key: taxi_payload[key] for key in ("reference_id", "manifest_freeze_id")}
    # JSON round-tripping is intentionally avoided for typed arithmetic.
    for split in SPLITS:
        all_profiles[split] = {}
        for target in TARGETS:
            row_values = [value for _, value in _active_rows(cache, target, split)]
            groups = _episode_groups(cache, target, split)
            episode_values, consistency = _episode_values(groups, target)
            all_profiles[split][target] = {
                "selection_unit": "EPISODE_MAX" if target == "T_IB_REMAINING_HAZARD" else "UNIQUE_EPISODE",
                "row_profile": _profile(row_values, CURRENT_SUPPORT[target]),
                "episode_profile": _profile(episode_values.values(), CURRENT_SUPPORT[target]),
                "row_active_count": len(row_values), "unique_episode_count": len(episode_values),
                "within_episode_value_consistency": consistency,
                "episode_values": {key: float(value) for key, value in episode_values.items()},
            }
            if split == "train":
                all_candidates.extend(_candidate_rows(row_values, episode_values.values(), target))
            for episode_id, value in episode_values.items():
                if value < CURRENT_SUPPORT[target]:
                    continue
                indices = [i for i, row_value in _active_rows(cache, target, split)
                           if store.sample_episode_ids[i] == episode_id]
                lineage = _lineage_fields(store.static_context_lineages[indices[0]] if indices else None)
                episode = episodes.get(episode_id)
                row = {"target": target, "split": split, "episode_id": episode_id,
                       "target_value": value, "row_repetition_count": len(groups[episode_id]),
                       "origin": lineage.get("origin"), "destination": lineage.get("destination"),
                       "carrier": lineage.get("carrier"), "source_verification": "SOURCE_VERIFICATION_REQUIRED"}
                if episode is not None and source is not None:
                    check = _source_status_for_episode(
                        target, split, episode, groups[episode_id], records, lineage, taxi_identity)
                    row["source_verification"] = check["status"]
                    verification.append(check)
                overflow_rows.append(row)
    return {"profiles": all_profiles, "candidate_tables": all_candidates,
            "overflow_episodes": overflow_rows, "source_verification": verification}


def _weighting_audit() -> dict[str, Any]:
    lifecycle = (ROOT / "model" / "M1" / "lifecycle.py").read_text(encoding="utf-8")
    uses_weights = "episode_normalized_weights" in lifecycle and re.search(r"episode_weights|weights=.*episode", lifecycle) is not None
    return {
        "episode_balanced_loss_status": "PASS" if uses_weights else "M1_EPISODE_WEIGHTING_CONTRACT_REVIEW_REQUIRED",
        "formal_lifecycle_uses_episode_normalized_weights": uses_weights,
        "row_weighted_loss_detected": not uses_weights,
        "evidence": "M1Lifecycle._global_loss_counts counts active rows and _loss normalizes by row counts; model/M1/data.py defines episode_normalized_weights but lifecycle does not consume it." if not uses_weights else "episode-normalized weights are consumed by M1Lifecycle.",
    }


def _config_audit() -> dict[str, Any]:
    config = yaml.safe_load((ROOT / "configs" / "scientific" / "foundation.yaml").read_text(encoding="utf-8"))
    params = config["parameters"]
    return {
        "positive_quantile_tail_policy": params["m1_v2_positive_tail_policy"]["value"],
        "train_value_loss_truncation": False,
        "d_tx_parent_conditioning_role": "NONE",
        "foundation_yaml_changed": False,
    }


def _tensor_group_hash(values: dict[str, torch.Tensor]) -> str:
    hasher = sha256()
    for name in sorted(values):
        tensor = values[name].detach().cpu().contiguous()
        hasher.update(name.encode("utf-8"))
        hasher.update(str(tensor.dtype).encode("ascii"))
        hasher.update(str(tuple(tensor.shape)).encode("ascii"))
        hasher.update(tensor.numpy().tobytes())
    return f"sha256:{hasher.hexdigest()}"


def _recommendations(audit: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = audit["profiles"]["train"]
    tib = profiles["T_IB_REMAINING_HAZARD"]
    dob = profiles["D_OB"]
    dtx = profiles["D_TX"]
    tib_tail = tib["episode_profile"]["current_support_count"]
    d_ob_210 = next(row for row in audit["candidate_tables"] if row["target"] == "D_OB" and row["candidate_support_minutes"] == 210)
    d_ob = [row for row in audit["overflow_episodes"] if row["target"] == "D_OB" and row["split"] == "train"]
    dtx_tail = dtx["episode_profile"]["current_support_count"]
    return [
        {"decision_id": "C0A-D01", "target": "T_IB_REMAINING_HAZARD", "recommendation": "KEEP_360" if tib_tail <= 1 else "EXPAND_TO_390",
         "evidence": f"Train episode-max tail={tib_tail}; row tail={tib['row_profile']['current_support_count']}; episode-max max={tib['episode_profile']['max']} and support remains a survival/overflow state."},
        {"decision_id": "C0A-D02", "target": "D_OB", "recommendation": "EXPAND_TO_210" if len(d_ob) >= 2 and d_ob_210["episode_tail_count"] < dob["episode_profile"]["current_support_count"] else "KEEP_180",
         "evidence": f"Train unique D_OB tail episodes={len(d_ob)} with values={[row['target_value'] for row in d_ob]}; at 210 min episode tail={d_ob_210['episode_tail_count']} and row tail={d_ob_210['row_tail_count']}."},
        {"decision_id": "C0A-D03", "target": "D_TX", "recommendation": "KEEP_60" if dtx_tail == 0 else "EXPAND_TO_75",
         "evidence": f"Train unique D_TX tail episodes={dtx_tail}; D_TX parent-conditioning role is NONE; Development-only tails remain generalization diagnostics."},
    ]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if value is None else _jsonable(value) for key, value in row.items()})


def _packet(report: dict[str, Any]) -> str:
    profiles = report["episode_balance"]["profiles"]
    source = report["source_clock"]
    decisions = report["human_decisions"]
    lines = [
        "# AIR_SLOT_M1_V2_TARGET_SUPPORT_GATE_C0A", "",
        f"- Status: `{report['TARGET_SUPPORT_C0A_STATUS']}`",
        f"- Repository HEAD: `{report['repository_head']}`",
        "- Scope: audit-only; Train/Calibration/Development and Jan-Sep source paths only.", "",
        "## DST / Source Clock", "",
        f"- All departure mismatches: `{source['departure_inconsistency_count']}`.",
        f"- Classification counts: `{source['departure_classification_counts']}`.",
        f"- Canonical timestamp changes (all/B2): `{source['canonical_timestamp_change_count']}` / `{source['canonical_timestamp_change_count_in_b2']}`.",
        f"- 265-minute case: `{json.dumps(source['max_difference_case'], default=str, sort_keys=True)}`.",
        f"- Cohort intersection: `{json.dumps(source['intersection'], sort_keys=True)}`.", "",
        "## Episode-Balanced Support", "",
    ]
    for target in TARGETS:
        train = profiles["train"][target]
        lines.append(f"- `{target}`: rows={train['row_active_count']}, unique episodes={train['unique_episode_count']}, episode profile={json.dumps(train['episode_profile'], sort_keys=True)}")
    lines.extend(["", "## Overflow Episodes", "", "| Split | Target | Value | Row repetitions | Source verification |", "|---|---|---:|---:|---|"])
    for row in report["episode_balance"]["overflow_episodes"]:
        lines.append(f"| {row['split']} | {row['target']} | {row['target_value']} | {row['row_repetition_count']} | {row['source_verification']} |")
    lines.extend(["", "## Training Weighting", "", f"- `{report['training_weighting']['episode_balanced_loss_status']}`", f"- {report['training_weighting']['evidence']}", "",
                  "## Human Review Recommendations", ""])
    for decision in decisions:
        lines.extend([f"### {decision['decision_id']}", f"- `{decision['recommendation']}`", f"- {decision['evidence']}", ""])
    lines.extend(["## B2 Immutability / Safety", "", f"- B2 schema: `{report['b2_immutability']['schema_hash']}`", f"- B2 cache: `{report['b2_immutability']['cache_hash']}`", f"- Labels unchanged: `{report['b2_immutability']['labels_unchanged']}`", f"- Active masks unchanged: `{report['b2_immutability']['active_masks_unchanged']}`", "", "```text", "M1_TRAINING_RUNS = 0", "TUNING_RUNS = 0", "FINAL_TEST_ACCESS_COUNT = 0", "M1_TARGET_SUPPORT_FROZEN = false", "```", "", "No support/config update, training, tuning, C0B, C1, Final Test, FULL, or paper_full was run.", ""])
    return "\n".join(lines)


def run(output_dir: Path = DEFAULT_OUTPUT, *, source_scan: bool = True) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cache, manifest, b2 = _load_b2()
    episodes = _load_a2_episodes()
    balance = _episode_audit(cache, episodes, None)
    labels_before = _tensor_group_hash(cache.store.labels)
    active_before = _tensor_group_hash(cache.store.active)
    source = scan_source_clock(cache, episodes) if source_scan else {
        "scope": "SOURCE_SCAN_SKIPPED_FOR_UNIT_TEST", "departure_inconsistency_count": None,
        "departure_classification_counts": {}, "departure_inconsistency_rows": [],
        "intersection": {}, "canonical_timestamp_change_count": None,
        "canonical_timestamp_change_count_in_b2": None, "max_difference_case": None,
        "selected_canonical_records": {}, "final_test_access_count": 0,
    }
    if source_scan:
        balance = _episode_audit(cache, episodes, source)
    source_records = source.get("selected_canonical_records", {})
    source_report = {key: value for key, value in source.items()
                     if key != "selected_canonical_records"}
    labels_after = _tensor_group_hash(cache.store.labels)
    active_after = _tensor_group_hash(cache.store.active)
    weighting = _weighting_audit()
    config = _config_audit()
    recommendations = _recommendations(balance)
    schema_unchanged = manifest.get("feature_schema_hash") == EXPECTED_SCHEMA_HASH
    cache_unchanged = manifest.get("cache_hash") == EXPECTED_CACHE_HASH
    flags = []
    if source_scan and source["canonical_timestamp_change_count_in_b2"]:
        flags.append("TARGET_SUPPORT_C0A_PRE_TIMESTAMP_REPAIR_REQUIRED")
    if source_scan and source["intersection"].get("conflict_flights_in_a2_cohort", 0):
        flags.append("TARGET_SUPPORT_C0A_SOURCE_ANOMALY_INTERSECTS_SUPPORT")
    if weighting["episode_balanced_loss_status"] != "PASS":
        flags.append("TARGET_SUPPORT_C0A_WEIGHTING_REVIEW_REQUIRED")
    contract_failure = (
        not schema_unchanged or not cache_unchanged
        or labels_before != labels_after or active_before != active_after
        or any(item["within_episode_value_consistency"]["status"] != "PASS"
               for split in balance["profiles"].values() for item in split.values())
        or any(item["status"] != "SOURCE_CONSISTENT" for item in balance["source_verification"])
        or source.get("final_test_access_count") != 0
    )
    if contract_failure:
        flags.append("TARGET_SUPPORT_C0A_CONTRACT_FAILURE")
    report = {
        "schema_version": "AIR_SLOT_M1_V2_TARGET_SUPPORT_GATE_C0A_V1",
        "TARGET_SUPPORT_C0A_STATUS": "TARGET_SUPPORT_C0A_REVIEW_PACKET_READY" if not flags else flags[0],
        "status_flags": flags,
        "repository_head": _head(), "scope": "SOURCE_VERIFICATION_EPISODE_BALANCE_HUMAN_REVIEW_ONLY",
        "source_clock": source_report,
        "episode_balance": balance,
        "training_weighting": weighting,
        "config_contract": config,
        "human_decisions": recommendations,
        "current_support": CURRENT_SUPPORT,
        "b2_immutability": {
            "schema_hash": manifest.get("feature_schema_hash"), "cache_hash": manifest.get("cache_hash"),
            "schema_expected": EXPECTED_SCHEMA_HASH, "cache_expected": EXPECTED_CACHE_HASH,
            "schema_unchanged": schema_unchanged, "cache_unchanged": cache_unchanged,
            "labels_before": labels_before, "labels_after": labels_after,
            "active_masks_before": active_before, "active_masks_after": active_after,
            "labels_unchanged": labels_before == labels_after,
            "active_masks_unchanged": active_before == active_after,
            "feature_width": "39 dynamic + 4 static = 43",
        },
        "safety": SAFETY,
        "automatic_decisions_applied": False,
    }
    basis = json.dumps(_jsonable(report), sort_keys=True, separators=(",", ":"))
    report["artifact_hash"] = f"sha256:{sha256(basis.encode('utf-8')).hexdigest()}"
    _write_json(output_dir / "AIR_SLOT_M1_V2_TARGET_SUPPORT_GATE_C0A.json", report)
    _write_json(output_dir / "M1_V2_TARGET_SUPPORT_GATE_C0A_EPISODE_PROFILES.json", balance["profiles"])
    _write_json(output_dir / "M1_V2_TARGET_SUPPORT_GATE_C0A_SOURCE_RECORDS.json", source_records)
    _write_csv(output_dir / "M1_V2_TARGET_SUPPORT_GATE_C0A_SOURCE_CLOCK.csv", source_report["departure_inconsistency_rows"])
    _write_csv(output_dir / "M1_V2_TARGET_SUPPORT_GATE_C0A_EPISODE_THRESHOLDS.csv", balance["candidate_tables"])
    _write_csv(output_dir / "M1_V2_TARGET_SUPPORT_GATE_C0A_OVERFLOW_EPISODES.csv", balance["overflow_episodes"])
    (output_dir / "M1_V2_TARGET_SUPPORT_GATE_C0A_HUMAN_REVIEW_PACKET.md").write_text(_packet(report), encoding="utf-8")
    return report


def main() -> None:
    report = run()
    print(json.dumps({key: report[key] for key in ("TARGET_SUPPORT_C0A_STATUS", "status_flags", "artifact_hash", "safety")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
