"""Materialize post-outcome Development labels for the current-stage cohort.

Labels are evaluation-only and never enter the frozen M1 input tensor. Exact
values beyond the finite support remain visible and receive OVERFLOW_TAIL;
they are not truncated, removed, winsorized, or scalar-extrapolated.
"""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from model.M1.target_builder import build_v2_target_labels
from model.PRE.contracts.pre_state import EpisodeRecord, PREState
from model.PRE.streaming.data2 import load_selected_typed_records, load_timezones
from model.common.identity import content_id


COHORT = Path("artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT_CURRENT_STAGE_V3.json")
INPUTS = Path(
    "artifacts/diagnostics/m1_v2_development_current_stage_refreeze_v3/"
    "M1_V2_CURRENT_STAGE_DEVELOPMENT_INFERENCE_INPUTS.json"
)
SUPPORT = Path(
    "artifacts/diagnostics/m1_v2_positive_tail_policy_freeze_v2/"
    "M1_V2_TARGET_SUPPORT_MANIFEST.json"
)
DEFAULT_OUTPUT = Path("artifacts/experiment/m1_v2_current_stage_development_labels_v1")

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


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"M1_V2_DEVELOPMENT_LABEL_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _taxi_reference(state: PREState) -> tuple[float | None, str | None, str | None]:
    item = state.successor_state.get("taxi_reference")
    if item is None or item.support_state.value != "SUPPORTED" or not isinstance(item.value, dict):
        return None, None, None
    value = item.value
    return (
        None if value.get("value") is None else float(value["value"]),
        value.get("reference_id"),
        value.get("freeze_id"),
    )


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    cohort_path, inputs_path, support_path = root / COHORT, root / INPUTS, root / SUPPORT
    _require(all(path.is_file() for path in (cohort_path, inputs_path, support_path)), "M1_V2_DEVELOPMENT_LABEL_INPUT_MISSING")
    cohort, inputs, support = map(_load, (cohort_path, inputs_path, support_path))
    _require(cohort["split"] == "DEVELOPMENT", "M1_V2_DEVELOPMENT_LABEL_SPLIT_INVALID")
    _require(inputs["cohort"]["cohort_hash"] == cohort["cohort_hash"], "M1_V2_DEVELOPMENT_LABEL_COHORT_MISMATCH")
    _require(support["representation"] == "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS", "M1_V2_DEVELOPMENT_LABEL_TAIL_POLICY_INVALID")

    episodes = tuple(EpisodeRecord.model_validate(item) for item in cohort["episode_records"])
    source_paths = tuple(root / path for path in cohort["source_files"])
    _require(all(path.is_file() for path in source_paths), "M1_V2_DEVELOPMENT_LABEL_SOURCE_MISSING")
    zones = load_timezones(root / "data2/refs/us_airport_timezones.csv")
    schedules, outcomes = load_selected_typed_records(episodes, source_paths, zones)
    episode_by_id = {item.episode_id: item for item in episodes}
    q_max = {name: int(item["q_max_minutes"]) for name, item in support["target_contracts"].items()}
    public_name = {"T_IB_REMAINING_HAZARD": "T_IB_A00", "D_OB": "D_OB", "D_TX": "D_TX"}

    rows: list[dict[str, Any]] = []
    status_counts: dict[str, Counter[str]] = {name: Counter() for name in public_name.values()}
    for episode_id, serialized_states in inputs["pre_states_by_episode"].items():
        episode = episode_by_id[episode_id]
        schedule = schedules[episode.successor_flight_id]
        predecessor = outcomes[episode.predecessor_flight_id]
        successor = outcomes[episode.successor_flight_id]
        for serialized in serialized_states:
            state = PREState.model_validate(serialized)
            taxi_minutes, taxi_id, taxi_hash = _taxi_reference(state)
            labels = build_v2_target_labels(
                episode=episode,
                node=state.decision_node,
                predecessor_outcome=predecessor,
                successor_schedule=schedule,
                successor_outcome=successor,
                target_support=state.target_support,
                taxi_reference_minutes=taxi_minutes,
                taxi_reference_id=taxi_id,
                taxi_reference_hash=taxi_hash,
            )
            for label in labels:
                target = public_name[label.target_name]
                value = label.exact_minutes
                class_id = "INACTIVE"
                if label.active and value is not None:
                    class_id = "OVERFLOW_TAIL" if float(value) > q_max[target] else "FINITE_SUPPORT"
                status_counts[target][class_id] += 1
                rows.append({
                    "episode_id": label.episode_id,
                    "decision_node_id": label.decision_node_id,
                    "operational_stage": state.decision_node.operational_stage.value,
                    "target_name": target,
                    "internal_target_name": label.target_name,
                    "active": label.active,
                    "label_status": label.label_status,
                    "exact_minutes": value,
                    "class_id": class_id,
                    "q_max_minutes": q_max[target],
                    "abstention_reason": label.abstention_reason,
                    "t_ib_a00_utc": label.t_ib_a00_utc,
                    "decision_time_utc": label.decision_time_utc,
                    "split": label.split,
                    "provenance": [item.model_dump(mode="json") for item in label.provenance],
                })

    _require(len(rows) == cohort["new_cohort_node_count"] * 3 if "new_cohort_node_count" in cohort else len(cohort["node_ids"]) * 3, "M1_V2_DEVELOPMENT_LABEL_CARDINALITY_INVALID")
    _require({row["decision_node_id"] for row in rows} == set(cohort["node_ids"]), "M1_V2_DEVELOPMENT_LABEL_NODE_SET_MISMATCH")
    payload = {
        "schema_version": "M1_V2_CURRENT_STAGE_DEVELOPMENT_LABEL_ARTIFACT_V1",
        "status": "M1_V2_CURRENT_STAGE_DEVELOPMENT_LABELS_MATERIALIZED",
        "scope": "DATA2_DEVELOPMENT_CURRENT_STAGE_V3_POST_OUTCOME_EVALUATION_ONLY",
        "cohort_hash": cohort["cohort_hash"],
        "node_count": len(cohort["node_ids"]),
        "row_count": len(rows),
        "target_count_per_node": 3,
        "tail_policy": support["representation"],
        "status_counts": {name: dict(counts) for name, counts in status_counts.items()},
        "labels_are_model_inputs": False,
        "exact_tail_values_retained": True,
        "truncation": False,
        "deletion": False,
        "winsorization": False,
        "source_lineage": {
            "cohort": {"path": str(COHORT).replace("\\", "/"), "sha256": _sha(cohort_path)},
            "pre_inputs": {"path": str(INPUTS).replace("\\", "/"), "sha256": _sha(inputs_path)},
            "support": {"path": str(SUPPORT).replace("\\", "/"), "sha256": _sha(support_path)},
            "source_files": {str(path.relative_to(root)).replace("\\", "/"): _sha(path) for path in source_paths},
        },
        "rows": rows,
        "safety": SAFETY,
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "M1_V2_CURRENT_STAGE_DEVELOPMENT_LABELS.json"
    _write(artifact_path, payload)
    manifest = {
        "schema_version": "M1_V2_CURRENT_STAGE_DEVELOPMENT_LABEL_MANIFEST_V1",
        "status": "M1_CURRENT_STAGE_DEVELOPMENT_LABEL_ARTIFACT_MATERIALIZED",
        "artifact": _relative(artifact_path, root),
        "artifact_hash": payload["artifact_hash"],
        "cohort_hash": cohort["cohort_hash"],
        "node_count": payload["node_count"],
        "row_count": payload["row_count"],
        "status_counts": payload["status_counts"],
        "next_gate": "EXP2A_REPRESENTATION_METRIC_EXECUTION_READY",
        "safety": SAFETY,
    }
    manifest_path = output_root / "M1_V2_CURRENT_STAGE_DEVELOPMENT_LABEL_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[1], output_root=args.output_root)
    print("M1_CURRENT_STAGE_DEVELOPMENT_LABEL_ARTIFACT_MATERIALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
