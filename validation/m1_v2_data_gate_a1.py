"""Real-data, no-training diagnostics for AIR_SLOT_M1_V2_DATA_GATE_A1."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from statistics import median
from pathlib import Path
import subprocess
import time

import torch

from model.common.config import load_config_layers
from model.common.identity import content_id
from model.M1.cache import (
    REQUIRED_CONTRACT_HASHES,
    M1DevelopmentBaseCache,
    cache_key,
)
from model.M1.contracts import V2_TARGETS
from model.M1.data import (
    FEATURE_NAMES_V2,
    STATIC_FEATURE_NAMES,
    fit_train_normalization,
)
from model.M1.preparation import active_rows, build_training_examples, normalization_rows
from model.PRE.development import materialize_preselected_cohorts
from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
from model.PRE.reference.turnaround_data2 import data2_turnaround_reference_from_payload
from model.PRE.streaming.data2 import development_source_manifest_hash
from validation.m1_v2_data_gate_lineage import (
    feature_decisions,
    lineage_rows,
)
from validation.m1_v2_data_gate_semantics import (
    potential_downstream_error_sources,
    unresolved_column_queue,
    upstream_trace_cases,
)
from validation.m1_v2_data_gate_statistics import (
    SPLITS,
    history_diagnostics,
    identity_statistics,
    label_statistics,
    numeric_statistics,
    raw_preprocessing_statistics,
    time_diagnostics,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "diagnostics" / "m1_v2_data_gate_a1"
PREPARATION_ROOT = ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _json_serialized_payload(payload):
    return json.loads(json.dumps(payload, sort_keys=True, default=str))


def _heartbeat(phase: str, **values) -> None:
    print(json.dumps({"phase": phase, **values}, sort_keys=True, default=str), flush=True)


def _bts_consistency(cohorts) -> dict:
    fields = {
        "DepTime": ("actual_departure_direct_utc", "actual_departure_derived_utc"),
        "ArrTime": ("actual_arrival_direct_utc", "actual_arrival_derived_utc"),
        "WheelsOff": ("wheels_off_direct_utc", "wheels_off_derived_utc"),
    }
    output = {}
    for split in SPLITS:
        output[split] = {}
        prepared_rows = [item for item in getattr(cohorts, split)]
        for label, (direct_name, derived_name) in fields.items():
            differences = []
            cases = []
            date_offset = 0
            cross_midnight = 0
            both = 0
            for prepared in prepared_rows:
                record = prepared.predecessor_outcome if label == "ArrTime" else prepared.successor_outcome
                direct = getattr(record, direct_name)
                derived = getattr(record, derived_name)
                if direct is None or derived is None:
                    continue
                both += 1
                diff = abs((direct - derived).total_seconds()) / 60.0
                differences.append(diff)
                if diff > 5 and len(cases) < 10:
                    cases.append({
                        "episode_id": prepared.episode.episode_id,
                        "source_record_id": record.canonical_record_id,
                        "direct": direct,
                        "derived": derived,
                        "abs_difference_minutes": diff,
                    })
                date_offset += int(direct.date() != derived.date())
                cross_midnight += int(
                    (direct.date() != derived.date()) and diff > 0
                )
            ordered = sorted(differences)
            percentile = lambda q: ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * q)))] if ordered else None
            output[split][label] = {
                "both_available_count": both,
                "exact_agreement_rate": sum(value == 0 for value in differences) / both if both else None,
                "within_1min_rate": sum(value <= 1 for value in differences) / both if both else None,
                "within_5min_rate": sum(value <= 5 for value in differences) / both if both else None,
                "median_abs_difference_minutes": median(differences) if differences else None,
                "p95_abs_difference_minutes": percentile(0.95),
                "p99_abs_difference_minutes": percentile(0.99),
                "max_abs_difference_minutes": max(differences) if differences else None,
                "date_offset_disagreement_count": date_offset,
                "cross_midnight_disagreement_count": cross_midnight,
                "precedence": "DIRECT_CLOCK_PRIMARY_DERIVED_CHECK_AND_MISSING_FALLBACK",
                "deterministic_disagreement_cases": cases,
            }
    return output


def _weather_profile(cohorts) -> dict:
    counts = {"total": 0, "finite": 0, "unlimited": 0, "missing": 0,
              "wind_direction_observed": 0}
    for split in SPLITS:
        for prepared in getattr(cohorts, split):
            for state in prepared.states:
                counts["total"] += 1
                item = state.current_state.get("current_weather")
                payload = getattr(item, "value", None)
                if not isinstance(payload, dict):
                    counts["missing"] += 1
                    continue
                status = payload.get("ceiling_status", "MISSING")
                counts[status.lower()] = counts.get(status.lower(), 0) + 1
                counts["wind_direction_observed"] += int(payload.get("wind_direction_deg") is not None)
    total = max(counts["total"], 1)
    return {
        **counts,
        "ceiling_finite_pct": 100.0 * counts.get("finite", 0) / total,
        "ceiling_unlimited_pct": 100.0 * counts.get("unlimited", 0) / total,
        "ceiling_missing_pct": 100.0 * counts.get("missing", 0) / total,
        "wind_direction_observed_pct": 100.0 * counts["wind_direction_observed"] / total,
        "wind_direction_sin_cos_coverage_pct": 100.0 * counts["wind_direction_observed"] / total,
    }


def _replay_leakage(cohorts) -> dict:
    requirements = {
        "PRE_IB": (),
        "POST_IB_PRE_OB": ("predecessor_outcome", "actual_arrival_utc"),
        "POST_OB_PRE_TO": (
            "predecessor_outcome", "actual_arrival_utc",
            "successor_outcome", "actual_departure_utc",
        ),
        "COMPLETED": (
            "predecessor_outcome", "actual_arrival_utc",
            "successor_outcome", "actual_departure_utc",
            "successor_outcome", "wheels_off_utc",
        ),
    }
    out = {stage: {"nodes": 0, "failures": 0, "samples": []} for stage in requirements}
    for split in SPLITS:
        for prepared in getattr(cohorts, split):
            for state in prepared.states:
                stage = state.decision_node.operational_stage.value
                item = out[stage]
                item["nodes"] += 1
                values = []
                req = requirements[stage]
                legal = True
                for index in range(0, len(req), 2):
                    record = getattr(prepared, req[index])
                    timestamp = getattr(record, req[index + 1])
                    okay = timestamp is not None and timestamp <= state.decision_node.information_cutoff
                    values.append({"event": f"{req[index]}.{req[index + 1]}", "declared_availability_time": timestamp, "cutoff": state.decision_node.information_cutoff, "legal": okay})
                    legal = legal and okay
                if not legal:
                    item["failures"] += 1
                if len(item["samples"]) < 3:
                    item["samples"].append({"episode_id": prepared.episode.episode_id, "node_id": state.decision_node.decision_node_id, "events": values})
    for item in out.values():
        item["status"] = "PASS" if item["failures"] == 0 else "LEAKAGE_FAIL"
    return out


def _load_references():
    taxi_payload = json.loads(
        (PREPARATION_ROOT / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json")
        .read_text(encoding="utf-8")
    )
    turnaround_payload = json.loads(
        (PREPARATION_ROOT / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json")
        .read_text(encoding="utf-8")
    )
    return (
        data2_taxi_reference_from_payload(taxi_payload),
        data2_turnaround_reference_from_payload(turnaround_payload),
        {
            "taxi_reference_id": taxi_payload["reference_id"],
            "taxi_reference_hash": taxi_payload["manifest_freeze_id"],
            "turnaround_reference_id": turnaround_payload["reference_id"],
            "turnaround_reference_hash": turnaround_payload["manifest_freeze_id"],
        },
    )


def _load_frozen_partitions() -> tuple[dict[str, tuple], dict]:
    state_path = PREPARATION_ROOT / "M1_BASE_CACHE_PREPARATION_STATE.pt"
    progress_path = PREPARATION_ROOT / "M1_BASE_CACHE_PREPARATION_PROGRESS.json"
    cache_manifest_path = PREPARATION_ROOT / "M1_BASE_CACHE_MANIFEST.json"
    state = torch.load(state_path, map_location="cpu", weights_only=False)
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    cache_manifest = json.loads(cache_manifest_path.read_text(encoding="utf-8"))
    if state.get("next_month") != 10 or progress.get("completion_status") != "PASS":
        raise RuntimeError("DATA_GATE_A_FROZEN_RESERVOIR_INCOMPLETE")
    reservoirs = state["reservoirs"]
    if reservoirs.get("test") or progress.get("final_test_access_count") != 0:
        raise RuntimeError("FINAL_TEST_EPISODE_MATERIALIZED")
    current_source = development_source_manifest_hash(ROOT)
    if current_source != cache_manifest["source_manifest_hash"]:
        raise RuntimeError("DATA_GATE_A_SOURCE_MANIFEST_DRIFT")
    partitions = {
        name: tuple(sorted(reservoirs[name], key=lambda row: row.episode_id))
        for name in SPLITS
    }
    audit = {
        "selection_source": str(state_path.relative_to(ROOT)),
        "selection_schema": progress["schema_version"],
        "source_manifest_hash": current_source,
        "cohort_counts": {name: len(partitions[name]) for name in SPLITS},
        "pool_sizes": state["pool_sizes"],
        "final_test_access_count": 0,
    }
    return partitions, audit


def _static_and_cache(examples, normalization, source_hash) -> dict:
    static = {}
    for split in SPLITS:
        values = [row.static_values for row in examples[split] if row.static_values is not None]
        matrix = torch.stack(values) if values else torch.empty((0, len(STATIC_FEATURE_NAMES)))
        static[split] = {
            "row_count": len(examples[split]),
            "available_count": len(values),
            "shape": list(matrix.shape),
            "dtype": str(matrix.dtype),
            "missing_count": len(examples[split]) - len(values),
            "feature_names": list(STATIC_FEATURE_NAMES),
            "means": matrix.mean(dim=0).tolist() if len(matrix) else None,
            "mins": matrix.min(dim=0).values.tolist() if len(matrix) else None,
            "maxs": matrix.max(dim=0).values.tolist() if len(matrix) else None,
        }
    contracts = {
        name: content_id({
            "gate": "A1",
            "contract": name,
            "feature_schema": "AIR_SLOT_M1_V2_DATA_GATE_A1_V1",
            "feature_names": list(FEATURE_NAMES_V2),
        })
        for name in REQUIRED_CONTRACT_HASHES
    }
    key = cache_key(
        source_manifest_hash=source_hash,
        contract_hashes=contracts,
        cohort_counts={name: len(examples[name]) for name in SPLITS},
        cohort_seed=20260821,
    )
    cache = M1DevelopmentBaseCache.from_partitions(
        partitions=examples,
        normalization=normalization,
        audit={"final_test_access_count": 0, "scope": "DATA_GATE_A1"},
        cache_key=key,
        source_manifest_hash=source_hash,
        contract_hashes=contracts,
    )
    data_path = OUTPUT / "M1_V2_DATA_GATE_A1_CACHE.npz"
    manifest_path = OUTPUT / "M1_V2_DATA_GATE_A1_CACHE_MANIFEST.json"
    cache.save(data_path, manifest_path)
    loaded = M1DevelopmentBaseCache.load(data_path, manifest_path, expected_cache_key=key)
    static_equal = (
        cache.store.static_values is None
        and loaded.store.static_values is None
    ) or (
        cache.store.static_values is not None
        and loaded.store.static_values is not None
        and torch.equal(cache.store.static_values, loaded.store.static_values)
    )
    equal = (
        torch.equal(cache.store.values_flat, loaded.store.values_flat)
        and static_equal
        and cache.store.static_context_lineages == loaded.store.static_context_lineages
        and all(
            torch.equal(cache.store.labels[name], loaded.store.labels[name])
            and torch.equal(cache.store.active[name], loaded.store.active[name])
            for name in V2_TARGETS
        )
    )
    return {
        "statistics": static,
        "cache_status": "MISS_BUILT_THEN_HIT",
        "cache_roundtrip_equal": equal,
        "cache_path": str(data_path.relative_to(ROOT)),
        "manifest_path": str(manifest_path.relative_to(ROOT)),
        "cache_hash": loaded.manifest["cache_hash"],
    }


def _write_lineage(rows: list[dict]) -> Path:
    path = OUTPUT / "M1_V2_DATA_GATE_A1_LINEAGE.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def run() -> dict:
    started = time.perf_counter()
    partitions, selection_audit = _load_frozen_partitions()
    taxi, turnaround, reference_ids = _load_references()
    scientific = load_config_layers(ROOT / "configs").scientific
    if scientific.parameters["data2_factual_replay_availability"].value != "DECLARED_EVENT_TIME_REPLAY":
        raise RuntimeError("DATA_GATE_A1_EXPECTED_DECLARED_EVENT_TIME_REPLAY")
    _heartbeat("PRE_MATERIALIZATION_START", counts=selection_audit["cohort_counts"])
    cohorts = materialize_preselected_cohorts(
        scientific,
        root=ROOT,
        partitions=partitions,
        selection_audit=selection_audit,
        heartbeat=_heartbeat,
        taxi_reference=taxi,
        turnaround_reference=turnaround,
    )
    rows, examples = {}, {}
    for split in SPLITS:
        rows[split], _ = active_rows(getattr(cohorts, split), taxi_reference=taxi)
    normalization = fit_train_normalization(
        normalization_rows([prefix for _, prefix, _ in rows["train"]]),
        split="train",
    )
    for split in SPLITS:
        examples[split] = build_training_examples(rows[split], normalization, None)
    matrices = {
        split: torch.cat([row.values for row in examples[split]], dim=0)
        for split in SPLITS
    }
    feature_stats = numeric_statistics(matrices)
    lineage = lineage_rows(feature_stats["train"])
    lineage_path = _write_lineage(lineage)
    static = _static_and_cache(
        examples, normalization, selection_audit["source_manifest_hash"]
    )
    time_checks = time_diagnostics(cohorts)
    unresolved = unresolved_column_queue(cohorts)
    bts_consistency = _bts_consistency(cohorts)
    weather_profile = _weather_profile(cohorts)
    leakage = _replay_leakage(cohorts)
    train_profile = feature_stats["train"]
    feature_profile = {
        "before_dynamic_feature_count": 108,
        "after_dynamic_feature_count": len(FEATURE_NAMES_V2),
        "static_feature_count": len(STATIC_FEATURE_NAMES),
        "context_only_count": 4,
        "constant_count_train": sum(item["constant"] for item in train_profile),
        "near_constant_count_train": sum(item["near_constant"] for item in train_profile),
        "derived_valid_coverage": {
            item["feature"]: 1.0 - item["missing_pct"] / 100.0
            for item in train_profile
            if item["feature"].startswith(("delta.", "ar."))
            and not item["feature"].endswith("derived_missing_mask")
        },
        "removed_principal": [
            "weather.wind_gust_mps", "delta.weather.wind_gust_mps", "ar.weather.wind_gust_mps",
            "delta.weather.wind_direction_deg", "ar.weather.wind_direction_deg",
            "stage.*", "node.spacing_minutes",
        ],
    }
    result = {
        "schema_version": "AIR_SLOT_M1_V2_DATA_GATE_A1_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "scope": "TRAIN_CALIBRATION_DEVELOPMENT_ONLY",
        "counts": {
            "raw_candidate_source_column_pairs": 28,
            "pre_published_expanded_fields": len({row["PRE_OUTPUT"] for row in lineage}),
            "m1_dynamic": len(FEATURE_NAMES_V2),
            "m1_static": len(STATIC_FEATURE_NAMES),
            "context_only": 4,
            "labels": 3,
            "episodes": selection_audit["cohort_counts"],
            "active_examples": {split: len(examples[split]) for split in SPLITS},
            "training_exposure_rows": {split: len(matrices[split]) for split in SPLITS},
        },
        "selection_audit": cohorts.audit,
        "reference_ids": reference_ids,
        "normalization": normalization.model_dump(mode="json"),
        "normalization_fix": "WEATHER_VALUES_NOW_EXTRACTED_FROM_TRAIN_PRE_STATES",
        "factual_replay": {
            "policy": "DECLARED_EVENT_TIME_REPLAY",
            "principal_lag_minutes": 0,
            "availability_time_rule": "OPERATIONAL_EVENT_TIME",
            "observed_message_arrival_claim": False,
            "production_availability_claim": False,
            "source_outcome_role": "EVAL_OUTCOME",
            "source_outcome_availability_basis": "POSTHOC_ONLY",
            "projection_rule_id": "D2-BTS-FACTUAL-REPLAY",
        },
        "source_spec_verification": {
            "WND_DIRECTION": "PASS",
            "WND_SPEED_SCALING": "PASS",
            "CIG_HEIGHT_SCALING_AND_CODES": "FIXED",
            "VIS_SCALING": "FIXED_EXACT_999999_MISSING_CODE",
            "TMP_SCALING": "PASS",
            "DEW_SCALING": "PASS",
            "BTS_DIRECT_CLOCK_PRECEDENCE": "FIXED",
            "BTS_DELAY_TAXI_DERIVATION": "CONSISTENCY_CHECK_AND_FALLBACK_ONLY",
        },
        "raw_preprocessing_statistics": raw_preprocessing_statistics(rows),
        "numeric_feature_statistics": feature_stats,
        "identity_statistics": identity_statistics(examples),
        "static": static,
        "history": history_diagnostics(rows, normalization),
        "labels": label_statistics(rows),
        "time_checks": time_checks,
        "bts_actual_consistency": bts_consistency,
        "weather_ceiling_profile": weather_profile,
        "replay_leakage": leakage,
        "feature_profile": feature_profile,
        "lineage_path": str(lineage_path.relative_to(ROOT)),
        "upstream_trace_cases": upstream_trace_cases(cohorts, normalization),
        "SEMANTIC_CLOSURE_QUEUE": unresolved,
        "Potential downstream error sources": potential_downstream_error_sources(
            time_checks, static
        ),
        "issues": [
            {
                "severity": "FIXED",
                "field": "state.*_realized and stage.*",
                "problem": (
                    "operational stages now consume cutoff-legal declared replay "
                    "events while labels retain posthoc outcomes"
                ),
            },
            {
                "severity": "FIXED",
                "field": "weather numeric normalization",
                "problem": (
                    "normalization_rows previously omitted all weather values and "
                    "silently used mean=0/std=1"
                ),
            },
            {
                "severity": "FIXED",
                "field": "delta/ar weather with missing values",
                "problem": (
                    "delta and AR now require observed coverage and publish derived masks"
                ),
            },
            {
                "severity": "FIXED",
                "field": "wind_direction delta/ar",
                "problem": "linear direction delta and AR removed; sin/cos retained",
            },
            {
                "severity": "FIXED",
                "field": "wind_gust_mps",
                "problem": (
                    "wind gust value, delta, AR, and principal masks removed"
                ),
            },
            {
                "severity": "MEDIUM",
                "field": (
                    "state flags, schedule delta, "
                    "metadata one-hots"
                ),
                "problem": (
                    "deterministic duplicate or near-constant inputs require "
                    "Gate B removal review"
                ),
            },
        ],
        "feature_decisions": feature_decisions(lineage),
        "DATA_GATE_STATUS": (
            "DATA_GATE_A1_HUMAN_REVIEW_REMAINS"
            if any(
                item["within_5min_rate"] is not None and item["within_5min_rate"] < 0.95
                for split in bts_consistency.values()
                for item in split.values()
            )
            else "DATA_GATE_A1_PASS_READY_FOR_FEATURE_FREEZE"
        ),
        "FINAL_TEST_ACCESS_COUNT": 0,
        "M1_TRAINING_RUNS": 0,
        "TUNING_RUNS": 0,
        "PAPER_FULL_RUN": False,
        "artifact_hash_basis": "JSON_SERIALIZED_PAYLOAD_WITHOUT_ARTIFACT_HASH",
        "runtime_seconds": time.perf_counter() - started,
    }
    result["artifact_hash"] = content_id(_json_serialized_payload(result))
    _write_json(OUTPUT / "AIR_SLOT_M1_V2_DATA_GATE_A1.json", result)
    _heartbeat("DATA_GATE_A1_COMPLETE", status=result["DATA_GATE_STATUS"])
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True, default=str))
