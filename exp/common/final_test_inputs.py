"""Materialize the held-out Data2 Q4 2019 inputs used by the Final Test chain.

The module deliberately shares the production Data2 episode, node, PRE-state,
label and M1 feature builders with the Development materializer.  Its only
cohort difference is the split-contained successor service-date window.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import torch

from exp.common.full_development_inputs import _json_safe, _references, _taxi_reference_for
from model.M1.contracts import static_reference_context_from_pre
from model.M1.coverage import active_node_prefixes
from model.M1.data import FEATURE_NAMES_V2, encode_pre_sequence
from model.M1.pipeline import M1Pipeline
from model.M1.static_features import static_reference_features_from_pre
from model.PRE.pipeline import ProductionPREPublisher
from model.PRE.streaming.data2 import (
    config_hash,
    load_selected_typed_records,
    load_timezones,
    ontime_paths,
    publish_episode_states,
    registry_hash,
    select_bounded_data2_split_episodes,
    weather_index,
)
from model.common.config import load_config_layers
from model.common.identity import content_id


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path("artifacts/experiment/final_test_inputs_v1")
CACHE_MANIFEST = Path(
    "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json"
)
CHECKPOINT = Path(
    "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt"
)
BINDING = Path(
    "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json"
)
CONFIG = Path("configs/experiment/m1_data2_development_fast.yaml")
START_DATE = date(2019, 10, 1)
END_DATE = date(2019, 12, 31)
FINAL_TEST_COHORT_COUNT = 128
FINAL_TEST_COHORT_SEED = 20260813
SCOPE = "FINAL_TEST_OUT_OF_TIME_2019_10_12"


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


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

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=default) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _completed_paths(output_root: Path) -> dict[str, Path]:
    return {
        "cohort": output_root / "DATA2_FINAL_TEST_COHORT.json",
        "inputs": output_root / "M1_V2_FINAL_TEST_INFERENCE_INPUTS.json",
        "labels": output_root / "M1_V2_FINAL_TEST_LABELS.json",
        "manifest": output_root / "FINAL_TEST_INPUT_MANIFEST.json",
    }


def _completed_manifest_is_valid(root: Path, output_root: Path) -> bool:
    paths = _completed_paths(output_root)
    if not all(path.is_file() for path in paths.values()):
        return False
    manifest = _load(paths["manifest"])
    if (
        manifest.get("scope") != SCOPE
        or manifest.get("development_input_used") is not False
        or manifest.get("start_date") != START_DATE.isoformat()
        or manifest.get("end_date") != END_DATE.isoformat()
    ):
        return False
    return all(
        path.is_file() and _sha(path) == manifest["input_hashes"][name]
        for name, path in paths.items()
        if name != "manifest"
    )


def materialize(*, root: Path = ROOT, output_root: Path | None = None) -> dict[str, Path]:
    """Materialize one frozen-model, held-out Q4 input cohort.

    ``selection_path`` survives an interrupted raw scan and is reused on the
    next invocation.  Once the final input artifacts pass their hash checks,
    this function returns without reopening the raw sources.
    """
    root = root.resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    paths = _completed_paths(output_root)
    if _completed_manifest_is_valid(root, output_root):
        return paths

    required = (
        root / CACHE_MANIFEST,
        root / CHECKPOINT,
        root / BINDING,
        root / CONFIG,
    )
    _require(all(path.is_file() for path in required), "FINAL_TEST_INPUT_REQUIRED_ARTIFACT_MISSING")
    cache_manifest = _load(root / CACHE_MANIFEST)
    binding = _load(root / BINDING)
    config = _load_yaml(root / CONFIG)
    _require(binding["model_id"] == "M1_V2_GRU_H32", "FINAL_TEST_MODEL_NOT_FROZEN_H32")
    _require(binding["checkpoint"]["sha256"] == _sha(root / CHECKPOINT), "FINAL_TEST_CHECKPOINT_HASH_MISMATCH")
    _require(
        binding["frozen_contracts"]["cache_hash"] == cache_manifest["cache_hash"],
        "FINAL_TEST_CACHE_HASH_MISMATCH",
    )
    _require(
        binding["frozen_contracts"]["feature_schema_hash"] == cache_manifest["feature_schema_hash"],
        "FINAL_TEST_FEATURE_SCHEMA_HASH_MISMATCH",
    )
    _require(
        int(config["base_cohort"]["episode_counts"]["development"]) == FINAL_TEST_COHORT_COUNT,
        "FINAL_TEST_COHORT_CARDINALITY_POLICY_DRIFT",
    )

    selection_path = output_root / "FINAL_TEST_EPISODE_SELECTION.json"
    database_path = output_root / "FINAL_TEST_Q4_BOUNDED_ORDERING.sqlite"
    episodes, selection_audit = select_bounded_data2_split_episodes(
        root=root,
        split="FINAL_TEST",
        start_date=START_DATE,
        end_date=END_DATE,
        cohort_count=FINAL_TEST_COHORT_COUNT,
        cohort_seed=FINAL_TEST_COHORT_SEED,
        selection_path=selection_path,
        database_path=database_path,
    )
    _require(len(episodes) > 0, "FINAL_TEST_EPISODE_SELECTION_EMPTY")

    source_paths = ontime_paths(root, (10, 11, 12), allow_final_test=True)
    zones = load_timezones(root / "data2" / "refs" / "us_airport_timezones.csv")
    schedules, outcomes = load_selected_typed_records(episodes, source_paths, zones)
    taxi_reference, turnaround_reference = _references(root)
    scientific = load_config_layers(root / "configs").scientific
    replay_lag = int(scientific.parameters["data2_weather_replay_lag_minutes"].value)
    weather_max_age = int(scientific.parameters["weather_max_age_minutes"].value)
    weather, weather_audit = weather_index(
        root / "data2",
        replay_lag,
        start_inclusive=START_DATE,
        end_exclusive=date(2020, 1, 1),
    )
    publisher = ProductionPREPublisher.from_project()
    current_config_hash = config_hash(root)
    current_registry_hash = registry_hash(root)

    prepared = []
    for episode in episodes:
        successor_schedule = schedules[episode.successor_flight_id]
        predecessor_outcome = outcomes[episode.predecessor_flight_id]
        successor_outcome = outcomes[episode.successor_flight_id]
        nodes, states = publish_episode_states(
            (episode, successor_schedule, predecessor_outcome, successor_outcome),
            current_config_hash,
            current_registry_hash,
            weather,
            weather_max_age,
            publisher=publisher,
            taxi_reference=taxi_reference,
            turnaround_reference=turnaround_reference,
        )
        prepared.append(
            (
                episode,
                successor_schedule,
                predecessor_outcome,
                successor_outcome,
                tuple(nodes),
                tuple(states),
            )
        )

    pipeline = M1Pipeline.load(root / CHECKPOINT)
    pipeline.model.eval()
    inputs: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    states_by_episode: dict[str, list[dict[str, Any]]] = {}
    decision_nodes: list[dict[str, Any]] = []
    successor_service_dates: dict[str, str] = {}
    stage_counts: Counter[str] = Counter()
    active_total = 0
    for (
        episode,
        successor_schedule,
        predecessor_outcome,
        successor_outcome,
        nodes,
        states,
    ) in prepared:
        episode_id = episode.episode_id
        successor_date = successor_schedule.service_date.isoformat()
        _require(START_DATE.isoformat() <= successor_date <= END_DATE.isoformat(), "FINAL_TEST_SUCCESSOR_DATE_OUT_OF_RANGE")
        successor_service_dates[episode_id] = successor_date
        reference_minutes, reference_id, reference_hash = _taxi_reference_for(
            type("Prepared", (), {"episode": episode})(), taxi_reference
        )
        episode_states: list[dict[str, Any]] = []
        for yielded_node, prefix, target_labels in active_node_prefixes(
            episode=episode,
            nodes=nodes,
            states=states,
            successor_schedule=successor_schedule,
            predecessor_outcome=predecessor_outcome,
            successor_outcome=successor_outcome,
            taxi_reference_minutes=reference_minutes,
            taxi_reference_id=reference_id,
            taxi_reference_hash=reference_hash,
        ):
            # ``active_node_prefixes`` yields the decision-grid node and its
            # current PRE prefix.  Persist the prefix endpoint, exactly as the
            # shared full-development builder does, so scenario inference and
            # labels carry the same current decision-node identity.
            node = prefix[-1].decision_node
            _require(
                yielded_node.node_index == node.node_index
                and yielded_node.decision_time == node.decision_time,
                "FINAL_TEST_NODE_PREFIX_BINDING_DRIFT",
            )
            values = encode_pre_sequence(prefix, pipeline.normalization)
            context = static_reference_context_from_pre(prefix[-1].static_reference_publication)
            static, static_lineage = static_reference_features_from_pre(
                prefix[-1], context, pipeline.static_normalization,
            )
            _require(
                torch.isfinite(values).all().item() and torch.isfinite(static).all().item(),
                "FINAL_TEST_NONFINITE_INPUT",
            )
            stage_counts[node.operational_stage.value] += 1
            active_total += 1
            episode_states.append(prefix[-1].model_dump(mode="json"))
            decision_nodes.append(node.model_dump(mode="json"))
            inputs.append(
                {
                    "episode_id": episode_id,
                    "decision_node_id": node.decision_node_id,
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
                }
            )
            for label in target_labels:
                labels.append(
                    {
                        "episode_id": episode_id,
                        "decision_node_id": node.decision_node_id,
                        "node_index": node.node_index,
                        "target_name": label.target_name,
                        "active": bool(label.active),
                        "exact_minutes": (
                            None if label.exact_minutes is None else float(label.exact_minutes)
                        ),
                        "role": "POST_OUTCOME_FINAL_TEST_EVALUATION_ONLY",
                    }
                )
        _require(episode_states, "FINAL_TEST_EPISODE_WITHOUT_ACTIVE_NODE")
        states_by_episode[episode_id] = episode_states

    _require(active_total == len(inputs) == len(decision_nodes), "FINAL_TEST_NODE_ACCOUNTING_DRIFT")
    episode_ids = tuple(sorted(states_by_episode))
    node_ids = tuple(item["decision_node_id"] for item in inputs)
    min_successor_date = min(successor_service_dates.values())
    max_successor_date = max(successor_service_dates.values())
    cohort_hash = content_id(
        {
            "dataset_id": "DATA2",
            "split": "FINAL_TEST",
            "scope": SCOPE,
            "episode_ids": episode_ids,
            "node_ids": node_ids,
            "successor_service_dates": successor_service_dates,
            "model_hash": binding["checkpoint"]["sha256"],
            "feature_schema_hash": cache_manifest["feature_schema_hash"],
            "current_pre_config_hash": current_config_hash,
            "current_pre_registry_hash": current_registry_hash,
            "selection_source_identity": selection_audit["source_identity"],
        }
    )
    cohort = {
        "schema_version": "AIR_SLOT_DATA2_FINAL_TEST_COHORT_V1",
        "status": "FINAL_TEST_COHORT_MATERIALIZED",
        "scope": SCOPE,
        "dataset_id": "DATA2",
        "split": "FINAL_TEST",
        "episode_count": len(episode_ids),
        "decision_node_count": len(node_ids),
        "node_count": len(node_ids),
        "episode_ids": episode_ids,
        "node_ids": node_ids,
        "decision_nodes": decision_nodes,
        "successor_service_dates": successor_service_dates,
        "min_successor_service_date": min_successor_date,
        "max_successor_service_date": max_successor_date,
        "stage_distribution": dict(sorted(stage_counts.items())),
        "selection": selection_audit,
        "selection_pre_outcome": True,
        "feature_schema_hash": cache_manifest["feature_schema_hash"],
        "model_hash": binding["checkpoint"]["sha256"],
        "cohort_hash": cohort_hash,
        "development_input_used": False,
    }
    cohort["artifact_hash"] = content_id(cohort)
    inference = {
        "schema_version": "M1_V2_FINAL_TEST_INFERENCE_INPUTS_V1",
        "status": "FINAL_TEST_INFERENCE_INPUTS_MATERIALIZED",
        "scope": SCOPE,
        "cohort_hash": cohort_hash,
        "cohort_artifact_hash": cohort["artifact_hash"],
        "model_hash": binding["checkpoint"]["sha256"],
        "feature_schema_hash": cache_manifest["feature_schema_hash"],
        "pre_states_by_episode": states_by_episode,
        "inference_inputs": inputs,
        "labels_materialized_separately": True,
        "development_input_used": False,
    }
    inference["artifact_hash"] = content_id(inference)
    label_payload = {
        "schema_version": "M1_V2_FINAL_TEST_LABELS_V1",
        "status": "FINAL_TEST_LABELS_MATERIALIZED",
        "scope": "POST_OUTCOME_FINAL_TEST_EVALUATION_ONLY_NOT_INFERENCE",
        "cohort_hash": cohort_hash,
        "row_count": len(labels),
        "node_count": len(node_ids),
        "labels": labels,
        "labels_are_model_inputs": False,
        "development_input_used": False,
    }
    label_payload["artifact_hash"] = content_id(label_payload)
    _write(paths["cohort"], cohort)
    _write(paths["inputs"], inference)
    _write(paths["labels"], label_payload)
    manifest = {
        "schema_version": "AIR_SLOT_FINAL_TEST_INPUT_MANIFEST_V1",
        "status": "FINAL_TEST_INPUTS_READY",
        "scope": SCOPE,
        "source_scope": SCOPE,
        "start_date": START_DATE.isoformat(),
        "end_date": END_DATE.isoformat(),
        "min_successor_service_date": min_successor_date,
        "max_successor_service_date": max_successor_date,
        "episode_count": len(episode_ids),
        "decision_node_count": len(node_ids),
        "node_count": len(node_ids),
        "cohort_hash": cohort_hash,
        "development_input_used": False,
        "final_test_source_file_reads": len(source_paths) * (
            1 + int(not selection_audit.get("selection_reused", False))
        ),
        "frozen_hashes": {
            "model_hash": binding["checkpoint"]["sha256"],
            "schema_hash": cache_manifest["feature_schema_hash"],
            "cache_hash": cache_manifest["cache_hash"],
            "support_hash": binding["frozen_contracts"]["support_hash"],
        },
        "input_hashes": {
            "cohort": _sha(paths["cohort"]),
            "inputs": _sha(paths["inputs"]),
            "labels": _sha(paths["labels"]),
        },
        "raw_source_hashes": {str(path.relative_to(root)).replace("\\", "/"): _sha(path) for path in source_paths},
        "selection_artifact": str(selection_path.relative_to(root)).replace("\\", "/"),
        "selection_artifact_hash": _sha(selection_path),
        "weather_audit": weather_audit,
        "outputs": {
            name: str(path.relative_to(root)).replace("\\", "/")
            for name, path in paths.items()
            if name != "manifest"
        },
    }
    manifest["artifact_hash"] = content_id(manifest)
    _write(paths["manifest"], manifest)
    return paths


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=ROOT, output_root=args.output_root)
    print("FINAL_TEST_INPUTS_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
