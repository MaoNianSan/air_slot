"""Development E2E runtime repeats for Exp4D (operational adequacy only).

Each repeat runs the real decision-node chain from frozen state load to a
serialized conditional-ranking row:

    PRE state load -> M1 scenario read (materialized offline)
    -> M2 consequence read (materialized offline) -> M3 action risk
    -> ranking -> output serialization

M1 scenario generation and M2 consequence materialization are offline batch
products of the frozen development chain; their reads are timed and their
offline materialization is explicitly excluded and never repeated.  The
resulting percentiles (P50/P95/P99) and within-budget rates are engineering
adequacy diagnostics only: they are not scientific evidence, never claim
novelty, and never touch Final Test.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

import pyarrow.parquet as pq

from exp.common.official_execution import file_sha256, load_json, write_json
from exp.exp3.global_development import (
    FIVE_ANCHOR_COMPONENTS,
    PENDING_MONETARY_COMPONENTS,
)
from exp.exp4.metrics import latency_percentiles
from model.M3.instantiate import instantiate_candidates
from model.M3.registry import ActionRegistry
from model.M3.response import action_post_consequences, response_draw
from model.M3.response_registry import ResponseScenarioRegistry, SENSITIVITY_LEVELS
from model.PRE.contracts.pre_state import PREState
from model.common.identity import content_id


EXP2_ROOT = Path("artifacts/experiments/exp2/full_development_v1")
SCENARIO_ROOT = Path("artifacts/experiments/exp2/full_development_scenarios_v1")
INPUT_ROOT = Path("artifacts/experiment/full_development_inputs_v1")
DEFAULT_OUTPUT = Path("artifacts/experiments/exp4/e2e_runtime_v1")
ACTION_REGISTRY = Path("registries/action_templates.yaml")
RESPONSE_REGISTRY = Path("registries/m3_response_scenarios.yaml")
M2_REGISTRY = Path("registries/m2_data2_formal_cu_v2.json")
MAPPING_REGISTRY = Path("registries/m4_eur_mapping_assumption_grounded_v1.json")
RISK_POLICY = Path("artifacts/experiment/exp2/DATA2_DEV_PILOT_M4_RISK_POLICY.json")
SEED = 20260823
BUDGETS = (60, 120, 300)
SAFETY = {
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "DEVELOPMENT_TUNING": False,
    "AUTHORITATIVE_RANKING": False,
    "SCIENTIFIC_CLAIM": False,
}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _money_rates(mapping: dict[str, Any]) -> dict[str, dict[str, float]]:
    rates: dict[str, dict[str, float]] = {}
    for item in mapping["ops_components"]:
        rates[item["component_id"]] = {
            band["band_id"]: band["per_cu_money"] for band in item["bands"]
        }
    return rates


def _row_group_index(parquet: pq.ParquetFile) -> dict[str, int]:
    """Map decision_node_id -> row-group index (row groups are single-node)."""
    index: dict[str, int] = {}
    for group_index in range(parquet.num_row_groups):
        meta = parquet.metadata.row_group(group_index)
        statistics = meta.column(1).statistics
        if statistics is not None and statistics.has_min_max and statistics.min == statistics.max:
            node_id = str(statistics.min)
        else:
            node_id = str(
                parquet.read_row_group(
                    group_index, columns=["decision_node_id"],
                ).column(0)[0].as_py()
            )
        _require(node_id not in index, "EXP4_E2E_ROW_GROUP_NODE_DUPLICATE")
        index[node_id] = group_index
    return index


def _node_chain(
    *,
    pre_state: dict[str, Any],
    consequence_rows: list[dict[str, Any]],
    candidates: list[Any],
    templates: dict[str, Any],
    response_registry: Any,
    rates: dict[str, dict[str, float]],
) -> dict[str, Any]:
    """One decision node: 23 actions x 3 sensitivities over its scenarios."""
    output_rows = 0
    all_rows: list[dict[str, Any]] = []
    for sensitivity in SENSITIVITY_LEVELS:
        node_risk: list[dict[str, Any]] = []
        for candidate in candidates:
            template = templates[candidate.template_id]
            parameters = response_registry.parameters(
                candidate.template_id, sensitivity=sensitivity,
            )
            values: list[float] = []
            weights: list[float] = []
            for row in consequence_rows:
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
                    decision_node_id=row["decision_node_id"],
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
                values.append(sum(
                    post[name] * float(rates[name][sensitivity])
                    for name in FIVE_ANCHOR_COMPONENTS
                ))
                weights.append(float(row["scenario_weight"]))
            if not values:
                expected = None
            else:
                total = sum(weights)
                expected = sum(
                    value * weight for value, weight in zip(values, weights)
                ) / total
            node_risk.append({
                "action_id": candidate.template_id,
                "sensitivity": sensitivity,
                "expected_constructed_eur": expected,
            })
            output_rows += 1
        node_risk.sort(key=lambda item: (
            item["expected_constructed_eur"] is None,
            float("inf") if item["expected_constructed_eur"] is None else item["expected_constructed_eur"],
            item["action_id"],
        ))
        rank = 0
        for item in node_risk:
            if item["expected_constructed_eur"] is None:
                item["diagnostic_rank"] = None
            else:
                rank += 1
                item["diagnostic_rank"] = rank
        all_rows.extend(node_risk)
    return {
        "decision_node_id": pre_state["decision_node"]["decision_node_id"],
        "output_rows": output_rows,
        "ranking_rows": [
            {
                "decision_node_id": pre_state["decision_node"]["decision_node_id"],
                "action_id": item["action_id"],
                "response_sensitivity": item["sensitivity"],
                "expected_constructed_eur": item["expected_constructed_eur"],
                "conditional_diagnostic_rank": item["diagnostic_rank"],
                "ranking_authority": "CONDITIONAL_DIAGNOSTIC_5_ANCHOR_SUBSET_NOT_PRINCIPAL",
                "pending_monetary_event_status": "EVENT_COUNTS_ONLY_MONETARY_NOT_ANCHORED",
            }
            for item in all_rows
        ],
    }


def run(
    *,
    root: Path,
    exp2_root: Path | None = None,
    input_root: Path | None = None,
    output_root: Path | None = None,
    repeats: int = 60,
) -> dict[str, Path]:
    root = root.resolve()
    exp2_root = (exp2_root or root / EXP2_ROOT).resolve()
    input_root = (input_root or root / INPUT_ROOT).resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    _require(repeats > 0, "EXP4_E2E_REPEATS_REQUIRED")
    paths = {
        "exp2_manifest": exp2_root / "EXP2_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json",
        "consequences": exp2_root / "M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet",
        "scenarios": exp2_root.parent / SCENARIO_ROOT.name / "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIOS.parquet",
        "scenario_manifest": exp2_root.parent / SCENARIO_ROOT.name / "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json",
        "inputs": input_root / "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json",
        "action_registry": root / ACTION_REGISTRY,
        "response_registry": root / RESPONSE_REGISTRY,
        "m2_registry": root / M2_REGISTRY,
        "mapping_registry": root / MAPPING_REGISTRY,
        "risk_policy": root / RISK_POLICY,
    }
    _require(all(path.is_file() for path in paths.values()), "EXP4_E2E_INPUT_MISSING")
    exp2_manifest = load_json(paths["exp2_manifest"])
    scenario_manifest = load_json(paths["scenario_manifest"])
    bootstrap_started = perf_counter()
    inputs = load_json(paths["inputs"])
    state_store_load_seconds = perf_counter() - bootstrap_started
    m2_registry = load_json(paths["m2_registry"])
    mapping = load_json(paths["mapping_registry"])
    policy_payload = load_json(paths["risk_policy"])
    _require(exp2_manifest["episode_count"] == 128 and exp2_manifest["node_count"] == 1769, "EXP4_E2E_EXP2_CARDINALITY_INVALID")
    _require(file_sha256(paths["consequences"]) == exp2_manifest["artifact_hashes"]["consequences"], "EXP4_E2E_EXP2_HASH_MISMATCH")
    _require(file_sha256(paths["scenarios"]) == scenario_manifest["artifact_hash"], "EXP4_E2E_SCENARIOS_HASH_MISMATCH")
    _require(mapping["registry_hash"] == "sha256:88beec332b885baf90cef90e3cc8091c8679f4ea93628c0e9227cd919c76d6a3", "EXP4_E2E_EUR_MAPPING_DRIFT")
    _require(len(m2_registry["formal_scope"]) == 7, "EXP4_E2E_FORMAL_SCOPE_INVALID")
    rates = _money_rates(mapping)
    policy = policy_payload["policy"]
    _require(policy["policy_status"] == "FROZEN", "EXP4_E2E_POLICY_NOT_FROZEN")

    action_registry = ActionRegistry.load(paths["action_registry"])
    response_registry = ResponseScenarioRegistry.load(
        paths["response_registry"], structural_registry=action_registry,
    )
    templates = {item.template_id: item for item in action_registry.templates}
    pre_by_node: dict[str, dict[str, Any]] = {}
    for states in inputs["pre_states_by_episode"].values():
        for state in states:
            pre_by_node[state["decision_node"]["decision_node_id"]] = state
    _require(len(pre_by_node) == 1769, "EXP4_E2E_PRE_STATE_COUNT_INVALID")

    parquet = pq.ParquetFile(paths["consequences"])
    scenarios = pq.ParquetFile(paths["scenarios"])
    _require(
        parquet.num_row_groups == 1769 and scenarios.num_row_groups == 1769,
        "EXP4_E2E_ROW_GROUP_COUNT_INVALID",
    )
    node_ids = tuple(sorted(pre_by_node))
    _require(len(node_ids) == 1769, "EXP4_E2E_NODE_COUNT_INVALID")
    selected = node_ids[:repeats]
    indexed = perf_counter()
    consequences_index = _row_group_index(parquet)
    scenarios_index = _row_group_index(scenarios)
    row_group_index_seconds = perf_counter() - indexed
    _require(set(consequences_index) == set(pre_by_node), "EXP4_E2E_CONSEQUENCES_INDEX_INCOMPLETE")
    _require(set(scenarios_index) == set(pre_by_node), "EXP4_E2E_SCENARIOS_INDEX_INCOMPLETE")

    repeats_rows: list[dict[str, Any]] = []
    stage_totals: dict[str, list[float]] = {
        "pre_state_load": [], "m1_scenario_read": [], "m2_consequence_read": [],
        "m3_action_risk": [], "ranking_output_serialization": [],
    }
    ranking_rows: list[dict[str, Any]] = []
    for node_id in selected:
        timings: dict[str, float] = {}
        started = perf_counter()
        pre_state = pre_by_node[node_id]
        pre = PREState.model_validate(pre_state)
        timings["pre_state_load"] = perf_counter() - started

        started = perf_counter()
        scenario_rows = scenarios.read_row_group(scenarios_index[node_id]).to_pylist()
        timings["m1_scenario_read"] = perf_counter() - started
        _require(len(scenario_rows) == 250, "EXP4_E2E_NODE_SCENARIOS_INVALID")

        started = perf_counter()
        consequence_rows = parquet.read_row_group(consequences_index[node_id]).to_pylist()
        timings["m2_consequence_read"] = perf_counter() - started
        _require(len(consequence_rows) == 250, "EXP4_E2E_NODE_CONSEQUENCES_INVALID")

        started = perf_counter()
        candidates = instantiate_candidates(
            pre, action_registry, response_registry=response_registry,
            sensitivity="BASE",
        )
        _require(len(candidates) == 23, "EXP4_E2E_ACTION_LIBRARY_CARDINALITY_INVALID")
        node_result = _node_chain(
            pre_state=pre_state,
            consequence_rows=consequence_rows,
            candidates=candidates,
            templates=templates,
            response_registry=response_registry,
            rates=rates,
        )
        timings["m3_action_risk"] = perf_counter() - started

        started = perf_counter()
        ranking_rows.extend(node_result["ranking_rows"])
        timings["ranking_output_serialization"] = perf_counter() - started
        row = {
            "decision_node_id": node_id,
            "e2e_seconds": round(sum(timings.values()), 6),
            **{f"{name}_seconds": round(value, 6) for name, value in timings.items()},
            "ranking_rows": node_result["output_rows"],
        }
        repeats_rows.append(row)
        for name, value in timings.items():
            stage_totals[name].append(value)
    _require(len(repeats_rows) == repeats, "EXP4_E2E_REPEAT_COUNT_INVALID")
    _require(len(ranking_rows) == repeats * 23 * len(SENSITIVITY_LEVELS), "EXP4_E2E_RANKING_ROWS_INVALID")

    e2e_values = [float(row["e2e_seconds"]) for row in repeats_rows]
    e2e_stats = latency_percentiles(
        ({"E2E_latency": value} for value in e2e_values), "E2E_latency",
    )
    within = {
        f"WITHIN_{budget}S": (
            sum(1.0 for value in e2e_values if value <= budget) / len(e2e_values)
        )
        for budget in BUDGETS
    }
    stage_stats = {
        name: latency_percentiles(
            ({"E2E_latency": value} for value in values), "E2E_latency",
        )
        for name, values in stage_totals.items()
    }
    output_root.mkdir(parents=True, exist_ok=True)
    metrics = {
        "schema_version": "EXP4_E2E_RUNTIME_METRICS_V1",
        "status": "COMPLETE_ENGINEERING_ADEQUACY_DIAGNOSTIC",
        "role": "OPERATIONAL_ADEQUACY_NOT_SCIENTIFIC_EVIDENCE",
        "pipeline_scope": (
            "DECISION_NODE_CHAIN_PRE_STATE_LOAD_M1_SCENARIO_READ_M2_CONSEQUENCE_READ_"
            "M3_ACTION_RISK_RANKING_OUTPUT_SERIALIZATION"
        ),
        "m1_scenario_generation": "MATERIALIZED_OFFLINE_EXCLUDED_FROM_REPEATS",
        "m2_consequence_materialization": "MATERIALIZED_OFFLINE_EXCLUDED_FROM_REPEATS",
        "repeats": repeats,
        "nodes": list(selected),
        "bootstrap": {
            "state_store_load_seconds": round(state_store_load_seconds, 6),
            "row_group_index_seconds": round(row_group_index_seconds, 6),
            "note": "ONE_TIME_STARTUP_COSTS_EXCLUDED_FROM_PER_REPEAT_E2E",
        },
        "e2e_percentiles_seconds": e2e_stats,
        "within_budget_rates": within,
        "hard_budget_seconds": 300,
        "stage_percentiles_seconds": stage_stats,
        "ranking_authority": "CONDITIONAL_DIAGNOSTIC_5_ANCHOR_SUBSET_NOT_PRINCIPAL",
        "pending_monetary_event_status": "EVENT_COUNTS_ONLY_MONETARY_NOT_ANCHORED",
        "safety": dict(SAFETY),
    }
    metrics["artifact_hash"] = content_id(metrics)
    repeats_path = output_root / "EXP4_E2E_RUNTIME_REPEATS.json"
    write_json(repeats_path, {"schema_version": "EXP4_E2E_RUNTIME_REPEATS_V1", "repeats": repeats_rows})
    metrics_path = output_root / "EXP4_E2E_RUNTIME_METRICS.json"
    write_json(metrics_path, metrics)
    table_path = output_root / "EXP4_E2E_RUNTIME_TABLE.csv"
    with table_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "metric", "value", "unit", "support_status",
        ))
        writer.writeheader()
        writer.writerow({"metric": "E2E_P50_SECONDS", "value": e2e_stats["p50"], "unit": "seconds", "support_status": "OPERATIONAL_ADEQUACY"})
        writer.writerow({"metric": "E2E_P95_SECONDS", "value": e2e_stats["p95"], "unit": "seconds", "support_status": "OPERATIONAL_ADEQUACY"})
        writer.writerow({"metric": "E2E_P99_SECONDS", "value": e2e_stats["p99"], "unit": "seconds", "support_status": "OPERATIONAL_ADEQUACY"})
        for budget in BUDGETS:
            writer.writerow({"metric": f"WITHIN_{budget}S", "value": within[f"WITHIN_{budget}S"], "unit": "rate", "support_status": "OPERATIONAL_ADEQUACY"})
        for name, stats in stage_stats.items():
            writer.writerow({"metric": f"{name}_p95_seconds", "value": stats["p95"], "unit": "seconds", "support_status": "OPERATIONAL_ADEQUACY"})
    interpretation_path = output_root / "EXP4_E2E_RUNTIME_INTERPRETATION.md"
    interpretation_path.write_text(
        "# Exp4D Development E2E Runtime Interpretation\n\n"
        "These repeats are an engineering adequacy (operational adequacy) diagnostic of the "
        "decision-node chain: PRE state load -> M1 scenario read (materialized offline) -> "
        "M2 consequence read (materialized offline) -> M3 action risk -> ranking -> output "
        "serialization. They are NOT scientific evidence: no novelty, no predictive "
        "performance, no causal/regret/optimal claim, no Final Test. The 300-second budget "
        "is the formal hard budget (roll = 5 minutes); 60/120 seconds are descriptive "
        "references only. M1 scenario generation and M2 consequence materialization are "
        "offline batch products of the frozen development chain and are excluded from the "
        "repeats; their reads are included.\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "EXP4_E2E_RUNTIME_EXECUTION_MANIFEST_V1",
        "status": metrics["status"],
        "role": "OPERATIONAL_ADEQUACY_NOT_SCIENTIFIC_EVIDENCE",
        "repeats": repeats,
        "source_exp2_manifest_hash": exp2_manifest["artifact_hash"],
        "frozen_hashes": {
            "action_registry_hash": action_registry.registry_hash,
            "response_registry_hash": response_registry.registry_hash,
            "m2_registry_hash": m2_registry["registry_hash"],
            "mapping_registry_hash": mapping["registry_hash"],
            "risk_policy_hash": policy["policy_hash"],
        },
        "outputs": {
            "repeats": _relative(repeats_path, root),
            "metrics": _relative(metrics_path, root),
            "table": _relative(table_path, root),
            "interpretation": _relative(interpretation_path, root),
        },
        "artifact_hashes": {
            "metrics": metrics["artifact_hash"],
            "repeats": file_sha256(repeats_path),
        },
        "safety": dict(SAFETY),
    }
    manifest["artifact_hash"] = content_id(manifest)
    manifest_path = output_root / "EXP4_E2E_RUNTIME_EXECUTION_MANIFEST.json"
    write_json(manifest_path, manifest)
    return {
        "manifest": manifest_path, "metrics": metrics_path,
        "repeats": repeats_path, "table": table_path,
        "interpretation": interpretation_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exp4D development E2E runtime repeats.")
    parser.add_argument("--exp2-root", type=Path)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--repeats", type=int, default=60)
    args = parser.parse_args(argv)
    run(
        root=Path(__file__).resolve().parents[2],
        exp2_root=args.exp2_root,
        input_root=args.input_root,
        output_root=args.output_root,
        repeats=args.repeats,
    )
    print("EXP4_E2E_RUNTIME_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
