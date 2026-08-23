"""Materialize M2 consequence representations from current-stage M1 scenarios.

The seven-component ontology is preserved exactly.  The five components with
the frozen ``M2_DATA2_FORMAL_CU_V1`` normalization receive constructed loss
units when their inputs are supported.  ``P_itinerary`` and ``P_service``
remain typed ABSTAIN, so this artifact never presents the unresolved V2
seven-component aggregate as a formal scalar.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from model.M2.context import (
    AirportReferenceKeys,
    build_m2_context,
    build_m2_frozen_scope,
    load_data2_reference_bundle,
)
from model.M2.contracts import M2ScenarioInput
from model.M2.freeze import FrozenData2CUNormalizationRegistry, load_m2_registry
from model.M2.mapper import M2Mapper
from model.common.enums import SupportState
from model.common.identity import content_id


M1_ARTIFACT = Path(
    "artifacts/experiment/m1_v2_current_stage_scenarios_v4/"
    "M1_V2_CURRENT_STAGE_TYPED_JOINT_SCENARIOS.json"
)
M1_MANIFEST = Path(
    "artifacts/experiment/m1_v2_current_stage_scenarios_v4/"
    "M1_V2_CURRENT_STAGE_TYPED_JOINT_SCENARIO_MANIFEST.json"
)
PRE_INPUTS = Path(
    "artifacts/diagnostics/m1_v2_development_current_stage_refreeze_v3/"
    "M1_V2_CURRENT_STAGE_DEVELOPMENT_INFERENCE_INPUTS.json"
)
M2_REGISTRY = Path("registries/m2_data2_formal_cu_v1.json")
M2_DESIGN = Path("registries/m2_v2_design.json")
REFERENCE_ROOT = Path("artifacts/diagnostics/v5_development_freeze")
DEFAULT_OUTPUT = Path("artifacts/experiment/m2_v2_current_stage_consequences_v1")

REFERENCE_FILES = {
    "turnaround": "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json",
    "taxi": "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json",
    "downstream_exposure": "DATA2_DOWNSTREAM_EXPOSURE_REFERENCE_TRAIN_FROZEN_V1.json",
    "passenger": "DATA2_PASSENGER_REFERENCE_H1_TRAIN_FROZEN_V1.json",
}

SAFETY = {
    "M1_TRAINING_RUNS_THIS_MATERIALIZATION": 0,
    "TUNING_RUNS_THIS_MATERIALIZATION": 0,
    "EXP2_RUNS_THIS_MATERIALIZATION": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"M2_V2_CONSEQUENCE_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _node_airports(pre_inputs: dict[str, Any]) -> dict[str, AirportReferenceKeys]:
    result: dict[str, AirportReferenceKeys] = {}
    for states in pre_inputs["pre_states_by_episode"].values():
        for state in states:
            node_id = state["decision_node"]["decision_node_id"]
            schedule = state["successor_state"].get("schedule_reference", {}).get("value")
            _require(isinstance(schedule, dict), "M2_V2_NODE_SCHEDULE_REFERENCE_MISSING")
            origin = schedule.get("origin_airport_id")
            destination = schedule.get("destination_airport_id")
            _require(bool(origin and destination), "M2_V2_NODE_AIRPORT_KEYS_MISSING")
            result[node_id] = AirportReferenceKeys(
                connection_airport_id=str(origin),
                successor_destination_airport_id=str(destination),
            )
    return result


def _m2_input(row: dict[str, Any], reference_lineage: tuple[str, ...]) -> M2ScenarioInput:
    envelopes = {item["target_name"]: item for item in row["target_envelopes"]}

    def scalar(target: str) -> float | None:
        value = envelopes[target]["scalar_minutes"]
        return None if value is None else float(value)

    def support(target: str) -> SupportState:
        return (
            SupportState.SUPPORTED
            if envelopes[target]["scalar_support_state"] == "SUPPORTED"
            else SupportState.ABSTAIN
        )

    t_ib = envelopes["T_IB_A00"]
    return M2ScenarioInput(
        episode_id=row["episode_id"],
        decision_node_id=row["decision_node_id"],
        scenario_id=row["scenario_id"],
        scenario_weight=row["scenario_weight"],
        t_ib_a00_utc=t_ib.get("event_time_utc") or t_ib.get("raw_observed_time_utc"),
        r_ib_minutes=scalar("T_IB_A00"),
        d_ob_minutes=scalar("D_OB"),
        d_tx_minutes=scalar("D_TX"),
        d_to_minutes=row["D_TO"],
        r_ib_support=support("T_IB_A00"),
        d_ob_support=support("D_OB"),
        d_tx_support=support("D_TX"),
        d_to_support=(SupportState.SUPPORTED if row["D_TO"] is not None else SupportState.ABSTAIN),
        pre_lineage=tuple(row["lineage"]),
        reference_lineage=reference_lineage,
        m1_scenario_seed_key=row["scenario_seed_key"],
    )


def _compact(consequence: Any) -> dict[str, Any]:
    components = []
    channels: dict[str, list[Any]] = defaultdict(list)
    for item in consequence.component_vector.rows:
        row = {
            "component_id": item.component_id,
            "aspect": item.aspect,
            "native_quantity": item.native_quantity,
            "native_unit": item.native_unit,
            "constructed_value_cu": item.constructed_value_cu,
            "support_state": item.support_state.value,
            "cu_status": item.cu_status.value,
            "reason_code": item.reason_code,
            "native_artifact_id": item.native_artifact_id,
            "cu_artifact_id": item.cu_artifact_id,
            "reference_lineage": list(item.reference_lineage),
        }
        components.append(row)
        channels[item.aspect].append(item)
    channel_values = []
    for aspect in ("Flight", "Passenger", "Resource"):
        members = channels[aspect]
        supported = all(item.constructed_value_cu is not None for item in members)
        channel_values.append({
            "channel_id": aspect,
            "component_ids": [item.component_id for item in members],
            "value_cu": (
                sum(float(item.constructed_value_cu) for item in members)
                if supported else None
            ),
            "support_state": "SUPPORTED" if supported else "ABSTAIN",
            "reason_code": None if supported else "CHANNEL_CONTAINS_UNSUPPORTED_COMPONENT",
        })
    seven_supported = all(item.constructed_value_cu is not None for item in consequence.component_vector.rows)
    return {
        "episode_id": consequence.episode_id,
        "decision_node_id": consequence.decision_node_id,
        "scenario_id": consequence.scenario_id,
        "scenario_weight": consequence.scenario_weight,
        "components": components,
        "channels": channel_values,
        "formal_five_component_value_cu": consequence.formal_estimand_value.value_cu,
        "formal_five_component_status": consequence.formal_estimand_value.status.value,
        "formal_five_component_reason": consequence.formal_estimand_value.reason_code,
        "seven_component_value_cu": (
            sum(float(item.constructed_value_cu) for item in consequence.component_vector.rows)
            if seven_supported else None
        ),
        "seven_component_status": "SUPPORTED" if seven_supported else "ABSTAIN",
        "seven_component_reason": None if seven_supported else "P_ITINERARY_AND_P_SERVICE_NOT_FROZEN",
        "consequence_artifact_id": consequence.consequence_artifact_id,
        "m1_scenario_seed_key": consequence.m1_scenario_seed_key,
    }


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    paths = {
        "m1_artifact": root / M1_ARTIFACT,
        "m1_manifest": root / M1_MANIFEST,
        "pre_inputs": root / PRE_INPUTS,
        "m2_registry": root / M2_REGISTRY,
        "m2_design": root / M2_DESIGN,
        **{
            name: root / REFERENCE_ROOT / filename
            for name, filename in REFERENCE_FILES.items()
        },
    }
    _require(all(path.is_file() for path in paths.values()), "M2_V2_MATERIALIZATION_INPUT_MISSING")
    m1 = _load(paths["m1_artifact"])
    m1_manifest = _load(paths["m1_manifest"])
    pre_inputs = _load(paths["pre_inputs"])
    design = _load(paths["m2_design"])
    _require(m1_manifest["artifact_hash"] == m1["artifact_hash"], "M2_V2_M1_ARTIFACT_HASH_MISMATCH")
    _require(m1["scope"] == "DATA2_DEVELOPMENT_CURRENT_STAGE_V3_NO_FINAL_TEST", "M2_V2_M1_SCOPE_INVALID")
    _require(design["formal_aggregate_status"] == "FORMAL_AGGREGATE_UNRESOLVED", "M2_V2_DESIGN_AGGREGATE_STATUS_DRIFT")
    references = {name: _load(paths[name]) for name in REFERENCE_FILES}
    bundle = load_data2_reference_bundle(references)
    registry = load_m2_registry(paths["m2_registry"])
    mapper = M2Mapper(
        FrozenData2CUNormalizationRegistry(registry),
        build_m2_frozen_scope(registry.model_dump()),
    )
    node_airports = _node_airports(pre_inputs)
    by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in m1["rows"]:
        by_node[row["decision_node_id"]].append(row)
    _require(set(by_node) == set(node_airports), "M2_V2_NODE_SET_MISMATCH")
    reference_lineage = tuple(bundle.reference_ids.values())
    consequence_rows: list[dict[str, Any]] = []
    component_support: dict[str, Counter[str]] = defaultdict(Counter)
    formal_status = Counter()
    seven_status = Counter()
    for node_id, source_rows in by_node.items():
        context = build_m2_context(bundle, node_airports[node_id])
        inputs = tuple(_m2_input(row, reference_lineage) for row in source_rows)
        outputs = mapper.map_m1_scenarios(inputs, context)
        for output in outputs:
            compact = _compact(output)
            consequence_rows.append(compact)
            formal_status[compact["formal_five_component_status"]] += 1
            seven_status[compact["seven_component_status"]] += 1
            for component in compact["components"]:
                component_support[component["component_id"]][component["support_state"]] += 1
    _require(len(consequence_rows) == m1["row_count"], "M2_V2_SCENARIO_COUNT_MISMATCH")
    payload = {
        "schema_version": "M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCE_ARTIFACT_V1",
        "status": "M2_V2_SEVEN_COMPONENT_REPRESENTATION_MATERIALIZED_WITH_TYPED_ABSTENTION",
        "scope": "DATA2_DEVELOPMENT_CURRENT_STAGE_V3",
        "source_m1_artifact_hash": m1["artifact_hash"],
        "source_m1_scenario_count_per_node": m1["scenario_count_per_node"],
        "m2_design": {
            "design_id": design["design_id"],
            "version": design["version"],
            "formal_aggregate_status": design["formal_aggregate_status"],
        },
        "cu_normalization": {
            "registry_id": registry.registry_id,
            "registry_hash": registry.registry_hash,
            "registry_path": str(M2_REGISTRY).replace("\\", "/"),
            "role": "FIVE_SUPPORTED_COMPONENTS_ONLY_NOT_V2_SEVEN_COMPONENT_PROMOTION",
        },
        "component_order": list(design["component_order"]),
        "formally_valued_components": list(registry.formal_scope),
        "typed_abstain_components": list(registry.outside_principal_scope),
        "consequences": consequence_rows,
        "row_count": len(consequence_rows),
        "node_count": len(by_node),
        "component_support_counts": {
            key: dict(value) for key, value in component_support.items()
        },
        "formal_five_component_status_counts": dict(formal_status),
        "seven_component_status_counts": dict(seven_status),
        "monetary_claim": False,
        "monetary_mapping_owner": "M4_ONLY",
        "zero_fill": False,
        "silent_renormalization": False,
        "safety": SAFETY,
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCES.json"
    _write(artifact_path, payload)
    manifest = {
        "schema_version": "M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCE_MANIFEST_V1",
        "status": "M2_V2_CONSEQUENCE_ARTIFACT_MATERIALIZED",
        "artifact": str(artifact_path.relative_to(root)).replace("\\", "/"),
        "artifact_hash": payload["artifact_hash"],
        "source_m1_artifact_hash": m1["artifact_hash"],
        "row_count": len(consequence_rows),
        "node_count": len(by_node),
        "representation_readiness": {
            "EXP2A_POINT_MARGINAL_JOINT": "READY_FROM_M1_ARTIFACT",
            "EXP2B_7COMP_TYPED_VECTOR": "READY_WITH_P_ITINERARY_P_SERVICE_ABSTAIN",
            "EXP2B_3CHANNEL": "BLOCKED_PASSENGER_CHANNEL_INCOMPLETE",
            "EXP2B_SCALAR": "BLOCKED_SEVEN_COMPONENT_AGGREGATE_UNRESOLVED",
        },
        "next_gate": "MANUSCRIPT_IMPLEMENTATION_MISMATCH_SEVEN_COMPONENT_FULL_SUPPORT_DECISION_REQUIRED",
        "safety": SAFETY,
    }
    manifest_path = output_root / "M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCE_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    materialize(root=root, output_root=args.output_root)
    print("M2_V2_CONSEQUENCE_ARTIFACT_MATERIALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
