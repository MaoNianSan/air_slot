"""Held-out Final Test Exp3 RMB action-risk materialization.

The implementation is deliberately bounded: it reads one Final Test decision
node row group at a time, writes verified Exp3 staging shards, and publishes
the final parquet only after an end-to-end schema and lineage audit. It never
fits, calibrates, or reselects a model or an action-response parameter.
"""

from __future__ import annotations

import csv
from collections import Counter
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from exp.common.official_execution import file_sha256, load_json, write_json
from exp.exp3.global_development import (
    ACTION_REGISTRY, FIVE_ANCHOR_COMPONENTS, M2_REGISTRY, RESPONSE_REGISTRY,
    RISK_POLICY, SEED, _conditional_risk, _require,
)
from model.M3.instantiate import instantiate_candidates
from model.M3.registry import ActionRegistry
from model.M3.response import action_post_consequences, response_draw
from model.M3.response_registry import ResponseScenarioRegistry, SENSITIVITY_LEVELS
from model.PRE.contracts.pre_state import PREState
from model.common.identity import content_id


SCOPE = "FINAL_TEST_OUT_OF_TIME_2019_10_12"
RMB_REGISTRY = Path("registries/m4_rmb_mapping_v1.json")
NODES_PER_SHARD = 100
FINAL_SCHEMA = pa.schema([
    pa.field("episode_id", pa.string()),
    pa.field("decision_node_id", pa.string()),
    pa.field("decision_time", pa.string()),
    pa.field("successor_service_date", pa.string()),
    pa.field("action_id", pa.string()),
    pa.field("action_family", pa.string()),
    pa.field("response_sensitivity", pa.string()),
    pa.field("valuation_band", pa.string()),
    pa.field("is_A00", pa.bool_()),
    pa.field("chi_inst", pa.bool_()),
    pa.field("chi_num", pa.bool_()),
    pa.field("opportunity_probability", pa.float64()),
    pa.field("opportunity_probability_status", pa.string()),
    pa.field("eligibility_state", pa.string()),
    pa.field("eligibility_interpretation", pa.string()),
    pa.field("response_support", pa.string()),
    pa.field("response_support_status", pa.string()),
    pa.field("response_registry_hash", pa.string()),
    pa.field("scenario_lineage_hash", pa.string()),
    pa.field("rmb_registry_hash", pa.string()),
    pa.field("scenario_count", pa.int64()),
    pa.field("finite_support_scenario_count", pa.int64()),
    pa.field("finite_support_rate", pa.float64()),
    pa.field("finite_status", pa.string()),
    pa.field("diagnostic_support_status", pa.string()),
    pa.field("conditional_expected_rmb", pa.float64()),
    pa.field("conditional_rmb_variance", pa.float64()),
    pa.field("conditional_rmb_var_alpha", pa.float64()),
    pa.field("conditional_rmb_cvar_alpha", pa.float64()),
    pa.field("conditional_residual_risk_rmb", pa.float64()),
    pa.field("complete_seven_component_supported_scenarios", pa.int64()),
    pa.field("complete_seven_component_risk_status", pa.string()),
    pa.field("complete_seven_component_risk_reason", pa.string()),
    pa.field("p_itinerary_event_count", pa.float64()),
    pa.field("p_service_event_count", pa.float64()),
    pa.field("pending_monetary_event_status", pa.string()),
    pa.field("ranking_authority", pa.string()),
    pa.field("monetary_ground_truth_claim", pa.bool_()),
    pa.field("causal_action_effect_claim", pa.bool_()),
    pa.field("conditional_diagnostic_rank", pa.int64()),
])


def _rates(registry: dict[str, Any]) -> dict[str, dict[str, float]]:
    _require(registry.get("monetary_system") == "RMB", "EXP3_FINAL_RMB_SYSTEM_INVALID")
    _require(registry.get("rmb_base_mapping") == "1_CU_EQUALS_1_RMB", "EXP3_FINAL_RMB_CU_MAPPING_INVALID")
    _require(tuple(registry.get("main_monetary_components", [])) == FIVE_ANCHOR_COMPONENTS,
             "EXP3_FINAL_RMB_SCOPE_INVALID")
    entries = {item["component_id"]: item for item in registry.get("components", [])}
    _require(all(name in entries for name in FIVE_ANCHOR_COMPONENTS), "EXP3_FINAL_RMB_COMPONENT_MISSING")
    _require(all(entries[name].get("scope_status") == "IN_MAIN_MONETARY_SCOPE" for name in FIVE_ANCHOR_COMPONENTS),
             "EXP3_FINAL_RMB_COMPONENT_SCOPE_INVALID")
    _require(all(entries[name].get("zero_fill_allowed") is False for name in entries),
             "EXP3_FINAL_RMB_ZERO_FILL_FORBIDDEN")
    _require(all(entries[name].get("scope_status") == "NOT_IN_MAIN_MONETARY_SCOPE"
                 for name in ("P_itinerary", "P_service")), "EXP3_FINAL_RMB_EXCLUDED_SCOPE_INVALID")
    result = {name: {band: float(entries[name]["beta_k_rmb"][band]) for band in SENSITIVITY_LEVELS}
              for name in FIVE_ANCHOR_COMPONENTS}
    _require(all(result[name]["BASE"] == 1.0 and result[name]["LOW"] == 0.5
                 and result[name]["HIGH"] == 2.0 for name in FIVE_ANCHOR_COMPONENTS),
             "EXP3_FINAL_RMB_BAND_INVALID")
    return result


def _rmb_risk(values: list[float], weights: list[float], *, alpha: float,
              expected_coefficient: float, cvar_coefficient: float) -> dict[str, float] | None:
    internal = _conditional_risk(values, weights, alpha=alpha,
                                 expected_coefficient=expected_coefficient,
                                 cvar_coefficient=cvar_coefficient)
    if internal is None:
        return None
    return {
        "expected_rmb": internal["expected_constructed_eur"],
        "rmb_variance": internal["constructed_eur_variance"],
        "rmb_var_alpha": internal["constructed_eur_var_alpha"],
        "rmb_cvar_alpha": internal["constructed_eur_cvar_alpha"],
        "residual_risk_rmb": internal["residual_risk_objective"],
    }


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _unlink_staging(paths: Iterable[Path]) -> None:
    for path in paths:
        if path.is_file():
            path.unlink()


def _stage_config(paths: dict[str, Path], *, registry_hash: str, source_manifest_hash: str) -> dict[str, str]:
    return {
        "consequences_hash": file_sha256(paths["consequences"]),
        "inputs_hash": file_sha256(paths["inputs"]),
        "response_registry_file_hash": file_sha256(paths["response_registry"]),
        "rmb_registry_file_hash": file_sha256(paths["mapping_registry"]),
        "rmb_registry_hash": registry_hash,
        "source_exp2_manifest_hash": source_manifest_hash,
        "schema_hash": content_id(str(FINAL_SCHEMA)),
    }


def _staging_state(*, total_nodes: int, completed_nodes: int, completed_rows: int,
                   last_episode_id: str | None, last_decision_time: str | None,
                   staging_file: Path | None, status: str, config: dict[str, str], root: Path) -> dict[str, Any]:
    return {
        "schema_version": "EXP3_FINAL_TEST_RMB_PROGRESS_V1", "scope": SCOPE,
        "total_nodes": total_nodes, "completed_nodes": completed_nodes,
        "completed_rows": completed_rows, "last_episode_id": last_episode_id,
        "last_decision_time": last_decision_time,
        "staging_file": None if staging_file is None else _relative(staging_file, root),
        "status": status, "stage_config": config,
    }


def _read_verified_shards(*, staging: Path, progress_path: Path, root: Path,
                          total_nodes: int, config: dict[str, str]) -> tuple[list[Path], int, int]:
    """Return resumable shard files or remove only Exp3 staging on mismatch."""
    shards = sorted(staging.glob("part-*.parquet"))
    progress = load_json(progress_path) if progress_path.is_file() else None
    valid = bool(progress and progress.get("status") == "RUNNING" and progress.get("stage_config") == config)
    valid = valid and int(progress.get("total_nodes", -1)) == total_nodes
    if valid:
        expected = int(progress.get("completed_nodes", -1))
        expected_rows = int(progress.get("completed_rows", -1))
        rows = nodes = 0
        for index, shard in enumerate(shards):
            try:
                parquet = pq.ParquetFile(shard)
                metadata_path = shard.with_suffix(".json")
                metadata = load_json(metadata_path)
                if (parquet.schema_arrow != FINAL_SCHEMA or parquet.metadata.num_rows <= 0
                        or metadata.get("stage_config") != config
                        or int(metadata.get("shard_index", -1)) != index
                        or int(metadata.get("row_count", -1)) != parquet.metadata.num_rows):
                    raise ValueError("invalid staging shard")
                nodes += int(metadata["node_count"])
                rows += parquet.metadata.num_rows
            except Exception:
                valid = False
                break
        valid = valid and nodes == expected and rows == expected_rows
    if not valid:
        _unlink_staging([*staging.glob("*"), progress_path])
        return [], 0, 0
    return shards, expected, expected_rows


def _source_lineage(source_rows: list[dict[str, Any]], node_id: str) -> str:
    return content_id({"decision_node_id": node_id, "scenarios": [
        {"scenario_id": int(row["scenario_id"]), "scenario_weight": float(row["scenario_weight"]),
         "m1_scenario_seed_key": row.get("m1_scenario_seed_key")}
        for row in source_rows
    ]})


def _node_rows(*, source_rows: list[dict[str, Any]], state: dict[str, Any], successor_service_date: str,
               action_registry: ActionRegistry, response_registry: ResponseScenarioRegistry,
               templates: dict[str, Any], rates: dict[str, dict[str, float]], registry_hash: str,
               alpha: float, expected_coefficient: float, cvar_coefficient: float) -> tuple[list[dict[str, Any]], int]:
    node_id = state["decision_node"]["decision_node_id"]
    pre = PREState.model_validate(state)
    _require(len({row["decision_node_id"] for row in source_rows}) == 1, "EXP3_FINAL_TEST_RMB_NODE_ROW_GROUP_INVALID")
    _require(source_rows[0]["decision_node_id"] == node_id, "EXP3_FINAL_TEST_RMB_PRE_STATE_NODE_MISMATCH")
    total_weight = sum(float(row["scenario_weight"]) for row in source_rows)
    _require(total_weight > 0, "EXP3_FINAL_TEST_RMB_SCENARIO_WEIGHT_INVALID")
    lineage = _source_lineage(source_rows, node_id)
    candidates = instantiate_candidates(pre, action_registry, response_registry=response_registry, sensitivity="BASE")
    _require(len(candidates) == 23, "EXP3_FINAL_TEST_RMB_ACTION_LIBRARY_CARDINALITY_INVALID")
    rows: list[dict[str, Any]] = []
    a00_checks = 0
    for sensitivity in SENSITIVITY_LEVELS:
        for candidate in candidates:
            template = templates[candidate.template_id]
            parameters = response_registry.parameters(candidate.template_id, sensitivity=sensitivity)
            frozen_response = parameters.get("response_parameter_status") in {"FROZEN", "NOT_REQUIRED"}
            values: list[float] = []
            weights: list[float] = []
            itinerary_events: list[float] = []
            service_events: list[float] = []
            complete_supported = 0
            for scenario in source_rows:
                components = json.loads(scenario["components_json"])
                supported = {item["component_id"]: float(item["constructed_value_cu"])
                             for item in components if item["constructed_value_cu"] is not None}
                if len(supported) == 7:
                    complete_supported += 1
                if not all(component in supported for component in FIVE_ANCHOR_COMPONENTS):
                    continue
                rho = response_draw(seed=SEED, episode_id=scenario["episode_id"], decision_node_id=node_id,
                                    scenario_id=int(scenario["scenario_id"]), action_template_id=candidate.template_id,
                                    parameters=parameters, response_registry_hash=response_registry.registry_hash,
                                    sensitivity_level=sensitivity)
                post = action_post_consequences(pre_by_component=supported, mitigation=template.mitigation,
                                                induced=template.induced, rho=rho,
                                                induced_score_to_cu=float(parameters.get("induced_score_to_cu", response_registry.induced_score_to_cu)),
                                                included_components=tuple(supported))
                if candidate.template_id == "A00":
                    _require(all(math.isclose(post[key], supported[key], rel_tol=0.0, abs_tol=1e-12)
                                 for key in supported), "EXP3_FINAL_TEST_RMB_A00_CONSEQUENCE_IDENTITY_INVALID")
                    a00_checks += len(supported)
                values.append(sum(post[name] * rates[name][sensitivity] for name in FIVE_ANCHOR_COMPONENTS))
                weights.append(float(scenario["scenario_weight"]))
                itinerary_events.append(post.get("P_itinerary"))
                service_events.append(post.get("P_service"))
            conditional = _rmb_risk(values, weights, alpha=alpha,
                                    expected_coefficient=expected_coefficient,
                                    cvar_coefficient=cvar_coefficient)
            chi_num = bool(candidate.instantiable and frozen_response and conditional is not None)
            weight_total = sum(weights)
            response_support = "IDENTITY" if candidate.template_id == "A00" else "SCENARIO_ASSUMPTION"
            rows.append({
                "episode_id": pre.decision_node.episode_id, "decision_node_id": node_id,
                "decision_time": pre.decision_node.decision_time.isoformat().replace("+00:00", "Z"), "successor_service_date": successor_service_date,
                "action_id": candidate.template_id, "action_family": candidate.action_family,
                "response_sensitivity": sensitivity, "valuation_band": sensitivity,
                "is_A00": candidate.template_id == "A00", "chi_inst": bool(candidate.instantiable), "chi_num": chi_num,
                "opportunity_probability": None,
                "opportunity_probability_status": "NOT_OBSERVED_NO_PROBABILISTIC_OPPORTUNITY_MODEL",
                "eligibility_state": candidate.precondition_state,
                "eligibility_interpretation": "FACTUAL_ELIGIBLE" if candidate.precondition_state == "TRUE" else "CONDITIONAL_ON_REQUIRED_FACTS_TRUE",
                "response_support": response_support,
                "response_support_status": "IDENTITY_BASELINE" if candidate.template_id == "A00" else "CONDITIONAL_SCENARIO_ASSUMPTION",
                "response_registry_hash": response_registry.registry_hash, "scenario_lineage_hash": lineage,
                "rmb_registry_hash": registry_hash, "scenario_count": len(source_rows),
                "finite_support_scenario_count": len(values), "finite_support_rate": sum(weights) / total_weight,
                "finite_status": "FINITE_MAIN_MONETARY_SCOPE" if chi_num else "NO_COMMON_FINITE_MONETARY_SUPPORT",
                "diagnostic_support_status": "PARTIAL_DIAGNOSTIC" if chi_num else "NOT_RUN",
                "conditional_expected_rmb": None if conditional is None else conditional["expected_rmb"],
                "conditional_rmb_variance": None if conditional is None else conditional["rmb_variance"],
                "conditional_rmb_var_alpha": None if conditional is None else conditional["rmb_var_alpha"],
                "conditional_rmb_cvar_alpha": None if conditional is None else conditional["rmb_cvar_alpha"],
                "conditional_residual_risk_rmb": None if conditional is None else conditional["residual_risk_rmb"],
                "complete_seven_component_supported_scenarios": complete_supported,
                "complete_seven_component_risk_status": "NOT_IN_MAIN_MONETARY_SCOPE",
                "complete_seven_component_risk_reason": "P_ITINERARY_P_SERVICE_NOT_IN_MAIN_MONETARY_SCOPE",
                "p_itinerary_event_count": None if not weight_total else sum(value * weight for value, weight in zip(itinerary_events, weights)) / weight_total,
                "p_service_event_count": None if not weight_total else sum(value * weight for value, weight in zip(service_events, weights)) / weight_total,
                "pending_monetary_event_status": "NOT_IN_MAIN_MONETARY_SCOPE",
                "ranking_authority": "CONDITIONAL_DIAGNOSTIC_5_COMPONENT_RMB_NOT_OPERATIONAL_RECOMMENDATION",
                "monetary_ground_truth_claim": False, "causal_action_effect_claim": False,
                "conditional_diagnostic_rank": None,
            })
    for sensitivity in SENSITIVITY_LEVELS:
        comparable = [row for row in rows if row["response_sensitivity"] == sensitivity and row["chi_num"]]
        comparable.sort(key=lambda row: (row["conditional_residual_risk_rmb"], row["action_id"]))
        for rank, row in enumerate(comparable, start=1):
            row["conditional_diagnostic_rank"] = rank
    return rows, a00_checks


def _merge_shards(*, shards: list[Path], output: Path) -> None:
    if output.exists():
        output.unlink()
    writer: pq.ParquetWriter | None = None
    try:
        for shard in shards:
            reader = pq.ParquetFile(shard)
            _require(reader.schema_arrow == FINAL_SCHEMA, "EXP3_FINAL_TEST_RMB_STAGING_SCHEMA_INVALID")
            for batch in reader.iter_batches(batch_size=8192):
                if writer is None:
                    writer = pq.ParquetWriter(output, FINAL_SCHEMA, compression="zstd")
                writer.write_table(pa.Table.from_batches([batch], schema=FINAL_SCHEMA))
    finally:
        if writer is not None:
            writer.close()


def _validate_published(*, path: Path, expected_nodes: int, expected_actions: set[str], registry_hash: str) -> dict[str, Any]:
    reader = pq.ParquetFile(path)
    _require(reader.schema_arrow == FINAL_SCHEMA, "EXP3_FINAL_TEST_RMB_FINAL_SCHEMA_INVALID")
    _require(reader.metadata.num_rows > 0, "EXP3_FINAL_TEST_RMB_FINAL_EMPTY")
    node_ids: set[str] = set(); action_ids: set[str] = set(); rows = 0
    a00_by_node: dict[str, dict[str, float]] = {}
    top_by_band: dict[str, dict[str, str]] = {band: {} for band in SENSITIVITY_LEVELS}
    group_rows: list[dict[str, Any]] = []; current_key: tuple[str, str] | None = None
    def flush() -> None:
        if not group_rows:
            return
        node_id, band = group_rows[0]["decision_node_id"], group_rows[0]["valuation_band"]
        _require(len(group_rows) == len(expected_actions), "EXP3_FINAL_TEST_RMB_ACTION_GROUP_CARDINALITY_INVALID")
        _require({row["action_id"] for row in group_rows} == expected_actions, "EXP3_FINAL_TEST_RMB_ACTION_ID_INVALID")
        _require(len({row["scenario_lineage_hash"] for row in group_rows}) == 1, "EXP3_FINAL_TEST_RMB_SCENARIO_LINEAGE_MISMATCH")
        _require(all(row["response_sensitivity"] == band for row in group_rows), "EXP3_FINAL_TEST_RMB_BAND_MISMATCH")
        _require(all(bool(row["is_A00"]) == (row["action_id"] == "A00") for row in group_rows), "EXP3_FINAL_TEST_RMB_A00_IDENTITY_INVALID")
        comparable = [row for row in group_rows if row["chi_num"]]
        comparable.sort(key=lambda row: (row["conditional_residual_risk_rmb"], row["action_id"]))
        if comparable:
            _require([row["conditional_diagnostic_rank"] for row in comparable] == list(range(1, len(comparable) + 1)),
                     "EXP3_FINAL_TEST_RMB_RANK_INVALID")
            top_by_band[band][node_id] = comparable[0]["action_id"]
        a00 = next(row for row in group_rows if row["action_id"] == "A00")
        if a00["conditional_residual_risk_rmb"] is not None:
            a00_by_node.setdefault(node_id, {})[band] = float(a00["conditional_residual_risk_rmb"])
    for batch in reader.iter_batches(batch_size=8192):
        for row in batch.to_pylist():
            rows += 1
            _require("2019-10-01" <= row["successor_service_date"] <= "2019-12-31", "EXP3_FINAL_TEST_RMB_DATE_RANGE_INVALID")
            _require(row["rmb_registry_hash"] == registry_hash, "EXP3_FINAL_TEST_RMB_REGISTRY_HASH_INVALID")
            _require(row["pending_monetary_event_status"] == "NOT_IN_MAIN_MONETARY_SCOPE", "EXP3_FINAL_TEST_RMB_UNSUPPORTED_ZERO_FILL")
            _require(row["complete_seven_component_risk_status"] == "NOT_IN_MAIN_MONETARY_SCOPE", "EXP3_FINAL_TEST_RMB_UNSUPPORTED_SCOPE_INVALID")
            _require(row["opportunity_probability"] is None and row["opportunity_probability_status"].startswith("NOT_OBSERVED"),
                     "EXP3_FINAL_TEST_RMB_OPPORTUNITY_ZERO_FILL")
            node_ids.add(row["decision_node_id"]); action_ids.add(row["action_id"])
            key = (row["decision_node_id"], row["valuation_band"])
            if current_key is not None and key != current_key:
                flush(); group_rows.clear()
            current_key = key; group_rows.append(row)
    flush()
    _require(len(node_ids) == expected_nodes, "EXP3_FINAL_TEST_RMB_NODE_COUNT_INVALID")
    _require(action_ids == expected_actions, "EXP3_FINAL_TEST_RMB_ACTION_LIBRARY_INVALID")
    _require(rows == expected_nodes * len(expected_actions) * len(SENSITIVITY_LEVELS), "EXP3_FINAL_TEST_RMB_OUTPUT_CARDINALITY_INVALID")
    for values in a00_by_node.values():
        _require(set(values) == set(SENSITIVITY_LEVELS), "EXP3_FINAL_TEST_RMB_A00_BAND_MISSING")
        _require(math.isclose(values["LOW"] * 2.0, values["BASE"], rel_tol=1e-10, abs_tol=1e-10),
                 "EXP3_FINAL_TEST_RMB_LOW_IDENTITY_INVALID")
        _require(math.isclose(values["HIGH"] * 0.5, values["BASE"], rel_tol=1e-10, abs_tol=1e-10),
                 "EXP3_FINAL_TEST_RMB_HIGH_IDENTITY_INVALID")
    base = top_by_band["BASE"]
    agreement = {band: (None if not base else mean(base[node] == top_by_band[band].get(node) for node in base))
                 for band in ("LOW", "HIGH")}
    return {"row_count": rows, "node_count": len(node_ids), "action_count": len(action_ids),
            "conditional_top1_sensitivity_agreement": agreement,
            "a00_band_identity_node_count": len(a00_by_node)}


def run(*, root: Path, exp2_root: Path, input_root: Path, output_root: Path,
        monetary_registry: Path | None = None) -> dict[str, Path]:
    """Materialize Exp3 Final Test RMB action-risk from verified upstream artifacts."""
    root = root.resolve()
    exp2_root, input_root, output_root = (path.resolve() for path in (exp2_root, input_root, output_root))
    monetary_registry = (monetary_registry or root / RMB_REGISTRY).resolve()
    paths = {"exp2_manifest": exp2_root / "EXP2_FINAL_TEST_EXECUTION_MANIFEST.json",
             "consequences": exp2_root / "M2_FINAL_TEST_CONSEQUENCES.parquet",
             "inputs": input_root / "M1_V2_FINAL_TEST_INFERENCE_INPUTS.json",
             "cohort": input_root / "DATA2_FINAL_TEST_COHORT.json",
             "action_registry": root / ACTION_REGISTRY, "response_registry": root / RESPONSE_REGISTRY,
             "m2_registry": root / M2_REGISTRY, "mapping_registry": monetary_registry,
             "risk_policy": root / RISK_POLICY}
    _require(all(path.is_file() for path in paths.values()), "EXP3_FINAL_TEST_RMB_INPUT_MISSING")
    exp2_manifest, inputs, cohort = (load_json(paths[name]) for name in ("exp2_manifest", "inputs", "cohort"))
    m2_registry, mapping, policy_payload = (load_json(paths[name]) for name in ("m2_registry", "mapping_registry", "risk_policy"))
    _require(exp2_manifest.get("scope") == SCOPE and exp2_manifest.get("split") == "FINAL_TEST", "EXP3_FINAL_TEST_RMB_EXP2_SCOPE_INVALID")
    _require(exp2_manifest.get("safety", {}).get("FINAL_TEST_ACCESS_COUNT", 0) > 0, "EXP3_FINAL_TEST_RMB_EXP2_ACCESS_INVALID")
    _require(file_sha256(paths["consequences"]) == exp2_manifest["artifact_hashes"]["consequences"], "EXP3_FINAL_TEST_RMB_EXP2_HASH_MISMATCH")
    _require(cohort.get("scope") == SCOPE and cohort.get("development_input_used") is False, "EXP3_FINAL_TEST_RMB_COHORT_SCOPE_INVALID")
    _require(len(tuple(m2_registry["formal_scope"])) == 7, "EXP3_FINAL_TEST_RMB_FORMAL_SCOPE_INVALID")
    registry_hash = str(mapping.get("registry_hash")); _require(registry_hash.startswith("sha256:"), "EXP3_FINAL_TEST_RMB_REGISTRY_IDENTITY_MISSING")
    money_rates = _rates(mapping); policy = policy_payload["policy"]
    action_registry = ActionRegistry.load(paths["action_registry"])
    response_registry = ResponseScenarioRegistry.load(paths["response_registry"], structural_registry=action_registry)
    templates = {item.template_id: item for item in action_registry.templates}
    pre_by_node = {state["decision_node"]["decision_node_id"]: state
                   for states in inputs["pre_states_by_episode"].values() for state in states}
    successor_date_by_episode = cohort["successor_service_dates"]
    expected_nodes = int(exp2_manifest["node_count"])
    _require(len(pre_by_node) == expected_nodes == int(cohort["node_count"]), "EXP3_FINAL_TEST_RMB_INPUT_CARDINALITY_INVALID")

    output_root.mkdir(parents=True, exist_ok=True)
    staging = output_root / "staging"; staging.mkdir(parents=True, exist_ok=True)
    progress_path = output_root / "EXP3_PROGRESS.json"
    action_risk_path = output_root / "EXP3_FINAL_TEST_RMB_ACTION_RISK.parquet"
    final_staging = staging / "EXP3_FINAL_TEST_RMB_ACTION_RISK.parquet.staging"
    config = _stage_config(paths, registry_hash=registry_hash, source_manifest_hash=exp2_manifest["artifact_hash"])
    _unlink_staging([*staging.glob("*.tmp"), *staging.glob("*.partial"), *staging.glob("*.incomplete")])
    shards, completed_nodes, completed_rows = _read_verified_shards(staging=staging, progress_path=progress_path,
                                                                     root=root, total_nodes=expected_nodes, config=config)
    reader = pq.ParquetFile(paths["consequences"])
    _require(reader.num_row_groups == expected_nodes, "EXP3_FINAL_TEST_RMB_CONSEQUENCE_NODE_GROUP_INVALID")
    a00_identity_checks = 0; last_episode_id = last_decision_time = None; pending: list[dict[str, Any]] = []
    shard_start = completed_nodes
    try:
        for group_index in range(completed_nodes, reader.num_row_groups):
            source_rows = reader.read_row_group(group_index).to_pylist(); node_id = source_rows[0]["decision_node_id"]
            _require(node_id in pre_by_node, "EXP3_FINAL_TEST_RMB_PRE_STATE_MISSING")
            state = pre_by_node[node_id]; episode_id = state["decision_node"]["episode_id"]
            successor_date = successor_date_by_episode.get(episode_id)
            _require(successor_date is not None and "2019-10-01" <= successor_date <= "2019-12-31", "EXP3_FINAL_TEST_RMB_DATE_IDENTITY_INVALID")
            node_rows, checks = _node_rows(source_rows=source_rows, state=state, successor_service_date=successor_date,
                                            action_registry=action_registry, response_registry=response_registry,
                                            templates=templates, rates=money_rates, registry_hash=registry_hash,
                                            alpha=float(policy["alpha"]), expected_coefficient=float(policy["expected_loss_coefficient"]),
                                            cvar_coefficient=float(policy["cvar_coefficient"]))
            pending.extend(node_rows); a00_identity_checks += checks
            last_episode_id, last_decision_time = episode_id, state["decision_node"]["decision_time"]
            flush = len(pending) >= NODES_PER_SHARD * len(templates) * len(SENSITIVITY_LEVELS) or group_index + 1 == reader.num_row_groups
            if not flush:
                continue
            shard_index = len(shards); shard = staging / f"part-{shard_index:05d}.parquet"; temporary = shard.with_suffix(".parquet.tmp")
            pq.write_table(pa.Table.from_pylist(pending, schema=FINAL_SCHEMA), temporary, compression="zstd"); temporary.replace(shard)
            shard_nodes = (group_index + 1) - shard_start
            metadata = {"schema_version": "EXP3_FINAL_TEST_RMB_STAGING_SHARD_V1", "shard_index": shard_index,
                        "node_start": shard_start, "node_end_exclusive": group_index + 1, "node_count": shard_nodes,
                        "row_count": len(pending), "stage_config": config, "sha256": file_sha256(shard),
                        "last_episode_id": last_episode_id, "last_decision_time": last_decision_time}
            write_json(shard.with_suffix(".json"), metadata)
            shards.append(shard); completed_nodes = group_index + 1; completed_rows += len(pending)
            write_json(progress_path, _staging_state(total_nodes=expected_nodes, completed_nodes=completed_nodes,
                       completed_rows=completed_rows, last_episode_id=last_episode_id, last_decision_time=last_decision_time,
                       staging_file=shard, status="RUNNING", config=config, root=root))
            pending = []; shard_start = completed_nodes
    finally:
        reader.close()
    _require(completed_nodes == expected_nodes, "EXP3_FINAL_TEST_RMB_STAGING_INCOMPLETE")
    _require(completed_rows == expected_nodes * len(templates) * len(SENSITIVITY_LEVELS), "EXP3_FINAL_TEST_RMB_STAGING_CARDINALITY_INVALID")
    _merge_shards(shards=shards, output=final_staging)
    validation = _validate_published(path=final_staging, expected_nodes=expected_nodes,
                                     expected_actions=set(templates), registry_hash=registry_hash)
    final_staging.replace(action_risk_path)

    eligibility_counts: Counter[str] = Counter(); support_rates: list[float] = []
    for batch in pq.ParquetFile(action_risk_path).iter_batches(batch_size=8192, columns=["eligibility_state", "finite_support_rate"]):
        for row in batch.to_pylist():
            eligibility_counts[row["eligibility_state"]] += 1; support_rates.append(float(row["finite_support_rate"]))
    safety = {"FINAL_TEST_ACCESS_COUNT": 3, "PAPER_FULL_RUN": True, "MODEL_RETRAINED": False, "PARAMETER_RESELECTED": False}
    metrics = {"schema_version": "EXP3_FINAL_TEST_RMB_METRICS_V2", "status": "COMPLETE_WITH_CONDITIONAL_RMB_ACTION_COMPARISON",
               "scope": SCOPE, "dataset": "DATA2", "split": "FINAL_TEST", "episode_count": exp2_manifest["episode_count"],
               "node_count": validation["node_count"], "action_count": validation["action_count"], "output_row_count": validation["row_count"],
               "eligibility_counts": dict(eligibility_counts), "finite_support_rate_mean": mean(support_rates),
               "conditional_top1_sensitivity_agreement": validation["conditional_top1_sensitivity_agreement"],
               "monetary_system": "RMB", "cu_to_rmb": 1.0, "main_monetary_components": list(FIVE_ANCHOR_COMPONENTS),
               "excluded_operational_components": ["P_itinerary", "P_service"],
               "bands": {band: {name: money_rates[name][band] for name in FIVE_ANCHOR_COMPONENTS} for band in SENSITIVITY_LEVELS},
               "support_policy": "EXPLICIT_CONDITIONING_NO_ZERO_FILL_NO_SILENT_RENORMALIZATION",
               "validation": {**validation, "a00_consequence_identity_checks_current_run": a00_identity_checks,
                              "scenario_lineage_shared_per_node": True, "no_development_evaluation_rows": True,
                              "unsupported_component_zero_fill": False}, "safety": safety}
    metrics["artifact_hash"] = content_id(metrics)
    metrics_path = output_root / "EXP3_FINAL_TEST_RMB_METRICS.json"; write_json(metrics_path, metrics)
    table_path = output_root / "EXP3_FINAL_TEST_RMB_TABLE.csv"
    with table_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("metric", "value", "support_status")); writer.writeheader()
        writer.writerows([{ "metric": "node_count", "value": validation["node_count"], "support_status": "SUPPORTED"},
                          { "metric": "action_count", "value": validation["action_count"], "support_status": "SUPPORTED"},
                          { "metric": "main_monetary_scope", "value": "FIVE_COMPONENT_RMB", "support_status": "ASSUMPTION_GROUNDED"}])
    manifest = {"schema_version": "EXP3_FINAL_TEST_RMB_EXECUTION_MANIFEST_V2", "status": metrics["status"],
                "scope": SCOPE, "source_scope": SCOPE, "dataset": "DATA2", "split": "FINAL_TEST",
                "episode_count": exp2_manifest["episode_count"], "node_count": validation["node_count"], "action_count": validation["action_count"],
                "source_exp2_manifest_hash": exp2_manifest["artifact_hash"],
                "frozen_hashes": {"action_registry_hash": action_registry.registry_hash,
                                  "response_registry_hash": response_registry.registry_hash,
                                  "m2_registry_hash": m2_registry["registry_hash"], "rmb_registry_hash": registry_hash,
                                  "rmb_registry_file_hash": file_sha256(paths["mapping_registry"]), "risk_policy_hash": policy["policy_hash"]},
                "staging": {"directory": _relative(staging, root), "shard_count": len(shards), "progress": _relative(progress_path, root)},
                "outputs": {"action_risk": _relative(action_risk_path, root), "metrics": _relative(metrics_path, root), "table": _relative(table_path, root)},
                "artifact_hashes": {"action_risk": file_sha256(action_risk_path), "metrics": metrics["artifact_hash"]},
                "validation": metrics["validation"], "safety": safety, "paper_result": True}
    manifest["artifact_hash"] = content_id(manifest)
    manifest_path = output_root / "EXP3_FINAL_TEST_RMB_EXECUTION_MANIFEST.json"; write_json(manifest_path, manifest)
    write_json(progress_path, _staging_state(total_nodes=expected_nodes, completed_nodes=expected_nodes,
               completed_rows=validation["row_count"], last_episode_id=last_episode_id, last_decision_time=last_decision_time,
               staging_file=action_risk_path, status="PUBLISHED", config=config, root=root))
    return {"manifest": manifest_path, "metrics": metrics_path, "action_risk": action_risk_path, "table": table_path,
            "progress": progress_path}


def materialize_ranking_and_a00_gate(*, root: Path, action_risk: Path, output_root: Path) -> dict[str, Path]:
    """Materialize Final Test A_num records and the fail-closed A_sup gate."""
    from exp.exp3.a00_baseline_gate import evaluate_records, summary as gate_summary

    root, action_risk, output_root = (path.resolve() for path in (root, action_risk, output_root))
    _require(action_risk.is_file(), "M3M4_FINAL_TEST_RMB_ACTION_RISK_MISSING")
    required = {"episode_id", "decision_node_id", "decision_time", "successor_service_date", "action_id",
                "response_sensitivity", "valuation_band", "is_A00", "chi_inst", "chi_num", "response_support",
                "conditional_expected_rmb", "conditional_rmb_cvar_alpha", "conditional_residual_risk_rmb",
                "conditional_diagnostic_rank", "scenario_lineage_hash", "rmb_registry_hash"}
    source = pd.read_parquet(action_risk)
    _require(required.issubset(source.columns), "M3M4_FINAL_TEST_RMB_SCHEMA_INVALID")
    _require(source["successor_service_date"].between("2019-10-01", "2019-12-31").all(), "M3M4_FINAL_TEST_DATE_INVALID")
    _require(source["is_A00"].eq(source["action_id"].eq("A00")).all(), "M3M4_FINAL_TEST_A00_IDENTITY_INVALID")
    _require(source["action_id"].eq("A00").groupby([source["decision_node_id"], source["response_sensitivity"]]).sum().eq(1).all(),
             "M3M4_FINAL_TEST_A00_BASELINE_MISSING")
    _require(source.groupby(["decision_node_id", "response_sensitivity"])["scenario_lineage_hash"].nunique().eq(1).all(),
             "M3M4_FINAL_TEST_SCENARIO_LINEAGE_INVALID")
    records = source.loc[source["chi_num"], [
        "episode_id", "decision_node_id", "decision_time", "successor_service_date", "action_id", "action_family",
        "response_sensitivity", "valuation_band", "is_A00", "chi_inst", "chi_num", "eligibility_state",
        "response_support", "finite_status", "conditional_expected_rmb", "conditional_rmb_cvar_alpha",
        "conditional_residual_risk_rmb", "conditional_diagnostic_rank", "scenario_lineage_hash", "rmb_registry_hash",
    ]].copy()
    records["rank_position"] = records["conditional_diagnostic_rank"]
    records["conditional_top1"] = records["rank_position"].eq(1).where(records["rank_position"].notna(), None)
    records["chi_feas"] = records["eligibility_state"].eq("TRUE")
    records["chi_resp"] = records["response_support"].eq("SUPPORTED")
    records["monetary_system"] = "RMB"; records["excluded_operational_components"] = "P_itinerary,P_service"
    gate_input = records.copy(); gate_input["conditional_residual_risk"] = gate_input["conditional_residual_risk_rmb"]
    gated = evaluate_records(gate_input)
    gated.rename(columns={"a00_baseline_objective": "a00_baseline_rmb", "recommended_objective": "recommended_rmb"}, inplace=True)
    gate_stats = gate_summary(gated.rename(columns={"a00_baseline_rmb": "a00_baseline_objective", "recommended_rmb": "recommended_objective"}))
    total_node_bands = int(source.groupby(["decision_node_id", "response_sensitivity"]).ngroups)
    a_num_node_bands = int(records.groupby(["decision_node_id", "response_sensitivity"]).ngroups)
    a_sup_mask = records["chi_feas"] & records["chi_resp"] & records["action_id"].ne("A00")
    supported_node_bands = int(records.loc[a_sup_mask].groupby(["decision_node_id", "response_sensitivity"]).ngroups)
    a_num = {"status": "PASS", "decision_node_count": int(source["decision_node_id"].nunique()), "node_band_count": total_node_bands,
             "numerical_node_band_count": a_num_node_bands, "non_a00_candidate_count": int((records["action_id"] != "A00").sum()),
             "coverage": a_num_node_bands / total_node_bands if total_node_bands else None}
    a_sup = {"status": "NO_SUPPORTED_NON_A00_RECOMMENDATION" if supported_node_bands == 0 else "PASS",
             "supported_non_a00_candidate_count": int(a_sup_mask.sum()),
             "non_a00_node_band_coverage": supported_node_bands / total_node_bands if total_node_bands else None,
             "recommendation_status_counts": gate_stats["recommendation_status_counts"], "no_zero_fill": True,
             "a00_never_recommended": gate_stats["a00_recommendation_count"] == 0}
    output_root.mkdir(parents=True, exist_ok=True)
    paths = {"records": output_root / "M3M4_FINAL_TEST_RMB_COMPARISON_RANKING_RECORDS.parquet",
             "records_csv": output_root / "M3M4_FINAL_TEST_RMB_COMPARISON_RANKING_RECORDS.csv",
             "gate": output_root / "A00_FINAL_TEST_RMB_GATED_RECOMMENDATIONS.parquet",
             "gate_csv": output_root / "A00_FINAL_TEST_RMB_GATED_RECOMMENDATIONS.csv",
             "gate_summary": output_root / "A00_FINAL_TEST_RMB_GATE_SUMMARY.json",
             "stats": output_root / "M3M4_FINAL_TEST_RMB_AGGREGATE_STATS.json",
             "manifest": output_root / "M3M4_FINAL_TEST_RMB_MANIFEST.json"}
    records.to_parquet(paths["records"], index=False); records.to_csv(paths["records_csv"], index=False)
    gated.to_parquet(paths["gate"], index=False); gated.to_csv(paths["gate_csv"], index=False)
    write_json(paths["gate_summary"], {**gate_stats, "A_num": a_num, "A_sup": a_sup})
    stats = {"node_count": a_num["decision_node_count"], "episode_count": int(records["episode_id"].nunique()),
             "action_count": int(records["action_id"].nunique()), "band_count": int(records["valuation_band"].nunique()),
             "record_count": int(len(records)), "ranked_node_band_count": a_num_node_bands, "A_num": a_num, "A_sup": a_sup}
    write_json(paths["stats"], stats)
    safety = {"FINAL_TEST_ACCESS_COUNT": 1, "PAPER_FULL_RUN": True, "MODEL_RETRAINED": False, "PARAMETER_RESELECTED": False}
    manifest = {"schema_version": "AIR_SLOT_M3M4_FINAL_TEST_RMB_V2", "status": "MATERIALIZED_FAIL_CLOSED",
                "scope": SCOPE, "source_scope": SCOPE, "dataset": "DATA2", "split": "FINAL_TEST", "monetary_system": "RMB",
                "cu_to_rmb": 1.0, "main_monetary_components": list(FIVE_ANCHOR_COMPONENTS),
                "excluded_operational_components": ["P_itinerary", "P_service"],
                "selection_rule": "MIN_J_RMB_WITHIN_A_NUM_TIE_ACTION_ID_A00_REQUIRED",
                "operational_recommendation": "A00_BASELINE_FAIL_CLOSED_GATE",
                "input_hashes": {"action_risk": file_sha256(action_risk)}, "aggregate": stats,
                "outputs": {name: _relative(path, root) for name, path in paths.items() if name != "manifest"},
                "safety": safety, "paper_result": True}
    manifest["artifact_hash"] = content_id(manifest); write_json(paths["manifest"], manifest)
    return paths
