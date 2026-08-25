"""Real-data, no-training closure for BTS signed-delay Data Gate A2."""

from __future__ import annotations

import json
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

from model.common.config import load_config_layers
from model.common.identity import content_id
from model.M1.cache import REQUIRED_CONTRACT_HASHES, M1DevelopmentBaseCache, cache_key
from model.M1.data import FEATURE_NAMES_V2, fit_train_normalization
from model.M1.preparation import (
    active_rows,
    build_training_examples,
    fit_static_normalization_from_rows,
    normalization_rows,
)
from model.PRE.development import materialize_preselected_cohorts
from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
from model.PRE.reference.turnaround_data2 import data2_turnaround_reference_from_payload
from model.PRE.streaming.data2 import (
    development_source_manifest_hash,
    episode_reservoirs,
    load_timezones,
    ontime_paths,
)
from validation.data_usage_contract_audit import run as run_data_usage_audit
from validation.m1_v2_data_gate_a1 import _replay_leakage
from validation.m1_v2_data_gate_a2_source import scan_bts_signed_delay_semantics
from validation.m1_v2_data_gate_statistics import SPLITS, label_statistics

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "diagnostics" / "m1_v2_data_gate_a2"
PREPARATION_ROOT = ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"
A1_ROOT = ROOT / "artifacts" / "diagnostics" / "m1_v2_data_gate_a1"
SEMANTIC_TOKEN = "BTS_SIGNED_DELAY_SEMANTIC_CORRECTION"
COHORT_COUNTS = {"train": 128, "calibration": 64, "development": 128, "test": 0}
COHORT_SEED = 20260813


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _heartbeat(phase: str, **values: Any) -> None:
    payload = {
        "phase": phase,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        **values,
    }
    _write_json(OUTPUT / "HEARTBEAT.json", payload)


def _hist_median(histogram: Counter[float]) -> float:
    total = sum(histogram.values())
    if total <= 0:
        raise RuntimeError("DATA_GATE_A2_REFERENCE_EMPTY")

    def at(position: int) -> float:
        cumulative = 0
        for value in sorted(histogram):
            cumulative += histogram[value]
            if cumulative > position:
                return float(value)
        raise AssertionError("reference histogram exhausted")

    left = (total - 1) // 2
    right = total // 2
    return (at(left) + at(right)) / 2.0


class ReferenceCollector:
    def __init__(self) -> None:
        self.taxi_global: Counter[float] = Counter()
        self.taxi_airports: dict[str, Counter[float]] = defaultdict(Counter)
        self.turnaround_global: Counter[float] = Counter()
        self.turnaround_airports: dict[str, Counter[float]] = defaultdict(Counter)

    def observe_flights(self, split: str, rows: list[dict]) -> None:
        if split != "train":
            return
        for row in rows:
            value = row.get("taxi_out_minutes")
            if value is None or float(value) <= 0:
                continue
            minutes = float(value)
            airport = str(row["origin_airport_id"])
            self.taxi_global[minutes] += 1
            self.taxi_airports[airport][minutes] += 1

    def observe_episode(
        self, split: str, episode: object, rows: dict[str, dict]
    ) -> None:
        if split != "train":
            return
        predecessor = rows[episode.predecessor_flight_id]
        successor = rows[episode.successor_flight_id]
        gap = (
            successor["actual_departure_utc"] - predecessor["actual_arrival_utc"]
        ).total_seconds() / 60.0
        airport = str(episode.connection_airport_id)
        self.turnaround_global[gap] += 1
        self.turnaround_airports[airport][gap] += 1


def _reference_payload(
    *,
    template: dict[str, Any],
    global_histogram: Counter[float],
    airport_histograms: dict[str, Counter[float]],
    scope: str,
) -> dict[str, Any]:
    global_value = _hist_median(global_histogram)
    global_count = sum(global_histogram.values())
    cells = []
    for airport in sorted(airport_histograms):
        histogram = airport_histograms[airport]
        count = sum(histogram.values())
        fallback = "AIRPORT_CELL" if count >= 50 else "GLOBAL"
        value = _hist_median(histogram) if fallback == "AIRPORT_CELL" else global_value
        cells.append(
            {
                "airport_id": airport,
                "value_minutes": value,
                "sample_count": count,
                "fallback_level": fallback,
                "provenance": [
                    f"airport={airport}",
                    f"n={count}",
                    f"fallback_level={fallback}",
                    f"{template['rule_id']}@{template['rule_version']}",
                    SEMANTIC_TOKEN,
                ],
            }
        )
    identity_basis = {
        "scope": scope,
        "semantic_token": SEMANTIC_TOKEN,
        "rule_id": template["rule_id"],
        "rule_version": template["rule_version"],
        "global_value_minutes": global_value,
        "global_sample_count": global_count,
        "cells": [
            {
                "airport_id": item["airport_id"],
                "value_minutes": item["value_minutes"],
                "sample_count": item["sample_count"],
                "fallback_level": item["fallback_level"],
            }
            for item in cells
        ],
    }
    payload = {
        **template,
        "schema_version": "DATA_GATE_A2_DIAGNOSTIC_REFERENCE_V1",
        "fit_period": "2019-H1",
        "cells": cells,
        "cells_count": len(cells),
        "global_value_minutes": global_value,
        "global_sample_count": global_count,
        "manifest_freeze_id": content_id({**identity_basis, "kind": "manifest"}),
        "reference_id": content_id({**identity_basis, "kind": "reference"}),
        "semantic_correction": SEMANTIC_TOKEN,
        "final_test_access_count": 0,
    }
    payload.pop("source_hashes", None)
    payload.pop("artifact_hash", None)
    payload["artifact_hash"] = content_id(payload)
    return payload


def _reference_comparison(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    def cells(payload: dict[str, Any]) -> dict[str, tuple[float, int, str]]:
        return {
            item["airport_id"]: (
                float(item["value_minutes"]),
                int(item["sample_count"]),
                item["fallback_level"],
            )
            for item in payload["cells"]
        }

    old_cells, new_cells = cells(old), cells(new)
    changed_airports = sorted(
        airport
        for airport in set(old_cells) | set(new_cells)
        if old_cells.get(airport) != new_cells.get(airport)
    )
    changed = (
        float(old["global_value_minutes"]) != float(new["global_value_minutes"])
        or int(old["global_sample_count"]) != int(new["global_sample_count"])
        or bool(changed_airports)
    )
    return {
        "changed": changed,
        "old_reference_id": old["reference_id"],
        "new_reference_id": new["reference_id"],
        "old_global_value_minutes": old["global_value_minutes"],
        "new_global_value_minutes": new["global_value_minutes"],
        "old_global_sample_count": old["global_sample_count"],
        "new_global_sample_count": new["global_sample_count"],
        "changed_airport_count": len(changed_airports),
        "changed_airport_samples": changed_airports[:20],
    }


def _build_cache(
    examples: dict[str, tuple], normalization, static_normalization, source_hash: str
) -> dict[str, Any]:
    contract_hashes = {
        name: content_id(
            {
                "gate": "A2",
                "contract": name,
                "semantic_token": SEMANTIC_TOKEN,
                "feature_schema": "AIR_SLOT_M1_V2_DATA_GATE_A2_V1",
                "feature_names": list(FEATURE_NAMES_V2),
            }
        )
        for name in REQUIRED_CONTRACT_HASHES
    }
    key = cache_key(
        source_manifest_hash=source_hash,
        contract_hashes=contract_hashes,
        cohort_counts={name: len(examples[name]) for name in SPLITS},
        cohort_seed=COHORT_SEED,
    )
    cache = M1DevelopmentBaseCache.from_partitions(
        partitions=examples,
        normalization=normalization,
        static_normalization=static_normalization,
        audit={
            "final_test_access_count": 0,
            "scope": "DATA_GATE_A2",
            "invalidation_reason": SEMANTIC_TOKEN,
        },
        cache_key=key,
        source_manifest_hash=source_hash,
        contract_hashes=contract_hashes,
    )
    data_path = OUTPUT / "M1_V2_DATA_GATE_A2_CACHE.npz"
    manifest_path = OUTPUT / "M1_V2_DATA_GATE_A2_CACHE_MANIFEST.json"
    saved = cache.save(data_path, manifest_path)
    loaded = M1DevelopmentBaseCache.load(
        data_path, manifest_path, expected_cache_key=key
    )
    equal = (
        torch.equal(cache.store.values_flat, loaded.store.values_flat)
        and cache.store.static_context_lineages == loaded.store.static_context_lineages
        and all(
            torch.equal(cache.store.labels[name], loaded.store.labels[name])
            and torch.equal(cache.store.active[name], loaded.store.active[name])
            for name in cache.store.labels
        )
    )
    return {
        "cache_path": str(data_path.relative_to(ROOT)),
        "manifest_path": str(manifest_path.relative_to(ROOT)),
        "cache_key": key,
        "cache_hash": saved["cache_hash"],
        "cache_roundtrip_equal": equal,
        "manifest": saved,
    }


def _count_delta(old: dict[str, int], new: dict[str, int]) -> dict[str, dict[str, Any]]:
    return {
        split: {
            "old": int(old[split]),
            "new": int(new[split]),
            "delta": int(new[split]) - int(old[split]),
            "changed": int(old[split]) != int(new[split]),
        }
        for split in SPLITS
    }


def _label_comparison(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    return {
        split: {
            target: {
                "changed": old[split][target] != new[split][target],
                "old": old[split][target],
                "new": new[split][target],
            }
            for target in sorted(new[split])
        }
        for split in SPLITS
    }


def run() -> dict[str, Any]:
    started = time.perf_counter()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    _heartbeat("SOURCE_SEMANTICS_START")
    source = scan_bts_signed_delay_semantics(ROOT, heartbeat=_heartbeat)
    _write_json(OUTPUT / "BTS_SIGNED_DELAY_SOURCE_SEMANTICS.json", source)
    if source["gate_status"] == "BTS_SIGNED_DELAY_SOURCE_COLUMN_MISSING":
        result = {
            "schema_version": "AIR_SLOT_M1_V2_DATA_GATE_A2_V1",
            "repository_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "source_semantics": source,
            "DATA_GATE_STATUS": "DATA_GATE_A2_SOURCE_COLUMN_BLOCKED",
            "M1_TRAINING_RUNS": 0,
            "TUNING_RUNS": 0,
            "FINAL_TEST_ACCESS_COUNT": 0,
            "GATE_B_ENTERED": False,
            "PAPER_FULL_RUN": False,
        }
        _write_json(OUTPUT / "AIR_SLOT_M1_V2_DATA_GATE_A2.json", result)
        return result

    _heartbeat("DATA_USAGE_AUDIT_START")
    audit = run_data_usage_audit(
        ROOT / "artifacts" / "diagnostics" / "data_usage_contract_audit"
    )
    old_a1 = json.loads(
        (A1_ROOT / "AIR_SLOT_M1_V2_DATA_GATE_A1.json").read_text(encoding="utf-8")
    )
    old_cache = json.loads(
        (A1_ROOT / "M1_V2_DATA_GATE_A1_CACHE_MANIFEST.json").read_text(encoding="utf-8")
    )
    old_progress = json.loads(
        (PREPARATION_ROOT / "M1_BASE_CACHE_PREPARATION_PROGRESS.json").read_text(
            encoding="utf-8"
        )
    )
    old_taxi = json.loads(
        (PREPARATION_ROOT / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json").read_text(
            encoding="utf-8"
        )
    )
    old_turnaround = json.loads(
        (
            PREPARATION_ROOT / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json"
        ).read_text(encoding="utf-8")
    )

    _heartbeat("EPISODE_POOL_REBUILD_START")
    paths = ontime_paths(ROOT, range(1, 10))
    zones = load_timezones(ROOT / "data2" / "refs" / "us_airport_timezones.csv")
    collector = ReferenceCollector()
    reservoirs, pool_sizes, total_episodes, per_month, skipped = episode_reservoirs(
        ROOT,
        paths,
        zones,
        cohort_counts=COHORT_COUNTS,
        cohort_seed=COHORT_SEED,
        state_path=OUTPUT / "M1_V2_DATA_GATE_A2_PREPARATION_STATE.pt",
        manifest_path=OUTPUT / "M1_V2_DATA_GATE_A2_PREPARATION_PROGRESS.json",
        resume=False,
        heartbeat=_heartbeat,
        semantic_token=SEMANTIC_TOKEN,
        include_warning_fields=True,
        flight_observer=collector.observe_flights,
        episode_observer=collector.observe_episode,
    )
    if reservoirs["test"]:
        raise RuntimeError("FINAL_TEST_EPISODE_MATERIALIZED")
    partitions = {
        split: tuple(sorted(reservoirs[split], key=lambda item: item.episode_id))
        for split in SPLITS
    }

    new_taxi = _reference_payload(
        template=old_taxi,
        global_histogram=collector.taxi_global,
        airport_histograms=collector.taxi_airports,
        scope="TAXI_OUT_TRAIN_ROWS",
    )
    new_turnaround = _reference_payload(
        template=old_turnaround,
        global_histogram=collector.turnaround_global,
        airport_histograms=collector.turnaround_airports,
        scope="TURNAROUND_TRAIN_EPISODES",
    )
    _write_json(OUTPUT / "DATA2_TAXI_REFERENCE_GATE_A2_DIAGNOSTIC.json", new_taxi)
    _write_json(
        OUTPUT / "DATA2_TURNAROUND_REFERENCE_GATE_A2_DIAGNOSTIC.json",
        new_turnaround,
    )
    taxi_reference = data2_taxi_reference_from_payload(new_taxi)
    turnaround_reference = data2_turnaround_reference_from_payload(new_turnaround)

    scientific = load_config_layers(ROOT / "configs").scientific
    if (
        scientific.parameters["data2_factual_replay_availability"].value
        != "DECLARED_EVENT_TIME_REPLAY"
    ):
        raise RuntimeError("DATA_GATE_A2_EXPECTED_DECLARED_EVENT_TIME_REPLAY")
    selection_audit = {
        "selection_schema": "M1_V2_DATA_GATE_A2_PREPARATION_V1",
        "source_manifest_hash": development_source_manifest_hash(ROOT),
        "cohort_counts": {split: len(partitions[split]) for split in SPLITS},
        "pool_sizes": pool_sizes,
        "total_episode_pool": total_episodes,
        "ontime_rows_by_month": per_month,
        "ontime_rows_skipped": skipped,
        "semantic_token": SEMANTIC_TOKEN,
        "final_test_access_count": 0,
    }
    _heartbeat("PRE_MATERIALIZATION_START")
    cohorts = materialize_preselected_cohorts(
        scientific,
        root=ROOT,
        partitions=partitions,
        selection_audit=selection_audit,
        heartbeat=_heartbeat,
        taxi_reference=taxi_reference,
        turnaround_reference=turnaround_reference,
    )
    rows, examples = {}, {}
    for split in SPLITS:
        rows[split], _ = active_rows(
            getattr(cohorts, split), taxi_reference=taxi_reference
        )
    normalization = fit_train_normalization(
        normalization_rows([prefix for _, prefix, _ in rows["train"]]),
        split="train",
    )
    static_normalization = fit_static_normalization_from_rows(rows["train"])
    for split in SPLITS:
        examples[split] = build_training_examples(
            rows[split],
            normalization,
            None,
            static_normalization=static_normalization,
        )
    cache = _build_cache(
        examples,
        normalization,
        static_normalization,
        selection_audit["source_manifest_hash"],
    )
    new_labels = label_statistics(rows)
    replay = _replay_leakage(cohorts)
    episode_comparison = _count_delta(old_progress["pool_sizes"], pool_sizes)
    node_comparison = _count_delta(
        old_a1["selection_audit"]["pre_decision_nodes"],
        cohorts.audit["pre_decision_nodes"],
    )
    labels_comparison = _label_comparison(old_a1["labels"], new_labels)
    references = {
        "taxi": _reference_comparison(old_taxi, new_taxi),
        "turnaround": _reference_comparison(old_turnaround, new_turnaround),
    }
    cache_invalidation = {
        "old_cache_hash": old_cache["cache_hash"],
        "new_cache_hash": cache["cache_hash"],
        "old_cache_key": old_cache["cache_key"],
        "new_cache_key": cache["cache_key"],
        "content_hash_changed": old_cache["cache_hash"] != cache["cache_hash"],
        "semantic_identity_changed": old_cache["cache_key"] != cache["cache_key"],
        "invalidation_reason": SEMANTIC_TOKEN,
    }
    failure_counts = {
        key: audit["counts"][key]
        for key in (
            "PRE_BYPASS",
            "RUNTIME_USED_NO_CONTRACT",
            "AMBIGUOUS_ACTIVE_COLUMN",
            "ACTIVE_SEMANTIC_CONFLICT",
            "ACTIVE_REGISTRY_CONFLICT",
            "ACTIVE_PRE_OUTPUT_CONFLICT",
        )
    }
    contract_failure = (
        audit["status"] != "DATA_USAGE_CONTRACT_AUDIT_PASS"
        or not cache["cache_roundtrip_equal"]
        or not cache_invalidation["semantic_identity_changed"]
        or any(item["status"] != "PASS" for item in replay.values())
    )
    if contract_failure:
        status = "CONTRACT_FAILURE"
    elif source["gate_status"] == "PASS_STRONG":
        status = "DATA_GATE_A2_PASS_READY_FOR_GATE_B"
    else:
        status = "DATA_GATE_A2_SOURCE_ROUNDING_REVIEW"

    result = {
        "schema_version": "AIR_SLOT_M1_V2_DATA_GATE_A2_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "scope": "TRAIN_CALIBRATION_DEVELOPMENT_ONLY",
        "source_semantics": source,
        "canonical_rule": {
            "departure": "DIRECT_CLOCK_WITH_SIGNED_DELAY_DATE_DISAMBIGUATION",
            "arrival": "DIRECT_CLOCK_WITH_SIGNED_DELAY_DATE_DISAMBIGUATION",
            "multi_day": "SCHEDULE_PLUS_SIGNED_DELAY_NATURAL_DATE_RESTORATION",
            "wheels_off": "DIRECT_WHEELSOFF_THEN_ACTUAL_DEPARTURE_PLUS_TAXIOUT",
            "wheels_on": "DIRECT_WHEELSON_THEN_ACTUAL_ARRIVAL_MINUS_TAXIIN",
            "delay_minutes": "NONNEGATIVE_DELAY_REPORTING_ONLY",
        },
        "downstream": {
            "episodes": episode_comparison,
            "nodes": node_comparison,
            "labels": labels_comparison,
            "references": references,
            "sampled_episode_counts": {
                split: len(partitions[split]) for split in SPLITS
            },
            "active_example_counts": {split: len(examples[split]) for split in SPLITS},
        },
        "factual_replay": {
            "policy": "DECLARED_EVENT_TIME_REPLAY",
            "declared_lag_minutes": 0,
            "leakage": replay,
        },
        "data_usage": {
            "status": audit["status"],
            "artifact_hash": audit["artifact_hash"],
            "failure_counts": failure_counts,
        },
        "cache": cache_invalidation,
        "cache_artifact": {
            key: value for key, value in cache.items() if key != "manifest"
        },
        "selection_audit": cohorts.audit,
        "DATA_GATE_STATUS": status,
        "M1_TRAINING_RUNS": 0,
        "TUNING_RUNS": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "GATE_B_ENTERED": False,
        "PAPER_FULL_RUN": False,
        "runtime_seconds": time.perf_counter() - started,
        "artifact_hash_basis": "JSON_SERIALIZED_PAYLOAD_WITHOUT_ARTIFACT_HASH",
    }
    result["artifact_hash"] = content_id(result)
    _write_json(OUTPUT / "AIR_SLOT_M1_V2_DATA_GATE_A2.json", result)
    _heartbeat("DATA_GATE_A2_COMPLETE", status=status)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True, default=str))
