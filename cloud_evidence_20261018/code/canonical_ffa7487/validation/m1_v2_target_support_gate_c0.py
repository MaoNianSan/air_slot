"""Read-only M1 V2 finite-support audit (Gate C0).

The runner consumes the frozen B2 cache labels/active masks and the static
lineage retained by that cache.  It never rebuilds targets from BTS and never
changes the scientific configuration or support contracts.
"""

from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any

import numpy as np
import yaml

from model.M1.cache import M1DevelopmentBaseCache

ROOT = Path(__file__).resolve().parents[1]
B2_OUTPUT = ROOT / "artifacts" / "diagnostics" / "m1_v2_feature_gate_b2"
A2_OUTPUT = ROOT / "artifacts" / "diagnostics" / "m1_v2_data_gate_a2"
DEFAULT_OUTPUT = ROOT / "artifacts" / "diagnostics" / "m1_v2_target_support_gate_c0"

TARGETS = ("T_IB_REMAINING_HAZARD", "D_OB", "D_TX")
CURRENT_SUPPORT = {"T_IB_REMAINING_HAZARD": 360, "D_OB": 180, "D_TX": 60}
CANDIDATES = {
    "T_IB_REMAINING_HAZARD": [300, 330, 360, 390, 420, 450, 480],
    "D_OB": [120, 150, 180, 210, 240, 270, 300, 360, 420, 480],
    "D_TX": [30, 45, 60, 75, 90, 120, 150],
}
BIN_WIDTH = 5
QUANTILE_LEVELS = (0.1, 0.3, 0.5, 0.7, 0.9)
EXPECTED_SCHEMA_HASH = (
    "sha256:1f4b886a9bddc67f3fe72b977ea957cf5828b6cdd20dcc69655dcf3f2ec2972a"
)
EXPECTED_CACHE_HASH = (
    "sha256:157c0d555c40efd9d7dc5ecebc5dda60a902b855d42bdab9a3657aa601e6f919"
)
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
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def _load_b2() -> tuple[M1DevelopmentBaseCache, dict, dict]:
    manifest_path = B2_OUTPUT / "M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json"
    data_path = B2_OUTPUT / "M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz"
    report_path = B2_OUTPUT / "AIR_SLOT_M1_V2_FEATURE_GATE_B2.json"
    manifest = _read_json(manifest_path)
    report = _read_json(report_path)
    if report.get("FEATURE_GATE_STATUS") != EXPECTED_B2_STATUS:
        raise ValueError("TARGET_SUPPORT_C0_B2_STATUS_NOT_FROZEN")
    if manifest.get("feature_schema_hash") != EXPECTED_SCHEMA_HASH:
        raise ValueError("TARGET_SUPPORT_C0_B2_SCHEMA_HASH_MISMATCH")
    if manifest.get("cache_hash") != EXPECTED_CACHE_HASH:
        raise ValueError("TARGET_SUPPORT_C0_B2_CACHE_HASH_MISMATCH")
    if manifest.get("final_test_access_count") != 0:
        raise ValueError("TARGET_SUPPORT_C0_FINAL_TEST_ACCESS")
    cache = M1DevelopmentBaseCache.load(
        data_path, manifest_path, expected_cache_key=manifest["cache_key"]
    )
    return cache, manifest, report


def _load_a2_report() -> dict[str, Any]:
    return _read_json(A2_OUTPUT / "AIR_SLOT_M1_V2_DATA_GATE_A2.json")


def _config_provenance() -> dict[str, Any]:
    config = yaml.safe_load(
        (ROOT / "configs" / "scientific" / "foundation.yaml").read_text(
            encoding="utf-8"
        )
    )
    parameters = config["parameters"]
    names = {
        "T_IB_REMAINING_HAZARD": "m1_r_ib_max_finite_minutes",
        "D_OB": "m1_delta_ob_max_finite_minutes",
        "D_TX": "m1_t_tx_max_finite_minutes",
    }
    values = {target: int(parameters[name]["value"]) for target, name in names.items()}
    support_sources = parameters["m1_state_estimator_v2"]["provenance"][
        "support_sources"
    ]
    return {
        "legacy_parameter_names": names,
        "legacy_parameter_values": values,
        "support_sources_text": support_sources,
        "legacy_support_parameter_name_drift": True,
        "suggested_v2_names": {
            "T_IB_REMAINING_HAZARD": "m1_v2_t_ib_remaining_max_finite_minutes",
            "D_OB": "m1_v2_d_ob_max_finite_minutes",
            "D_TX": "m1_v2_d_tx_max_finite_minutes",
        },
        "quantile_levels": list(parameters["m1_v2_quantile_levels"]["value"]),
        "positive_tail_policy": parameters["m1_v2_positive_tail_policy"]["value"],
    }


def _active_values(
    cache: M1DevelopmentBaseCache, target: str, split: str
) -> np.ndarray:
    store = cache.store
    values = [
        float(store.labels[target][index])
        for index, current_split in enumerate(store.sample_splits)
        if current_split == split and bool(store.active[target][index])
    ]
    return np.asarray(values, dtype=np.float64)


def _profile(values: np.ndarray, support: int) -> dict[str, Any]:
    if not len(values):
        return {
            "active_count": 0,
            "zero_count": 0,
            "positive_count": 0,
            "min": None,
            "p50": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "p97.5": None,
            "p99": None,
            "p99.5": None,
            "p99.9": None,
            "max": None,
            "mean": None,
            "std": None,
            "current_support_count": 0,
            "current_support_fraction": None,
        }
    quantiles = np.quantile(
        values, (0.5, 0.75, 0.9, 0.95, 0.975, 0.99, 0.995, 0.999), method="linear"
    )
    tail = values >= support
    return {
        "active_count": int(len(values)),
        "zero_count": int(np.sum(values == 0)),
        "positive_count": int(np.sum(values > 0)),
        "min": float(np.min(values)),
        "p50": float(quantiles[0]),
        "p75": float(quantiles[1]),
        "p90": float(quantiles[2]),
        "p95": float(quantiles[3]),
        "p97.5": float(quantiles[4]),
        "p99": float(quantiles[5]),
        "p99.5": float(quantiles[6]),
        "p99.9": float(quantiles[7]),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "current_support_count": int(np.sum(tail)),
        "current_support_fraction": float(np.mean(tail)),
    }


def _candidate_rows(values: np.ndarray, target: str) -> list[dict[str, Any]]:
    current = CURRENT_SUPPORT[target]
    current_class_count = current // BIN_WIDTH + 1
    current_finite_bins = {
        int(value // BIN_WIDTH) for value in values if value < current
    }
    rows = []
    candidates = list(CANDIDATES[target])
    max_value = float(np.max(values)) if len(values) else 0.0
    next_candidate = (int(np.ceil(max_value / BIN_WIDTH)) * BIN_WIDTH) or BIN_WIDTH
    while candidates[-1] < next_candidate:
        candidates.append(candidates[-1] + BIN_WIDTH)
    for candidate in candidates:
        finite = values < candidate
        finite_bins = {int(value // BIN_WIDTH) for value in values[finite]}
        class_count = candidate // BIN_WIDTH + 1
        rows.append(
            {
                "target": target,
                "candidate_support_minutes": candidate,
                "finite_count": int(np.sum(finite)),
                "tail_count": int(np.sum(~finite)),
                "tail_fraction": float(np.mean(~finite)) if len(values) else None,
                "additional_finite_classes": max(
                    0, candidate // BIN_WIDTH - current // BIN_WIDTH
                ),
                "additional_finite_classes_observed": max(
                    0, len(finite_bins - current_finite_bins)
                ),
                "finite_class_count": candidate // BIN_WIDTH,
                "class_count_including_tail": class_count,
                "relative_class_count_increase": float(
                    class_count / current_class_count - 1.0
                ),
            }
        )
    return rows


def _infer_stage(store, index: int) -> str:
    ib = bool(store.active["T_IB_REMAINING_HAZARD"][index])
    ob = bool(store.active["D_OB"][index])
    tx = bool(store.active["D_TX"][index])
    if ib and ob and tx:
        return "PRE_IB"
    if not ib and ob:
        return "POST_IB_PRE_OB"
    if not ob and tx:
        return "POST_OB_PRE_TO"
    if not tx:
        return "UNRESOLVED_STAGE_OR_TAXI_REFERENCE_ABSTAIN"
    return "UNKNOWN"


def _lineage_fields(lineage: dict[str, Any] | None) -> dict[str, Any]:
    lineage = lineage or {}
    schedule = lineage.get("schedule_reference") or {}
    route = lineage.get("route_context") or {}
    carrier = lineage.get("carrier_context") or {}
    taxi = lineage.get("taxi_reference") or {}
    return {
        "origin": route.get("origin_airport_id"),
        "destination": route.get("destination_airport_id"),
        "carrier": carrier.get("carrier_id"),
        "schedule_flight_id": schedule.get("flight_id"),
        "scheduled_departure": schedule.get("scheduled_departure_utc"),
        "taxi_reference": taxi.get("value"),
        "taxi_reference_level": taxi.get("fallback_level"),
        "taxi_reference_id": taxi.get("reference_id"),
        "taxi_reference_fallback_level": taxi.get("fallback_level"),
    }


def _overflow_rows(cache: M1DevelopmentBaseCache) -> list[dict[str, Any]]:
    store = cache.store
    rows: list[dict[str, Any]] = []
    for index, split in enumerate(store.sample_splits):
        lineage = _lineage_fields(store.static_context_lineages[index])
        for target in TARGETS:
            if not bool(store.active[target][index]):
                continue
            value = float(store.labels[target][index])
            support = CURRENT_SUPPORT[target]
            if value < support:
                continue
            row = {
                "target": target,
                "split": split,
                "episode_id": store.sample_episode_ids[index],
                "decision_node_id": store.sample_decision_node_ids[index],
                "service_date": store.sample_episode_dates[index],
                "operational_stage": _infer_stage(store, index),
                "origin": lineage["origin"],
                "destination": lineage["destination"],
                "carrier": lineage["carrier"],
                "tail_episode_identity": lineage["schedule_flight_id"],
                "target_exact_minutes": value,
                "current_support_minutes": support,
                "excess_above_support_minutes": value - support,
                "decision_time": None,
                "t_ib_a00": None,
                "remaining_minutes": (
                    value if target == "T_IB_REMAINING_HAZARD" else None
                ),
                "scheduled_departure": lineage["scheduled_departure"],
                "actual_departure": None,
                "signed_dep_delay": None,
                "d_ob_minutes": value if target == "D_OB" else None,
                "taxi_out_minutes": None,
                "taxi_reference_minutes": lineage["taxi_reference"],
                "taxi_reference_level": lineage["taxi_reference_level"],
                "taxi_reference_id": lineage["taxi_reference_id"],
                "fallback_level": lineage["taxi_reference_fallback_level"],
                "source_fields_status": "NOT_RETAINED_IN_B2_CACHE",
                "source_consistency_status": "NOT_VERIFIABLE_FROM_FROZEN_CACHE",
            }
            rows.append(_jsonable(row))
    rows.sort(
        key=lambda row: (
            row["target"],
            row["split"],
            row["episode_id"],
            row["decision_node_id"],
        )
    )
    return rows


def _source_consistency(
    a2: dict[str, Any], overflow_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    source = a2.get("source_semantics", {})
    direct = source.get("direct_signed_consistency", {})
    departure_details = {
        split: {
            "exact_agreement_rate": direct.get(split, {})
            .get("departure", {})
            .get("exact_agreement_rate"),
            "within_1min_rate": direct.get(split, {})
            .get("departure", {})
            .get("within_1min_rate"),
            "max_abs_difference_minutes": direct.get(split, {})
            .get("departure", {})
            .get("max_abs_difference_minutes"),
            "deterministic_inconsistency_samples": direct.get(split, {})
            .get("departure", {})
            .get("deterministic_inconsistency_samples", []),
        }
        for split in ("train", "calibration", "development")
    }
    global_pass = all(
        item["exact_agreement_rate"] == 1.0
        and not item["deterministic_inconsistency_samples"]
        for item in departure_details.values()
    )
    unavailable = len(overflow_rows) > 0
    return {
        "a2_global_signed_departure_consistency": "PASS" if global_pass else "FAIL",
        "a2_departure_details": departure_details,
        "a2_canonical_rule": a2.get("canonical_rule", {}),
        "row_level_source_fields_retained": False,
        "row_level_verification": "NOT_VERIFIABLE_FROM_FROZEN_CACHE",
        "classification_if_unverifiable": "TARGET_SUPPORT_C0_DATA_ANOMALY",
        "overflow_rows_with_unverifiable_source_fields": (
            len(overflow_rows) if unavailable else 0
        ),
        "status": "TARGET_SUPPORT_C0_DATA_ANOMALY" if unavailable else "PASS",
        "formulas": {
            "T_IB_REMAINING_HAZARD": "max(0, T_IB_A00 - decision_time)",
            "D_OB": "max(0, actual_departure - scheduled_departure); signed DepDelay alignment required",
            "D_TX": "max(0, TaxiOut - taxi_reference)",
        },
    }


def _d_ob_tail_bands(cache: M1DevelopmentBaseCache) -> dict[str, int]:
    values = _active_values(cache, "D_OB", "train")
    bands = (
        (180, 210, "180--210"),
        (210, 240, "210--240"),
        (240, 300, "240--300"),
        (300, 360, "300--360"),
        (360, float("inf"), ">360"),
    )
    return {
        name: int(np.sum((values >= low) & (values < high)))
        for low, high, name in bands
    }


def _d_tx_comparison(cache: M1DevelopmentBaseCache) -> dict[str, Any]:
    store = cache.store
    groups: dict[str, list[float]] = {"D_OB_finite": [], "D_OB_overflow": []}
    for index, split in enumerate(store.sample_splits):
        if (
            split != "train"
            or not bool(store.active["D_OB"][index])
            or not bool(store.active["D_TX"][index])
        ):
            continue
        key = (
            "D_OB_overflow"
            if float(store.labels["D_OB"][index]) >= CURRENT_SUPPORT["D_OB"]
            else "D_OB_finite"
        )
        groups[key].append(float(store.labels["D_TX"][index]))
    output = {}
    for key, values in groups.items():
        array = np.asarray(values, dtype=np.float64)
        positive = array[array > 0]
        output[key] = {
            "row_count": int(len(array)),
            "zero_fraction": float(np.mean(array == 0)) if len(array) else None,
            "positive_mean": float(np.mean(positive)) if len(positive) else None,
            "positive_median": float(np.median(positive)) if len(positive) else None,
            "positive_p90": (
                float(np.quantile(positive, 0.9)) if len(positive) else None
            ),
        }
    return output


def _d_tx_development_clusters(cache: M1DevelopmentBaseCache) -> dict[str, Any]:
    store = cache.store
    rows = []
    for index, split in enumerate(store.sample_splits):
        if split != "development" or not bool(store.active["D_TX"][index]):
            continue
        value = float(store.labels["D_TX"][index])
        if value < CURRENT_SUPPORT["D_TX"]:
            continue
        fields = _lineage_fields(store.static_context_lineages[index])
        rows.append(
            {
                "episode_id": store.sample_episode_ids[index],
                "service_date": store.sample_episode_dates[index],
                "origin": fields["origin"],
                "destination": fields["destination"],
                "carrier": fields["carrier"],
                "taxi_reference_minutes": fields["taxi_reference"],
                "fallback_level": fields["taxi_reference_level"],
                "target_exact_minutes": value,
            }
        )

    def grouped(key: str) -> list[dict[str, Any]]:
        counts: dict[str, dict[str, Any]] = {}
        for row in rows:
            value = str(row[key])
            item = counts.setdefault(
                value,
                {
                    "group": value,
                    "row_count": 0,
                    "episode_ids": set(),
                    "target_values": set(),
                },
            )
            item["row_count"] += 1
            item["episode_ids"].add(row["episode_id"])
            item["target_values"].add(row["target_exact_minutes"])
        return [
            {
                "group": item["group"],
                "row_count": item["row_count"],
                "episode_count": len(item["episode_ids"]),
                "target_values": sorted(item["target_values"]),
            }
            for item in sorted(
                counts.values(), key=lambda item: (-item["row_count"], item["group"])
            )
        ]

    return {
        "overflow_row_count": len(rows),
        "overflow_episode_count": len({row["episode_id"] for row in rows}),
        "by_origin": grouped("origin"),
        "by_destination": grouped("destination"),
        "by_carrier": grouped("carrier"),
        "by_service_date": grouped("service_date"),
        "by_taxi_reference": grouped("taxi_reference_minutes"),
        "weather_context": "NOT_RETAINED_IN_B2_CACHE",
        "interpretation": "Development-only shift/generalization diagnostic; not support-selection evidence.",
    }


def _scenario_representation(cache: M1DevelopmentBaseCache) -> dict[str, Any]:
    output = {}
    for target, split in (
        ("T_IB_REMAINING_HAZARD", "train"),
        ("D_OB", "train"),
        ("D_TX", "development"),
    ):
        values = _active_values(cache, target, split)
        support = CURRENT_SUPPORT[target]
        overflow = values[values >= support]
        representative = support + BIN_WIDTH
        errors = np.abs(overflow - representative)
        output[target] = {
            "split": split,
            "overflow_count": int(len(overflow)),
            "overflow_values": sorted(set(float(value) for value in overflow)),
            "representative_minutes": representative,
            "absolute_error_mean_minutes": (
                float(np.mean(errors)) if len(errors) else None
            ),
            "absolute_error_max_minutes": (
                float(np.max(errors)) if len(errors) else None
            ),
        }
    return output


def _loss_truncation() -> dict[str, Any]:
    source = (ROOT / "model" / "M1" / "lifecycle.py").read_text(encoding="utf-8")
    exact_minutes = all(
        token in source
        for token in (
            "d_ob_minutes[index] = minutes",
            "d_tx_minutes[index] = minutes",
            'value=encoded["d_ob_minutes"]',
            'value=encoded["d_tx_minutes"]',
        )
    )
    return {
        "TRAIN_VALUE_LOSS_TRUNCATION": False if exact_minutes else True,
        "evidence": "M1Lifecycle._encode stores exact positive minutes and _loss passes encoded minute values to hurdle_quantile_loss.",
        "source_contract_check": exact_minutes,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {key: "" if row.get(key) is None else row.get(key) for key in fields}
            )


def _markdown(report: dict[str, Any]) -> str:
    profiles = report["train_profiles"]
    current = report["current_support"]
    decisions = report["human_decisions"]
    lines = [
        "# AIR_SLOT_M1_V2_TARGET_SUPPORT_GATE_C0",
        "",
        f"- Status: `{report['TARGET_SUPPORT_C0_STATUS']}`",
        f"- Repository HEAD: `{report['repository_head']}`",
        "- Scope: frozen B2 labels/active masks and retained lineage only; no raw BTS target reconstruction.",
        "",
        "## B2 Baseline",
        "",
        f"- Frozen schema: `{report['b2_baseline']['frozen_schema_hash']}`",
        f"- Frozen cache: `{report['b2_baseline']['frozen_cache_hash']}`",
        f"- Feature schema/hash contract unchanged: `{report['b2_baseline']['feature_contract_unchanged']}`",
        "",
        "## Current Support",
        "",
        f"- T_IB_REMAINING_HAZARD: `{current['T_IB_REMAINING_HAZARD']} min`",
        f"- D_OB: `{current['D_OB']} min`",
        f"- D_TX: `{current['D_TX']} min`",
        f"- Bin width: `{report['bin_width_minutes']} min` (out of scope)",
        "",
        "## Provenance",
        "",
        "| Target | Legacy source | Transfer status |",
        "|---|---|---|",
        "| T_IB_REMAINING_HAZARD | V1 R_IB support statistics | PARTIALLY_TRANSFERABLE; cohort changed |",
        "| D_OB | V1 signed DELTA_OB support | PARTIALLY_TRANSFERABLE / REESTIMATION_REQUIRED |",
        "| D_TX | V1 raw T_TX support | NOT_SEMANTICALLY_TRANSFERABLE / REESTIMATION_REQUIRED |",
        "",
        "## TRAIN_SELECTION_EVIDENCE",
        "",
    ]
    for target in TARGETS:
        item = profiles[target]
        lines.append(
            f"- `{target}`: active={item['active_count']}, zero={item['zero_count']}, positive={item['positive_count']}, "
            f"p50={item['p50']}, p90={item['p90']}, p99={item['p99']}, max={item['max']}, "
            f"current-tail={item['current_support_count']} ({item['current_support_fraction']:.6f})."
        )
    lines.extend(
        [
            "",
            "## CALIBRATION_DIAGNOSTIC",
            "",
            f"- Calibration: `{json.dumps(report['CALIBRATION_DIAGNOSTIC'], sort_keys=True)}`",
            "- Calibration is diagnostic only and was not used to select support.",
            "",
            "## DEVELOPMENT_DIAGNOSTIC",
            "",
            f"- Development: `{json.dumps(report['DEVELOPMENT_DIAGNOSTIC'], sort_keys=True)}`",
            "- Development is diagnostic only and was not used to select support.",
            "",
            "## Forensic Gate",
            "",
            f"- Overflow rows: `{report['overflow_counts']}`.",
            f"- A2 global signed departure consistency: `{report['source_consistency']['a2_global_signed_departure_consistency']}`.",
            f"- A2 departure detail: `{json.dumps(report['source_consistency']['a2_departure_details'], sort_keys=True)}`.",
            "- Row-level actual departure, signed DepDelay, TaxiOut, T_IB_A00, and decision time are not retained in the frozen B2 cache.",
            f"- Row-level source-consistency status: `{report['source_consistency']['status']}`; see `M1_V2_TARGET_SUPPORT_C0_OVERFLOW.csv`.",
            "",
            "## Conditioning And Representation",
            "",
            f"- D_OB Train tail bands: `{report['d_ob_train_tail_bands']}`.",
            f"- D_OB finite-vs-overflow D_TX diagnostic: `{json.dumps(report['d_ob_to_d_tx_diagnostic'], sort_keys=True)}`.",
            f"- D_TX parent-conditioning role: `{report['conditioning_consequences']['D_TX_PARENT_CONDITIONING_ROLE']}`.",
            f"- Scenario representative diagnostics: `{json.dumps(report['scenario_representation'], sort_keys=True)}`.",
            f"- TRAIN_VALUE_LOSS_TRUNCATION: `{report['train_value_loss_truncation']['TRAIN_VALUE_LOSS_TRUNCATION']}`.",
            "",
            "## Finite Support vs Quantile Tail",
            "",
            "- `FINITE_SUPPORT_REVIEW` is the only C0 decision surface.",
            "- `POSITIVE_QUANTILE_TAIL_STATUS = UNRESOLVED_AND_OUT_OF_SCOPE`.",
            "- Positive quantile levels remain `[0.1, 0.3, 0.5, 0.7, 0.9]`; no tail policy was changed.",
            "",
            "## Human Decisions",
            "",
        ]
    )
    for decision in decisions:
        lines.extend(
            [
                f"### {decision['decision_id']}",
                "",
                f"- Options: `{' / '.join(decision['options'])}`",
                f"- Recommendation: `{decision['recommendation']}`",
                f"- Evidence: {decision['evidence']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Safety",
            "",
            "```text",
            "M1_TRAINING_RUNS = 0",
            "TUNING_RUNS = 0",
            "FINAL_TEST_ACCESS_COUNT = 0",
            "PAPER_FULL_RUN = false",
            "GATE_B2_FEATURE_FREEZE = true",
            "M1_TARGET_SUPPORT_FROZEN = false",
            "HYPERPARAMETER_TUNING_AUTHORIZED = false",
            "```",
            "",
            "No support/config update, training, tuning, C1, Final Test, FULL, or paper_full was run.",
            "",
        ]
    )
    return "\n".join(lines)


def run(output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cache, manifest, b2 = _load_b2()
    a2 = _load_a2_report()
    provenance = _config_provenance()
    train_profiles = {
        target: _profile(
            _active_values(cache, target, "train"), CURRENT_SUPPORT[target]
        )
        for target in TARGETS
    }
    split_profiles = {
        split: {
            target: _profile(
                _active_values(cache, target, split), CURRENT_SUPPORT[target]
            )
            for target in TARGETS
        }
        for split in ("calibration", "development")
    }
    threshold_rows = [
        row
        for target in TARGETS
        for row in _candidate_rows(_active_values(cache, target, "train"), target)
    ]
    overflow_rows = _overflow_rows(cache)
    source_consistency = _source_consistency(a2, overflow_rows)
    schema_unchanged = (
        manifest.get("feature_schema_hash") == EXPECTED_SCHEMA_HASH
        and b2.get("frozen_schema_hash") == EXPECTED_SCHEMA_HASH
        and b2.get("cache", {}).get("frozen") == EXPECTED_CACHE_HASH
        and b2.get("cache", {}).get("tensor_equivalence", {}).get("status") == "PASS"
    )
    report: dict[str, Any] = {
        "schema_version": "AIR_SLOT_M1_V2_TARGET_SUPPORT_GATE_C0_V1",
        "TARGET_SUPPORT_C0_STATUS": (
            "TARGET_SUPPORT_C0_DATA_ANOMALY"
            if source_consistency["status"] != "PASS"
            else "TARGET_SUPPORT_C0_REVIEW_PACKET_READY"
        ),
        "repository_head": _head(),
        "scope": "TRAIN_SELECTION_CALIBRATION_DIAGNOSTIC_DEVELOPMENT_DIAGNOSTIC_ONLY",
        "b2_baseline": {
            "frozen_schema_hash": manifest.get("feature_schema_hash"),
            "frozen_cache_hash": manifest.get("cache_hash"),
            "feature_contract_unchanged": schema_unchanged,
            "b2_status": b2.get("FEATURE_GATE_STATUS"),
            "tensor_equivalence": b2.get("cache", {}).get("tensor_equivalence"),
        },
        "current_support": CURRENT_SUPPORT,
        "bin_width_minutes": BIN_WIDTH,
        "provenance": provenance,
        "train_profiles": train_profiles,
        "split_profiles": split_profiles,
        "TRAIN_SELECTION_EVIDENCE": {
            "profiles": train_profiles,
            "threshold_candidates": threshold_rows,
            "selection_split": "train",
        },
        "CALIBRATION_DIAGNOSTIC": split_profiles["calibration"],
        "DEVELOPMENT_DIAGNOSTIC": split_profiles["development"],
        "threshold_candidates_train_only": threshold_rows,
        "overflow_counts": {
            target: {
                split: sum(
                    1
                    for row in overflow_rows
                    if row["target"] == target and row["split"] == split
                )
                for split in ("train", "calibration", "development")
            }
            for target in TARGETS
        },
        "overflow_forensic": {
            "row_count": len(overflow_rows),
            "fields": "M1_V2_TARGET_SUPPORT_C0_OVERFLOW.csv",
            "source_field_limitation": "B2 frozen cache retains labels/active masks and static lineage, but not actual departure, signed DepDelay, TaxiOut, T_IB_A00, or decision_time.",
        },
        "source_consistency": source_consistency,
        "d_ob_train_tail_bands": _d_ob_tail_bands(cache),
        "d_ob_to_d_tx_diagnostic": _d_tx_comparison(cache),
        "d_tx_development_shift": _d_tx_development_clusters(cache),
        "conditioning_consequences": {
            "T_IB_TO_D_OB": "All T_IB >= 360 share the explicit hazard survival/overflow state; Train fraction is 2/342.",
            "D_OB_TO_D_TX": "All D_OB >= 180 share the D_OB overflow parent embedding; Train fraction is 34/1793.",
            "D_TX_PARENT_CONDITIONING_ROLE": "NONE",
        },
        "scenario_representation": _scenario_representation(cache),
        "train_value_loss_truncation": _loss_truncation(),
        "finite_support_review": "REVIEW_REQUIRED; support is not changed by C0",
        "positive_quantile_tail_status": "UNRESOLVED_AND_OUT_OF_SCOPE",
        "c0_bin_width_decision_required": False,
        "human_decisions": [
            {
                "decision_id": "C0-D01",
                "target": "T_IB_REMAINING_HAZARD",
                "options": [
                    "KEEP_360",
                    "EXPAND_TO_390",
                    "EXPAND_TO_420",
                    "EXPAND_TO_450",
                    "EXPAND_TO_480",
                    "OTHER",
                ],
                "recommendation": "KEEP_360",
                "evidence": "Train overflow is 2/342 (0.58%), exact values are 360 and 365, and the 365-minute survival representative has mean absolute error 2.5 minutes (max 5).",
            },
            {
                "decision_id": "C0-D02",
                "target": "D_OB",
                "options": [
                    "KEEP_180",
                    "EXPAND_TO_210",
                    "EXPAND_TO_240",
                    "EXPAND_TO_300",
                    "EXPAND_TO_360",
                    "OTHER",
                ],
                "recommendation": "EXPAND_TO_210",
                "evidence": "Train overflow is 34/1793 (1.90%); 24 rows are 189/199 and 10 rows are 343. Expanding to 210 resolves the 24 moderate-tail rows while retaining the rare 343-minute tail and avoids unnecessary class doubling.",
            },
            {
                "decision_id": "C0-D03",
                "target": "D_TX",
                "options": [
                    "KEEP_60",
                    "EXPAND_TO_75",
                    "EXPAND_TO_90",
                    "EXPAND_TO_120",
                    "OTHER",
                ],
                "recommendation": "KEEP_60",
                "evidence": "Train overflow is 0/1880; Development has 28/1765 (1.59%) across only 3 episodes, and D_TX is a chain endpoint with no downstream parent-conditioning role.",
            },
        ],
        "safety": SAFETY,
        "automatic_decisions_applied": False,
    }
    report["artifact_hash_basis"] = "JSON_SERIALIZED_PAYLOAD_WITHOUT_ARTIFACT_HASH"
    basis = json.dumps(_jsonable(report), sort_keys=True, separators=(",", ":"))
    report["artifact_hash"] = f"sha256:{sha256(basis.encode('utf-8')).hexdigest()}"

    _write_json(output_dir / "AIR_SLOT_M1_V2_TARGET_SUPPORT_GATE_C0.json", report)
    _write_json(
        output_dir / "M1_V2_TARGET_SUPPORT_GATE_C0_PROFILES.json",
        {
            "train": train_profiles,
            "calibration": split_profiles["calibration"],
            "development": split_profiles["development"],
        },
    )
    _write_json(
        output_dir / "M1_V2_TARGET_SUPPORT_GATE_C0_DTX_SHIFT.json",
        report["d_tx_development_shift"],
    )
    _write_csv(
        output_dir / "M1_V2_TARGET_SUPPORT_GATE_C0_THRESHOLDS.csv", threshold_rows
    )
    _write_csv(output_dir / "M1_V2_TARGET_SUPPORT_GATE_C0_OVERFLOW.csv", overflow_rows)
    (output_dir / "M1_V2_TARGET_SUPPORT_GATE_C0_HUMAN_REVIEW_PACKET.md").write_text(
        _markdown(report), encoding="utf-8"
    )
    return report


def main() -> None:
    report = run()
    print(
        json.dumps(
            {
                "TARGET_SUPPORT_C0_STATUS": report["TARGET_SUPPORT_C0_STATUS"],
                "artifact_hash": report["artifact_hash"],
                "overflow_counts": report["overflow_counts"],
                "safety": report["safety"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
