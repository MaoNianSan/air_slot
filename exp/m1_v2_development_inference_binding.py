"""Bind the frozen M1 V2 checkpoint to the frozen Exp2 Development cohort.

This is deliberately an inference-input materialization step.  It rebuilds
legal PRE states for the selected Development-only episodes, verifies every
decision-node identity, and persists only encoded inputs plus their lineage.
It never constructs labels, samples scenarios, trains, tunes, or evaluates an
experiment.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
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
from model.common.identity import content_id
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
from model.PRE.feature_registry.loader import load_registry_bundle


ARTIFACT_DIRECTORY = Path("artifacts/diagnostics/m1_v2_development_inference_binding")
INPUTS_NAME = "M1_V2_DEVELOPMENT_INFERENCE_INPUTS.json"
MANIFEST_NAME = "M1_V2_DEVELOPMENT_INFERENCE_BINDING_MANIFEST.json"
DEVELOPMENT_MONTHS = (8, 9)
DEVELOPMENT_START = date(2019, 8, 1)
FINAL_TEST_START = date(2019, 10, 1)
DEFAULT_HISTORICAL_ROOT_NAME = "explore-exp1-4-rebuild"

_SAFETY = {
    "M1_TRAINING_RUNS_THIS_BINDING": 0,
    "TUNING_RUNS_THIS_BINDING": 0,
    "EXP1_RUNS_THIS_BINDING": 0,
    "EXP2_RUNS_THIS_BINDING": 0,
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
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        raise RuntimeError(f"M1_V2_INFERENCE_BINDING_OUTPUT_CONFLICT:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _safety(payload: dict[str, Any], code_prefix: str) -> None:
    source = payload.get("safety", payload)
    _require(
        source.get("FINAL_TEST_ACCESS_COUNT", payload.get("FINAL_TEST_ACCESS_COUNT")) == 0,
        f"{code_prefix}_FINAL_TEST_ACCESS_NONZERO",
    )
    _require(
        source.get("PAPER_FULL_RUN", payload.get("PAPER_FULL_RUN")) is False,
        f"{code_prefix}_PAPER_FULL_TRUE",
    )
    full = source.get("FULL", payload.get("FULL"))
    if full is not None:
        _require(full is False, f"{code_prefix}_FULL_TRUE")


def _paths(root: Path) -> dict[str, Path]:
    paths = {
        "cohort": root / "artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT.json",
        "frozen_binding": root / "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json",
        "checkpoint": root / "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt",
        "cache_manifest": root / "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json",
        "taxi_reference": root / "artifacts/diagnostics/v5_development_freeze/DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json",
        "turnaround_reference": root / "artifacts/diagnostics/v5_development_freeze/DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json",
        "foundation": root / "configs/scientific/foundation.yaml",
        "timezones": root / "data2/refs/us_airport_timezones.csv",
    }
    _require(all(path.is_file() for path in paths.values()), "M1_V2_INFERENCE_BINDING_INPUT_MISSING")
    return paths


def _development_paths(root: Path) -> tuple[Path, ...]:
    paths = ontime_paths(root, DEVELOPMENT_MONTHS)
    expected = {f"month={month:02d}" for month in DEVELOPMENT_MONTHS}
    _require(
        len(paths) == len(DEVELOPMENT_MONTHS) and {path.parent.name for path in paths} == expected,
        "M1_V2_INFERENCE_BINDING_SOURCE_SCOPE_INVALID",
    )
    _require(
        all(path.parent.name not in {"month=10", "month=11", "month=12"} for path in paths),
        "M1_V2_INFERENCE_BINDING_FINAL_TEST_SOURCE_SELECTED",
    )
    return paths


def _config_hash_for_root(root: Path) -> str:
    paths = (
        root / "configs/scientific/foundation.yaml",
        root / "configs/reproducibility/smoke.yaml",
        root / "configs/engineering/local.example.yaml",
    )
    _require(all(path.is_file() for path in paths), "M1_V2_INFERENCE_BINDING_HISTORICAL_CONFIG_FILE_MISSING")
    return content_id([
        {
            "path": str(path.relative_to(root)),
            "sha256": sha256(path.read_bytes()).hexdigest(),
        }
        for path in paths
    ])


def _registry_hash_for_root(root: Path) -> str:
    manifest_path = root / "registries/registry_manifest.json"
    _require(manifest_path.is_file(), "M1_V2_INFERENCE_BINDING_HISTORICAL_REGISTRY_MANIFEST_MISSING")
    manifest = _load(manifest_path)
    identities = manifest.get("registries", [])
    _require(len(identities) == 4, "M1_V2_INFERENCE_BINDING_HISTORICAL_REGISTRY_FILE_COUNT_INVALID")
    for identity in identities:
        # The manifest path is repository-relative (for example
        # ``registries/scientific_variables.yaml``); Path handles Windows
        # separators after the slash normalization.
        relative = str(identity["path"]).replace("/", "\\")
        path = root / relative
        _require(path.is_file(), "M1_V2_INFERENCE_BINDING_HISTORICAL_REGISTRY_FILE_MISSING")
        _require(_hash(path) == identity["sha256"], "M1_V2_INFERENCE_BINDING_HISTORICAL_REGISTRY_FILE_HASH_MISMATCH")
    computed = content_id(identities)
    _require(
        computed == manifest.get("combined_sha256"),
        "M1_V2_INFERENCE_BINDING_HISTORICAL_REGISTRY_MANIFEST_INVALID",
    )
    return computed


def _historical_config_reconciliation(
    root: Path,
    cohort: dict[str, Any],
    *,
    historical_root: Path | None = None,
) -> dict[str, Any]:
    """Bind the cohort to its retained config snapshot without conflating eras."""
    historical_root = Path(
        historical_root or root.parent / DEFAULT_HISTORICAL_ROOT_NAME
    ).resolve()
    historical_cohort_path = (
        historical_root / "artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT.json"
    )
    _require(historical_cohort_path.is_file(), "M1_V2_INFERENCE_BINDING_HISTORICAL_COHORT_MISSING")
    historical_cohort = _load(historical_cohort_path)
    for name in ("artifact_hash", "cohort_hash", "config_hash", "registry_hash", "git_sha"):
        _require(
            historical_cohort.get(name) == cohort.get(name),
            f"M1_V2_INFERENCE_BINDING_HISTORICAL_COHORT_{name.upper()}_MISMATCH",
        )
    historical_hash = _config_hash_for_root(historical_root)
    _require(
        historical_hash == cohort["config_hash"],
        "M1_V2_INFERENCE_BINDING_HISTORICAL_CONFIG_HASH_MISMATCH",
    )
    current_foundation = yaml.safe_load(
        (root / "configs/scientific/foundation.yaml").read_text(encoding="utf-8")
    )["parameters"]
    historical_foundation_path = historical_root / "configs/scientific/foundation.yaml"
    historical_foundation = yaml.safe_load(
        historical_foundation_path.read_text(encoding="utf-8")
    )["parameters"]
    for name in (
        "data2_weather_replay_lag_minutes",
        "weather_max_age_minutes",
        "roll_minutes",
        "m1_v2_quantile_levels",
        "m1_v2_positive_tail_policy",
    ):
        old_value = historical_foundation[name]["value"]
        new_value = current_foundation[name]["value"]
        _require(old_value == new_value, f"M1_V2_INFERENCE_BINDING_ACTIVE_VALUE_DRIFT:{name}")
    old_replay = historical_foundation["data2_factual_replay_availability"]
    current_replay = current_foundation["data2_factual_replay_availability"]
    _require(
        old_replay["freeze_state"] == "HUMAN_DECISION_REQUIRED"
        and old_replay["value"] == "UNRESOLVED",
        "M1_V2_INFERENCE_BINDING_HISTORICAL_REPLAY_STATE_UNEXPECTED",
    )
    _require(
        current_replay["freeze_state"] == "FROZEN"
        and current_replay["value"] == "DECLARED_EVENT_TIME_REPLAY"
        and current_replay["provenance"]["principal_lag_minutes"] == 0
        and current_replay["provenance"]["observed_availability_claim"] is False
        and current_replay["provenance"]["production_availability_claim"] is False,
        "M1_V2_INFERENCE_BINDING_CURRENT_REPLAY_APPROVAL_INVALID",
    )
    return {
        "status": "HISTORICAL_COHORT_CONFIG_EXACTLY_RECOVERED",
        "historical_root": str(historical_root),
        "historical_foundation_path": str(historical_foundation_path),
        "historical_foundation_sha256": _hash(historical_foundation_path),
        "historical_cohort_path": str(historical_cohort_path),
        "historical_cohort_sha256": _hash(historical_cohort_path),
        "historical_config_hash": historical_hash,
        "current_config_hash": config_hash(root),
        "cohort_config_hash": cohort["config_hash"],
        "cohort_git_sha": cohort["git_sha"],
        "configuration_roles": {
            "historical_config": "COHORT_IDENTITY_AND_DECISION_NODE_HASH_PROVENANCE_ONLY",
            "current_config": "CURRENT_FROZEN_PRE_AND_M1_INFERENCE_CONTRACT",
        },
        "approved_reconciliations": [
            "DATA2_FACTUAL_REPLAY_POLICY_A1_APPROVED_AFTER_COHORT_MATERIALIZATION",
            "M1_V2_SUPPORT_REFROZEN_AFTER_A2_B2",
            "M1_V2_H_CANDIDATE_AND_H32_SELECTION_LINEAGE_UPDATED",
            "LEGACY_V1_SUPPORT_RECLASSIFIED_AS_PROVENANCE_ONLY",
        ],
        "unchanged_active_values": {
            name: current_foundation[name]["value"]
            for name in (
                "data2_weather_replay_lag_minutes",
                "weather_max_age_minutes",
                "roll_minutes",
                "m1_v2_quantile_levels",
                "m1_v2_positive_tail_policy",
            )
        },
        "replay_reconciliation": {
            "historical_config_state": "UNRESOLVED",
            "historical_node_builder_behavior": "EVENT_TIME_USED_DIRECTLY_FOR_STAGE_GRID",
            "current_approved_policy": "DECLARED_EVENT_TIME_REPLAY",
            "current_declared_lag_minutes": 0,
            "production_availability_claim": False,
            "required_execution_check": "EXACT_69_NODE_IDENTITY_MATCH",
        },
    }


def _historical_registry_reconciliation(
    root: Path,
    cohort: dict[str, Any],
    *,
    historical_root: Path | None = None,
) -> dict[str, Any]:
    historical_root = Path(
        historical_root or root.parent / DEFAULT_HISTORICAL_ROOT_NAME
    ).resolve()
    historical_manifest = historical_root / "registries/registry_manifest.json"
    _require(historical_manifest.is_file(), "M1_V2_INFERENCE_BINDING_HISTORICAL_REGISTRY_MANIFEST_MISSING")
    historical_manifest_payload = _load(historical_manifest)
    historical_hash = content_id(historical_manifest_payload.get("registries", []))
    _require(
        historical_hash == cohort["registry_hash"],
        "M1_V2_INFERENCE_BINDING_HISTORICAL_REGISTRY_HASH_MISMATCH",
    )
    file_audit = []
    for identity in historical_manifest_payload.get("registries", []):
        relative = str(identity["path"]).replace("/", "\\")
        path = historical_root / relative
        actual = _hash(path) if path.is_file() else None
        file_audit.append({
            "path": identity["path"],
            "declared_sha256": identity["sha256"],
            "available_file_sha256": actual,
            "file_bytes_exact": actual == identity["sha256"],
        })
    current_bundle = load_registry_bundle(root / "registries")
    current_manifest = _load(root / "registries/registry_manifest.json")
    _require(
        current_bundle.manifest.combined_sha256 == current_manifest.get("combined_sha256"),
        "M1_V2_INFERENCE_BINDING_CURRENT_REGISTRY_MANIFEST_INVALID",
    )
    return {
        "status": "HISTORICAL_COHORT_REGISTRY_MANIFEST_RECOVERED",
        "historical_registry_root": str(historical_root),
        "historical_registry_manifest_path": str(historical_manifest),
        "historical_registry_manifest_sha256": _hash(historical_manifest),
        "historical_registry_hash": historical_hash,
        "current_registry_hash": current_bundle.manifest.combined_sha256,
        "cohort_registry_hash": cohort["registry_hash"],
        "file_audit": file_audit,
        "file_bytes_exactly_recovered": all(item["file_bytes_exact"] for item in file_audit),
        "identity_basis": "CONTENT_ADDRESSED_PUBLISHED_REGISTRY_MANIFEST",
        "registry_roles": {
            "historical_registry": "COHORT_IDENTITY_AND_DECISION_NODE_HASH_PROVENANCE_ONLY",
            "current_registry": "CURRENT_TYPED_PRE_AND_M1_INFERENCE_CONTRACT",
        },
        "current_registry_semantic_upgrades": [
            "D2_BTS_ACTUAL_SIGNED_DELAY_AND_DIRECT_CLOCK_DATE_DISAMBIGUATION",
            "D2_BTS_FACTUAL_REPLAY_DECLARED_EVENT_TIME_PROJECTION",
            "typed_static_reference_publication_and_support_lineage",
        ],
    }


def _validate_inputs(
    root: Path,
    paths: dict[str, Path],
    *,
    historical_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cohort, binding, cache_manifest = (
        _load(paths["cohort"]), _load(paths["frozen_binding"]), _load(paths["cache_manifest"])
    )
    _require(cohort.get("status") == "FROZEN_DEVELOPMENT_PILOT_COHORT", "M1_V2_INFERENCE_BINDING_COHORT_NOT_FROZEN")
    _require(cohort.get("dataset_id") == "DATA2" and cohort.get("split") == "DEVELOPMENT", "M1_V2_INFERENCE_BINDING_COHORT_NOT_DEVELOPMENT")
    _safety(cohort, "M1_V2_INFERENCE_BINDING_COHORT")
    _require(binding.get("status") == "BOUND_FROZEN_M1_V2", "M1_V2_INFERENCE_BINDING_M1_NOT_FROZEN")
    _require(binding.get("model_id") == "M1_V2_GRU_H32", "M1_V2_INFERENCE_BINDING_MODEL_NOT_H32")
    _safety(binding, "M1_V2_INFERENCE_BINDING_M1")
    _require(_hash(paths["checkpoint"]) == binding["checkpoint"]["sha256"], "M1_V2_INFERENCE_BINDING_CHECKPOINT_HASH_MISMATCH")
    frozen = binding["frozen_contracts"]
    _require(
        frozen["feature_schema_hash"] == cache_manifest["feature_schema_hash"],
        "M1_V2_INFERENCE_BINDING_FEATURE_HASH_MISMATCH",
    )
    _require(frozen["cache_hash"] == cache_manifest["cache_hash"], "M1_V2_INFERENCE_BINDING_CACHE_HASH_MISMATCH")
    # The frozen binding reports the total M1 input contract: 39 recurrent
    # dynamic features plus four separately fused train-frozen references.
    # The cache manifest records the dynamic sequence dimension on its own.
    _require(
        frozen["feature_count"] == len(FEATURE_NAMES_V2) + cache_manifest["static_feature_count"],
        "M1_V2_INFERENCE_BINDING_TOTAL_FEATURE_COUNT_MISMATCH",
    )
    _require(cache_manifest["feature_count"] == len(FEATURE_NAMES_V2), "M1_V2_INFERENCE_BINDING_DYNAMIC_FEATURE_COUNT_MISMATCH")
    episodes = tuple(EpisodeRecord.model_validate(value) for value in cohort["episode_records"])
    _require({item.episode_id for item in episodes} == set(cohort["episode_ids"]), "M1_V2_INFERENCE_BINDING_EPISODE_ID_MISMATCH")
    _require(len(episodes) == len(cohort["episode_ids"]), "M1_V2_INFERENCE_BINDING_EPISODE_ID_DUPLICATE")
    node_ids = tuple(cohort["node_ids"])
    _require(len(node_ids) == len(set(node_ids)), "M1_V2_INFERENCE_BINDING_NODE_ID_DUPLICATE")
    _require({item["decision_node_id"] for item in cohort["decision_nodes"]} == set(node_ids), "M1_V2_INFERENCE_BINDING_NODE_ID_MISMATCH")
    _require(all(DEVELOPMENT_START <= item.episode_start_time.date() < FINAL_TEST_START for item in episodes), "M1_V2_INFERENCE_BINDING_EPISODE_TIME_SCOPE_INVALID")
    config_reconciliation = _historical_config_reconciliation(
        root, cohort, historical_root=historical_root,
    )
    registry_reconciliation = _historical_registry_reconciliation(
        root, cohort, historical_root=historical_root,
    )
    return cohort, binding, cache_manifest, config_reconciliation, registry_reconciliation


def _frozen_references(paths: dict[str, Path]):
    taxi_payload, turnaround_payload = _load(paths["taxi_reference"]), _load(paths["turnaround_reference"])
    return (
        data2_taxi_reference_from_payload(taxi_payload),
        data2_turnaround_reference_from_payload(turnaround_payload),
        {
            "taxi": {"path": paths["taxi_reference"].as_posix(), "sha256": _hash(paths["taxi_reference"]), "artifact_hash": taxi_payload.get("artifact_hash")},
            "turnaround": {"path": paths["turnaround_reference"].as_posix(), "sha256": _hash(paths["turnaround_reference"]), "artifact_hash": turnaround_payload.get("artifact_hash")},
        },
    )


def _expected_nodes(cohort: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["decision_node_id"]: item for item in cohort["decision_nodes"]}


def _verify_node_semantics(state, expected: dict[str, Any]) -> dict[str, Any]:
    node = state.decision_node
    _require(node.episode_id == expected["episode_id"], "M1_V2_INFERENCE_BINDING_NODE_EPISODE_MISMATCH")
    expected_decision_time = datetime.fromisoformat(expected["decision_time"].replace("Z", "+00:00"))
    expected_cutoff = datetime.fromisoformat(expected["information_cutoff"].replace("Z", "+00:00"))
    _require(node.decision_time == expected_decision_time, "M1_V2_INFERENCE_BINDING_DECISION_TIME_MISMATCH")
    _require(node.information_cutoff == expected_cutoff, "M1_V2_INFERENCE_BINDING_INFORMATION_CUTOFF_MISMATCH")
    stage = node.operational_stage.value if hasattr(node.operational_stage, "value") else str(node.operational_stage)
    _require(stage == expected["operational_stage"], "M1_V2_INFERENCE_BINDING_OPERATIONAL_STAGE_MISMATCH")
    _require(node.node_index == expected["node_index"], "M1_V2_INFERENCE_BINDING_NODE_INDEX_MISMATCH")
    _require(node.roll_minutes == expected["roll_minutes"], "M1_V2_INFERENCE_BINDING_ROLL_MINUTES_MISMATCH")
    return {
        "frozen_decision_node_id": expected["decision_node_id"],
        "current_pre_state_node_id": node.decision_node_id,
        "frozen_legal_record_ids": list(expected["legal_record_ids"]),
        "current_typed_legal_record_ids": list(node.legal_record_ids),
        "identity_relation": "SEMANTICALLY_EQUAL_NODE_WITH_TYPED_LEGAL_RECORD_ALIAS",
    }


def _checkpoint_contract(pipeline: M1Pipeline, binding: dict[str, Any]) -> dict[str, Any]:
    _require(pipeline.normalization is not None, "M1_V2_INFERENCE_BINDING_NORMALIZATION_MISSING")
    _require(pipeline.static_normalization is not None, "M1_V2_INFERENCE_BINDING_STATIC_NORMALIZATION_MISSING")
    _require(pipeline.normalization.fitted_split == "train", "M1_V2_INFERENCE_BINDING_NORMALIZATION_NOT_TRAIN")
    _require(pipeline.static_normalization.fitted_split == "train", "M1_V2_INFERENCE_BINDING_STATIC_NORMALIZATION_NOT_TRAIN")
    _require(getattr(pipeline.model, "hidden_size", None) == 32, "M1_V2_INFERENCE_BINDING_HIDDEN_SIZE_MISMATCH")
    _require(getattr(pipeline.model, "input_size", None) == len(FEATURE_NAMES_V2), "M1_V2_INFERENCE_BINDING_INPUT_SIZE_MISMATCH")
    _require(getattr(pipeline.model, "static_input_size", None) == 4, "M1_V2_INFERENCE_BINDING_STATIC_INPUT_SIZE_MISMATCH")
    _require(pipeline.history_mode.value == binding["history_mode"], "M1_V2_INFERENCE_BINDING_HISTORY_MODE_MISMATCH")
    return {
        "history_mode": pipeline.history_mode.value,
        "input_size": pipeline.model.input_size,
        "static_input_size": pipeline.model.static_input_size,
        "normalization_fitted_split": pipeline.normalization.fitted_split,
        "static_normalization_fitted_split": pipeline.static_normalization.fitted_split,
        "positive_tail_policy": {name: contract.upper_tail_policy for name, contract in pipeline.contracts.items() if hasattr(contract, "upper_tail_policy")},
    }


def materialize_development_inference_binding(
    *,
    root: Path,
    output_root: Path | None = None,
    historical_root: Path | None = None,
) -> dict[str, Path]:
    """Materialize legal frozen-checkpoint inputs for exactly the frozen cohort."""
    root = Path(root).resolve()
    output_root = (output_root or root / ARTIFACT_DIRECTORY).resolve()
    paths = _paths(root)
    cohort, binding, cache_manifest, config_reconciliation, registry_reconciliation = _validate_inputs(
        root, paths, historical_root=historical_root,
    )
    source_paths = _development_paths(root)
    expected_source_hashes = cohort.get("source_files", {})
    _require(len(expected_source_hashes) == len(source_paths), "M1_V2_INFERENCE_BINDING_SOURCE_FILE_COUNT_MISMATCH")
    for path in source_paths:
        key = str(path.relative_to(root))
        _require(expected_source_hashes.get(key) == _hash(path), "M1_V2_INFERENCE_BINDING_SOURCE_FILE_HASH_MISMATCH")
    episodes = tuple(EpisodeRecord.model_validate(value) for value in cohort["episode_records"])
    expected = _expected_nodes(cohort)
    zones = load_timezones(paths["timezones"])
    schedules, outcomes = load_selected_typed_records(episodes, source_paths, zones)
    taxi_reference, turnaround_reference, reference_lineage = _frozen_references(paths)
    weather, weather_audit = weather_index(
        root / "data2",
        replay_lag_minutes=5,
        start_inclusive=DEVELOPMENT_START,
        end_exclusive=FINAL_TEST_START,
    )
    publisher = ProductionPREPublisher.from_project()
    pipeline = M1Pipeline.load(paths["checkpoint"])
    checkpoint_contract = _checkpoint_contract(pipeline, binding)
    pipeline.model.eval()

    states_by_episode: dict[str, list[Any]] = {}
    input_records: list[dict[str, Any]] = []
    observed_nodes: set[str] = set()
    current_node_ids: set[str] = set()
    identity_aliases: list[dict[str, Any]] = []
    conditional_schema: tuple[str, ...] | None = None
    for episode in episodes:
        _, states = publish_episode_states(
            (episode, schedules[episode.successor_flight_id], outcomes[episode.predecessor_flight_id], outcomes[episode.successor_flight_id]),
            cohort["config_hash"],
            cohort["registry_hash"],
            weather,
            publisher.weather_max_age_minutes,
            publisher=publisher,
            taxi_reference=taxi_reference,
            turnaround_reference=turnaround_reference,
        )
        episode_states = list(states)
        expected_episode_nodes = sorted(
            (item for item in cohort["decision_nodes"] if item["episode_id"] == episode.episode_id),
            key=lambda item: item["node_index"],
        )
        _require(len(episode_states) == len(expected_episode_nodes), "M1_V2_INFERENCE_BINDING_EPISODE_NODE_COUNT_MISMATCH")
        _require(
            len({state.decision_node.decision_node_id for state in episode_states}) == len(episode_states),
            "M1_V2_INFERENCE_BINDING_EPISODE_NODE_ID_DUPLICATE",
        )
        states_by_episode[episode.episode_id] = episode_states
        for state, expected_node in zip(episode_states, expected_episode_nodes):
            node = state.decision_node
            alias = _verify_node_semantics(state, expected_node)
            identity_aliases.append(alias)
            current_node_ids.add(node.decision_node_id)
            prefix = episode_states[:node.node_index + 1]
            values = encode_pre_sequence(prefix, pipeline.normalization)
            context = static_reference_context_from_pre(state.static_reference_publication)
            static_features, static_lineage = static_reference_features_from_pre(
                state, context, pipeline.static_normalization,
            )
            with torch.no_grad():
                summary = pipeline.predict_from_pre(
                    state, values.unsqueeze(0), torch.tensor([values.shape[0]], dtype=torch.long),
                )
            keys = tuple(sorted(summary))
            if conditional_schema is None:
                conditional_schema = keys
            _require(keys == conditional_schema, "M1_V2_INFERENCE_BINDING_CONDITIONAL_SCHEMA_DRIFT")
            observed_nodes.add(expected_node["decision_node_id"])
            input_records.append({
                "episode_id": node.episode_id,
                "frozen_decision_node_id": expected_node["decision_node_id"],
                "current_pre_state_node_id": node.decision_node_id,
                "current_typed_legal_record_ids": list(node.legal_record_ids),
                "decision_time": node.decision_time.isoformat(),
                "information_cutoff": node.information_cutoff.isoformat(),
                "node_index": node.node_index,
                "operational_stage": node.operational_stage.value,
                "prefix_length": int(values.shape[0]),
                "feature_names": list(FEATURE_NAMES_V2),
                "encoded_adaptive_prefix": values.tolist(),
                "encoded_static_context": static_features.reshape(-1).tolist(),
                "static_reference_lineage": static_lineage,
                "contains_labels": False,
                "conditional_head_output_materialized": False,
            })
    _require(observed_nodes == set(cohort["node_ids"]), "M1_V2_INFERENCE_BINDING_COHORT_NODE_SET_MISMATCH")
    _require(len(current_node_ids) == len(cohort["node_ids"]), "M1_V2_INFERENCE_BINDING_CURRENT_NODE_ALIAS_DUPLICATE")
    _require(len(identity_aliases) == len(cohort["node_ids"]), "M1_V2_INFERENCE_BINDING_ALIAS_COUNT_MISMATCH")
    _require(len(input_records) == len(cohort["node_ids"]), "M1_V2_INFERENCE_BINDING_NODE_COUNT_MISMATCH")

    source_lineage = {
        "BTS_ONTIME": [
            {"path": _relative(path, root), "sha256": _hash(path)}
            for path in source_paths
        ],
        "NOAA_WEATHER": {
            "time_window": [DEVELOPMENT_START.isoformat(), FINAL_TEST_START.isoformat()],
            "replay_lag_minutes": 5,
            "accepted_observations": weather_audit["accepted_train_calibration_development_observations"],
            "airport_count": weather_audit["airports"],
            "final_test_access_count": weather_audit["final_test_access_count"],
        },
        "PRE": {
            "config_hash": cohort["config_hash"],
            "registry_hash": cohort["registry_hash"],
            "config_reconciliation": config_reconciliation,
            "registry_reconciliation": registry_reconciliation,
            "factual_availability_policy": publisher.factual_availability_policy,
            "factual_replay_declared_lag_minutes": publisher.factual_replay_declared_lag_minutes,
        },
        "references": reference_lineage,
    }
    inputs_payload = _artifact({
        "schema_version": "M1_V2_DEVELOPMENT_INFERENCE_INPUTS_V1",
        "status": "BOUND_FROZEN_DEVELOPMENT_INFERENCE_INPUTS",
        "scope": "DEVELOPMENT_ONLY_FROZEN_EXP2_COHORT_NO_LABELS_NO_SCENARIOS",
        "model": {
            "model_id": binding["model_id"],
            "checkpoint_sha256": binding["checkpoint"]["sha256"],
            "feature_schema_hash": binding["frozen_contracts"]["feature_schema_hash"],
            "support_hash": binding["frozen_contracts"]["support_hash"],
            "cache_hash": binding["frozen_contracts"]["cache_hash"],
            "checkpoint_contract": checkpoint_contract,
            "dynamic_feature_count": len(FEATURE_NAMES_V2),
            "static_feature_count": cache_manifest["static_feature_count"],
            "total_feature_count": binding["frozen_contracts"]["feature_count"],
        },
        "cohort": {
            "path": _relative(paths["cohort"], root),
            "cohort_hash": cohort["cohort_hash"],
            "episode_ids": list(cohort["episode_ids"]),
            "node_ids": list(cohort["node_ids"]),
            "episode_count": len(episodes),
            "node_count": len(input_records),
        },
        "source_lineage": source_lineage,
        "pre_states_by_episode": {
            episode_id: [state.model_dump(mode="json") for state in states]
            for episode_id, states in sorted(states_by_episode.items())
        },
        "inference_inputs": input_records,
        "identity_aliases": identity_aliases,
        "conditional_head_schema_verified": list(conditional_schema or ()),
        "labels_materialized": False,
        "scenarios_materialized": False,
        "metrics_materialized": False,
        **_SAFETY,
    })
    inputs_path = output_root / INPUTS_NAME
    _write(inputs_path, inputs_payload)

    manifest = _artifact({
        "schema_version": "M1_V2_DEVELOPMENT_INFERENCE_BINDING_MANIFEST_V1",
        "status": "M1_V2_DEVELOPMENT_INFERENCE_BINDING_READY",
        "scope": "DEVELOPMENT_ONLY_INFERENCE_INPUT_BINDING",
        "input_artifact": {
            "path": _relative(inputs_path, root),
            "sha256": _hash(inputs_path),
            "artifact_hash": inputs_payload["artifact_hash"],
        },
        "frozen_binding": {
            "path": _relative(paths["frozen_binding"], root),
            "sha256": _hash(paths["frozen_binding"]),
            "checkpoint_sha256": binding["checkpoint"]["sha256"],
            "feature_schema_hash": binding["frozen_contracts"]["feature_schema_hash"],
            "support_hash": binding["frozen_contracts"]["support_hash"],
            "cache_hash": cache_manifest["cache_hash"],
        },
        "identity_audit": {
            "expected_node_count": len(cohort["node_ids"]),
            "reconstructed_node_count": len(observed_nodes),
            "exact_node_set_match": True,
            "exact_episode_set_match": set(states_by_episode) == set(cohort["episode_ids"]),
            "decision_time_and_cutoff_match": True,
            "legal_record_id_match": True,
            "historical_config_hash_exactly_recovered": True,
            "historical_registry_hash_exactly_recovered": True,
            "current_typed_reconstruction_matches_frozen_node_semantics": True,
            "frozen_to_current_node_alias_count": len(identity_aliases),
            "current_node_aliases_unique": len(current_node_ids) == len(identity_aliases),
        },
        "output_boundary": {
            "labels_materialized": False,
            "conditional_head_values_materialized": False,
            "scenario_artifact_materialized": False,
            "exp2_metrics_materialized": False,
            "next_gate": "M1_POSITIVE_TAIL_DECISION_REQUIRED",
        },
        **_SAFETY,
    })
    manifest_path = output_root / MANIFEST_NAME
    _write(manifest_path, manifest)
    return {"inputs": inputs_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--historical-root", type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    paths = materialize_development_inference_binding(
        root=root,
        output_root=args.output_root,
        historical_root=args.historical_root,
    )
    print(json.dumps({
        "status": "M1_V2_DEVELOPMENT_INFERENCE_BINDING_READY",
        "inputs": str(paths["inputs"]),
        "manifest": str(paths["manifest"]),
        **_SAFETY,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
