"""Materialize non-causal conditional Exp2 downstream diagnostics."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any

from model.M3.registry import ActionRegistry
from model.M3.response import action_post_consequences, response_draw
from model.M3.response_registry import ResponseScenarioRegistry
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id

FORMAL_COMPONENTS = (
    "F_continuity", "F_execution", "F_propagation", "P_time", "R_operating",
)
VARIANTS = ("EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT", "EXP2B_SCALAR", "EXP2B_3CHANNEL", "EXP2B_7COMP")
SAFETY = {
    "M1_TRAINING_RUNS": 0, "TUNING_RUNS": 0, "EXP2_RUNS": 0,
    "EXP3_RUNS": 0, "EXP4_RUNS": 0, "FINAL_TEST_ACCESS_COUNT": 0,
    "FULL": False, "PAPER_FULL_RUN": False,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"EXP2_CONDITIONAL_DIAGNOSTIC_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(rendered, encoding="utf-8")
    temp.replace(path)


def _group(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return dict(grouped)


def _component_map(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["component_id"]: item for item in row["components"]}


def _variant_status(variant: str) -> tuple[str, str]:
    if variant == "EXP2B_7COMP":
        return "READY_CONDITIONAL_COMPONENT_LANE", "M3_CONSUMES_EXACT_SEVEN_COMPONENTS"
    if variant in {"EXP2B_SCALAR", "EXP2B_3CHANNEL"}:
        return "BLOCKED_REPRESENTATION_CANNOT_BIND_EXACT_SEVEN_COMPONENT_INTERFACE", "M3_M4_TYPED_INTERFACE_REQUIRES_EXACT_SEVEN_COMPONENTS"
    return "READY_CONDITIONAL_COMPONENT_LANE", "M1_SCENARIO_TRANSFORM_PRESERVED_WITHOUT_EFFECT_IDENTIFICATION"


def _scenario_rows(variant: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = list(rows)
    if variant in {"EXP2A_JOINT", "EXP2B_7COMP"}:
        return rows
    if variant == "EXP2A_POINT":
        def distance(candidate: dict[str, Any]) -> float:
            return sum(float(row["scenario_weight"]) * sum((float(candidate.get(name, 0.0)) - float(row.get(name, 0.0))) ** 2 for name in ("D_OB", "D_TX", "D_TO")) for row in rows)
        selected = dict(min(enumerate(rows), key=lambda item: (distance(item[1]), item[0]))[1])
        selected["scenario_id"] = f"POINT:{selected['scenario_id']}"
        selected["scenario_weight"] = 1.0
        return [selected]
    if variant == "EXP2A_MARGINAL":
        if len({float(row["scenario_weight"]) for row in rows}) != 1:
            raise RuntimeError("EXP2_CONDITIONAL_MARGINAL_WEIGHT_POLICY_BLOCKED")
        output = []
        for index, original in enumerate(rows):
            row = dict(original)
            row["D_OB"] = rows[index].get("D_OB")
            row["D_TX"] = rows[(index + 1) % len(rows)].get("D_TX")
            row["D_TO"] = None if row["D_OB"] is None or row["D_TX"] is None else float(row["D_OB"]) + float(row["D_TX"])
            row["lineage"] = tuple(dict.fromkeys(tuple(rows[index].get("lineage", ())) + tuple(rows[(index + 1) % len(rows)].get("lineage", ()))))
            output.append(row)
        return output
    return rows


def _action_row(action_id: str, action_template: Any, response: ResponseScenarioRegistry, baseline: dict[str, Any], decision_node_id: str, episode_id: str, scenario_id: Any, scenario_weight: float, seed: int) -> dict[str, Any]:
    components = _component_map(baseline)
    parameters = response.parameters(action_id, sensitivity="BASE")
    rho = 0.0
    if action_id != "A00":
        rho = response_draw(seed=seed, episode_id=episode_id, decision_node_id=decision_node_id, scenario_id=scenario_id, action_template_id=action_id, parameters=parameters, response_registry_hash=response.registry_hash, sensitivity_level="BASE")
    formal_values = {component: float(components[component]["constructed_value_cu"]) for component in FORMAL_COMPONENTS if components[component]["support_state"] == "SUPPORTED" and components[component]["constructed_value_cu"] is not None}
    post_formal = dict(formal_values)
    if action_id != "A00" and formal_values:
        post_formal = action_post_consequences(pre_by_component=formal_values, mitigation=action_template.mitigation, induced=action_template.induced, rho=rho, induced_score_to_cu=float(parameters["induced_score_to_cu"]), included_components=tuple(formal_values))
    effects = []
    for component_id in CONSEQUENCE_COMPONENTS:
        item = components[component_id]
        supported = item["support_state"] == "SUPPORTED" and item["constructed_value_cu"] is not None
        effects.append({
            "component_id": component_id,
            "baseline_cu": item["constructed_value_cu"] if supported else None,
            "post_action_cu": post_formal.get(component_id) if supported else None,
            "delta_cu": (post_formal[component_id] - float(item["constructed_value_cu"])) if supported and component_id in post_formal else None,
            "support_state": "SUPPORTED" if supported else "ABSTAIN",
            "reason_code": None if supported else item.get("reason_code") or "BASELINE_COMPONENT_ABSTAIN",
            "baseline_reference_lineage": item.get("reference_lineage", ()),
        })
    supported_count = sum(item["support_state"] == "SUPPORTED" for item in effects)
    return {
        "action_id": action_id,
        "action_family": action_template.family,
        "action_support": "SUPPORTED_IDENTITY" if action_id == "A00" else "CONDITIONAL_HYBRID",
        "interpretation_scope": "BASELINE_IDENTITY" if action_id == "A00" else "SCENARIO_CONDITIONED_NON_AUTHORITATIVE",
        "causal_effect_identified": False,
        "response_parameters": parameters,
        "response_rho": rho,
        "component_effects": effects,
        "supported_component_count": supported_count,
        "seven_component_coverage": supported_count / len(CONSEQUENCE_COMPONENTS),
        "formal_five_component_sum_cu": sum(post_formal.values()) if len(post_formal) == len(FORMAL_COMPONENTS) else None,
        "formal_five_component_status": "SUPPORTED" if len(post_formal) == len(FORMAL_COMPONENTS) else "ABSTAIN",
        "formal_five_component_reason": None if len(post_formal) == len(FORMAL_COMPONENTS) else "FORMAL_FIVE_COMPONENT_INPUT_INCOMPLETE",
        "m4_total_risk": None,
        "m4_risk_status": "NOT_COMPUTED_INCOMPLETE_SEVEN_COMPONENT_COVERAGE",
        "decision_node_id": decision_node_id,
        "episode_id": episode_id,
        "scenario_id": scenario_id,
        "scenario_weight": scenario_weight,
    }


def materialize(*, root: Path, output_root: Path | None = None, seed: int = 20260823) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/experiment/exp2_conditional_scenario_diagnostics_v1").resolve()
    m1_path = root / "artifacts/experiment/m1_v2_current_stage_scenarios_v4/M1_V2_CURRENT_STAGE_TYPED_JOINT_SCENARIOS.json"
    m2_path = root / "artifacts/experiment/m2_v2_current_stage_consequences_v1/M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCES.json"
    action_path = root / "registries/action_templates.yaml"
    response_path = root / "registries/m3_response_scenarios.yaml"
    if not all(path.is_file() for path in (m1_path, m2_path, action_path, response_path)):
        raise RuntimeError("EXP2_CONDITIONAL_DIAGNOSTIC_INPUT_MISSING")
    m1, m2 = _load(m1_path), _load(m2_path)
    actions = ActionRegistry.load(action_path)
    action_by_id = {item.template_id: item for item in actions.templates}
    response = ResponseScenarioRegistry.load(response_path, structural_registry=actions)
    m1_by_node, m2_by_node = _group(m1["rows"], "decision_node_id"), _group(m2["consequences"], "decision_node_id")
    if set(m1_by_node) != set(m2_by_node):
        raise RuntimeError("EXP2_CONDITIONAL_DIAGNOSTIC_NODE_SET_MISMATCH")
    rows: list[dict[str, Any]] = []
    summary: dict[str, dict[str, Any]] = {}
    for variant in VARIANTS:
        status, reason = _variant_status(variant)
        variant_rows: list[dict[str, Any]] = []
        if not status.startswith("BLOCKED"):
            for node_id, m1_node_rows in sorted(m1_by_node.items()):
                m2_by_scenario = {str(row["scenario_id"]): row for row in m2_by_node[node_id]}
                for scenario in _scenario_rows(variant, m1_node_rows):
                    source_id = str(scenario["scenario_id"]).replace("POINT:", "")
                    baseline = m2_by_scenario.get(source_id)
                    if baseline is None:
                        raise RuntimeError("EXP2_CONDITIONAL_DIAGNOSTIC_SCENARIO_LINEAGE_MISMATCH")
                    for action_id in response.actions:
                        variant_rows.append(_action_row(action_id, action_by_id[action_id], response, baseline, node_id, str(baseline["episode_id"]), scenario["scenario_id"], float(scenario["scenario_weight"]), seed))
        rows.extend({"variant": variant, **row} for row in variant_rows)
        summary[variant] = {
            "status": status,
            "reason": reason,
            "row_count": len(variant_rows),
            "action_count": len({row["action_id"] for row in variant_rows}),
            "formal_five_supported_row_count": sum(row["formal_five_component_status"] == "SUPPORTED" for row in variant_rows),
            "m4_total_risk_supported_row_count": 0,
        }
    payload = {
        "schema_version": "EXP2_CONDITIONAL_SCENARIO_DIAGNOSTICS_V1",
        "status": "MATERIALIZED_CONDITIONAL_NON_CAUSAL_DIAGNOSTICS",
        "scope": "DATA2_DEVELOPMENT_CURRENT_STAGE_V3",
        "scientific_question": "EXP2_REPRESENTATION_AND_CONSTRUCTED_RISK_SENSITIVITY",
        "interpretation": "Scenario-conditioned component response only; no empirical action effect and no authoritative ranking.",
        "m1_scenario_artifact_hash": m1["artifact_hash"],
        "m2_consequence_artifact_hash": m2["artifact_hash"],
        "m3_response_registry_hash": response.registry_hash,
        "m3_action_registry_hash": actions.registry_hash,
        "variants": summary,
        "rows": rows,
        "abstain_policy": "UNAVAILABLE_ABSTAIN_NO_DROP_RENORM_ZERO_PROXY",
        "m4_policy": {"rmb_mapping": "RMB_k = 1.0 * CU_k", "risk_policy": "alpha=0.90, expected=0.75, cvar=0.25", "total_risk_allowed": False, "reason": "P_itinerary_and_P_service_ABSTAIN; M4 requires complete seven-component coverage"},
        "safety": dict(SAFETY),
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "EXP2_CONDITIONAL_SCENARIO_DIAGNOSTICS.json"
    _write(artifact_path, payload)
    manifest = {
        "schema_version": "EXP2_CONDITIONAL_SCENARIO_DIAGNOSTICS_MANIFEST_V1",
        "status": payload["status"],
        "artifact": str(artifact_path.resolve()),
        "artifact_hash": payload["artifact_hash"],
        "variants": summary,
        "m4_total_risk_supported": False,
        "authoritative_ranking_allowed": False,
        "causal_effect_claim_allowed": False,
        "safety": dict(SAFETY),
    }
    manifest_path = output_root / "EXP2_CONDITIONAL_SCENARIO_DIAGNOSTICS_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--seed", type=int, default=20260823)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[2], output_root=args.output_root, seed=args.seed)
    print("EXP2_CONDITIONAL_SCENARIO_DIAGNOSTICS_MATERIALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
