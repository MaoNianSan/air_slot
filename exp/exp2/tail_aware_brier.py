"""Tail-aware Development Brier diagnostics for Exp2A.

The principal event is the frozen ``D_TO > 30`` warning.  Scenario draws are
classified from finite support intervals and the explicit overflow class:
overflow is not assigned a scalar substitute.  If a draw interval straddles
the threshold, that node/variant is ABSTAIN rather than silently coerced.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import mean
from typing import Any

from model.common.identity import content_id


SCENARIO_PATH = Path(
    "artifacts/experiment/m1_v2_current_stage_scenarios_v4/"
    "M1_V2_CURRENT_STAGE_TYPED_JOINT_SCENARIOS.json"
)
LABEL_PATH = Path(
    "artifacts/experiment/m1_v2_current_stage_development_labels_v1/"
    "M1_V2_CURRENT_STAGE_DEVELOPMENT_LABELS.json"
)
THRESHOLD_MINUTES = 30.0
VARIANTS = ("EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT")
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


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"EXP2_TAIL_AWARE_BRIER_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _interval(env: dict[str, Any]) -> tuple[float, float] | None:
    if env.get("support_state") != "SUPPORTED":
        return None
    if env.get("class_id") == "ZERO":
        return 0.0, 0.0
    lower = env.get("class_lower_minutes")
    upper = env.get("class_upper_minutes")
    if lower is None:
        return None
    return float(lower), float("inf") if upper is None else float(upper)


def _event(env_ob: dict[str, Any], env_tx: dict[str, Any]) -> bool | None:
    ob = _interval(env_ob)
    tx = _interval(env_tx)
    if ob is None or tx is None:
        return None
    lower, upper = ob[0] + tx[0], ob[1] + tx[1]
    if lower > THRESHOLD_MINUTES:
        return True
    if upper <= THRESHOLD_MINUTES:
        return False
    return None


def _groups(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        output[row["decision_node_id"]].append(row)
    return dict(output)


def _point_index(rows: list[dict[str, Any]]) -> int:
    def scalar(row: dict[str, Any], target: str) -> float | None:
        env = next(item for item in row["target_envelopes"] if item["target_name"] == target)
        return None if env.get("scalar_minutes") is None else float(env["scalar_minutes"])

    def distance(candidate: dict[str, Any]) -> float:
        total = 0.0
        for row in rows:
            squared = 0.0
            for target in ("D_OB", "D_TX"):
                left, right = scalar(candidate, target), scalar(row, target)
                if left is not None and right is not None:
                    squared += (left - right) ** 2
            total += float(row["scenario_weight"]) * squared
        return total

    return min(range(len(rows)), key=lambda index: (distance(rows[index]), index))


def _source_pairs(rows: list[dict[str, Any]], variant: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if variant == "EXP2A_JOINT":
        return [
            (
                next(item for item in row["target_envelopes"] if item["target_name"] == "D_OB"),
                next(item for item in row["target_envelopes"] if item["target_name"] == "D_TX"),
            )
            for row in rows
        ]
    if variant == "EXP2A_POINT":
        row = rows[_point_index(rows)]
        return [(
            next(item for item in row["target_envelopes"] if item["target_name"] == "D_OB"),
            next(item for item in row["target_envelopes"] if item["target_name"] == "D_TX"),
        )]
    weights = {float(row["scenario_weight"]) for row in rows}
    _require(len(weights) == 1, "EXP2_TAIL_AWARE_MARGINAL_WEIGHT_POLICY_UNIMPLEMENTED")
    n = len(rows)
    return [
        (
            next(item for item in rows[index]["target_envelopes"] if item["target_name"] == "D_OB"),
            next(item for item in rows[(index + 1) % n]["target_envelopes"] if item["target_name"] == "D_TX"),
        )
        for index in range(n)
    ]


def _observed(labels: list[dict[str, Any]]) -> bool | None:
    by_target = {row["target_name"]: row for row in labels}
    ob, tx = by_target.get("D_OB"), by_target.get("D_TX")
    if not ob or not tx or not ob["active"] or not tx["active"]:
        return None
    if ob["exact_minutes"] is None or tx["exact_minutes"] is None:
        return None
    return float(ob["exact_minutes"]) + float(tx["exact_minutes"]) > THRESHOLD_MINUTES


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/experiment/exp2a_tail_aware_brier_v1").resolve()
    scenario_path, label_path = root / SCENARIO_PATH, root / LABEL_PATH
    _require(scenario_path.is_file() and label_path.is_file(), "EXP2_TAIL_AWARE_BRIER_INPUT_MISSING")
    scenarios, labels = _load(scenario_path), _load(label_path)
    _require(scenarios["cohort"]["cohort_hash"] == labels["cohort_hash"], "EXP2_TAIL_AWARE_BRIER_COHORT_MISMATCH")
    _require(scenarios["tail_scalar_extrapolation"] is False, "EXP2_TAIL_AWARE_BRIER_TAIL_EXTRAPOLATION_ENABLED")
    grouped = _groups(scenarios["rows"])
    labels_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in labels["rows"]:
        labels_by_node[row["decision_node_id"]].append(row)

    node_rows: list[dict[str, Any]] = []
    for node_id, rows in sorted(grouped.items()):
        observed = _observed(labels_by_node.get(node_id, []))
        for variant in VARIANTS:
            events = [_event(ob, tx) for ob, tx in _source_pairs(rows, variant)]
            unresolved = sum(item is None for item in events)
            if observed is None:
                status, probability, brier = "ABSTAIN_NO_OBSERVED_D_TO_LABEL", None, None
            elif unresolved:
                status, probability, brier = "ABSTAIN_INTERVAL_STRADDLES_THRESHOLD", None, None
            else:
                probability = mean(float(item) for item in events)
                brier = (probability - float(observed)) ** 2
                status = "SUPPORTED"
            node_rows.append({
                "decision_node_id": node_id,
                "episode_id": rows[0]["episode_id"],
                "variant": variant,
                "threshold_minutes": THRESHOLD_MINUTES,
                "observed_event": observed,
                "event_probability": probability,
                "brier": brier,
                "unresolved_sample_count": unresolved,
                "support_status": status,
                "source_scenario_artifact_hash": scenarios["artifact_hash"],
                "source_label_artifact_hash": labels["artifact_hash"],
            })

    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in node_rows:
        by_variant[row["variant"]].append(row)
    metrics = {}
    for variant, rows in by_variant.items():
        supported = [row for row in rows if row["support_status"] == "SUPPORTED"]
        episode_values: dict[str, list[float]] = defaultdict(list)
        for row in supported:
            episode_values[row["episode_id"]].append(float(row["brier"]))
        episode_means = [mean(values) for values in episode_values.values()]
        metrics[variant] = {
            "episode_balanced_brier": None if not episode_means else mean(episode_means),
            "supported_node_count": len(supported),
            "supported_episode_count": len(episode_means),
            "abstain_node_count": len(rows) - len(supported),
            "support_status": "SUPPORTED" if supported else "ABSTAIN",
        }

    payload = {
        "schema_version": "EXP2A_TAIL_AWARE_BRIER_ARTIFACT_V1",
        "status": "EXP2A_TAIL_AWARE_BRIER_MATERIALIZED",
        "scope": "DATA2_DEVELOPMENT_CURRENT_STAGE_V3",
        "principal_event": "D_TO_POST_GT_30",
        "threshold_minutes": THRESHOLD_MINUTES,
        "aggregation": "EPISODE_BALANCED_MEAN_OF_NODE_BRIERS",
        "variants": metrics,
        "node_rows": node_rows,
        "source_scenario_artifact_hash": scenarios["artifact_hash"],
        "source_label_artifact_hash": labels["artifact_hash"],
        "tail_policy": "FINITE_SUPPORT_INTERVALS_PLUS_EXPLICIT_TAIL_CLASS_NO_SCALAR_SUBSTITUTION",
        "abstention_policy": "UNRESOLVED_INTERVAL_OR_MISSING_OBSERVED_LABEL_ABSTAIN",
        "zero_fill": False,
        "synthetic_metrics": False,
        "safety": SAFETY,
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "EXP2A_TAIL_AWARE_BRIER.json"
    _write(artifact_path, payload)
    manifest = {
        "schema_version": "EXP2A_TAIL_AWARE_BRIER_MANIFEST_V1",
        "status": "EXP2A_TAIL_AWARE_BRIER_MATERIALIZED",
        "artifact": str(artifact_path.resolve()),
        "artifact_hash": payload["artifact_hash"],
        "source_scenario_artifact_hash": scenarios["artifact_hash"],
        "source_label_artifact_hash": labels["artifact_hash"],
        "metrics": metrics,
        "safety": SAFETY,
    }
    manifest_path = output_root / "EXP2A_TAIL_AWARE_BRIER_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    print("EXP2A_TAIL_AWARE_BRIER_MATERIALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
