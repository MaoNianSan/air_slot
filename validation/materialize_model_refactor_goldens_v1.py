"""Freeze Development-only behavioral fixtures before the V1R1 refactor."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import torch

from model.M1.coverage import active_node_prefixes
from model.M1.development_training import _load_fast_config, _load_references
from model.M2.context import (
    AirportReferenceKeys,
    build_m2_frozen_scope,
    build_m2_v4_context,
    build_node_exposure_references,
    load_data2_reference_bundle,
)
from model.M2.contracts import M2ScenarioInput
from model.M2.cu.registry import FrozenData2CUNormalizationRegistry
from model.M2.mapper import M2Mapper
from model.M2.scientific_registry import load_active_m2_cu_registry
from model.M3.action_response import (
    build_a00_identity_envelope,
    build_conditional_scenario_envelope,
)
from model.M3.instantiation_layer.builder import instantiate_action_records
from model.M3.m2_action_interface import M3BaselineConsequenceInput
from model.M3.registry_layer.actions import ActionRegistry
from model.M3.response_registry import ResponseScenarioRegistry
from model.M4.m3_action_interface import M4ActionEnvelopeInput
from model.M4.residual_risk import (
    evaluate_residual_risk,
    load_active_risk_policy,
    rank_risk_evaluations,
)
from model.M4.scientific_registry import load_active_rmb_mapping
from model.PRE.development import materialize_preselected_cohorts
from model.common.config import load_config_layers
from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT
from validation.materialize_m1_positive_tail_e2e_smoke import _m1, _payloads
from validation.materialize_non_a00_numerical_smoke_v1 import (
    ACTION_PATH,
    DESIGN_PATH,
    RESPONSE_PATH,
    SMOKE_SEED,
    _build_comparison_scope,
    _build_rule,
    _eligibility,
)


REFERENCE_FINGERPRINT = (
    "sha256:80133fa5a57593dcdeda3fb3871c037146b1faa98b135377a83ba8e1e4f86f1d"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts/diagnostics/model_refactor_v1"
SCENARIO_PATH = (
    PROJECT_ROOT
    / "artifacts/diagnostics/numerical_best_action_sanity_v1/"
    / "M1_DEVELOPMENT_64_NODE_SCENARIOS.json"
)
SANITY_RECORDS = (
    PROJECT_ROOT
    / "artifacts/diagnostics/numerical_best_action_sanity_v1/non_a00_path/"
    / "NON_A00_NUMERICAL_SMOKE_RECORDS.jsonl"
)
SANITY_SUMMARY = (
    PROJECT_ROOT
    / "artifacts/diagnostics/numerical_best_action_sanity_v1/"
    / "NUMERICAL_BEST_ACTION_SANITY_SUMMARY.json"
)
SMOKE_PREPARATION_STATE = (
    PROJECT_ROOT / "artifacts/models/m1/M1_FROZEN_H8/SMOKE_PREP.pt"
)
SMOKE_PREPARATION_MANIFEST = (
    PROJECT_ROOT / "artifacts/models/m1/M1_FROZEN_H8/SMOKE_PREP.json"
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _write_golden(output: Path, name: str, payload: dict[str, Any]) -> str:
    base = {
        "schema_version": f"{name.removesuffix('.json')}_V1",
        "scientific_parent_fingerprint": REFERENCE_FINGERPRINT,
        "artifact_scope": "DEVELOPMENT_ONLY_PRE_REFACTOR_GOLDEN",
        **payload,
        "guards": {
            "data1_modified": False,
            "data2_modified": False,
            "final_test_access_count": 0,
            "model_retrained": False,
            "parameter_reselected": False,
            "experiment_created": False,
        },
    }
    result = {**base, "artifact_hash": content_id(base)}
    path = output / name
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result["artifact_hash"]


def _pre_states(target_node_ids: set[str]) -> list[dict[str, Any]]:
    scientific = load_config_layers(PROJECT_ROOT / "configs").scientific
    _, _ = _load_fast_config(PROJECT_ROOT)
    taxi, turnaround, _ = _load_references(PROJECT_ROOT)
    manifest = _read_json(SMOKE_PREPARATION_MANIFEST)
    if manifest.get("completion_status") != "PASS":
        raise RuntimeError("MODEL_REFACTOR_SMOKE_PREPARATION_NOT_COMPLETE")
    prepared = torch.load(
        SMOKE_PREPARATION_STATE, map_location="cpu", weights_only=False
    )
    reservoirs = prepared.get("reservoirs", {})
    if reservoirs.get("test"):
        raise RuntimeError("FINAL_TEST_EPISODE_MATERIALIZED")
    partitions = {
        split: tuple(reservoirs.get(split, ()))
        for split in ("train", "calibration", "development")
    }
    cohorts = materialize_preselected_cohorts(
        scientific,
        root=PROJECT_ROOT,
        partitions=partitions,
        selection_audit={
            "preparation_state": str(SMOKE_PREPARATION_STATE.relative_to(PROJECT_ROOT)),
            "preparation_manifest": str(
                SMOKE_PREPARATION_MANIFEST.relative_to(PROJECT_ROOT)
            ),
            "preparation_state_key": prepared.get("state_key"),
        },
        taxi_reference=taxi,
        turnaround_reference=turnaround,
    )
    matches: dict[str, dict[str, Any]] = {}
    for item in cohorts.development:
        reference_minutes = reference_id = reference_hash = None
        if taxi is not None:
            lookup = taxi.lookup(item.episode.connection_airport_id)
            if (
                getattr(lookup, "value", None) is not None
                and getattr(getattr(lookup, "support_state", None), "value", None)
                == "SUPPORTED"
            ):
                reference_minutes = float(lookup.value)
                reference_id = getattr(taxi, "reference_id", None)
                reference_hash = getattr(taxi, "manifest_freeze_id", None)
        for _, prefix, _ in active_node_prefixes(
            episode=item.episode,
            nodes=item.nodes,
            states=item.states,
            successor_schedule=item.successor_schedule,
            predecessor_outcome=item.predecessor_outcome,
            successor_outcome=item.successor_outcome,
            taxi_reference_minutes=reference_minutes,
            taxi_reference_id=reference_id,
            taxi_reference_hash=reference_hash,
        ):
            state = prefix[-1]
            node_id = state.decision_node.decision_node_id
            if node_id in target_node_ids:
                matches[node_id] = state.model_dump(mode="json")
    missing = sorted(target_node_ids - set(matches))
    if missing:
        raise RuntimeError(f"MODEL_REFACTOR_PRE_GOLDEN_NODE_MISSING:{missing}")
    return [matches[node_id] for node_id in sorted(matches)]


def _action_chain(
    scenario_payload: dict[str, Any], node_id: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    rows = sorted(
        (
            row
            for row in scenario_payload["scenarios"]
            if row["decision_node_id"] == node_id
        ),
        key=lambda row: row["scenario_id"],
    )
    node_meta = next(
        row for row in scenario_payload["nodes"] if row["decision_node_id"] == node_id
    )
    first = rows[0]
    decision_time = datetime.fromisoformat(first["decision_time_utc"])
    keys = AirportReferenceKeys(
        connection_airport_id=node_meta["connection_airport_id"],
        successor_destination_airport_id=node_meta["successor_destination_airport_id"],
        carrier_id=None,
        month=decision_time.month,
        quarter=(decision_time.month - 1) // 3 + 1,
    )
    bundle = load_data2_reference_bundle(_payloads())
    references = build_node_exposure_references(bundle, keys)
    context = build_m2_v4_context(
        bundle, keys, node_specific_exposure=references.airport
    )
    cu_registry = FrozenData2CUNormalizationRegistry(load_active_m2_cu_registry())
    mapper = M2Mapper(cu_registry, build_m2_frozen_scope())
    inputs = tuple(
        M2ScenarioInput.from_m1(
            _m1(row),
            pre_lineage=("M1_DEVELOPMENT_64_NODE_SCENARIOS", node_id),
            reference_lineage=(scenario_payload["tail_manifest_hash"],),
        )
        for row in rows
    )
    distribution = mapper.map_m1_distribution(inputs, context)
    baselines = tuple(
        M3BaselineConsequenceInput.model_validate(item.m3_baseline_payload())
        for item in distribution.consequences
    )

    action_registry = ActionRegistry.load(ACTION_PATH)
    response_registry = ResponseScenarioRegistry.load(
        RESPONSE_PATH, structural_registry=action_registry
    )
    design_payload = _read_json(DESIGN_PATH)
    design = {row["action_id"]: row for row in design_payload["responses"]}
    instantiations = instantiate_action_records(
        {
            "episode_id": first["episode_id"],
            "decision_node_id": node_id,
            "facts": {},
            "parameters": {},
        },
        action_registry,
        response_registry=response_registry,
        sensitivity="BASE",
    )
    by_id = {item.template_id: item for item in instantiations}
    readiness = {
        item.action_id: item
        for item in action_registry.numerical_readiness(
            response_registry=response_registry
        )
    }
    rmb = load_active_rmb_mapping()
    policy = load_active_risk_policy()
    scope = _build_comparison_scope(rmb)
    envelopes = []
    risks = []
    action_records = []
    for template in action_registry.templates:
        action_id = template.template_id
        instantiation = by_id[action_id]
        candidate = instantiation.candidate
        ready = readiness[action_id]
        action_records.append(
            {
                "action_id": action_id,
                "instantiation": instantiation.model_dump(mode="json"),
                "numerical_readiness": ready.model_dump(mode="json"),
            }
        )
        if candidate is None:
            continue
        if action_id == "A00":
            envelope = build_a00_identity_envelope(
                baselines,
                eligibility=_eligibility(candidate, node_id=node_id),
                response_rule=_build_rule(design[action_id]),
            )
        elif ready.chi_num_possible_if_state_complete:
            envelope = build_conditional_scenario_envelope(
                baselines,
                eligibility=_eligibility(candidate, node_id=node_id),
                response_rule=_build_rule(design[action_id]),
                response_parameters=response_registry.parameters(
                    action_id, sensitivity="BASE"
                ),
                mitigation=candidate.mitigation,
                induced=candidate.induced,
                induced_response=candidate.induced_response,
                footprint=candidate.footprint,
                seed=SMOKE_SEED,
                response_registry_hash=response_registry.digest(),
                sensitivity_level="BASE",
            )
        else:
            continue
        m4_input = M4ActionEnvelopeInput.from_m3(envelope).model_copy(
            update={"comparison_scope": scope}
        )
        risk = evaluate_residual_risk(
            m4_input, monetary_mapping=rmb, risk_policy=policy
        )
        envelopes.append(envelope.model_dump(mode="json"))
        risks.append(risk)

    ranking = rank_risk_evaluations(tuple(risks))
    m2_payload = {
        "decision_node_id": node_id,
        "context": context.model_dump(mode="json"),
        "consequence_scope": mapper.consequence_scope.model_dump(mode="json"),
        "scenario_consequences": [
            item.model_dump(mode="json") for item in distribution.consequences
        ],
    }
    m3_payload = {
        "decision_node_id": node_id,
        "action_registry_hash": action_registry.digest(),
        "response_registry_hash": response_registry.digest(),
        "action_records": action_records,
        "action_conditioned_envelopes": envelopes,
    }
    m4_payload = {
        "decision_node_id": node_id,
        "measurement_registry": rmb.model_dump(mode="json"),
        "risk_policy": policy.model_dump(mode="json"),
        "comparison_scope": scope.model_dump(mode="json"),
        "risk_evaluations": [item.model_dump(mode="json") for item in risks],
        "ranking": ranking.model_dump(mode="json"),
    }
    return m2_payload, m3_payload, m4_payload


def materialize(output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("MODEL_REFACTOR_GOLDEN_DIRECTORY_NOT_EMPTY")
    output.mkdir(parents=True, exist_ok=True)
    scenario_payload = _read_json(SCENARIO_PATH)
    node_ids = sorted(row["decision_node_id"] for row in scenario_payload["nodes"])
    if len(node_ids) != 64:
        raise RuntimeError("MODEL_REFACTOR_EXPECTS_64_DEVELOPMENT_NODES")
    fixed_node_id = node_ids[0]
    pre_payload = {
        "source_preparation_state_hash": _sha256_file(SMOKE_PREPARATION_STATE),
        "source_preparation_manifest_hash": _sha256_file(
            SMOKE_PREPARATION_MANIFEST
        ),
        "selected_node_ids": node_ids[:8],
        "pre_states": _pre_states(set(node_ids[:8])),
    }
    fixed_scenarios = [
        row
        for row in scenario_payload["scenarios"]
        if row["decision_node_id"] == fixed_node_id
    ]
    m1_payload = {
        "source_artifact_hash": _sha256_file(SCENARIO_PATH),
        "source_declared_artifact_hash": scenario_payload["artifact_hash"],
        "checkpoint_hash": scenario_payload["checkpoint_hash"],
        "tail_manifest_hash": scenario_payload["tail_manifest_hash"],
        "decision_node_id": fixed_node_id,
        "scenario_count": len(fixed_scenarios),
        "scenarios": fixed_scenarios,
    }
    m2_payload, m3_payload, m4_payload = _action_chain(
        scenario_payload, fixed_node_id
    )
    sanity = _read_json(SANITY_SUMMARY)
    distribution = sanity["best_action_distribution"]
    non_a00_payload = {
        "scenario_source_hash": _sha256_file(SCENARIO_PATH),
        "records_source_hash": _sha256_file(SANITY_RECORDS),
        "summary_source_hash": _sha256_file(SANITY_SUMMARY),
        "records_relative_path": str(SANITY_RECORDS.relative_to(PROJECT_ROOT)),
        "summary_relative_path": str(SANITY_SUMMARY.relative_to(PROJECT_ROOT)),
        "nodes": sanity["cohort"]["nodes"],
        "non_A00_chi_num_defined": sum(
            1
            for line in SANITY_RECORDS.read_text(encoding="utf-8").splitlines()
            if line.strip()
            and (row := json.loads(line))["action_id"] != "A00"
            and row["chi_num"] == "DEFINED"
        ),
        "non_A00_M4_evaluated": sum(
            1
            for line in SANITY_RECORDS.read_text(encoding="utf-8").splitlines()
            if line.strip()
            and (row := json.loads(line))["action_id"] != "A00"
            and row.get("risk_numerical_state") == "DEFINED"
        ),
        "A00_best": distribution["A00_best_count"],
        "non_A00_best": distribution["non_A00_best_count"],
        "winner_distribution": distribution["winner_distribution"],
        "chi_sel": sanity["operational_authority"]["chi_sel"],
        "operational_recommendations": sanity["operational_authority"]
        ["operational_recommendations"],
    }
    hashes = {
        "PRE_GOLDEN.json": _write_golden(output, "PRE_GOLDEN.json", pre_payload),
        "M1_GOLDEN.json": _write_golden(output, "M1_GOLDEN.json", m1_payload),
        "M2_GOLDEN.json": _write_golden(output, "M2_GOLDEN.json", m2_payload),
        "M3_GOLDEN.json": _write_golden(output, "M3_GOLDEN.json", m3_payload),
        "M4_GOLDEN.json": _write_golden(output, "M4_GOLDEN.json", m4_payload),
        "NON_A00_GOLDEN.json": _write_golden(
            output, "NON_A00_GOLDEN.json", non_a00_payload
        ),
    }
    return {
        "output": str(output),
        "fixed_node_id": fixed_node_id,
        "hashes": hashes,
        "final_test_access_count": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(materialize(args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

