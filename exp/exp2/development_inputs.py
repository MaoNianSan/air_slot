"""Inference-only H16 Development scenario and M2 V4 materialization."""

from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from math import isclose
from pathlib import Path

import pandas as pd
import torch

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.coverage import active_node_prefixes
from model.M1.data import encode_pre_sequence
from model.M1.pipeline import M1Pipeline
from model.M1.scenario_layer.sampler import required_observations_v2
from model.M1.tail import load_tail_continuations
from model.M2.context import (
    AirportReferenceKeys,
    build_m2_v4_context,
    build_node_exposure_references,
    load_data2_reference_bundle,
)
from model.PRE.development import materialize_preselected_cohorts
from model.common.config import load_config_layers
from model.common.paths import PROJECT_ROOT

from model.M1.development_training import _load_references

from .common_support import identify_common_supported_scenarios
from .model_inputs import (
    active_model_contract,
    flatten_node,
    map_model_outputs,
    typed_m1_inputs,
)
from .protocol import COMPONENTS
from .reporting import write_frame, write_json


MODEL_ROOT = PROJECT_ROOT / "artifacts" / "models" / "m1"
H16_ROOT = MODEL_ROOT / "M1_H16_HISTORY_PRIMARY"
H16_MANIFEST = H16_ROOT / "M1_H16_HISTORY_PRIMARY_MANIFEST.json"
H16_CHECKPOINT = H16_ROOT / "M1_H16_HISTORY_PRIMARY.pt"
FORMAL_COHORT = MODEL_ROOT / "M1_FORMAL_TRAINING_COHORT_V1.json"
SOURCE_CACHE_ROOT = MODEL_ROOT / "M1_FROZEN_H16"
SOURCE_CACHE = SOURCE_CACHE_ROOT / "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3.npz"
SOURCE_CACHE_MANIFEST = (
    SOURCE_CACHE_ROOT / "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3_MANIFEST.json"
)
PREP_ROOT = PROJECT_ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"
PREP_STATE = PREP_ROOT / "M1_BASE_CACHE_PREPARATION_STATE.pt"
PREP_MANIFEST = PREP_ROOT / "M1_BASE_CACHE_PREPARATION_PROGRESS.json"
TAIL_MANIFEST = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "m1_positive_tail_continuation_v1"
    / "M1_POSITIVE_TAIL_CONTINUATION_V1.json"
)
PASSENGER_REF_ROOT = (
    PROJECT_ROOT / "artifacts" / "diagnostics" / "passenger_reference_freeze_v4"
)
OUTPUT = PROJECT_ROOT / "artifacts" / "experiment" / "exp2" / "development"
EXPECTED_SCENARIO_COUNT = 64
EXPECTED_DEVELOPMENT_EPISODES = 128
EXPECTED_CHECKPOINT_HASH = (
    "sha256:061c3540c38ad8272982590de437d27064d50b1e023b55b672e77392d2c4ac3b"
)
EXPECTED_DEVELOPMENT_COHORT_HASH = (
    "sha256:79c3dd9d47e3ec6f15f228213f69bf84f40e8b8f5b6bb7fbea390fbe5613af79"
)


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _reference_payloads() -> dict[str, dict]:
    return {
        "turnaround": _read_json(
            PREP_ROOT / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json"
        ),
        "taxi": _read_json(
            PREP_ROOT / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json"
        ),
        "downstream_exposure": _read_json(
            PREP_ROOT / "DATA2_DOWNSTREAM_EXPOSURE_REFERENCE_TRAIN_FROZEN_V1.json"
        ),
        "passenger": _read_json(
            PREP_ROOT / "DATA2_PASSENGER_REFERENCE_H1_TRAIN_FROZEN_V1.json"
        ),
        "expected_passengers": _read_json(
            PASSENGER_REF_ROOT / "T100_EXPECTED_PAX_PER_FLIGHT_REFERENCE.json"
        ),
        "connection_share": _read_json(
            PASSENGER_REF_ROOT / "DB1B_CONNECTION_SHARE_REFERENCE.json"
        ),
    }


def _observed(prepared, state) -> dict[str, object]:
    required = required_observations_v2(
        state.decision_node.operational_stage.value
    )
    observed: dict[str, object] = {}
    if "T_IB_A00" in required:
        observed["T_IB_A00"] = (
            prepared.predecessor_outcome.actual_arrival_utc.isoformat()
        )
    if "D_OB" in required:
        observed["D_OB"] = max(
            0.0,
            (
                prepared.successor_outcome.actual_departure_utc
                - prepared.successor_schedule.scheduled_departure_utc
            ).total_seconds()
            / 60.0,
        )
    return observed


def _destination(state) -> str:
    route = state.successor_state.get("route_context")
    value = None if route is None else route.value
    if not isinstance(value, dict) or not value.get("destination_airport_id"):
        raise RuntimeError("BLOCK_EXP2_M2_ROUTE_CONTEXT_MISSING")
    return str(value["destination_airport_id"])


def _load_authorities():
    required = (
        H16_MANIFEST,
        H16_CHECKPOINT,
        FORMAL_COHORT,
        SOURCE_CACHE,
        SOURCE_CACHE_MANIFEST,
        PREP_STATE,
        PREP_MANIFEST,
        TAIL_MANIFEST,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"BLOCK_EXP2_H16_ARTIFACT_MISSING:{missing}")
    manifest = _read_json(H16_MANIFEST)
    cohort = _read_json(FORMAL_COHORT)
    prep_manifest = _read_json(PREP_MANIFEST)
    if (
        manifest.get("model_role") != "PRIMARY"
        or manifest.get("model_version") != "M1_STATE_ESTIMATOR_V2_H16"
        or manifest.get("history_mode") != "FULL_ADAPTIVE_CAUSAL_PREFIX"
    ):
        raise RuntimeError("BLOCK_EXP2_ACTIVE_M1_NOT_H16_HISTORY_PRIMARY")
    if int(manifest.get("scenario_count", -1)) != EXPECTED_SCENARIO_COUNT:
        raise RuntimeError("BLOCK_EXP2_H16_SCENARIO_CONTRACT_MISMATCH")
    if manifest.get("checkpoint_hash") != EXPECTED_CHECKPOINT_HASH:
        raise RuntimeError("BLOCK_EXP2_H16_CHECKPOINT_LINEAGE_MISMATCH")
    if _file_hash(H16_CHECKPOINT) != EXPECTED_CHECKPOINT_HASH:
        raise RuntimeError("BLOCK_EXP2_H16_CHECKPOINT_HASH_MISMATCH")
    if manifest.get("development_cohort_hash") != EXPECTED_DEVELOPMENT_COHORT_HASH:
        raise RuntimeError("BLOCK_EXP2_H16_DEVELOPMENT_COHORT_MISMATCH")
    if cohort.get("development_episode_hash") != EXPECTED_DEVELOPMENT_COHORT_HASH:
        raise RuntimeError("BLOCK_EXP2_FORMAL_COHORT_HASH_MISMATCH")
    if int(cohort.get("development_episode_count", -1)) != EXPECTED_DEVELOPMENT_EPISODES:
        raise RuntimeError("BLOCK_EXP2_FORMAL_COHORT_COUNT_MISMATCH")
    if prep_manifest.get("completion_status") != "PASS":
        raise RuntimeError("BLOCK_EXP2_PREPARATION_NOT_COMPLETE")
    if any(
        int(payload.get("final_test_access_count", -1)) != 0
        for payload in (manifest, cohort, prep_manifest)
    ):
        raise RuntimeError("BLOCK_EXP2_FINAL_TEST_ACCESS_VIOLATION")
    cache_manifest = _read_json(SOURCE_CACHE_MANIFEST)
    cache = M1DevelopmentBaseCache.load(
        SOURCE_CACHE,
        SOURCE_CACHE_MANIFEST,
        expected_cache_key=cache_manifest["cache_key"],
        allow_legacy_schema=True,
    )
    return manifest, cohort, prep_manifest, cache


def materialize_h16_development_inputs(
    *, output: Path = OUTPUT, max_nodes: int | None = None
) -> dict[str, object]:
    """Create Development-only H16/M2 inputs without train or calibration calls."""
    manifest, cohort, prep_manifest, cache = _load_authorities()
    prep = torch.load(PREP_STATE, map_location="cpu", weights_only=False)
    reservoirs = prep.get("reservoirs", {})
    if reservoirs.get("test"):
        raise RuntimeError("BLOCK_EXP2_FINAL_TEST_EPISODE_MATERIALIZED")
    partitions = {
        name: tuple(sorted(reservoirs.get(name, ()), key=lambda row: row.episode_id))
        for name in ("train", "calibration", "development")
    }
    development_ids = tuple(row.episode_id for row in partitions["development"])
    if set(development_ids) != set(cohort["development_episode_ids"]):
        raise RuntimeError("BLOCK_EXP2_PREP_FORMAL_COHORT_ID_MISMATCH")
    if any(
        row.episode_start_time.date() < date(2019, 8, 1)
        or row.episode_end_time.date() >= date(2019, 10, 1)
        for row in partitions["development"]
    ):
        raise RuntimeError("BLOCK_EXP2_DEVELOPMENT_TEST_SEPARATION_FAILED")

    scientific = load_config_layers(PROJECT_ROOT / "configs").scientific
    taxi, turnaround, _ = _load_references(PROJECT_ROOT)
    cohorts = materialize_preselected_cohorts(
        scientific,
        root=PROJECT_ROOT,
        partitions=partitions,
        selection_audit={
            "preparation_state": str(PREP_STATE),
            "preparation_manifest": str(PREP_MANIFEST),
            "preparation_state_key": prep.get("state_key"),
            "preparation_completion_status": prep_manifest.get("completion_status"),
        },
        taxi_reference=taxi,
        turnaround_reference=turnaround,
    )

    expected_nodes = {
        node_id
        for node_id, split in zip(
            cache.store.sample_decision_node_ids, cache.store.sample_splits
        )
        if split == "development"
    }
    prepared_rows = []
    for prepared in cohorts.development:
        reference_minutes = None
        reference_id = None
        reference_hash = None
        lookup = taxi.lookup(prepared.episode.connection_airport_id)
        if (
            getattr(lookup, "value", None) is not None
            and getattr(getattr(lookup, "support_state", None), "value", None)
            == "SUPPORTED"
        ):
            reference_minutes = float(lookup.value)
            reference_id = taxi.reference_id
            reference_hash = taxi.manifest_freeze_id
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
            node_id = prefix[-1].decision_node.decision_node_id
            if node_id in expected_nodes:
                prepared_rows.append((prepared, prefix))
    prepared_rows.sort(
        key=lambda item: (
            item[0].episode.episode_id,
            item[1][-1].decision_node.decision_node_id,
        )
    )
    materialized_node_ids = {
        prefix[-1].decision_node.decision_node_id for _, prefix in prepared_rows
    }
    if materialized_node_ids != expected_nodes:
        raise RuntimeError("BLOCK_EXP2_H16_PRE_NODE_SET_MISMATCH")
    if max_nodes is not None:
        prepared_rows = prepared_rows[: int(max_nodes)]

    pipeline = M1Pipeline.load(H16_CHECKPOINT)
    tails = load_tail_continuations(TAIL_MANIFEST)
    pipeline.tail_continuations = tails
    bundle = load_data2_reference_bundle(_reference_payloads())
    frozen, registry, _ = active_model_contract()
    scenario_rows: list[dict[str, object]] = []
    node_rows: list[dict[str, object]] = []
    for prepared, prefix in prepared_rows:
        state = prefix[-1]
        node = state.decision_node
        values = encode_pre_sequence(prefix, pipeline.normalization)
        scenarios = pipeline.sample_from_pre(
            state,
            values.unsqueeze(0),
            torch.tensor([len(values)]),
            observed=_observed(prepared, state),
            count=EXPECTED_SCENARIO_COUNT,
            seed=int(manifest["training_seed"]),
            taxi_reference=taxi,
            tail_continuations=tails,
        )
        if (
            len(scenarios) != EXPECTED_SCENARIO_COUNT
            or len({row.scenario_id for row in scenarios}) != EXPECTED_SCENARIO_COUNT
            or not isclose(
                sum(float(row.scenario_weight) for row in scenarios),
                1.0,
                abs_tol=1e-6,
            )
        ):
            raise RuntimeError("BLOCK_EXP2_H16_SCENARIO_CONTRACT_MISMATCH")

        decision_time = node.decision_time
        keys = AirportReferenceKeys(
            connection_airport_id=prepared.episode.connection_airport_id,
            successor_destination_airport_id=_destination(state),
            carrier_id=None,
            month=decision_time.month,
            quarter=(decision_time.month - 1) // 3 + 1,
        )
        references = build_node_exposure_references(bundle, keys)
        context = build_m2_v4_context(
            bundle, keys, node_specific_exposure=references.airport
        )
        typed = typed_m1_inputs(
            scenarios,
            pre_lineage=(
                cohort["cohort_hash"],
                node.decision_node_id,
                manifest["artifact_hash"],
            ),
            reference_lineage=(
                _read_json(TAIL_MANIFEST)["artifact_hash"],
                frozen.registry_hash,
            ),
        )
        mapped = map_model_outputs(typed, context)
        support_records = identify_common_supported_scenarios(
            typed, mapped, registry
        )
        node_rows.append(
            flatten_node(
                typed,
                mapped,
                metadata={
                    "decision_time": node.decision_time.isoformat(),
                    "information_cutoff": node.information_cutoff.isoformat(),
                    "operational_stage": node.operational_stage.value,
                    "final_test_access_count": 0,
                },
            )
        )
        for typed_row, mapped_row, support_row in zip(
            typed, mapped, support_records
        ):
            scenario_payload = {
                "episode_id": typed_row.episode_id,
                "decision_node_id": typed_row.decision_node_id,
                "scenario_id": typed_row.scenario_id,
                "scenario_weight": typed_row.scenario_weight,
                "D_TO": typed_row.d_to_minutes,
                "D_TO_support": typed_row.d_to_support.value,
                "common_supported": support_row["common_supported"],
                "unsupported_reasons": "|".join(
                    support_row["unsupported_reasons"]
                ),
                "formal_scenario_status": support_row["formal_scenario_status"],
            }
            for component_row in mapped_row.component_vector.rows:
                component = component_row.component_id
                scenario_payload[f"{component}_native"] = (
                    component_row.native_quantity
                )
                scenario_payload[f"Z_{component}"] = (
                    component_row.constructed_value_cu
                )
                scenario_payload[f"{component}_support"] = (
                    component_row.support_state.value
                )
                scenario_payload[f"{component}_cu_status"] = (
                    component_row.cu_status.value
                )
            scenario_rows.append(scenario_payload)

    node_frame = pd.DataFrame(node_rows)
    scenario_frame = pd.DataFrame(scenario_rows)
    data_dir = output / "data"
    write_frame(data_dir / "EXP2_H16_M2_V4_NODE_INPUT.parquet", node_frame)
    write_frame(data_dir / "EXP2_COMMON_SUPPORT.parquet", scenario_frame)
    payload = {
        "schema_version": "EXP2_H16_DEVELOPMENT_INPUT_MANIFEST_V1",
        "status": "PASS",
        "artifact_scope": "DEVELOPMENT_ONLY",
        "m1_model_version": manifest["model_version"],
        "m1_checkpoint_hash": manifest["checkpoint_hash"],
        "m1_artifact_hash": manifest["artifact_hash"],
        "development_cohort_hash": cohort["development_episode_hash"],
        "development_episode_count": int(node_frame["episode_id"].nunique()),
        "decision_node_count": int(len(node_frame)),
        "scenario_count_per_node": EXPECTED_SCENARIO_COUNT,
        "scenario_count": int(len(scenario_frame)),
        "m2_registry_id": frozen.registry_id,
        "m2_registry_hash": frozen.registry_hash,
        "model_retrained": False,
        "calibration_refit": False,
        "parameter_reselected": False,
        "model_scientific_definition_changed": False,
        "final_test_access_count": 0,
        "paper_result": False,
        "max_nodes": max_nodes,
    }
    write_json(output / "contract" / "EXP2_DEVELOPMENT_INPUT_MANIFEST.json", payload)
    return payload


__all__ = ["materialize_h16_development_inputs"]
