"""Freeze PRE-owned states for the exact formal M1 Development cohort."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import torch

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.development_training import _load_references
from model.PRE.contracts.pre_state import PREState
from model.PRE.development import (
    development_input_identity,
    materialize_preselected_cohorts,
)
from model.common.config import load_config_layers
from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT


COHORT_PATH = (
    PROJECT_ROOT / "artifacts" / "models" / "m1" / "M1_FORMAL_TRAINING_COHORT_V1.json"
)
PREPARATION_ROOT = PROJECT_ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"
PREPARATION_STATE_PATH = PREPARATION_ROOT / "M1_BASE_CACHE_PREPARATION_STATE.pt"
PREPARATION_MANIFEST_PATH = PREPARATION_ROOT / "M1_BASE_CACHE_PREPARATION_PROGRESS.json"
CACHE_ROOT = PROJECT_ROOT / "artifacts" / "models" / "m1" / "M1_FROZEN_H16"
CACHE_PATH = CACHE_ROOT / "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3.npz"
CACHE_MANIFEST_PATH = CACHE_ROOT / "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3_MANIFEST.json"
OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "models" / "pre" / "PRE_FORMAL_DEVELOPMENT_V1"
STATES_PATH = OUTPUT_ROOT / "PRE_FORMAL_DEVELOPMENT_STATES.jsonl"
MANIFEST_PATH = OUTPUT_ROOT / "PRE_FORMAL_DEVELOPMENT_MANIFEST.json"
AUDIT_PATH = OUTPUT_ROOT / "PRE_FORMAL_DEVELOPMENT_AUDIT.json"
SPLITS = ("train", "calibration", "development")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_frozen_partitions(cohort: dict) -> tuple[dict[str, tuple], dict]:
    preparation_manifest = _read_json(PREPARATION_MANIFEST_PATH)
    if preparation_manifest.get("completion_status") != "PASS":
        raise RuntimeError("FORMAL_PRE_PREPARATION_NOT_COMPLETE")
    if preparation_manifest.get("final_test_access_count") != 0:
        raise RuntimeError("FORMAL_PRE_PREPARATION_FINAL_TEST_ACCESS_NONZERO")

    preparation = torch.load(
        PREPARATION_STATE_PATH, map_location="cpu", weights_only=False
    )
    reservoirs = preparation.get("reservoirs", {})
    if reservoirs.get("test"):
        raise RuntimeError("FORMAL_PRE_TEST_RESERVOIR_NOT_EMPTY")
    partitions = {
        split: tuple(sorted(reservoirs.get(split, ()), key=lambda item: item.episode_id))
        for split in SPLITS
    }
    mismatches = {}
    for split, episodes in partitions.items():
        actual = tuple(item.episode_id for item in episodes)
        expected = tuple(sorted(cohort[f"{split}_episode_ids"]))
        if actual != expected:
            mismatches[split] = {
                "missing": sorted(set(expected) - set(actual)),
                "unexpected": sorted(set(actual) - set(expected)),
            }
    if mismatches:
        raise RuntimeError(f"FORMAL_PRE_COHORT_ID_MISMATCH:{mismatches}")
    return partitions, preparation_manifest


def _cache_development_rows() -> tuple[tuple, dict]:
    manifest = _read_json(CACHE_MANIFEST_PATH)
    cache = M1DevelopmentBaseCache.load(
        CACHE_PATH,
        CACHE_MANIFEST_PATH,
        expected_cache_key=manifest["cache_key"],
    )
    return tuple(cache.partition("development", representation="ADAPTIVE_HISTORY")), manifest


def _serialize_states(states: tuple[PREState, ...], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for state in states:
            payload = state.model_dump(mode="json")
            PREState.model_validate(payload)
            stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            stream.write("\n")
    temporary.replace(path)
    return _file_hash(path)


def _availability_violations(states: tuple[PREState, ...]) -> list[dict]:
    violations = []
    for state in states:
        decision_time = state.decision_node.decision_time
        entries = (*state.evidence_ledger, *state.variable_lineage)
        for entry in entries:
            availability_time = entry.availability_time
            if availability_time is not None and availability_time > decision_time:
                violations.append(
                    {
                        "episode_id": state.decision_node.episode_id,
                        "decision_node_id": state.decision_node.decision_node_id,
                        "availability_time": availability_time.isoformat(),
                        "decision_time": decision_time.isoformat(),
                        "source_record_id": entry.source_record_id,
                    }
                )
    return violations


def materialize(output_root: Path = OUTPUT_ROOT) -> dict:
    cohort = _read_json(COHORT_PATH)
    if (
        cohort["development_episode_count"] != 128
        or cohort["final_test_episode_count"] != 0
        or cohort["final_test_access_count"] != 0
    ):
        raise RuntimeError("FORMAL_PRE_COHORT_CONTRACT_INVALID")

    partitions, preparation_manifest = load_frozen_partitions(cohort)
    cache_rows, cache_manifest = _cache_development_rows()
    scientific = load_config_layers(PROJECT_ROOT / "configs").scientific
    taxi, turnaround, reference_identity = _load_references(PROJECT_ROOT)
    source_identity = development_input_identity(PROJECT_ROOT)
    node_identity_config_hash = cache_manifest["audit"]["config_hash"]
    if node_identity_config_hash != source_identity["config_hash"]:
        raise RuntimeError(
            "FORMAL_PRE_CACHE_CONFIG_IDENTITY_MISMATCH:"
            f"cache={node_identity_config_hash}:current={source_identity['config_hash']}"
        )
    cohorts = materialize_preselected_cohorts(
        scientific,
        root=PROJECT_ROOT,
        partitions=partitions,
        selection_audit={
            "formal_cohort_id": cohort["cohort_id"],
            "formal_cohort_hash": cohort["cohort_hash"],
            "selection_reperformed": False,
            "selection_seed": cohort["selection_seed"],
            "selection_pre_outcome": cohort["selection_pre_outcome"],
            "source_preparation_artifact": str(PREPARATION_STATE_PATH),
        },
        taxi_reference=taxi,
        turnaround_reference=turnaround,
    )

    states = tuple(
        sorted(
            (state for episode in cohorts.development for state in episode.states),
            key=lambda state: (
                state.decision_node.episode_id,
                state.decision_node.decision_time,
                state.decision_node.decision_node_id,
            ),
        )
    )
    if not states:
        raise RuntimeError("FORMAL_PRE_DEVELOPMENT_STATES_EMPTY")
    node_keys = tuple(
        (state.decision_node.episode_id, state.decision_node.decision_node_id)
        for state in states
    )
    unique_keys = set(node_keys)
    if len(unique_keys) != len(node_keys):
        raise RuntimeError("FORMAL_PRE_DUPLICATE_NODE_KEY")

    pre_episode_ids = {state.decision_node.episode_id for state in states}
    expected_episode_ids = set(cohort["development_episode_ids"])
    missing_episode_ids = sorted(expected_episode_ids - pre_episode_ids)
    unexpected_episode_ids = sorted(pre_episode_ids - expected_episode_ids)
    episode_ids_exact_match = not missing_episode_ids and not unexpected_episode_ids
    if not episode_ids_exact_match:
        raise RuntimeError("FORMAL_PRE_DEVELOPMENT_EPISODE_ID_MISMATCH")

    final_test_nodes = [
        key
        for key, state in zip(node_keys, states)
        if state.decision_node.decision_time.date().isoformat() >= "2019-10-01"
    ]
    if final_test_nodes:
        raise RuntimeError("FINAL_TEST_DATE_IN_FORMAL_DEVELOPMENT_PRE")

    availability_violations = _availability_violations(states)
    if availability_violations:
        raise RuntimeError("FORMAL_PRE_CAUSAL_AVAILABILITY_VIOLATION")

    nodes_by_episode = {
        episode.episode.episode_id: tuple(episode.nodes)
        for episode in cohorts.development
    }
    state_node_ids = {
        state.decision_node.decision_node_id for state in states
    }
    alignment_errors = []
    matched_node_count = 0
    for row in cache_rows:
        episode_nodes = nodes_by_episode.get(row.episode_id, ())
        # ADAPTIVE_HISTORY ends at the current node. The cache stores the
        # prefix length, so recover that node by its final history position.
        node_position = len(row.values) - 1
        if node_position < 0 or node_position >= len(episode_nodes):
            alignment_errors.append(
                {
                    "episode_id": row.episode_id,
                    "decision_node_id": row.decision_node_id,
                    "node_position": node_position,
                    "prestate_count": len(episode_nodes),
                    "reason": "CACHE_HISTORY_POSITION_OUT_OF_RANGE",
                }
            )
            continue
        node = episode_nodes[node_position]
        if node.decision_node_id != row.decision_node_id:
            alignment_errors.append(
                {
                    "episode_id": row.episode_id,
                    "decision_node_id": row.decision_node_id,
                    "prestate_decision_node_id": node.decision_node_id,
                    "node_position": node_position,
                    "decision_time": node.decision_time.isoformat(),
                    "reason": "CACHE_PRESTATE_NODE_ID_MISMATCH",
                }
            )
        else:
            matched_node_count += 1
    if alignment_errors:
        first_state = states[0].decision_node
        raise RuntimeError(
            "PRE_M1_NODE_ALIGNMENT_FAIL:"
            f"cache={len(cache_rows)}:pre={len(unique_keys)}:"
            f"mismatches={len(alignment_errors)}:"
            f"state_config={first_state.config_hash}:"
            f"state_registry={first_state.registry_manifest_hash}:"
            f"sample={alignment_errors[:5]}"
        )

    states_path = output_root / STATES_PATH.name
    states_hash = _serialize_states(states, states_path)
    decision_node_hash = content_id(
        {"node_keys": [f"{episode_id}|{node_id}" for episode_id, node_id in node_keys]}
    )
    audit = {
        "schema_version": "PRE_FORMAL_DEVELOPMENT_AUDIT_V1",
        "artifact_scope": "FORMAL_DEVELOPMENT_PRESTATE_FREEZE",
        "status": "PASS",
        "episode_ids_exact_match": episode_ids_exact_match,
        "missing_episode_ids": missing_episode_ids,
        "unexpected_episode_ids": unexpected_episode_ids,
        "development_episode_count": len(pre_episode_ids),
        "prestate_count": len(states),
        "unique_node_count": len(unique_keys),
        "node_keys_unique": len(unique_keys) == len(states),
        "decision_node_hash": decision_node_hash,
        "split_integrity": True,
        "causal_availability_check": True,
        "causal_availability_violations": availability_violations,
        "prestate_roundtrip_validation": True,
        "cache_node_count": len(cache_rows),
        "matched_node_count": matched_node_count,
        "cache_nodes_missing_prestate": len(alignment_errors),
        "cache_nodes_missing_prestate_keys": alignment_errors,
        "m1_cache_node_alignment": "PASS",
        "prestate_node_identity_matches_published_nodes": (
            state_node_ids
            == {
                node.decision_node_id
                for episode in cohorts.development
                for node in episode.nodes
            }
        ),
        "selection_reperformed": False,
        "test_episode_materialized": False,
        "final_test_episode_count": 0,
        "final_test_access_count": 0,
        "paper_result": False,
        "formal_exp1_execution": False,
    }
    audit_path = output_root / AUDIT_PATH.name
    _write_json(audit_path, audit)

    weather_identity = {
        "replay_lag_minutes": int(
            scientific.parameters["data2_weather_replay_lag_minutes"].value
        ),
        "max_age_minutes": int(scientific.parameters["weather_max_age_minutes"].value),
        "publication_audit": cohorts.audit["weather"],
    }
    manifest = {
        "schema_version": "PRE_FORMAL_DEVELOPMENT_MANIFEST_V1",
        "artifact_id": "PRE_FORMAL_DEVELOPMENT_V1",
        "artifact_scope": "FORMAL_DEVELOPMENT_PRESTATE_FREEZE",
        "status": "PASS",
        "formal_cohort_id": cohort["cohort_id"],
        "formal_cohort_hash": cohort["cohort_hash"],
        "development_episode_count": len(pre_episode_ids),
        "development_episode_hash": cohort["development_episode_hash"],
        "prestate_count": len(states),
        "decision_node_hash": decision_node_hash,
        "selection_reperformed": False,
        "selection_seed": cohort["selection_seed"],
        "selection_pre_outcome": cohort["selection_pre_outcome"],
        "pre_config_hash": source_identity["config_hash"],
        "node_identity_config_hash": node_identity_config_hash,
        "pre_registry_hash": source_identity["registry_hash"],
        "source_manifest_hash": source_identity["source_manifest_hash"],
        "weather_replay": weather_identity,
        "taxi_reference": {
            "reference_id": reference_identity["taxi_reference_id"],
            "reference_hash": reference_identity["taxi_reference_hash"],
            "artifact_hash": reference_identity["taxi_artifact_hash"],
        },
        "turnaround_reference": {
            "reference_id": reference_identity["turnaround_reference_id"],
            "reference_hash": reference_identity["turnaround_reference_hash"],
            "artifact_hash": reference_identity["turnaround_artifact_hash"],
        },
        "source_preparation_artifact": {
            "path": str(PREPARATION_STATE_PATH),
            "sha256": _file_hash(PREPARATION_STATE_PATH),
            "manifest_path": str(PREPARATION_MANIFEST_PATH),
            "manifest_sha256": _file_hash(PREPARATION_MANIFEST_PATH),
            "state_key": preparation_manifest["state_key"],
        },
        "m1_cache": {
            "path": str(CACHE_PATH),
            "cache_hash": cache_manifest["cache_hash"],
            "development_node_count": len(cache_rows),
        },
        "states_path": str(states_path),
        "states_sha256": states_hash,
        "audit_path": str(audit_path),
        "audit_sha256": _file_hash(audit_path),
        "final_test_episode_count": 0,
        "final_test_access_count": 0,
        "paper_result": False,
        "formal_exp1_execution": False,
    }
    manifest["artifact_hash"] = content_id(manifest)
    _write_json(output_root / MANIFEST_PATH.name, manifest)
    return {"manifest": manifest, "audit": audit}


def main() -> int:
    print(json.dumps(materialize(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
