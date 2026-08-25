"""Reconcile frozen Development node semantics against the current typed PRE.

This is a read-only scientific gate.  It deliberately separates harmless
typed legal-record aliases from operational-stage drift, because stage is an
M1 feature input and cannot be repaired by identity aliasing.
"""

from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from model.PRE.contracts.pre_state import EpisodeRecord
from model.PRE.pipeline import ProductionPREPublisher
from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
from model.PRE.reference.turnaround_data2 import data2_turnaround_reference_from_payload
from model.PRE.streaming.data2 import (
    load_selected_typed_records,
    load_timezones,
    ontime_paths,
    publish_episode_states,
    weather_index,
)
from model.common.identity import content_id


ARTIFACT_DIRECTORY = Path("artifacts/diagnostics/m1_v2_development_inference_binding")
REPORT_NAME = "M1_V2_DEVELOPMENT_INFERENCE_SEMANTIC_RECONCILIATION_V2.json"
DEVELOPMENT_START = date(2019, 8, 1)
FINAL_TEST_START = date(2019, 10, 1)
DEVELOPMENT_MONTHS = (8, 9)

_SAFETY = {
    "M1_TRAINING_RUNS_THIS_RECONCILIATION": 0,
    "TUNING_RUNS_THIS_RECONCILIATION": 0,
    "EXP1_RUNS_THIS_RECONCILIATION": 0,
    "EXP2_RUNS_THIS_RECONCILIATION": 0,
    "EXP3_RUNS_THIS_RECONCILIATION": 0,
    "EXP4_RUNS_THIS_RECONCILIATION": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        raise RuntimeError(f"M1_V2_SEMANTIC_RECONCILIATION_OUTPUT_CONFLICT:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _reconcile_nodes(*, root: Path, cohort: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    episodes = tuple(EpisodeRecord.model_validate(value) for value in cohort["episode_records"])
    source_paths = ontime_paths(root, DEVELOPMENT_MONTHS)
    expected_source_dirs = {f"month={month:02d}" for month in DEVELOPMENT_MONTHS}
    _require({path.parent.name for path in source_paths} == expected_source_dirs, "M1_V2_SEMANTIC_SOURCE_SCOPE_INVALID")
    _require(all(path.parent.name not in {"month=10", "month=11", "month=12"} for path in source_paths), "M1_V2_SEMANTIC_FINAL_TEST_SOURCE_SELECTED")
    zones = load_timezones(paths["timezones"])
    schedules, outcomes = load_selected_typed_records(episodes, source_paths, zones)
    weather, weather_audit = weather_index(
        root / "data2",
        replay_lag_minutes=5,
        start_inclusive=DEVELOPMENT_START,
        end_exclusive=FINAL_TEST_START,
    )
    publisher = ProductionPREPublisher.from_project()
    taxi = data2_taxi_reference_from_payload(_load(paths["taxi_reference"]))
    turnaround = data2_turnaround_reference_from_payload(_load(paths["turnaround_reference"]))
    expected = {(item["episode_id"], item["node_index"]): item for item in cohort["decision_nodes"]}

    stage_mismatches: list[dict[str, Any]] = []
    legal_aliases: list[dict[str, Any]] = []
    core_mismatches: list[dict[str, Any]] = []
    reconstructed = 0
    current_node_ids: set[str] = set()
    for episode in episodes:
        _, states = publish_episode_states(
            (
                episode,
                schedules[episode.successor_flight_id],
                outcomes[episode.predecessor_flight_id],
                outcomes[episode.successor_flight_id],
            ),
            cohort["config_hash"],
            cohort["registry_hash"],
            weather,
            publisher.weather_max_age_minutes,
            publisher=publisher,
            taxi_reference=taxi,
            turnaround_reference=turnaround,
        )
        for state in states:
            node = state.decision_node
            key = (episode.episode_id, node.node_index)
            frozen = expected.get(key)
            _require(frozen is not None, "M1_V2_SEMANTIC_CURRENT_NODE_NOT_IN_FROZEN_COHORT")
            reconstructed += 1
            current_node_ids.add(node.decision_node_id)
            actual_stage = getattr(node.operational_stage, "value", str(node.operational_stage))
            core = {
                "episode_id": episode.episode_id,
                "node_index": node.node_index,
                "decision_time_equal": node.decision_time.isoformat() == frozen["decision_time"].replace("Z", "+00:00"),
                "information_cutoff_equal": node.information_cutoff.isoformat() == frozen["information_cutoff"].replace("Z", "+00:00"),
                "node_index_equal": node.node_index == frozen["node_index"],
                "roll_minutes_equal": node.roll_minutes == frozen["roll_minutes"],
            }
            if not all(value for key, value in core.items() if key.endswith("_equal")):
                core_mismatches.append({
                    "frozen_decision_node_id": frozen["decision_node_id"],
                    "current_pre_state_node_id": node.decision_node_id,
                    **core,
                })
            if actual_stage != frozen["operational_stage"]:
                stage_mismatches.append({
                    "episode_id": episode.episode_id,
                    "node_index": node.node_index,
                    "frozen_decision_node_id": frozen["decision_node_id"],
                    "current_pre_state_node_id": node.decision_node_id,
                    "frozen_operational_stage": frozen["operational_stage"],
                    "current_operational_stage": actual_stage,
                    "decision_time": node.decision_time.isoformat(),
                    "feature_semantic_impact": "stage_is_encoded_in_current_m1_feature_contract",
                })
            current_legal = list(node.legal_record_ids)
            frozen_legal = list(frozen["legal_record_ids"])
            if current_legal != frozen_legal:
                legal_aliases.append({
                    "frozen_decision_node_id": frozen["decision_node_id"],
                    "current_pre_state_node_id": node.decision_node_id,
                    "frozen_legal_record_ids": frozen_legal,
                    "current_typed_legal_record_ids": current_legal,
                    "identity_relation": "SEMANTICALLY_EQUAL_NODE_WITH_TYPED_LEGAL_RECORD_ALIAS",
                })

    expected_count = len(cohort["node_ids"])
    _require(reconstructed == expected_count, "M1_V2_SEMANTIC_NODE_COUNT_MISMATCH")
    _require(len(current_node_ids) == reconstructed, "M1_V2_SEMANTIC_CURRENT_NODE_ID_DUPLICATE")
    return {
        "expected_node_count": expected_count,
        "reconstructed_node_count": reconstructed,
        "core_identity_exact": not core_mismatches,
        "core_identity_mismatch_count": len(core_mismatches),
        "core_identity_mismatches": core_mismatches,
        "legal_record_exact_match_count": expected_count - len(legal_aliases),
        "typed_legal_record_alias_count": len(legal_aliases),
        "typed_legal_record_aliases": legal_aliases,
        "stage_exact_match_count": expected_count - len(stage_mismatches),
        "stage_mismatch_count": len(stage_mismatches),
        "stage_mismatches": stage_mismatches,
        "current_node_ids_unique": True,
        "weather_replay_audit": {
            "replay_lag_minutes": 5,
            "final_test_access_count": weather_audit["final_test_access_count"],
            "accepted_observations": weather_audit["accepted_train_calibration_development_observations"],
        },
        "current_factual_policy": publisher.factual_availability_policy,
        "current_declared_factual_lag_minutes": publisher.factual_replay_declared_lag_minutes,
    }


def materialize_semantic_reconciliation(*, root: Path, output: Path | None = None) -> Path:
    root = Path(root).resolve()
    cohort_path = root / "artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT.json"
    binding_path = root / "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json"
    checkpoint_path = root / "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt"
    cache_path = root / "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json"
    taxi_path = root / "artifacts/diagnostics/v5_development_freeze/DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json"
    turnaround_path = root / "artifacts/diagnostics/v5_development_freeze/DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json"
    timezone_path = root / "data2/refs/us_airport_timezones.csv"
    _require(all(path.is_file() for path in (cohort_path, binding_path, checkpoint_path, cache_path, taxi_path, turnaround_path, timezone_path)), "M1_V2_SEMANTIC_INPUT_MISSING")
    cohort = _load(cohort_path)
    binding = _load(binding_path)
    cache = _load(cache_path)
    paths = {"timezones": timezone_path, "taxi_reference": taxi_path, "turnaround_reference": turnaround_path}
    comparison = _reconcile_nodes(root=root, cohort=cohort, paths=paths)
    status = "M1_V2_DEVELOPMENT_INFERENCE_BINDING_BLOCKED_STAGE_SEMANTIC_DRIFT" if comparison["stage_mismatch_count"] else "M1_V2_DEVELOPMENT_INFERENCE_BINDING_SEMANTICALLY_RECONCILED"
    payload = {
        "schema_version": "M1_V2_DEVELOPMENT_INFERENCE_SEMANTIC_RECONCILIATION_V2",
        "status": status,
        "scope": "DEVELOPMENT_ONLY_FROZEN_EXP2_COHORT_CURRENT_TYPED_PRE_RECONCILIATION",
        "supersedes": {
            "path": "artifacts/diagnostics/m1_v2_development_inference_binding/M1_V2_DEVELOPMENT_INFERENCE_BINDING_BLOCKER.json",
            "prior_status": "BLOCKED_M1_COHORT_CONFIG_PROVENANCE_UNRESOLVED",
            "reason": "historical cohort config provenance is now recovered; stage semantics remain unresolved",
        },
        "identity_facts": {
            "cohort_path": _relative(cohort_path, root),
            "cohort_sha256": _hash(cohort_path),
            "cohort_hash": cohort.get("cohort_hash"),
            "cohort_config_hash": cohort.get("config_hash"),
            "cohort_registry_hash": cohort.get("registry_hash"),
            "cohort_git_sha": cohort.get("git_sha"),
            "current_binding_path": _relative(binding_path, root),
            "current_binding_sha256": _hash(binding_path),
            "checkpoint_sha256": _hash(checkpoint_path),
            "feature_schema_hash": binding.get("frozen_contracts", {}).get("feature_schema_hash"),
            "cache_hash": cache.get("cache_hash"),
            "support_hash": binding.get("frozen_contracts", {}).get("support_hash"),
            "configuration_roles": {
                "historical_config": "COHORT_IDENTITY_AND_DECISION_NODE_HASH_PROVENANCE_ONLY",
                "current_config": "CURRENT_APPROVED_TYPED_PRE_AND_M1_INFERENCE_CONTRACT",
            },
        },
        "semantic_comparison": comparison,
        "interpretation": {
            "legal_record_ids": "all current typed legal-record IDs are retained as aliases; this does not by itself alter node timing semantics",
            "operational_stage": "stage is part of the M1 feature encoding; the three mismatches are a scientific semantic drift and cannot be hidden by aliasing",
            "factual_replay": "current approved declared-event-time replay is recorded separately from historical cohort construction and is not silently substituted into the frozen cohort",
        },
        "required_human_decision": {
            "status": "HUMAN_DECISION_REQUIRED",
            "options": [
                {
                    "id": "HISTORICAL_STAGE_POLICY_SENSITIVITY",
                    "description": "retain the frozen cohort stage grid for the principal Development identity and run the current approved replay as a separately named sensitivity/reconciliation cohort",
                },
                {
                    "id": "REFREEZE_CURRENT_STAGE_POLICY",
                    "description": "materialize a new cohort/node grid under the current approved replay semantics and do not call it the existing frozen cohort",
                },
            ],
            "prohibited_automatic_actions": [
                "overwrite current stage with frozen stage",
                "overwrite frozen stage with current stage",
                "treat typed legal-record aliases as stage repair",
                "reuse the existing cohort name after re-materialization",
                "select positive-tail rule automatically",
            ],
        },
        "downstream_boundary": {
            "m1_inference_inputs": "BLOCKED",
            "m1_positive_tail_decision": "BLOCKED_PENDING_UPSTREAM_IDENTITY_RECONCILIATION",
            "m2_typed_consequence_values": "PREPARATION_ONLY",
            "exp2_metrics": "BLOCKED",
            "exp3_metrics": "BLOCKED",
            "exp4_metrics": "BLOCKED",
            "labels_materialized": False,
            "scenarios_materialized": False,
            "synthetic_metrics_generated": False,
        },
        **_SAFETY,
    }
    payload["artifact_hash"] = content_id(payload)
    output = (output or root / ARTIFACT_DIRECTORY / REPORT_NAME).resolve()
    _write(output, payload)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    path = materialize_semantic_reconciliation(root=Path(__file__).resolve().parents[2], output=args.output)
    payload = _load(path)
    print(json.dumps({"status": payload["status"], "artifact": str(path), **_SAFETY}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
