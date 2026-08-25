"""Materialize the frozen Data2 Development cohort for Exp2--Exp4.

The selected 128 Development episodes come from the frozen M1 cache
preparation state.  PRE states are republished under the current approved
information policy; M1 is loaded but never trained or tuned.  Labels are
carried in a separate post-outcome artifact and never enter inference inputs.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import torch
import yaml

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.contracts import static_reference_context_from_pre
from model.M1.data import FEATURE_NAMES_V2, encode_pre_sequence
from model.M1.coverage import active_node_prefixes
from model.M1.pipeline import M1Pipeline
from model.M1.static_features import static_reference_features_from_pre
from model.PRE.development import build_sampled_pre_cohorts
from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
from model.PRE.reference.turnaround_data2 import data2_turnaround_reference_from_payload
from model.common.config import load_config_layers
from model.common.identity import content_id


DEFAULT_OUTPUT = Path("artifacts/experiment/full_development_inputs_v1")
CACHE = Path("artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz")
CACHE_MANIFEST = CACHE.with_name("M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json")
CHECKPOINT = Path("artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt")
BINDING = Path("artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json")
PREPARATION_STATE = Path("artifacts/diagnostics/v5_development_freeze/M1_BASE_CACHE_PREPARATION_STATE.pt")
PREPARATION_MANIFEST = PREPARATION_STATE.with_name("M1_BASE_CACHE_PREPARATION_PROGRESS.json")
REFERENCE_ROOT = Path("artifacts/diagnostics/v5_development_freeze")
CONFIG = Path("configs/experiment/m1_data2_development_fast.yaml")

SAFETY = {
    "M1_TRAINING_RUNS": 0,
    "TUNING_RUNS": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _write(path: Path, payload: dict[str, Any]) -> None:
    def default(value: Any):
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        raise TypeError(type(value).__name__)

    rendered = json.dumps(payload, indent=2, sort_keys=True, default=default) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _load_cache(root: Path) -> M1DevelopmentBaseCache:
    manifest = _load(root / CACHE_MANIFEST)
    return M1DevelopmentBaseCache.load(
        root / CACHE,
        root / CACHE_MANIFEST,
        expected_cache_key=manifest["cache_key"],
    )


def _references(root: Path):
    taxi_payload = _load(root / REFERENCE_ROOT / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json")
    turnaround_payload = _load(root / REFERENCE_ROOT / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json")
    return (
        data2_taxi_reference_from_payload(taxi_payload),
        data2_turnaround_reference_from_payload(turnaround_payload),
    )




def _taxi_reference_for(prepared, taxi_reference):
    """A2-same per-airport taxi lookup (label-construction role only)."""
    reference_minutes, reference_id, reference_hash = None, None, None
    if taxi_reference is not None:
        lookup = taxi_reference.lookup(prepared.episode.connection_airport_id)
        value = getattr(lookup, "value", None)
        support = getattr(getattr(lookup, "support_state", None), "value", None)
        if value is not None and support == "SUPPORTED":
            reference_minutes = float(value)
            reference_id = getattr(taxi_reference, "reference_id", None)
            reference_hash = getattr(taxi_reference, "manifest_freeze_id", None)
    return reference_minutes, reference_id, reference_hash

def _json_safe(value):
    """Recursively convert non-JSON values (tz-aware datetimes) to the same
    ISO-8601 strings ``_write`` persists, so the recorded artifact hash can be
    recomputed from the written file."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value

def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = root.resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    required = (
        root / CACHE, root / CACHE_MANIFEST, root / CHECKPOINT, root / BINDING,
        root / PREPARATION_STATE, root / PREPARATION_MANIFEST, root / CONFIG,
    )
    _require(all(path.is_file() for path in required), "FULL_DEVELOPMENT_INPUT_MISSING")

    cache = _load_cache(root)
    cache_manifest = cache.manifest
    binding = _load(root / BINDING)
    config = yaml.safe_load((root / CONFIG).read_text(encoding="utf-8"))
    _require(binding["model_id"] == "M1_V2_GRU_H32", "FULL_DEVELOPMENT_MODEL_NOT_FROZEN_H32")
    _require(binding["checkpoint"]["sha256"] == _sha(root / CHECKPOINT), "FULL_DEVELOPMENT_CHECKPOINT_HASH_MISMATCH")
    _require(binding["frozen_contracts"]["cache_hash"] == cache_manifest["cache_hash"], "FULL_DEVELOPMENT_CACHE_HASH_MISMATCH")
    _require(binding["frozen_contracts"]["feature_schema_hash"] == cache_manifest["feature_schema_hash"], "FULL_DEVELOPMENT_SCHEMA_HASH_MISMATCH")
    _require(cache_manifest["final_test_access_count"] == 0 and not cache_manifest["final_test_included"], "FULL_DEVELOPMENT_FINAL_TEST_CACHE_FORBIDDEN")

    counts = {key: int(value) for key, value in config["base_cohort"]["episode_counts"].items()}
    _require(counts == {"train": 128, "calibration": 64, "development": 128, "test": 0}, "FULL_DEVELOPMENT_COHORT_COUNTS_DRIFT")
    taxi, turnaround = _references(root)
    cohorts = build_sampled_pre_cohorts(
        load_config_layers(root / "configs").scientific,
        root=root,
        cohort_counts=counts,
        cohort_seed=int(config["base_cohort"]["seed"]),
        preparation_state=root / PREPARATION_STATE,
        preparation_manifest=root / PREPARATION_MANIFEST,
        resume=True,
        taxi_reference=taxi,
        turnaround_reference=turnaround,
    )
    development = tuple(cohorts.development)
    cached = cache.partition("development", representation="ADAPTIVE_HISTORY")
    cached_by_episode: dict[str, list[Any]] = defaultdict(list)
    for example in cached:
        cached_by_episode[example.episode_id].append(example)
    for values in cached_by_episode.values():
        values.sort(key=lambda item: len(item.values))
    _require({item.episode.episode_id for item in development} == set(cached_by_episode), "FULL_DEVELOPMENT_EPISODE_ID_DRIFT")

    pipeline = M1Pipeline.load(root / CHECKPOINT)
    pipeline.model.eval()
    inputs: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    states_by_episode: dict[str, list[dict[str, Any]]] = {}
    decision_nodes: list[dict[str, Any]] = []
    stage_counts: Counter[str] = Counter()
    old_to_current: list[dict[str, Any]] = []

    active_total = 0
    for prepared in development:
        episode_id = prepared.episode.episode_id
        cached_rows = cached_by_episode[episode_id]
        reference_minutes, reference_id, reference_hash = _taxi_reference_for(prepared, taxi)
        active_items = tuple(active_node_prefixes(
            episode=prepared.episode,
            nodes=prepared.nodes,
            states=tuple(prepared.states),
            successor_schedule=prepared.successor_schedule,
            predecessor_outcome=prepared.predecessor_outcome,
            successor_outcome=prepared.successor_outcome,
            taxi_reference_minutes=reference_minutes,
            taxi_reference_id=reference_id,
            taxi_reference_hash=reference_hash,
        ))
        _require(
            len(active_items) == len(cached_rows),
            "FULL_DEVELOPMENT_EPISODE_ACTIVE_NODE_COUNT_DRIFT",
        )
        active_total += len(active_items)
        episode_states: list[dict[str, Any]] = []
        for (yielded_node, prefix, target_labels), old in zip(active_items, cached_rows, strict=True):
            node = prefix[-1].decision_node
            _require(
                yielded_node.node_index == node.node_index,
                "FULL_DEVELOPMENT_NODE_INDEX_MISMATCH",
            )
            _require(
                yielded_node.decision_time == node.decision_time,
                "FULL_DEVELOPMENT_DECISION_TIME_MISMATCH",
            )
            values = encode_pre_sequence(prefix, pipeline.normalization)
            for label in target_labels:
                if label.decision_time_utc is not None:
                    _require(
                        label.decision_time_utc == node.decision_time.isoformat(),
                        "FULL_DEVELOPMENT_DECISION_TIME_MISMATCH",
                    )
            _require(tuple(values.shape) == tuple(old.values.shape), "FULL_DEVELOPMENT_PREFIX_SHAPE_DRIFT")
            for label in target_labels:
                _require(
                    bool(old.active[label.target_name]) == bool(label.active),
                    "FULL_DEVELOPMENT_ACTIVE_FLAG_MISMATCH",
                )
                _require(
                    old.targets[label.target_name] == label.exact_minutes,
                    "FULL_DEVELOPMENT_TARGET_VALUE_MISMATCH",
                )
            context = static_reference_context_from_pre(prefix[-1].static_reference_publication)
            static, static_lineage = static_reference_features_from_pre(
                prefix[-1], context, pipeline.static_normalization,
            )
            _require(
                torch.isfinite(values).all().item() and torch.isfinite(static).all().item(),
                "FULL_DEVELOPMENT_NONFINITE_INPUT",
            )
            stage_counts[node.operational_stage.value] += 1
            episode_states.append(prefix[-1].model_dump(mode="json"))
            decision_nodes.append(node.model_dump(mode="json"))
            inputs.append({
                "episode_id": episode_id,
                "decision_node_id": node.decision_node_id,
                "historical_decision_node_id": old.decision_node_id,
                "node_index": node.node_index,
                "decision_time": node.decision_time.isoformat(),
                "information_cutoff": node.information_cutoff.isoformat(),
                "operational_stage": node.operational_stage.value,
                "prefix_length": len(values),
                "feature_names": list(FEATURE_NAMES_V2),
                "encoded_adaptive_prefix": values.tolist(),
                "encoded_static_context": static.reshape(-1).tolist(),
                "static_reference_lineage": _json_safe(static_lineage),
                "contains_labels": False,
            })
            old_to_current.append({
                "episode_id": episode_id,
                "node_index": node.node_index,
                "historical_decision_node_id": old.decision_node_id,
                "current_decision_node_id": node.decision_node_id,
            })
            for label in target_labels:
                labels.append({
                    "episode_id": episode_id,
                    "decision_node_id": node.decision_node_id,
                    "historical_decision_node_id": old.decision_node_id,
                    "node_index": node.node_index,
                    "target_name": label.target_name,
                    "active": bool(label.active),
                    "exact_minutes": None if label.exact_minutes is None else float(label.exact_minutes),
                    "role": "POST_OUTCOME_DEVELOPMENT_EVALUATION_ONLY",
                })
        states_by_episode[episode_id] = episode_states
    _require(active_total == len(cached) == 1769, "FULL_DEVELOPMENT_NODE_COUNT_DRIFT")
    node_ids = tuple(item["decision_node_id"] for item in decision_nodes)
    episode_ids = tuple(sorted(states_by_episode))
    cohort_hash = content_id({
        "dataset_id": "DATA2", "split": "DEVELOPMENT", "episode_ids": episode_ids,
        "node_ids": node_ids, "cache_hash": cache_manifest["cache_hash"],
        "model_hash": binding["checkpoint"]["sha256"],
        "feature_schema_hash": cache_manifest["feature_schema_hash"],
        "current_pre_config_hash": cohorts.audit["config_hash"],
        "current_pre_registry_hash": cohorts.audit["registry_hash"],
    })
    cohort = {
        "schema_version": "AIR_SLOT_DATA2_FULL_DEVELOPMENT_COHORT_V1",
        "status": "FULL_DEVELOPMENT_COHORT_MATERIALIZED",
        "dataset_id": "DATA2", "split": "DEVELOPMENT",
        "episode_count": len(episode_ids), "node_count": len(node_ids),
        "episode_ids": episode_ids, "node_ids": node_ids,
        "decision_nodes": decision_nodes, "node_lineage": old_to_current,
        "stage_distribution": dict(sorted(stage_counts.items())),
        "selection_rule": "FROZEN_M1_B2_SEEDED_DEVELOPMENT_RESERVOIR",
        "selection_pre_outcome": True,
        "cache_hash": cache_manifest["cache_hash"],
        "feature_schema_hash": cache_manifest["feature_schema_hash"],
        "model_hash": binding["checkpoint"]["sha256"],
        "cohort_hash": cohort_hash, "safety": dict(SAFETY),
    }
    cohort["artifact_hash"] = content_id(cohort)
    inference = {
        "schema_version": "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS_V1",
        "status": "FULL_DEVELOPMENT_INFERENCE_INPUTS_MATERIALIZED",
        "scope": "DATA2_FULL_DEVELOPMENT_NO_FINAL_TEST",
        "cohort_hash": cohort_hash, "cohort_artifact_hash": cohort["artifact_hash"],
        "model_hash": binding["checkpoint"]["sha256"],
        "feature_schema_hash": cache_manifest["feature_schema_hash"],
        "cache_hash": cache_manifest["cache_hash"],
        "pre_states_by_episode": states_by_episode,
        "inference_inputs": inputs, "labels_materialized_separately": True,
        "safety": dict(SAFETY),
    }
    inference["artifact_hash"] = content_id(inference)
    label_payload = {
        "schema_version": "M1_V2_FULL_DEVELOPMENT_LABELS_V1",
        "status": "FULL_DEVELOPMENT_LABELS_MATERIALIZED",
        "scope": "POST_OUTCOME_EVALUATION_ONLY_NOT_INFERENCE",
        "cohort_hash": cohort_hash, "row_count": len(labels), "node_count": len(node_ids),
        "labels": labels, "labels_are_model_inputs": False, "safety": dict(SAFETY),
    }
    label_payload["artifact_hash"] = content_id(label_payload)

    paths = {
        "cohort": output_root / "DATA2_FULL_DEVELOPMENT_COHORT.json",
        "inputs": output_root / "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json",
        "labels": output_root / "M1_V2_FULL_DEVELOPMENT_LABELS.json",
        "manifest": output_root / "FULL_DEVELOPMENT_INPUT_MANIFEST.json",
    }
    _write(paths["cohort"], cohort)
    _write(paths["inputs"], inference)
    _write(paths["labels"], label_payload)
    manifest = {
        "schema_version": "AIR_SLOT_FULL_DEVELOPMENT_INPUT_MANIFEST_V1",
        "status": "FULL_DEVELOPMENT_INPUTS_READY",
        "cohort_hash": cohort_hash, "episode_count": len(episode_ids), "node_count": len(node_ids),
        "frozen_hashes": {
            "model_hash": binding["checkpoint"]["sha256"],
            "schema_hash": cache_manifest["feature_schema_hash"],
            "cache_hash": cache_manifest["cache_hash"],
            "support_hash": binding["frozen_contracts"]["support_hash"],
        },
        "outputs": {key: str(value.relative_to(root)).replace("\\", "/") for key, value in paths.items() if key != "manifest"},
        "artifact_hashes": {
            "cohort": cohort["artifact_hash"], "inputs": inference["artifact_hash"],
            "labels": label_payload["artifact_hash"],
        },
        "safety": dict(SAFETY),
    }
    manifest["artifact_hash"] = content_id(manifest)
    _write(paths["manifest"], manifest)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    print("FULL_DEVELOPMENT_INPUTS_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
