"""Global Development materialization for conditional M3 action responses.

The complete seven-component RMB decision remains fail-closed.  A separate,
explicit finite-support conditional diagnostic is produced for Exp3 scenario
analysis; it is never promoted to an authoritative recommendation.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from exp.common.official_execution import file_sha256, load_json, write_json
from model.M3.instantiate import instantiate_candidates
from model.M3.registry import ActionRegistry
from model.M3.response import action_post_consequences, response_draw
from model.M3.response_registry import ResponseScenarioRegistry, SENSITIVITY_LEVELS
from model.M4.residual_risk import weighted_expectation, weighted_var_cvar, weighted_variance
from model.PRE.contracts.pre_state import PREState
from model.common.identity import content_id


EXP2_ROOT = Path("artifacts/experiments/exp2/full_development_v1")
INPUT_ROOT = Path("artifacts/experiment/full_development_inputs_v1")
DEFAULT_OUTPUT = Path("artifacts/experiments/exp3/full_development_v1")
ACTION_REGISTRY = Path("registries/action_templates.yaml")
RESPONSE_REGISTRY = Path("registries/m3_response_scenarios.yaml")
M2_REGISTRY = Path("registries/m2_data2_formal_cu_v1.json")
MAPPING_REGISTRY = Path("registries/m4_cu_rmb_mapping_candidate_v1.json")
RISK_POLICY = Path("artifacts/experiment/exp2/DATA2_DEV_PILOT_M4_RISK_POLICY.json")
SEED = 20260823
SAFETY = {
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "DEVELOPMENT_TUNING": False,
    "AUTHORITATIVE_RANKING": False,
}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _conditional_risk(
    values: list[float], weights: list[float], *, alpha: float,
    expected_coefficient: float, cvar_coefficient: float,
) -> dict[str, float] | None:
    if not values:
        return None
    total_weight = sum(weights)
    normalized = tuple(value / total_weight for value in weights)
    samples = tuple(values)
    expected = weighted_expectation(samples, normalized)
    variance = weighted_variance(samples, normalized)
    var, cvar = weighted_var_cvar(samples, normalized, alpha)
    return {
        "expected_rmb": expected,
        "rmb_variance": variance,
        "rmb_var_alpha": var,
        "rmb_cvar_alpha": cvar,
        "residual_risk_objective": expected_coefficient * expected + cvar_coefficient * cvar,
    }


def run(
    *, root: Path, exp2_root: Path | None = None,
    input_root: Path | None = None, output_root: Path | None = None,
    response_scenario_limit: int | None = None,
) -> dict[str, Path]:
    root = root.resolve()
    exp2_root = (exp2_root or root / EXP2_ROOT).resolve()
    input_root = (input_root or root / INPUT_ROOT).resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    paths = {
        "exp2_manifest": exp2_root / "EXP2_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json",
        "consequences": exp2_root / "M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet",
        "inputs": input_root / "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json",
        "action_registry": root / ACTION_REGISTRY,
        "response_registry": root / RESPONSE_REGISTRY,
        "m2_registry": root / M2_REGISTRY,
        "mapping_registry": root / MAPPING_REGISTRY,
        "risk_policy": root / RISK_POLICY,
    }
    _require(all(path.is_file() for path in paths.values()), "EXP3_GLOBAL_INPUT_MISSING")
    exp2_manifest = load_json(paths["exp2_manifest"])
    inputs = load_json(paths["inputs"])
    m2_registry = load_json(paths["m2_registry"])
    mapping = load_json(paths["mapping_registry"])
    policy_payload = load_json(paths["risk_policy"])
    _require(exp2_manifest["dataset"] == "DATA2" and exp2_manifest["split"] == "DEVELOPMENT", "EXP3_GLOBAL_EXP2_SCOPE_INVALID")
    _require(exp2_manifest["episode_count"] == 128 and exp2_manifest["node_count"] == 1769, "EXP3_GLOBAL_EXP2_CARDINALITY_INVALID")
    _require(file_sha256(paths["consequences"]) == exp2_manifest["artifact_hashes"]["consequences"], "EXP3_GLOBAL_EXP2_HASH_MISMATCH")
    formal_scope = tuple(m2_registry["formal_scope"])
    _require(len(formal_scope) == 5, "EXP3_GLOBAL_FORMAL_SCOPE_INVALID")
    _require(len(mapping.get("component_mappings", {})) == 7, "EXP3_GLOBAL_MAPPING_INVALID")
    _require(all(
        next(parameter["value"] for parameter in item["parameters"] if parameter["parameter_name"] == "rmb_per_cu") == 1.0
        for item in mapping["component_mappings"].values()
    ), "EXP3_GLOBAL_MAPPING_BASELINE_DRIFT")

    policy = policy_payload["policy"]
    alpha = float(policy["alpha"])
    expected_coefficient = float(policy["expected_loss_coefficient"])
    cvar_coefficient = float(policy["cvar_coefficient"])
    action_registry = ActionRegistry.load(paths["action_registry"])
    response_registry = ResponseScenarioRegistry.load(
        paths["response_registry"], structural_registry=action_registry,
    )
    templates = {item.template_id: item for item in action_registry.templates}
    pre_by_node: dict[str, dict[str, Any]] = {}
    for states in inputs["pre_states_by_episode"].values():
        for state in states:
            pre_by_node[state["decision_node"]["decision_node_id"]] = state

    output_root.mkdir(parents=True, exist_ok=True)
    result_path = output_root / "EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet"
    temporary = result_path.with_suffix(".parquet.tmp")
    writer: pq.ParquetWriter | None = None
    parquet = pq.ParquetFile(paths["consequences"])
    node_count = 0
    output_rows = 0
    eligibility_counts: Counter[str] = Counter()
    support_rates: list[float] = []
    top_by_sensitivity: dict[str, dict[str, str]] = {
        level: {} for level in SENSITIVITY_LEVELS
    }
    try:
        for row_group in range(parquet.num_row_groups):
            source_rows = parquet.read_row_group(row_group).to_pylist()
            node_ids = {row["decision_node_id"] for row in source_rows}
            _require(len(node_ids) == 1, "EXP3_GLOBAL_NODE_ROW_GROUP_INVALID")
            node_id = next(iter(node_ids))
            if response_scenario_limit is not None:
                _require(response_scenario_limit > 0, "EXP3_GLOBAL_RESPONSE_SCENARIO_LIMIT_INVALID")
                source_rows = source_rows[:response_scenario_limit]
            total_weight = sum(float(row["scenario_weight"]) for row in source_rows)
            _require(total_weight > 0, "EXP3_GLOBAL_SCENARIO_WEIGHT_INVALID")
            pre = PREState.model_validate(pre_by_node[node_id])
            candidates = instantiate_candidates(
                pre, action_registry, response_registry=response_registry,
                sensitivity="BASE",
            )
            _require(len(candidates) == 23, "EXP3_GLOBAL_ACTION_LIBRARY_CARDINALITY_INVALID")
            node_rows: list[dict[str, Any]] = []
            for sensitivity in SENSITIVITY_LEVELS:
                for candidate in candidates:
                    template = templates[candidate.template_id]
                    parameters = response_registry.parameters(
                        candidate.template_id, sensitivity=sensitivity,
                    )
                    diagnostic_values: list[float] = []
                    diagnostic_weights: list[float] = []
                    complete_supported = 0
                    for row in source_rows:
                        components = json.loads(row["components_json"])
                        supported = {
                            item["component_id"]: float(item["constructed_value_cu"])
                            for item in components
                            if item["constructed_value_cu"] is not None
                        }
                        if len(supported) == 7:
                            complete_supported += 1
                        if not all(component in supported for component in formal_scope):
                            continue
                        rho = response_draw(
                            seed=SEED,
                            episode_id=row["episode_id"],
                            decision_node_id=node_id,
                            scenario_id=int(row["scenario_id"]),
                            action_template_id=candidate.template_id,
                            parameters=parameters,
                            response_registry_hash=response_registry.registry_hash,
                            sensitivity_level=sensitivity,
                        )
                        post = action_post_consequences(
                            pre_by_component=supported,
                            mitigation=template.mitigation,
                            induced=template.induced,
                            rho=rho,
                            induced_score_to_cu=float(
                                parameters.get(
                                    "induced_score_to_cu",
                                    response_registry.induced_score_to_cu,
                                )
                            ),
                            included_components=tuple(supported),
                        )
                        diagnostic_values.append(sum(post[name] for name in formal_scope))
                        diagnostic_weights.append(float(row["scenario_weight"]))
                    conditional = _conditional_risk(
                        diagnostic_values, diagnostic_weights, alpha=alpha,
                        expected_coefficient=expected_coefficient,
                        cvar_coefficient=cvar_coefficient,
                    )
                    support_rate = sum(diagnostic_weights) / total_weight
                    support_rates.append(support_rate)
                    eligibility_counts[candidate.precondition_state] += 1
                    node_rows.append({
                        "episode_id": pre.decision_node.episode_id,
                        "decision_node_id": node_id,
                        "action_id": candidate.template_id,
                        "action_family": candidate.action_family,
                        "response_sensitivity": sensitivity,
                        "eligibility_state": candidate.precondition_state,
                        "eligibility_interpretation": (
                            "FACTUAL_ELIGIBLE" if candidate.precondition_state == "TRUE"
                            else "CONDITIONAL_ON_REQUIRED_FACTS_TRUE"
                        ),
                        "response_support": (
                            "IDENTITY" if candidate.template_id == "A00"
                            else "SCENARIO_ASSUMPTION"
                        ),
                        "response_registry_hash": response_registry.registry_hash,
                        "scenario_count": len(source_rows),
                        "finite_support_scenario_count": len(diagnostic_values),
                        "finite_support_rate": support_rate,
                        "diagnostic_support_status": (
                            "PARTIAL_DIAGNOSTIC" if conditional is not None else "NOT_RUN"
                        ),
                        "conditional_expected_rmb": None if conditional is None else conditional["expected_rmb"],
                        "conditional_rmb_variance": None if conditional is None else conditional["rmb_variance"],
                        "conditional_rmb_var_alpha": None if conditional is None else conditional["rmb_var_alpha"],
                        "conditional_rmb_cvar_alpha": None if conditional is None else conditional["rmb_cvar_alpha"],
                        "conditional_residual_risk": None if conditional is None else conditional["residual_risk_objective"],
                        "complete_seven_component_supported_scenarios": complete_supported,
                        "complete_rmb_risk_status": "NOT_RUN",
                        "complete_rmb_risk_reason": "P_ITINERARY_P_SERVICE_ABSTAIN_AND_POSITIVE_TAIL_MAGNITUDE_UNAVAILABLE",
                        "ranking_authority": "CONDITIONAL_DIAGNOSTIC_NOT_PRINCIPAL",
                        "monetary_ground_truth_claim": False,
                        "causal_action_effect_claim": False,
                    })
            for sensitivity in SENSITIVITY_LEVELS:
                comparable = [
                    row for row in node_rows
                    if row["response_sensitivity"] == sensitivity
                    and row["conditional_residual_risk"] is not None
                ]
                comparable.sort(key=lambda row: (row["conditional_residual_risk"], row["action_id"]))
                for rank, row in enumerate(comparable, start=1):
                    row["conditional_diagnostic_rank"] = rank
                if comparable:
                    top_by_sensitivity[sensitivity][node_id] = comparable[0]["action_id"]
            for row in node_rows:
                row.setdefault("conditional_diagnostic_rank", None)
            table = pa.Table.from_pylist(node_rows)
            if writer is None:
                writer = pq.ParquetWriter(temporary, table.schema, compression="zstd")
            writer.write_table(table)
            node_count += 1
            output_rows += len(node_rows)
    finally:
        if writer is not None:
            writer.close()
    _require(node_count == 1769, "EXP3_GLOBAL_NODE_COUNT_INVALID")
    _require(output_rows == node_count * 23 * len(SENSITIVITY_LEVELS), "EXP3_GLOBAL_OUTPUT_CARDINALITY_INVALID")
    temporary.replace(result_path)

    base = top_by_sensitivity["BASE"]
    agreement = {}
    for sensitivity in ("LOW", "HIGH"):
        common = set(base) & set(top_by_sensitivity[sensitivity])
        agreement[sensitivity] = None if not common else mean(
            base[node] == top_by_sensitivity[sensitivity][node] for node in common
        )
    metrics = {
        "schema_version": "EXP3_FULL_DEVELOPMENT_METRICS_V1",
        "status": "COMPLETE_WITH_CONDITIONAL_DIAGNOSTIC_AND_FORMAL_NOT_RUN",
        "dataset": "DATA2", "split": "DEVELOPMENT",
        "episode_count": 128, "node_count": node_count, "action_count": 23,
        "output_row_count": output_rows,
        "eligibility_counts": dict(eligibility_counts),
        "finite_support_rate_mean": mean(support_rates) if support_rates else None,
        "conditional_top1_response_sensitivity_agreement": agreement,
        "global_rmb_scale_sensitivity": {
            "scales": [0.5, 1.0, 2.0],
            "ranking_invariance": "MATHEMATICALLY_INVARIANT_UNDER_COMMON_POSITIVE_SCALE",
            "development_selection": False,
        },
        "formal_complete_chain": {
            "support_status": "NOT_RUN",
            "reason": "COMPLETE_SEVEN_COMPONENT_RMB_AND_TAIL_MAGNITUDE_UNAVAILABLE",
            "authoritative_ranking": False,
            "decision_selection": "NOT_RUN",
        },
        "diagnostic_scope": "FINITE_SUPPORT_CONDITIONAL_FIVE_COMPONENT_RMB_NOT_PRINCIPAL",
        "support_policy": "EXPLICIT_CONDITIONING_NO_ZERO_FILL_NO_SILENT_RENORMALIZATION",
        "safety": dict(SAFETY),
    }
    metrics["artifact_hash"] = content_id(metrics)
    metrics_path = output_root / "EXP3_FULL_DEVELOPMENT_METRICS.json"
    write_json(metrics_path, metrics)

    table_path = output_root / "EXP3_FULL_DEVELOPMENT_TABLE.csv"
    with table_path.open("w", newline="", encoding="utf-8") as stream:
        csv_writer = csv.DictWriter(stream, fieldnames=("metric", "value", "support_status"))
        csv_writer.writeheader()
        csv_writer.writerow({"metric": "node_count", "value": node_count, "support_status": "SUPPORTED"})
        csv_writer.writerow({"metric": "action_count", "value": 23, "support_status": "SUPPORTED"})
        csv_writer.writerow({"metric": "formal_authoritative_ranking", "value": None, "support_status": "NOT_RUN"})
        csv_writer.writerow({"metric": "finite_support_rate_mean", "value": metrics["finite_support_rate_mean"], "support_status": "PARTIAL_DIAGNOSTIC"})
    interpretation_path = output_root / "EXP3_FULL_DEVELOPMENT_INTERPRETATION.md"
    interpretation_path.write_text(
        "# Exp3 Development Interpretation\n\n"
        "All 23 action identities are evaluated as identity or versioned scenario-response assumptions. "
        "The finite-support five-component ranking is a conditional diagnostic only. Complete RMB risk and "
        "authoritative decision selection remain NOT_RUN because unsupported passenger components and "
        "positive-tail magnitudes are not fabricated. No causal action-effect claim is made.\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "EXP3_FULL_DEVELOPMENT_EXECUTION_MANIFEST_V1",
        "status": metrics["status"],
        "dataset": "DATA2", "split": "DEVELOPMENT",
        "episode_count": 128, "node_count": node_count, "action_count": 23,
        "source_exp2_manifest_hash": exp2_manifest["artifact_hash"],
        "frozen_hashes": {
            "action_registry_hash": action_registry.registry_hash,
            "response_registry_hash": response_registry.registry_hash,
            "m2_registry_hash": m2_registry["registry_hash"],
            "mapping_hash": mapping["registry_hash"],
            "risk_policy_hash": policy["policy_hash"],
        },
        "outputs": {
            "action_risk": str(result_path.relative_to(root)).replace("\\", "/"),
            "metrics": str(metrics_path.relative_to(root)).replace("\\", "/"),
            "table": str(table_path.relative_to(root)).replace("\\", "/"),
            "interpretation": str(interpretation_path.relative_to(root)).replace("\\", "/"),
        },
        "artifact_hashes": {
            "action_risk": file_sha256(result_path),
            "metrics": metrics["artifact_hash"],
        },
        "safety": dict(SAFETY),
    }
    manifest["artifact_hash"] = content_id(manifest)
    manifest_path = output_root / "EXP3_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json"
    write_json(manifest_path, manifest)
    return {
        "manifest": manifest_path, "metrics": metrics_path,
        "action_risk": result_path, "table": table_path,
        "interpretation": interpretation_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp2-root", type=Path)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--response-scenario-limit", type=int)
    args = parser.parse_args(argv)
    run(
        root=Path(__file__).resolve().parents[2], exp2_root=args.exp2_root,
        input_root=args.input_root, output_root=args.output_root,
        response_scenario_limit=args.response_scenario_limit,
    )
    print("EXP3_FULL_DEVELOPMENT_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
