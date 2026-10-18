"""Materialize a bounded Development-only H8 scenario smoke artifact."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

import torch

from model.M1.data import encode_pre_sequence
from model.M1.pipeline import M1Pipeline
from model.M1.coverage import active_node_prefixes
from model.M1.scenario_layer.sampler import required_observations_v2
from model.M1.tail import load_tail_continuations
from model.PRE.development import materialize_preselected_cohorts
from model.common.config import load_config_layers
from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT

from model.M1.development_training import _load_fast_config, _load_references


CHECKPOINT = PROJECT_ROOT / "artifacts/models/m1/M1_FROZEN_H8/DATA2_M1_V2_DEVELOPMENT_FAST.pt"
TAIL_MANIFEST = PROJECT_ROOT / "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_POSITIVE_TAIL_CONTINUATION_V1.json"
OUTPUT = PROJECT_ROOT / "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_FROZEN_H8_DEVELOPMENT_SCENARIOS.json"
PREPARATION_STATE = PROJECT_ROOT / "artifacts/diagnostics/v5_development_freeze/M1_BASE_CACHE_PREPARATION_STATE.pt"
PREPARATION_MANIFEST = PROJECT_ROOT / "artifacts/diagnostics/v5_development_freeze/M1_BASE_CACHE_PREPARATION_PROGRESS.json"
SMOKE_PREPARATION_STATE = PROJECT_ROOT / "artifacts/models/m1/M1_FROZEN_H8/SMOKE_PREP.pt"
SMOKE_PREPARATION_MANIFEST = PROJECT_ROOT / "artifacts/models/m1/M1_FROZEN_H8/SMOKE_PREP.json"


def _observed(item, state):
    required = required_observations_v2(state.decision_node.operational_stage.value)
    observed = {}
    if "T_IB_A00" in required:
        observed["T_IB_A00"] = item.predecessor_outcome.actual_arrival_utc.isoformat()
    if "D_OB" in required:
        observed["D_OB"] = max(
            0.0,
            (
                item.successor_outcome.actual_departure_utc
                - item.successor_schedule.scheduled_departure_utc
            ).total_seconds()
            / 60.0,
        )
    if "D_TX" in required:
        # D_TX is not observed before completion in the formal PRE state.
        pass
    return observed


def materialize(output: Path = OUTPUT, *, max_nodes: int = 8, count: int = 64) -> dict:
    if not CHECKPOINT.is_file() or not TAIL_MANIFEST.is_file():
        raise FileNotFoundError("M1_H8_CHECKPOINT_OR_TAIL_ARTIFACT_MISSING")
    config, _ = _load_fast_config(PROJECT_ROOT)
    scientific = load_config_layers(PROJECT_ROOT / "configs").scientific
    taxi, turnaround, _ = _load_references(PROJECT_ROOT)
    if not SMOKE_PREPARATION_STATE.is_file() or not SMOKE_PREPARATION_MANIFEST.is_file():
        raise FileNotFoundError("M1_H8_SMOKE_PREPARATION_ARTIFACT_MISSING")
    smoke_manifest = json.loads(SMOKE_PREPARATION_MANIFEST.read_text(encoding="utf-8"))
    if smoke_manifest.get("completion_status") != "PASS":
        raise RuntimeError("M1_H8_SMOKE_PREPARATION_NOT_COMPLETE")
    prep_payload = torch.load(SMOKE_PREPARATION_STATE, map_location="cpu", weights_only=False)
    reservoirs = prep_payload.get("reservoirs", {})
    if any(reservoirs.get(name) for name in ("test",)):
        raise RuntimeError("FINAL_TEST_EPISODE_MATERIALIZED")
    if len(reservoirs.get("development", ())) < 1:
        raise RuntimeError("M1_H8_SMOKE_DEVELOPMENT_RESERVOIR_EMPTY")
    # SMOKE_PREP is a completed Development-only selection artifact. Re-publish
    # its episode identities under the active PRE contracts before M1 sampling.
    partitions = {
        name: tuple(reservoirs.get(name, ()))
        for name in ("train", "calibration", "development")
    }
    cohorts = materialize_preselected_cohorts(
        scientific,
        root=PROJECT_ROOT,
        partitions=partitions,
        selection_audit={
            "preparation_state": str(SMOKE_PREPARATION_STATE),
            "preparation_manifest": str(SMOKE_PREPARATION_MANIFEST),
            "preparation_state_key": prep_payload.get("state_key"),
            "preparation_completion_status": smoke_manifest.get("completion_status"),
            "base_cohort_counts": {
                "train": len(partitions["train"]),
                "calibration": len(partitions["calibration"]),
                "development": len(partitions["development"]),
            },
        },
        taxi_reference=taxi,
        turnaround_reference=turnaround,
    )
    # Keep the prepared wrapper here: active_rows() projects to EpisodeRecord,
    # while this materializer also needs the frozen predecessor/successor
    # outcomes to construct stage-gated observed labels.
    rows = []
    for prepared in cohorts.development:
        reference_minutes = None
        reference_id = None
        reference_hash = None
        if taxi is not None:
            lookup = taxi.lookup(prepared.episode.connection_airport_id)
            if (
                getattr(lookup, "value", None) is not None
                and getattr(getattr(lookup, "support_state", None), "value", None)
                == "SUPPORTED"
            ):
                reference_minutes = float(lookup.value)
                reference_id = getattr(taxi, "reference_id", None)
                reference_hash = getattr(taxi, "manifest_freeze_id", None)
        for _, prefix, _ in active_node_prefixes(
            episode=prepared.episode,
            nodes=prepared.nodes,
            states=prepared.states,
            successor_schedule=prepared.successor_schedule,
            predecessor_outcome=prepared.predecessor_outcome,
            successor_outcome=prepared.successor_outcome,
            taxi_reference_minutes=reference_minutes,
            taxi_reference_id=reference_id,
            taxi_reference_hash=reference_hash,
        ):
            rows.append((prepared, prefix))
    rows = tuple(
        sorted(
            rows,
            key=lambda item: (
                item[0].episode.episode_id,
                item[1][-1].decision_node.decision_node_id,
            ),
        )[: int(max_nodes)]
    )
    tails = load_tail_continuations(TAIL_MANIFEST)
    pipeline = M1Pipeline.load(CHECKPOINT)
    pipeline.tail_continuations = tails
    scenarios = []
    node_records = []
    for prepared, prefix in rows:
        item = prepared.episode
        state = prefix[-1]
        observed = _observed(prepared, state)
        values = encode_pre_sequence(prefix, pipeline.normalization)
        kwargs = dict(
            observed=observed,
            count=int(count),
            seed=int(config["training"]["seed"]),
            taxi_reference=taxi,
            tail_continuations=tails,
        )
        first = pipeline.sample_from_pre(state, values.unsqueeze(0), torch.tensor([len(values)]), **kwargs)
        second = pipeline.sample_from_pre(state, values.unsqueeze(0), torch.tensor([len(values)]), **kwargs)
        first_dump = [row.model_dump(mode="json") for row in first]
        second_dump = [row.model_dump(mode="json") for row in second]
        if first_dump != second_dump:
            raise RuntimeError("M1_H8_SCENARIO_DETERMINISM_FAILED")
        scenarios.extend(first_dump)
        node_records.append(
            {
                "episode_id": item.episode_id,
                "decision_node_id": state.decision_node.decision_node_id,
                "operational_stage": state.decision_node.operational_stage.value,
                "connection_airport_id": item.connection_airport_id,
                "successor_destination_airport_id": state.successor_state.get("route_context").value.get("destination_airport_id")
                if state.successor_state.get("route_context") is not None
                and isinstance(state.successor_state.get("route_context").value, dict)
                else "UNKNOWN",
                "scenario_count": len(first_dump),
                "positive_tail_draws": sum(bool(row["positive_tail_used"]) for row in first_dump),
                "overflow_draws": sum(
                    bool(row["overflow_d_ob"] or row["overflow_d_tx"])
                    for row in first_dump
                ),
            }
        )
    payload_base = {
        "schema_version": "M1_FROZEN_H8_DEVELOPMENT_SCENARIOS_V1",
        "artifact_id": "M1_FROZEN_H8_DEVELOPMENT_SCENARIOS",
        "artifact_scope": "DEVELOPMENT_ONLY_SMOKE",
        "checkpoint_path": str(CHECKPOINT),
        "checkpoint_hash": f"sha256:{__import__('hashlib').sha256(CHECKPOINT.read_bytes()).hexdigest()}",
        "tail_manifest_path": str(TAIL_MANIFEST),
        "tail_manifest_hash": json.loads(TAIL_MANIFEST.read_text(encoding="utf-8"))["artifact_hash"],
        "preparation_manifest_path": str(SMOKE_PREPARATION_MANIFEST),
        "preparation_manifest_hash": content_id(smoke_manifest),
        "fit_partition": {"train_start": "2019-01-01", "train_end": "2019-06-30"},
        "development_smoke": {"max_nodes": int(max_nodes), "nodes": len(node_records)},
        "scenario_count_per_node": int(count),
        "scenario_count": len(scenarios),
        "nodes": node_records,
        "scenarios": scenarios,
        "final_test_access_count": 0,
        "model_retrained": False,
        "parameter_reselected": False,
        "experiment_created": False,
    }
    payload = dict(payload_base)
    payload["artifact_hash"] = content_id(payload_base)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "path": str(output),
        "artifact_hash": payload["artifact_hash"],
        "nodes": len(node_records),
        "scenario_count_per_node": int(count),
        "scenario_count": len(scenarios),
        "positive_tail_draws": sum(row["positive_tail_draws"] for row in node_records),
        "overflow_draws": sum(row["overflow_draws"] for row in node_records),
        "final_test_access_count": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--max-nodes", type=int, default=8)
    parser.add_argument("--count", type=int, default=64)
    args = parser.parse_args()
    print(json.dumps(materialize(args.output, max_nodes=args.max_nodes, count=args.count), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

