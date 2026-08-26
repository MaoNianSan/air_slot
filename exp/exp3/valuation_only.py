"""Exp3 valuation-only sensitivity materialization (F4/F5 scope).

F4 froze the 22 declared non-A00 scenario-response parameters; F5 restricts
the LOW/BASE/HIGH bands to monetary coefficients only (five-anchor EUR,
0.5x/1.0x/2.0x). Response parameters are therefore fixed at the frozen
declared BASE values for every band; no response-only perturbation is
implemented (EXP3_RESPONSE_ONLY=NOT_AUTHORIZED_PER_F4).

Every row is ASSUMPTION_GROUNDED and never authoritative. Outputs are
Development-only: filenames carry DEVELOPMENT_ONLY, the manifest carries
all-zero safety fields and input hashes, and paper_result is false.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from exp.common.official_execution import file_sha256, load_json, write_json
from exp.exp3.global_development import (
    ACTION_REGISTRY,
    EXP2_ROOT,
    FIVE_ANCHOR_COMPONENTS,
    INPUT_ROOT,
    M2_REGISTRY,
    MAPPING_REGISTRY,
    RESPONSE_REGISTRY,
    RISK_POLICY,
    SEED,
    _conditional_risk,
    _require,
)
from model.M3.instantiate import instantiate_candidates
from model.M3.registry import ActionRegistry
from model.M3.response import action_post_consequences, response_draw
from model.M3.response_registry import ResponseScenarioRegistry, SENSITIVITY_LEVELS
from model.PRE.contracts.pre_state import PREState
from model.common.identity import content_id


DEFAULT_OUTPUT = Path("artifacts/experiment/exp3/exp3_valuation_only_sensitivity_20260825")
EXISTING_ACTION_RISK = Path(
    "artifacts/experiments/exp3/full_development_v1/EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet"
)
EXPECTED_REGISTRY_HASH = "sha256:88beec332b885baf90cef90e3cc8091c8679f4ea93628c0e9227cd919c76d6a3"
RESPONSE_FREEZE_RULE = "F4_FROZEN_DECLARED_RESPONSE_PARAMETERS_BASE_FOR_ALL_BANDS"
MONETARY_BAND_RULE = "F5_MONETARY_COEFFICIENTS_ONLY_0_5X_1_0X_2_0X"
SAFETY = {
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "EXP3_RUNS": 0,
    "DEVELOPMENT_TUNING": False,
    "AUTHORITATIVE_RANKING": False,
}

VALUATION_RECORD_SCHEMA = pa.schema([
    pa.field("episode_id", pa.string()),
    pa.field("decision_node_id", pa.string()),
    pa.field("action_id", pa.string()),
    pa.field("action_family", pa.string()),
    pa.field("eligibility_state", pa.string()),
    pa.field("response_support", pa.string()),
    pa.field("valuation_band", pa.string()),
    pa.field("response_band", pa.string()),
    pa.field("response_freeze_rule", pa.string()),
    pa.field("scenario_count", pa.int64()),
    pa.field("finite_support_scenario_count", pa.int64()),
    pa.field("finite_support_rate", pa.float64()),
    pa.field("claim_status", pa.string()),
] + [
    pa.field(f"expected_consequence_{name}_cu", pa.float64())
    for name in FIVE_ANCHOR_COMPONENTS
] + [
    pa.field(f"expected_monetary_{name}_eur", pa.float64())
    for name in FIVE_ANCHOR_COMPONENTS
] + [
    pa.field("conditional_expected_constructed_eur", pa.float64()),
    pa.field("conditional_constructed_eur_variance", pa.float64()),
    pa.field("conditional_constructed_eur_var_alpha", pa.float64()),
    pa.field("conditional_constructed_eur_cvar_alpha", pa.float64()),
    pa.field("conditional_residual_risk", pa.float64()),
    pa.field("authoritative", pa.bool_()),
    pa.field("monetary_ground_truth_claim", pa.bool_()),
    pa.field("causal_action_effect_claim", pa.bool_()),
])


def _weighted_mean(values: list[float], weights: list[float]) -> float | None:
    if not values:
        return None
    total = sum(weights)
    return sum(value * weight for value, weight in zip(values, weights)) / total


def _materialize_records(
    risk_coefficients: dict, money_rates: dict, paths: dict,
    pre_by_node: dict, result_path: Path, expected_row_count: int,
    support_rates: list,
) -> None:
    """Stream per-node valuation-only records to the result parquet."""
    writer: pq.ParquetWriter | None = None
    parquet = pq.ParquetFile(paths["consequences"])
    temporary = result_path.with_suffix(".parquet.tmp")
    node_count = 0
    output_rows = 0
    action_registry = ActionRegistry.load(paths["action_registry"])
    response_registry = ResponseScenarioRegistry.load(
        paths["response_registry"], structural_registry=action_registry,
    )
    templates = {item.template_id: item for item in action_registry.templates}
    try:
        for row_group in range(parquet.num_row_groups):
            source_rows = parquet.read_row_group(row_group).to_pylist()
            node_ids = {row["decision_node_id"] for row in source_rows}
            _require(len(node_ids) == 1, "EXP3_VALUATION_NODE_ROW_GROUP_INVALID")
            node_id = next(iter(node_ids))
            total_weight = sum(float(row["scenario_weight"]) for row in source_rows)
            _require(total_weight > 0, "EXP3_VALUATION_SCENARIO_WEIGHT_INVALID")
            pre = PREState.model_validate(pre_by_node[node_id])
            candidates = instantiate_candidates(
                pre, action_registry, response_registry=response_registry,
                sensitivity="BASE",
            )
            _require(len(candidates) == 23, "EXP3_VALUATION_ACTION_LIBRARY_CARDINALITY_INVALID")
            node_rows: list[dict] = []
            for candidate in candidates:
                template = templates[candidate.template_id]
                parameters = response_registry.parameters(
                    candidate.template_id, sensitivity="BASE",
                )
                consequence_values = {name: [] for name in FIVE_ANCHOR_COMPONENTS}
                monetary_values = {
                    name: {band: [] for band in SENSITIVITY_LEVELS}
                    for name in FIVE_ANCHOR_COMPONENTS
                }
                band_values = {band: [] for band in SENSITIVITY_LEVELS}
                band_weights: list[float] = []
                for row in source_rows:
                    components = json.loads(row["components_json"])
                    supported = {
                        item["component_id"]: float(item["constructed_value_cu"])
                        for item in components
                        if item["constructed_value_cu"] is not None
                    }
                    if not all(component in supported for component in FIVE_ANCHOR_COMPONENTS):
                        continue
                    rho = response_draw(
                        seed=SEED,
                        episode_id=row["episode_id"],
                        decision_node_id=node_id,
                        scenario_id=int(row["scenario_id"]),
                        action_template_id=candidate.template_id,
                        parameters=parameters,
                        response_registry_hash=response_registry.registry_hash,
                        sensitivity_level="BASE",
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
                    weight = float(row["scenario_weight"])
                    for name in FIVE_ANCHOR_COMPONENTS:
                        consequence_values[name].append(post[name])
                        for band in SENSITIVITY_LEVELS:
                            monetary_values[name][band].append(
                                post[name] * float(money_rates[name][band])
                            )
                    for band in SENSITIVITY_LEVELS:
                        band_values[band].append(sum(
                            post[name] * float(money_rates[name][band])
                            for name in FIVE_ANCHOR_COMPONENTS
                        ))
                    band_weights.append(weight)
                support_rate = sum(band_weights) / total_weight
                support_rates.append(support_rate)
                for band in SENSITIVITY_LEVELS:
                    conditional = _conditional_risk(
                        band_values[band], band_weights, alpha=risk_coefficients["alpha"],
                        expected_coefficient=risk_coefficients["expected_coefficient"],
                        cvar_coefficient=risk_coefficients["cvar_coefficient"],
                    )
                    row: dict = {
                        "episode_id": pre.decision_node.episode_id,
                        "decision_node_id": node_id,
                        "action_id": candidate.template_id,
                        "action_family": candidate.action_family,
                        "eligibility_state": candidate.precondition_state,
                        "response_support": (
                            "IDENTITY" if candidate.template_id == "A00"
                            else "SCENARIO_ASSUMPTION"
                        ),
                        "valuation_band": band,
                        "response_band": "BASE",
                        "response_freeze_rule": RESPONSE_FREEZE_RULE,
                        "scenario_count": len(source_rows),
                        "finite_support_scenario_count": len(band_weights),
                        "finite_support_rate": support_rate,
                        "claim_status": "ASSUMPTION_GROUNDED",
                    }
                    for name in FIVE_ANCHOR_COMPONENTS:
                        row[f"expected_consequence_{name}_cu"] = _weighted_mean(
                            consequence_values[name], band_weights,
                        )
                    for name in FIVE_ANCHOR_COMPONENTS:
                        row[f"expected_monetary_{name}_eur"] = _weighted_mean(
                            monetary_values[name][band], band_weights,
                        )
                    row.update({
                        "conditional_expected_constructed_eur": (
                            None if conditional is None else conditional["expected_constructed_eur"]
                        ),
                        "conditional_constructed_eur_variance": (
                            None if conditional is None else conditional["constructed_eur_variance"]
                        ),
                        "conditional_constructed_eur_var_alpha": (
                            None if conditional is None else conditional["constructed_eur_var_alpha"]
                        ),
                        "conditional_constructed_eur_cvar_alpha": (
                            None if conditional is None else conditional["constructed_eur_cvar_alpha"]
                        ),
                        "conditional_residual_risk": (
                            None if conditional is None else conditional["residual_risk_objective"]
                        ),
                        "authoritative": False,
                        "monetary_ground_truth_claim": False,
                        "causal_action_effect_claim": False,
                    })
                    node_rows.append(row)
            table = pa.Table.from_pylist(node_rows).cast(VALUATION_RECORD_SCHEMA)
            if writer is None:
                writer = pq.ParquetWriter(temporary, VALUATION_RECORD_SCHEMA, compression="zstd")
            writer.write_table(table)
            node_count += 1
            output_rows += len(node_rows)
    finally:
        if writer is not None:
            writer.close()
    _require(node_count == 1769, "EXP3_VALUATION_NODE_COUNT_INVALID")
    _require(output_rows == expected_row_count, "EXP3_VALUATION_OUTPUT_CARDINALITY_INVALID")
    temporary.replace(result_path)


def run(
    *, root: Path, exp2_root: Path | None = None,
    input_root: Path | None = None, output_root: Path | None = None,
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
        "existing_action_risk": root / EXISTING_ACTION_RISK,
    }
    _require(all(path.is_file() for path in paths.values()), "EXP3_VALUATION_INPUT_MISSING")
    exp2_manifest = load_json(paths["exp2_manifest"])
    inputs = load_json(paths["inputs"])
    m2_registry = load_json(paths["m2_registry"])
    mapping = load_json(paths["mapping_registry"])
    policy_payload = load_json(paths["risk_policy"])
    _require(
        exp2_manifest["dataset"] == "DATA2" and exp2_manifest["split"] == "DEVELOPMENT",
        "EXP3_VALUATION_EXP2_SCOPE_INVALID",
    )
    _require(
        exp2_manifest["episode_count"] == 128 and exp2_manifest["node_count"] == 1769,
        "EXP3_VALUATION_EXP2_CARDINALITY_INVALID",
    )
    _require(
        file_sha256(paths["consequences"]) == exp2_manifest["artifact_hashes"]["consequences"],
        "EXP3_VALUATION_EXP2_HASH_MISMATCH",
    )
    _require(len(tuple(m2_registry["formal_scope"])) == 7, "EXP3_VALUATION_FORMAL_SCOPE_INVALID")
    _require(
        mapping.get("registry_hash") == EXPECTED_REGISTRY_HASH,
        "EXP3_VALUATION_EUR_MAPPING_REGISTRY_DRIFT",
    )
    components = mapping.get("ops_components")
    _require(isinstance(components, list) and len(components) == 7, "EXP3_VALUATION_MAPPING_INVALID")
    anchor_status = {item["component_id"]: item["anchor_status"] for item in components}
    _require(
        tuple(sorted(name for name, status in anchor_status.items() if status == "FROZEN_ASSUMPTION_GROUNDED"))
        == tuple(sorted(FIVE_ANCHOR_COMPONENTS)),
        "EXP3_VALUATION_MAPPING_FIVE_ANCHOR_DRIFT",
    )
    money_rates: dict[str, dict[str, float | None]] = {}
    for item in components:
        money_rates[item["component_id"]] = {
            band["band_id"]: band["per_cu_money"] for band in item["bands"]
        }
    _require(
        all(
            money_rates[component][level] is not None
            for component in FIVE_ANCHOR_COMPONENTS
            for level in SENSITIVITY_LEVELS
        ),
        "EXP3_VALUATION_MAPPING_FROZEN_RATE_MISSING",
    )

    policy = policy_payload["policy"]
    alpha = float(policy["alpha"])
    expected_coefficient = float(policy["expected_loss_coefficient"])
    cvar_coefficient = float(policy["cvar_coefficient"])
    pre_by_node: dict[str, dict] = {}
    for states in inputs["pre_states_by_episode"].values():
        for state in states:
            pre_by_node[state["decision_node"]["decision_node_id"]] = state

    output_root.mkdir(parents=True, exist_ok=True)
    result_path = output_root / "EXP3_VALUATION_ONLY_RECORDS_DEVELOPMENT_ONLY.parquet"
    expected_row_count = 1769 * 23 * len(SENSITIVITY_LEVELS)
    support_rates: list[float] = []
    if result_path.is_file():
        _require(
            pq.ParquetFile(result_path).metadata.num_rows == expected_row_count,
            "EXP3_VALUATION_RESUME_CARDINALITY_INVALID",
        )
    else:
        _materialize_records(
            {
                "alpha": alpha,
                "expected_coefficient": expected_coefficient,
                "cvar_coefficient": cvar_coefficient,
            },
            money_rates, paths, pre_by_node, result_path,
            expected_row_count, support_rates,
        )

    records = pq.read_table(
        result_path,
        columns=[
            "decision_node_id", "action_id", "valuation_band",
            "conditional_expected_constructed_eur",
        ],
    ).to_pylist()
    existing = pq.read_table(
        paths["existing_action_risk"],
        columns=[
            "decision_node_id", "action_id", "response_sensitivity",
            "conditional_expected_constructed_eur",
        ],
    ).to_pylist()
    base_by_key = {
        (row["decision_node_id"], row["action_id"]): row["conditional_expected_constructed_eur"]
        for row in existing
        if row["response_sensitivity"] == "BASE"
    }
    _require(
        len(base_by_key) == 1769 * 23,
        "EXP3_VALUATION_BASE_PARITY_CARDINALITY_INVALID",
    )
    differences: list[float] = []
    matched = 0
    null_mismatch = 0
    for row in records:
        if row["valuation_band"] != "BASE":
            continue
        key = (row["decision_node_id"], row["action_id"])
        _require(key in base_by_key, "EXP3_VALUATION_BASE_PARITY_KEY_MISSING")
        stored = base_by_key[key]
        mine = row["conditional_expected_constructed_eur"]
        if stored is None or mine is None:
            if stored is not None or mine is not None:
                null_mismatch += 1
            continue
        matched += 1
        differences.append(abs(stored - mine))
    expected_matched = sum(1 for value in base_by_key.values() if value is not None)
    _require(null_mismatch == 0, "EXP3_VALUATION_BASE_PARITY_NULL_MISMATCH")
    _require(matched == expected_matched, "EXP3_VALUATION_BASE_PARITY_MATCH_INCOMPLETE")
    parity_max_abs_diff = max(differences)
    _require(parity_max_abs_diff < 1e-9, "EXP3_VALUATION_BASE_PARITY_DRIFT")

    import statistics
    summary_rows: list[dict] = []
    for band in SENSITIVITY_LEVELS:
        band_records = pq.read_table(
            result_path,
            columns=[
                "decision_node_id", "action_id", "valuation_band",
                "conditional_expected_constructed_eur",
                "conditional_residual_risk", "finite_support_rate",
            ],
        ).to_pylist()
        band_records = [
            row for row in band_records
            if row["valuation_band"] == band
            and row["conditional_expected_constructed_eur"] is not None
        ]
        for action_id in sorted({row["action_id"] for row in band_records}):
            action_rows = [row for row in band_records if row["action_id"] == action_id]
            values = [row["conditional_expected_constructed_eur"] for row in action_rows]
            risks = [row["conditional_residual_risk"] for row in action_rows]
            rates = [row["finite_support_rate"] for row in action_rows]
            summary_rows.append({
                "valuation_band": band,
                "action_id": action_id,
                "nodes": len(action_rows),
                "expected_constructed_eur_mean": statistics.mean(values),
                "expected_constructed_eur_median": statistics.median(values),
                "residual_risk_mean": statistics.mean(risks),
                "finite_support_rate_mean": statistics.mean(rates),
            })
    summary_path = output_root / "EXP3_VALUATION_ONLY_SUMMARY_DEVELOPMENT_ONLY.csv"
    import csv
    with summary_path.open("w", newline="", encoding="utf-8") as stream:
        csv_writer = csv.DictWriter(stream, fieldnames=list(summary_rows[0]))
        csv_writer.writeheader()
        csv_writer.writerows(summary_rows)

    manifest = {
        "schema_version": "AIR_SLOT_EXP3_VALUATION_ONLY_MANIFEST_V1",
        "status": "MATERIALIZED_ASSUMPTION_GROUNDED",
        "scope": "DATA2_FULL_DEVELOPMENT_NO_FINAL_TEST",
        "dataset": "DATA2", "split": "DEVELOPMENT",
        "episode_count": 128, "node_count": 1769,
        "action_count": 23, "output_row_count": expected_row_count,
        "bands": list(SENSITIVITY_LEVELS),
        "response_freeze_rule": RESPONSE_FREEZE_RULE,
        "monetary_band_rule": MONETARY_BAND_RULE,
        "monetary_band_scales": {
            band: {
                component: money_rates[component][band] / money_rates[component]["BASE"]
                for component in FIVE_ANCHOR_COMPONENTS
            }
            for band in SENSITIVITY_LEVELS
        },
        "response_only_perturbation": "NOT_AUTHORIZED_PER_F4",
        "claim_status": "ASSUMPTION_GROUNDED_NOT_AUTHORITATIVE",
        "input_hashes": {
            "consequences": file_sha256(paths["consequences"]),
            "inputs": file_sha256(paths["inputs"]),
            "action_registry": file_sha256(paths["action_registry"]),
            "response_registry": file_sha256(paths["response_registry"]),
            "m2_registry": file_sha256(paths["m2_registry"]),
            "mapping_registry": file_sha256(paths["mapping_registry"]),
            "risk_policy": file_sha256(paths["risk_policy"]),
        },
        "base_parity_vs_existing_action_risk": {
            "existing_artifact": str(EXISTING_ACTION_RISK).replace("\\", "/"),
            "matched_rows": matched,
            "max_abs_diff_expected_constructed_eur": parity_max_abs_diff,
            "tolerance": 1e-9,
            "status": "PASS",
        },
        "outputs": {
            "records": "EXP3_VALUATION_ONLY_RECORDS_DEVELOPMENT_ONLY.parquet",
            "summary": "EXP3_VALUATION_ONLY_SUMMARY_DEVELOPMENT_ONLY.csv",
            "manifest": "EXP3_VALUATION_ONLY_MANIFEST_DEVELOPMENT_ONLY.json",
        },
        "safety": dict(SAFETY),
        "paper_result": False,
    }
    manifest["artifact_hash"] = content_id(manifest)
    manifest_path = output_root / "EXP3_VALUATION_ONLY_MANIFEST_DEVELOPMENT_ONLY.json"
    write_json(manifest_path, manifest)
    return {
        "manifest": manifest_path, "records": result_path,
        "summary": summary_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp2-root", type=Path)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    run(
        root=Path(__file__).resolve().parents[2],
        exp2_root=args.exp2_root, input_root=args.input_root,
        output_root=args.output_root,
    )
    print("EXP3_VALUATION_ONLY_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
