"""Compute a Development-only numerical best-action sanity report.

The output is deliberately separate from the operational selector lane:
``numerical_best_action_id`` is an argmin over frozen ``J`` values only and
never becomes ``recommended_action_id``.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from math import isfinite
from pathlib import Path
from statistics import mean
from typing import Any

from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT


DEFAULT_DIR = PROJECT_ROOT / "artifacts/diagnostics/numerical_best_action_sanity_v1"
DEFAULT_RECORDS = DEFAULT_DIR / "non_a00_path/NON_A00_NUMERICAL_SMOKE_RECORDS.jsonl"
DEFAULT_SCENARIOS = DEFAULT_DIR / "M1_DEVELOPMENT_64_NODE_SCENARIOS.json"
OUTPUT_NAME = "NUMERICAL_BEST_ACTION_SANITY"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _severity_labels(scenario_path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(scenario_path.read_text(encoding="utf-8"))
    by_node: dict[str, list[float]] = defaultdict(list)
    stages: dict[str, str] = {
        row["decision_node_id"]: row["operational_stage"]
        for row in payload["nodes"]
    }
    for row in payload["scenarios"]:
        value = row.get("d_to_minutes")
        if value is not None and isfinite(float(value)):
            by_node[row["decision_node_id"]].append(float(value))
    means = {node: mean(values) for node, values in by_node.items() if values}
    ordered = sorted(means.values())
    if not ordered:
        return {}
    q1 = ordered[(len(ordered) - 1) // 3]
    q2 = ordered[(2 * (len(ordered) - 1)) // 3]
    labels = {}
    for node, values in by_node.items():
        if not values:
            continue
        avg = mean(values)
        severity = "LOW" if avg <= q1 else "MEDIUM" if avg <= q2 else "HIGH"
        labels[node] = {
            "operational_stage": stages.get(node, "UNKNOWN"),
            "mean_d_to_minutes": avg,
            "max_d_to_minutes": max(values),
            "q90_d_to_minutes": sorted(values)[int(0.90 * (len(values) - 1))],
            "delay_severity": severity,
            "overflow_scenario_count": sum(
                bool(row.get("overflow_d_ob") or row.get("overflow_d_tx"))
                for row in payload["scenarios"]
                if row["decision_node_id"] == node
            ),
        }
    return labels


def _winner_distribution(cases: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(case["numerical_best_action_id"] for case in cases).items()))


def _group_distribution(cases: list[dict[str, Any]], key: str) -> dict[str, dict[str, int]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        groups[str(case[key])].append(case)
    return {name: _winner_distribution(rows) for name, rows in sorted(groups.items())}


def materialize(
    records_path: Path = DEFAULT_RECORDS,
    scenario_path: Path = DEFAULT_SCENARIOS,
    output_dir: Path = DEFAULT_DIR,
) -> dict[str, Any]:
    records = _read_jsonl(records_path)
    if not records:
        raise RuntimeError("NUMERICAL_BEST_ACTION_NO_RECORDS")
    labels = _severity_labels(scenario_path)
    by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_node[row["decision_node_id"]].append(row)
    if any(len(rows) != 23 for rows in by_node.values()):
        raise RuntimeError("NUMERICAL_BEST_ACTION_EXPECTS_23_RECORDS_PER_NODE")

    cases = []
    action_ids: set[str] = set()
    direction: dict[str, Counter] = defaultdict(Counter)
    differentiation: dict[str, Counter] = defaultdict(Counter)
    for node_id, rows in sorted(by_node.items()):
        comparable = [
            row
            for row in rows
            if row.get("chi_num") == "DEFINED"
            and row.get("J") is not None
            and isfinite(float(row["J"]))
        ]
        if not comparable:
            continue
        action_ids.update(row["action_id"] for row in comparable)
        ordered = sorted(comparable, key=lambda row: (float(row["J"]), row["action_id"]))
        best_j = float(ordered[0]["J"])
        ties = sorted(
            row["action_id"]
            for row in ordered
            if abs(float(row["J"]) - best_j) <= 1e-12
        )
        winner = ties[0]
        a00 = next((row for row in comparable if row["action_id"] == "A00"), None)
        if a00 is None:
            raise RuntimeError(f"NUMERICAL_BEST_ACTION_A00_MISSING:{node_id}")
        a00_j = float(a00["J"])
        for row in comparable:
            if row["action_id"] == "A00":
                continue
            action = row["action_id"]
            delta = float(row["J"]) - a00_j
            direction[action][
                "better_than_A00" if delta < -1e-12 else "worse_than_A00" if delta > 1e-12 else "equal_to_A00"
            ] += 1
            differentiation[action]["cu_different_from_A00"] += int(
                row.get("cu_signature") != a00.get("cu_signature")
            )
            differentiation[action]["j_different_from_A00"] += int(
                abs(float(row["J"]) - a00_j) > 1e-12
            )
        case = {
            "decision_node_id": node_id,
            "operational_stage": labels.get(node_id, {}).get("operational_stage", "UNKNOWN"),
            "delay_severity": labels.get(node_id, {}).get("delay_severity", "UNKNOWN"),
            "mean_d_to_minutes": labels.get(node_id, {}).get("mean_d_to_minutes"),
            "candidate_action_ids": sorted(action_ids),
            "comparable_action_count": len(comparable),
            "numerical_best_action_id": winner,
            "numerical_preferred_action_id": winner,
            "tie": len(ties) > 1,
            "tie_action_ids": ties,
            "best_J": best_j,
            "A00_J": a00_j,
            "delta_vs_A00": best_j - a00_j,
            "chi_sel": "UNIMPLEMENTED",
            "operational_recommendation": None,
        }
        cases.append(case)

    if not cases:
        raise RuntimeError("NUMERICAL_BEST_ACTION_NO_COMPARABLE_NODE_CASES")
    comparable_count = len(cases)
    winner_distribution = _winner_distribution(cases)
    a00_best_count = winner_distribution.get("A00", 0)
    non_a00_distribution = {
        action: count for action, count in winner_distribution.items() if action != "A00"
    }
    non_a00_best_count = sum(non_a00_distribution.values())
    unique_best = sorted(winner_distribution)
    universal_non_a00 = any(count == comparable_count for count in non_a00_distribution.values())
    universal_a00 = a00_best_count == comparable_count
    stage_distribution = _group_distribution(cases, "operational_stage")
    severity_distribution = _group_distribution(cases, "delay_severity")

    direction_payload = {}
    degenerate_actions = []
    for action in sorted(direction):
        counts = {
            "better_than_A00": direction[action]["better_than_A00"],
            "equal_to_A00": direction[action]["equal_to_A00"],
            "worse_than_A00": direction[action]["worse_than_A00"],
        }
        diff = {
            "nodes_C_a_different_from_C_A00": differentiation[action]["cu_different_from_A00"],
            "nodes_J_different_from_J_A00": differentiation[action]["j_different_from_A00"],
        }
        direction_payload[action] = {**counts, **diff}
        if diff["nodes_C_a_different_from_C_A00"] == 0 or diff["nodes_J_different_from_J_A00"] == 0:
            degenerate_actions.append(action)

    state_distributions = list(stage_distribution.values()) + list(severity_distribution.values())
    state_insensitive = len(state_distributions) > 1 and all(
        item == state_distributions[0] for item in state_distributions[1:]
    )
    non_degenerate = (
        a00_best_count > 0
        and non_a00_best_count > 0
        and len(unique_best) >= 2
        and not universal_a00
        and not universal_non_a00
    )
    payload = {
        "schema_version": "NUMERICAL_BEST_ACTION_SANITY_V1",
        "artifact_id": OUTPUT_NAME,
        "artifact_scope": "DEVELOPMENT_ONLY_LIGHTWEIGHT_SMOKE",
        "input_records_path": str(records_path),
        "input_scenario_path": str(scenario_path),
        "cohort": {
            "nodes": comparable_count,
            "comparable_node_cases": comparable_count,
            "scenario_count_per_node": 64,
            "stages": sorted({case["operational_stage"] for case in cases}),
            "severities": sorted({case["delay_severity"] for case in cases}),
        },
        "best_action_distribution": {
            "A00_best_count": a00_best_count,
            "non_A00_best_count": non_a00_best_count,
            "A00_best_rate": a00_best_count / comparable_count,
            "non_A00_best_rate": non_a00_best_count / comparable_count,
            "number_of_unique_best_actions": len(unique_best),
            "winner_distribution": winner_distribution,
            "per_action": {
                action: {
                    "best_count": winner_distribution.get(action, 0),
                    "best_rate": winner_distribution.get(action, 0) / comparable_count,
                }
                for action in unique_best
            },
        },
        "comparison_against_A00": direction_payload,
        "degeneracy": {
            "A00_ONLY_WINNER": universal_a00,
            "ALL_NON_A00_WINNER": non_a00_best_count == comparable_count,
            "UNIVERSAL_NON_A00_WINNER": universal_non_a00,
            "ACTION_RESPONSE_DEGENERATE": degenerate_actions,
        },
        "state_sensitivity": {
            "stage_winner_distribution": stage_distribution,
            "severity_winner_distribution": severity_distribution,
            "STATE_INSENSITIVE_NUMERICAL_RESPONSE": state_insensitive,
        },
        "operational_authority": {
            "chi_sel": "UNIMPLEMENTED",
            "operational_recommendations": 0,
            "numerical_best_action_is_not_recommendation": True,
        },
        "final_status": {
            "OLD_0_OF_5136_NON_A00_NUMERICAL_BEST_PROBLEM": (
                "RESOLVED" if non_a00_best_count > 0 else "NOT_RESOLVED"
            ),
            "NUMERICAL_ACTION_COMPARISON": "NON_DEGENERATE" if non_degenerate else "DEGENERATE_OR_SUSPICIOUS",
        },
        "guards": {
            "data1_modified": False,
            "data2_modified": False,
            "final_test_access_count": 0,
            "model_retrained": False,
            "parameter_reselected": False,
            "experiment_created": False,
        },
        "cases": cases,
    }
    payload["artifact_hash"] = content_id(payload)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "NUMERICAL_BEST_ACTION_SANITY_SUMMARY.json"
    report_path = output_dir / "NUMERICAL_BEST_ACTION_SANITY_REPORT.md"
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = [
        "# NUMERICAL BEST-ACTION SANITY REPORT",
        "",
        "## A. Cohort",
        f"- nodes = {comparable_count}",
        f"- comparable node-cases = {comparable_count}",
        f"- stages = {', '.join(payload['cohort']['stages'])}",
        f"- severities = {', '.join(payload['cohort']['severities'])}",
        "",
        "## B. Best-action distribution",
        f"- A00 best = {a00_best_count} ({a00_best_count / comparable_count:.3f})",
        f"- non-A00 best = {non_a00_best_count} ({non_a00_best_count / comparable_count:.3f})",
        f"- unique best actions = {len(unique_best)}",
        "- winner distribution: " + ", ".join(f"{k}={v}" for k, v in winner_distribution.items()),
        "",
        "## C. Comparison against A00",
    ]
    for action, values in direction_payload.items():
        report.append(
            f"- {action}: better={values['better_than_A00']}, equal={values['equal_to_A00']}, worse={values['worse_than_A00']}; "
            f"C-different={values['nodes_C_a_different_from_C_A00']}, J-different={values['nodes_J_different_from_J_A00']}"
        )
    report += [
        "",
        "## D. Degeneracy",
        f"- A00_ONLY_WINNER = {'YES' if universal_a00 else 'NO'}",
        f"- ALL_NON_A00_WINNER = {'YES' if non_a00_best_count == comparable_count else 'NO'}",
        f"- UNIVERSAL_NON_A00_WINNER = {'YES' if universal_non_a00 else 'NO'}",
        f"- ACTION_RESPONSE_DEGENERATE = {', '.join(degenerate_actions) or 'NONE'}",
        "",
        "## E. State sensitivity",
        f"- stage winner distribution = {json.dumps(stage_distribution, sort_keys=True)}",
        f"- severity winner distribution = {json.dumps(severity_distribution, sort_keys=True)}",
        f"- STATE_INSENSITIVE_NUMERICAL_RESPONSE = {'YES' if state_insensitive else 'NO'}",
        "",
        "## F. Operational authority",
        "- chi_sel = UNIMPLEMENTED",
        "- operational recommendations = 0",
        "- numerical_best_action_id is not an operational recommendation",
        "",
        "## G. Final status",
        f"- OLD_0_OF_5136_NON_A00_NUMERICAL_BEST_PROBLEM = {payload['final_status']['OLD_0_OF_5136_NON_A00_NUMERICAL_BEST_PROBLEM']}",
        f"- NUMERICAL_ACTION_COMPARISON = {payload['final_status']['NUMERICAL_ACTION_COMPARISON']}",
        "",
        "## Guards",
        "- DATA1 MODIFIED: NO",
        "- DATA2 MODIFIED: NO",
        "- FINAL TEST ACCESSED: NO",
        "- MODEL RETRAINED: NO",
        "- PARAMETER RESELECTED: NO",
        "- EXP CREATED: NO",
    ]
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    print(json.dumps(materialize(args.records, args.scenarios, args.output_dir), indent=2, sort_keys=True))

