"""Refreeze the Development pilot under the approved current PRE stage policy.

The historical cohort is immutable provenance.  This module reuses only its
pre-outcome episode selection, rebuilds typed PRE nodes under the approved
declared-event-time replay policy, verifies frozen M1 tensor compatibility,
and stops before positive-tail scenario materialization.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import torch
import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model.M1.contracts import static_reference_context_from_pre
from model.M1.data import FEATURE_NAMES_V2, encode_pre_sequence
from model.M1.pipeline import M1Pipeline
from model.M1.static_features import static_reference_features_from_pre
from model.PRE.contracts.pre_state import EpisodeRecord
from model.PRE.pipeline import ProductionPREPublisher
from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
from model.PRE.reference.turnaround_data2 import data2_turnaround_reference_from_payload
from model.PRE.streaming.data2 import (
    config_hash,
    load_selected_typed_records,
    load_timezones,
    ontime_paths,
    publish_episode_states,
    registry_hash,
    weather_index,
)
from model.common.identity import content_id


HISTORICAL_COHORT = Path("artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT.json")
NEW_COHORT = Path("artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT_CURRENT_STAGE_V3.json")
OUTPUT_DIRECTORY = Path("artifacts/diagnostics/m1_v2_development_current_stage_refreeze_v3")
INPUTS_NAME = "M1_V2_CURRENT_STAGE_DEVELOPMENT_INFERENCE_INPUTS.json"
MANIFEST_NAME = "M1_V2_CURRENT_STAGE_COHORT_REFREEZE_MANIFEST.json"
FEATURE_REPORT_NAME = "M1_V2_CURRENT_STAGE_FEATURE_COMPATIBILITY_REPORT.json"
M1_REPORT_NAME = "M1_V2_CURRENT_STAGE_M1_ARTIFACT_VALIDITY_REPORT.json"

DEVELOPMENT_START = date(2019, 8, 1)
FINAL_TEST_START = date(2019, 10, 1)
DEVELOPMENT_MONTHS = (8, 9)

_SAFETY = {
    "M1_TRAINING_RUNS_THIS_REFREEZE": 0,
    "TUNING_RUNS_THIS_REFREEZE": 0,
    "EXP1_RUNS_THIS_REFREEZE": 0,
    "EXP2_RUNS_THIS_REFREEZE": 0,
    "EXP3_RUNS_THIS_REFREEZE": 0,
    "EXP4_RUNS_THIS_REFREEZE": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _artifact(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "artifact_hash": content_id(payload)}


def _write(path: Path, payload: dict[str, Any]) -> None:
    def _json_default(value: Any):
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        raise TypeError(f"M1_V2_CURRENT_STAGE_REFREEZE_NON_JSON_VALUE:{type(value).__name__}")

    rendered = json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        raise RuntimeError(f"M1_V2_CURRENT_STAGE_REFREEZE_OUTPUT_CONFLICT:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _all_finite(value: Any) -> bool:
    if isinstance(value, dict):
        return all(_all_finite(item) for item in value.values())
    if torch.is_tensor(value):
        return bool(torch.isfinite(value).all().item())
    return True


def _paths(root: Path) -> dict[str, Path]:
    paths = {
        "historical_cohort": root / HISTORICAL_COHORT,
        "frozen_binding": root / "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json",
        "freeze_manifest": root / "artifacts/diagnostics/m1_v2_final_development_freeze/M1_V2_FINAL_FREEZE_MANIFEST.json",
        "checkpoint": root / "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt",
        "cache_manifest": root / "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json",
        "taxi_reference": root / "artifacts/diagnostics/v5_development_freeze/DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json",
        "turnaround_reference": root / "artifacts/diagnostics/v5_development_freeze/DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json",
        "foundation": root / "configs/scientific/foundation.yaml",
        "timezones": root / "data2/refs/us_airport_timezones.csv",
    }
    _require(all(path.is_file() for path in paths.values()), "M1_V2_CURRENT_STAGE_REFREEZE_INPUT_MISSING")
    return paths


def _source_paths(root: Path, historical: dict[str, Any]) -> tuple[Path, ...]:
    paths = ontime_paths(root, DEVELOPMENT_MONTHS)
    _require(
        len(paths) == 2 and {path.parent.name for path in paths} == {"month=08", "month=09"},
        "M1_V2_CURRENT_STAGE_REFREEZE_SOURCE_SCOPE_INVALID",
    )
    _require(
        all(path.parent.name not in {"month=10", "month=11", "month=12"} for path in paths),
        "M1_V2_CURRENT_STAGE_REFREEZE_FINAL_TEST_SOURCE_SELECTED",
    )
    declared = historical["source_files"]
    for path in paths:
        candidates = {
            str(path.relative_to(root)),
            str(path.relative_to(root)).replace("/", "\\"),
            path.relative_to(root).as_posix(),
        }
        declared_hash = next((declared[key] for key in candidates if key in declared), None)
        _require(declared_hash == _hash(path), "M1_V2_CURRENT_STAGE_REFREEZE_SOURCE_HASH_MISMATCH")
    return paths


def _validate_frozen_contracts(paths: dict[str, Path]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    binding = _load(paths["frozen_binding"])
    freeze = _load(paths["freeze_manifest"])
    cache = _load(paths["cache_manifest"])
    _require(binding["status"] == "BOUND_FROZEN_M1_V2", "M1_V2_CURRENT_STAGE_BINDING_NOT_FROZEN")
    _require(binding["model_id"] == "M1_V2_GRU_H32" and binding["hidden_size"] == 32, "M1_V2_CURRENT_STAGE_MODEL_NOT_H32")
    _require(freeze["status"] == "M1_V2_FINAL_DEVELOPMENT_FREEZE_READY", "M1_V2_CURRENT_STAGE_FREEZE_INVALID")
    _require(_hash(paths["checkpoint"]) == binding["checkpoint"]["sha256"], "M1_V2_CURRENT_STAGE_CHECKPOINT_HASH_MISMATCH")
    fixed = binding["frozen_contracts"]
    _require(fixed["feature_schema_hash"] == cache["feature_schema_hash"], "M1_V2_CURRENT_STAGE_FEATURE_HASH_MISMATCH")
    _require(fixed["cache_hash"] == cache["cache_hash"], "M1_V2_CURRENT_STAGE_CACHE_HASH_MISMATCH")
    _require(fixed["support_hash"] == freeze["fixed_contracts"]["support_hash"], "M1_V2_CURRENT_STAGE_SUPPORT_HASH_MISMATCH")
    _require(fixed["loss_version"] == freeze["fixed_contracts"]["loss_version"], "M1_V2_CURRENT_STAGE_LOSS_MISMATCH")
    _require(fixed["feature_count"] == len(FEATURE_NAMES_V2) + cache["static_feature_count"] == 43, "M1_V2_CURRENT_STAGE_FEATURE_COUNT_MISMATCH")
    return binding, freeze, cache


def _approved_policy(paths: dict[str, Path], publisher: ProductionPREPublisher) -> dict[str, Any]:
    parameters = yaml.safe_load(paths["foundation"].read_text(encoding="utf-8"))["parameters"]
    replay = parameters["data2_factual_replay_availability"]
    tail = parameters["m1_v2_positive_tail_policy"]
    _require(replay["freeze_state"] == "FROZEN", "M1_V2_CURRENT_STAGE_REPLAY_NOT_FROZEN")
    _require(replay["value"] == "DECLARED_EVENT_TIME_REPLAY", "M1_V2_CURRENT_STAGE_REPLAY_POLICY_INVALID")
    _require(replay["provenance"]["selection_state"] == "HUMAN_APPROVED", "M1_V2_CURRENT_STAGE_REPLAY_NOT_HUMAN_APPROVED")
    _require(replay["provenance"]["principal_lag_minutes"] == 0, "M1_V2_CURRENT_STAGE_REPLAY_LAG_INVALID")
    _require(publisher.factual_availability_policy == replay["value"], "M1_V2_CURRENT_STAGE_PUBLISHER_POLICY_MISMATCH")
    _require(publisher.factual_replay_declared_lag_minutes == 0.0, "M1_V2_CURRENT_STAGE_PUBLISHER_LAG_MISMATCH")
    _require(
        tail["freeze_state"] == "FROZEN"
        and tail["value"] == "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS",
        "M1_V2_CURRENT_STAGE_POSITIVE_TAIL_POLICY_NOT_FROZEN",
    )
    _require(
        tail["provenance"]["target_q_max_minutes"] == {"T_IB_A00": 360, "D_OB": 210, "D_TX": 60},
        "M1_V2_CURRENT_STAGE_POSITIVE_TAIL_QMAX_MISMATCH",
    )
    return {"replay": replay, "positive_tail": tail, "quantile_levels": parameters["m1_v2_quantile_levels"]}


def refreeze_current_stage_cohort(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / OUTPUT_DIRECTORY).resolve()
    paths = _paths(root)
    historical_path = paths["historical_cohort"]
    historical_sha_before = _hash(historical_path)
    historical = _load(historical_path)
    _require(historical["status"] == "FROZEN_DEVELOPMENT_PILOT_COHORT", "M1_V2_CURRENT_STAGE_HISTORICAL_COHORT_INVALID")
    _require(historical["split"] == "DEVELOPMENT" and historical["FINAL_TEST_ACCESS_COUNT"] == 0, "M1_V2_CURRENT_STAGE_HISTORICAL_SCOPE_INVALID")
    binding, freeze, cache = _validate_frozen_contracts(paths)
    source_paths = _source_paths(root, historical)
    episodes = tuple(EpisodeRecord.model_validate(value) for value in historical["episode_records"])
    _require(len(episodes) == len(historical["episode_ids"]) == 5, "M1_V2_CURRENT_STAGE_EPISODE_COUNT_INVALID")
    _require(tuple(item.episode_id for item in episodes) == tuple(historical["episode_ids"]), "M1_V2_CURRENT_STAGE_EPISODE_ORDER_DRIFT")
    _require(all(DEVELOPMENT_START <= item.episode_start_time.date() < FINAL_TEST_START for item in episodes), "M1_V2_CURRENT_STAGE_EPISODE_SCOPE_INVALID")

    zones = load_timezones(paths["timezones"])
    schedules, outcomes = load_selected_typed_records(episodes, source_paths, zones)
    replay_lag = int(yaml.safe_load(paths["foundation"].read_text(encoding="utf-8"))["parameters"]["data2_weather_replay_lag_minutes"]["value"])
    weather, weather_audit = weather_index(
        root / "data2",
        replay_lag_minutes=replay_lag,
        start_inclusive=DEVELOPMENT_START,
        end_exclusive=FINAL_TEST_START,
    )
    _require(weather_audit["final_test_access_count"] == 0, "M1_V2_CURRENT_STAGE_WEATHER_FINAL_TEST_ACCESS")
    publisher = ProductionPREPublisher.from_project()
    policy = _approved_policy(paths, publisher)
    taxi = data2_taxi_reference_from_payload(_load(paths["taxi_reference"]))
    turnaround = data2_turnaround_reference_from_payload(_load(paths["turnaround_reference"]))
    pipeline = M1Pipeline.load(paths["checkpoint"])
    pipeline.model.eval()
    _require(pipeline.normalization is not None and pipeline.normalization.fitted_split == "train", "M1_V2_CURRENT_STAGE_DYNAMIC_NORMALIZATION_INVALID")
    _require(pipeline.static_normalization is not None and pipeline.static_normalization.fitted_split == "train", "M1_V2_CURRENT_STAGE_STATIC_NORMALIZATION_INVALID")
    _require(pipeline.model.input_size == len(FEATURE_NAMES_V2) == 39, "M1_V2_CURRENT_STAGE_MODEL_INPUT_SIZE_INVALID")
    _require(pipeline.model.static_input_size == cache["static_feature_count"] == 4, "M1_V2_CURRENT_STAGE_STATIC_INPUT_SIZE_INVALID")
    _require(pipeline.model.hidden_size == 32, "M1_V2_CURRENT_STAGE_HIDDEN_SIZE_INVALID")
    _require(pipeline.history_mode.value == binding["history_mode"], "M1_V2_CURRENT_STAGE_HISTORY_MODE_INVALID")

    current_config_hash = config_hash(root)
    current_registry_hash = registry_hash(root)
    historical_by_key = {(item["episode_id"], item["node_index"]): item for item in historical["decision_nodes"]}
    states_by_episode: dict[str, list[Any]] = {}
    input_records: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    current_nodes: list[Any] = []
    old_stage_counts = Counter(item["operational_stage"] for item in historical["decision_nodes"])
    new_stage_counts: Counter[str] = Counter()
    stage_changes: list[dict[str, Any]] = []
    conditional_schema: tuple[str, ...] | None = None
    max_abs_dynamic = 0.0
    max_abs_static = 0.0

    for episode in episodes:
        _, states = publish_episode_states(
            (
                episode,
                schedules[episode.successor_flight_id],
                outcomes[episode.predecessor_flight_id],
                outcomes[episode.successor_flight_id],
            ),
            current_config_hash,
            current_registry_hash,
            weather,
            publisher.weather_max_age_minutes,
            publisher=publisher,
            taxi_reference=taxi,
            turnaround_reference=turnaround,
        )
        episode_states = list(states)
        expected = sorted(
            (item for item in historical["decision_nodes"] if item["episode_id"] == episode.episode_id),
            key=lambda item: item["node_index"],
        )
        _require(len(episode_states) == len(expected), "M1_V2_CURRENT_STAGE_EPISODE_NODE_COUNT_DRIFT")
        states_by_episode[episode.episode_id] = episode_states
        for state, old in zip(episode_states, expected):
            node = state.decision_node
            _require(node.episode_id == old["episode_id"] and node.node_index == old["node_index"], "M1_V2_CURRENT_STAGE_NODE_CORE_IDENTITY_DRIFT")
            _require(node.decision_time.isoformat() == old["decision_time"].replace("Z", "+00:00"), "M1_V2_CURRENT_STAGE_DECISION_TIME_DRIFT")
            _require(node.information_cutoff.isoformat() == old["information_cutoff"].replace("Z", "+00:00"), "M1_V2_CURRENT_STAGE_CUTOFF_DRIFT")
            new_stage = node.operational_stage.value
            new_stage_counts[new_stage] += 1
            current_nodes.append(node)
            alias = {
                "episode_id": episode.episode_id,
                "node_index": node.node_index,
                "historical_decision_node_id": old["decision_node_id"],
                "current_stage_decision_node_id": node.decision_node_id,
                "historical_legal_record_ids": list(old["legal_record_ids"]),
                "current_typed_legal_record_ids": list(node.legal_record_ids),
            }
            aliases.append(alias)
            if new_stage != old["operational_stage"]:
                stage_changes.append({
                    **{key: alias[key] for key in ("episode_id", "node_index", "historical_decision_node_id", "current_stage_decision_node_id")},
                    "decision_time": node.decision_time.isoformat(),
                    "historical_stage": old["operational_stage"],
                    "current_stage": new_stage,
                })

            prefix = episode_states[: node.node_index + 1]
            values = encode_pre_sequence(prefix, pipeline.normalization)
            context = static_reference_context_from_pre(state.static_reference_publication)
            static_values, static_lineage = static_reference_features_from_pre(
                state, context, pipeline.static_normalization,
            )
            _require(tuple(values.shape) == (node.node_index + 1, len(FEATURE_NAMES_V2)), "M1_V2_CURRENT_STAGE_DYNAMIC_TENSOR_SHAPE_INVALID")
            _require(static_values.numel() == 4, "M1_V2_CURRENT_STAGE_STATIC_TENSOR_SHAPE_INVALID")
            _require(torch.isfinite(values).all().item(), "M1_V2_CURRENT_STAGE_DYNAMIC_TENSOR_NONFINITE")
            _require(torch.isfinite(static_values).all().item(), "M1_V2_CURRENT_STAGE_STATIC_TENSOR_NONFINITE")
            max_abs_dynamic = max(max_abs_dynamic, float(values.abs().max().item()))
            max_abs_static = max(max_abs_static, float(static_values.abs().max().item()))
            with torch.no_grad():
                summary = pipeline.predict_from_pre(
                    state,
                    values.unsqueeze(0),
                    torch.tensor([values.shape[0]], dtype=torch.long),
                )
            schema = tuple(sorted(summary))
            if conditional_schema is None:
                conditional_schema = schema
            _require(schema == conditional_schema, "M1_V2_CURRENT_STAGE_CONDITIONAL_HEAD_SCHEMA_DRIFT")
            _require(_all_finite(summary), "M1_V2_CURRENT_STAGE_CONDITIONAL_OUTPUT_NONFINITE")
            input_records.append({
                "episode_id": episode.episode_id,
                "decision_node_id": node.decision_node_id,
                "historical_decision_node_id": old["decision_node_id"],
                "decision_time": node.decision_time.isoformat(),
                "information_cutoff": node.information_cutoff.isoformat(),
                "node_index": node.node_index,
                "operational_stage": new_stage,
                "prefix_length": int(values.shape[0]),
                "feature_names": list(FEATURE_NAMES_V2),
                "encoded_adaptive_prefix": values.tolist(),
                "encoded_static_context": static_values.reshape(-1).tolist(),
                "static_reference_lineage": static_lineage,
                "contains_labels": False,
                "conditional_head_values_materialized": False,
            })

    _require(len(current_nodes) == len(historical["node_ids"]) == 69, "M1_V2_CURRENT_STAGE_TOTAL_NODE_COUNT_DRIFT")
    new_node_ids = tuple(node.decision_node_id for node in current_nodes)
    _require(len(set(new_node_ids)) == len(new_node_ids), "M1_V2_CURRENT_STAGE_NODE_ID_DUPLICATE")
    _require(set(new_node_ids).isdisjoint(set(historical["node_ids"])), "M1_V2_CURRENT_STAGE_NODE_ID_NOT_NEW")
    _require(len(stage_changes) == 3, "M1_V2_CURRENT_STAGE_EXPECTED_STAGE_DELTA_CHANGED")

    identity = {
        "dataset_id": "DATA2",
        "source_dataset_id": historical["source_dataset_id"],
        "source_manifest_hash": historical["source_manifest_hash"],
        "split": "DEVELOPMENT",
        "selector_rule": historical["selector_rule"],
        "episode_ids": tuple(historical["episode_ids"]),
        "node_ids": new_node_ids,
        "config_hash": current_config_hash,
        "registry_hash": current_registry_hash,
        "factual_replay_policy": publisher.factual_availability_policy,
        "factual_replay_declared_lag_minutes": publisher.factual_replay_declared_lag_minutes,
        "historical_parent_cohort_hash": historical["cohort_hash"],
    }
    new_cohort_hash = content_id(identity)
    _require(new_cohort_hash != historical["cohort_hash"], "M1_V2_CURRENT_STAGE_COHORT_HASH_NOT_NEW")
    new_cohort = _artifact({
        "schema_version": "AIR_SLOT_EXP2_DATA2_DEVELOPMENT_CURRENT_STAGE_COHORT_V2",
        "status": "NEW_DEVELOPMENT_COHORT_REFROZEN",
        "dataset_id": "DATA2",
        "source_dataset_id": historical["source_dataset_id"],
        "dataset_version": "DATA2_2019_DEVELOPMENT_AUG_SEP_CURRENT_STAGE_V2",
        "split": "DEVELOPMENT",
        "successor_service_date_range": historical["successor_service_date_range"],
        "source_files": historical["source_files"],
        "source_manifest_hash": historical["source_manifest_hash"],
        "selector_rule": historical["selector_rule"],
        "selector_seed": historical["selector_seed"],
        "selector_seed_role": historical["selector_seed_role"],
        "selector_pre_outcome": True,
        "selector_disallows_variant_or_outcome_selection": True,
        "split_containment_rule": historical["split_containment_rule"],
        "rolling_interval_minutes": 5,
        "cohort_scope": "CURRENT_APPROVED_TYPED_PRE_STAGE_POLICY_WITH_HISTORICAL_EPISODE_SELECTION",
        "factual_replay_status": "DECLARED_EVENT_TIME_REPLAY_HUMAN_APPROVED",
        "factual_replay_policy": publisher.factual_availability_policy,
        "factual_replay_declared_lag_minutes": publisher.factual_replay_declared_lag_minutes,
        "episode_ids": tuple(historical["episode_ids"]),
        "episode_ids_hash": historical["episode_ids_hash"],
        "episode_records": historical["episode_records"],
        "node_ids": new_node_ids,
        "node_ids_hash": content_id(new_node_ids),
        "decision_nodes": tuple(node.model_dump(mode="json") for node in current_nodes),
        "historical_parent": {
            "path": _relative(historical_path, root),
            "sha256": historical_sha_before,
            "artifact_hash": historical["artifact_hash"],
            "cohort_hash": historical["cohort_hash"],
            "role": "IMMUTABLE_HISTORICAL_PROVENANCE_AND_SENSITIVITY_REFERENCE",
        },
        "node_lineage": aliases,
        "stage_distribution": {
            "historical": dict(sorted(old_stage_counts.items())),
            "current": dict(sorted(new_stage_counts.items())),
            "changed_node_count": len(stage_changes),
            "changes": stage_changes,
        },
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "config_hash": current_config_hash,
        "registry_hash": current_registry_hash,
        "cohort_hash": new_cohort_hash,
        **_SAFETY,
    })
    new_cohort_path = root / NEW_COHORT
    _write(new_cohort_path, new_cohort)
    _require(_hash(historical_path) == historical_sha_before, "M1_V2_CURRENT_STAGE_HISTORICAL_COHORT_MUTATED")

    inputs_payload = _artifact({
        "schema_version": "M1_V2_CURRENT_STAGE_DEVELOPMENT_INFERENCE_INPUTS_V1",
        "status": "BOUND_CURRENT_STAGE_DEVELOPMENT_INFERENCE_INPUTS",
        "scope": "DEVELOPMENT_ONLY_NO_LABELS_NO_SCENARIOS",
        "cohort": {
            "path": _relative(new_cohort_path, root),
            "sha256": _hash(new_cohort_path),
            "artifact_hash": new_cohort["artifact_hash"],
            "cohort_hash": new_cohort_hash,
            "episode_count": len(episodes),
            "node_count": len(current_nodes),
        },
        "model": {
            "model_id": binding["model_id"],
            "checkpoint_sha256": binding["checkpoint"]["sha256"],
            "feature_schema_hash": binding["frozen_contracts"]["feature_schema_hash"],
            "support_hash": binding["frozen_contracts"]["support_hash"],
            "cache_hash": binding["frozen_contracts"]["cache_hash"],
            "dynamic_feature_count": len(FEATURE_NAMES_V2),
            "static_feature_count": cache["static_feature_count"],
            "total_feature_count": 43,
        },
        "source_lineage": {
            "config_hash": current_config_hash,
            "registry_hash": current_registry_hash,
            "factual_replay_policy": publisher.factual_availability_policy,
            "factual_replay_declared_lag_minutes": publisher.factual_replay_declared_lag_minutes,
            "weather_replay_lag_minutes": replay_lag,
            "weather_final_test_access_count": weather_audit["final_test_access_count"],
            "taxi_reference_sha256": _hash(paths["taxi_reference"]),
            "turnaround_reference_sha256": _hash(paths["turnaround_reference"]),
        },
        "pre_states_by_episode": {
            episode_id: [state.model_dump(mode="json") for state in states]
            for episode_id, states in sorted(states_by_episode.items())
        },
        "inference_inputs": input_records,
        "conditional_head_schema_verified": list(conditional_schema or ()),
        "labels_materialized": False,
        "scenarios_materialized": False,
        "metrics_materialized": False,
        **_SAFETY,
    })
    inputs_path = output_root / INPUTS_NAME
    _write(inputs_path, inputs_payload)

    feature_report = _artifact({
        "schema_version": "M1_V2_CURRENT_STAGE_FEATURE_COMPATIBILITY_REPORT_V1",
        "status": "PASS_FROZEN_M1_FEATURE_TENSOR_COMPATIBILITY",
        "cohort_hash": new_cohort_hash,
        "node_count": len(current_nodes),
        "episode_count": len(episodes),
        "dynamic_feature_count": len(FEATURE_NAMES_V2),
        "static_feature_count": cache["static_feature_count"],
        "total_feature_count": 43,
        "feature_schema_hash": binding["frozen_contracts"]["feature_schema_hash"],
        "model_input_size": pipeline.model.input_size,
        "model_static_input_size": pipeline.model.static_input_size,
        "prefix_length_range": [min(item["prefix_length"] for item in input_records), max(item["prefix_length"] for item in input_records)],
        "all_dynamic_tensors_finite": True,
        "all_static_tensors_finite": True,
        "all_conditional_outputs_finite": True,
        "max_abs_encoded_dynamic": max_abs_dynamic,
        "max_abs_encoded_static": max_abs_static,
        "conditional_head_schema": list(conditional_schema or ()),
        "feature_schema_modified": False,
        "support_modified": False,
        **_SAFETY,
    })
    feature_path = output_root / FEATURE_REPORT_NAME
    _write(feature_path, feature_report)

    m1_report = _artifact({
        "schema_version": "M1_V2_CURRENT_STAGE_M1_ARTIFACT_VALIDITY_REPORT_V1",
        "status": "PASS_FROZEN_M1_ARTIFACT_VALID_FOR_CURRENT_STAGE_INPUTS",
        "model_id": binding["model_id"],
        "checkpoint_path": _relative(paths["checkpoint"], root),
        "checkpoint_sha256": binding["checkpoint"]["sha256"],
        "checkpoint_hash_match": True,
        "hidden_size": pipeline.model.hidden_size,
        "parameter_count": binding["parameter_count"],
        "history_mode": pipeline.history_mode.value,
        "normalization_fitted_split": pipeline.normalization.fitted_split,
        "static_normalization_fitted_split": pipeline.static_normalization.fitted_split,
        "feature_schema_hash_match": True,
        "support_hash_match": True,
        "loss_contract_match": binding["frozen_contracts"]["loss_version"] == freeze["fixed_contracts"]["loss_version"],
        "conditional_head_schema_stable": True,
        "positive_tail_policy": policy["positive_tail"]["value"],
        "next_gate": "M1_CURRENT_STAGE_JOINT_SCENARIO_ARTIFACT_REQUIRED",
        "model_modified": False,
        "checkpoint_modified": False,
        **_SAFETY,
    })
    m1_report_path = output_root / M1_REPORT_NAME
    _write(m1_report_path, m1_report)

    manifest = _artifact({
        "schema_version": "M1_V2_CURRENT_STAGE_COHORT_REFREEZE_MANIFEST_V1",
        "status": "NEW_DEVELOPMENT_COHORT_REFROZEN",
        "decision_id": "REFREEZE_CURRENT_STAGE_POLICY",
        "current_replay_policy": {
            "value": policy["replay"]["value"],
            "freeze_state": policy["replay"]["freeze_state"],
            "decision_id": policy["replay"]["provenance"]["decision_id"],
            "principal_lag_minutes": policy["replay"]["provenance"]["principal_lag_minutes"],
            "observed_availability_claim": policy["replay"]["provenance"]["observed_availability_claim"],
            "production_availability_claim": policy["replay"]["provenance"]["production_availability_claim"],
        },
        "historical_cohort": {
            "path": _relative(historical_path, root),
            "sha256_before": historical_sha_before,
            "sha256_after": _hash(historical_path),
            "cohort_hash": historical["cohort_hash"],
            "preserved": True,
        },
        "new_cohort": {
            "path": _relative(new_cohort_path, root),
            "sha256": _hash(new_cohort_path),
            "artifact_hash": new_cohort["artifact_hash"],
            "cohort_hash": new_cohort_hash,
            "new_hash_verified": new_cohort_hash != historical["cohort_hash"],
            "episode_count": len(episodes),
            "node_count": len(current_nodes),
        },
        "stage_audit": new_cohort["stage_distribution"],
        "feature_compatibility": {
            "path": _relative(feature_path, root),
            "sha256": _hash(feature_path),
            "status": feature_report["status"],
        },
        "m1_artifact_validity": {
            "path": _relative(m1_report_path, root),
            "sha256": _hash(m1_report_path),
            "status": m1_report["status"],
        },
        "m1_binding": {
            "model_id": binding["model_id"],
            "hidden_size": binding["hidden_size"],
            "history_mode": binding["history_mode"],
            "checkpoint_sha256": binding["checkpoint"]["sha256"],
            "feature_schema_hash": binding["frozen_contracts"]["feature_schema_hash"],
            "support_hash": binding["frozen_contracts"]["support_hash"],
            "cache_hash": binding["frozen_contracts"]["cache_hash"],
            "loss_version": binding["frozen_contracts"]["loss_version"],
            "feature_count": binding["frozen_contracts"]["feature_count"],
            "modified": False,
        },
        "inference_inputs": {
            "path": _relative(inputs_path, root),
            "sha256": _hash(inputs_path),
            "artifact_hash": inputs_payload["artifact_hash"],
            "labels_materialized": False,
            "scenarios_materialized": False,
        },
        "downstream_binding_status": "READY_FOR_EXP2_4_REBIND_BEFORE_SCENARIOS",
        "next_gate": "M1_CURRENT_STAGE_JOINT_SCENARIO_ARTIFACT_REQUIRED",
        **_SAFETY,
    })
    manifest_path = output_root / MANIFEST_NAME
    _write(manifest_path, manifest)
    return {
        "cohort": new_cohort_path,
        "inputs": inputs_path,
        "feature_report": feature_path,
        "m1_report": m1_report_path,
        "manifest": manifest_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    outputs = refreeze_current_stage_cohort(
        root=Path(__file__).resolve().parents[1],
        output_root=args.output_root,
    )
    manifest = _load(outputs["manifest"])
    print(json.dumps({
        "status": manifest["status"],
        "cohort": str(outputs["cohort"]),
        "cohort_hash": manifest["new_cohort"]["cohort_hash"],
        "next_gate": manifest["next_gate"],
        **_SAFETY,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
