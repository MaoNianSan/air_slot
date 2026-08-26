"""Held-out Q4 2019 Exp1 materialization using the frozen Exp1 semantics."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from exp.common.official_execution import file_sha256, write_json
from exp.exp1.closure import (
    SCENARIO_COLUMNS, _content_hash, _exp1a_summary, _exp1b_summary,
    _paired_comparison, build_exp1a_records, build_exp1b_records,
    build_sorting_diagnostic,
)
from model.M3.registry import ActionRegistry
from model.M3.response_registry import load_response_registry


SCOPE = "FINAL_TEST_OUT_OF_TIME_2019_10_12"
ACTION_REGISTRY = Path("registries/action_templates.yaml")
RESPONSE_REGISTRY = Path("registries/m3_response_scenarios.yaml")


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def run(*, root: Path, scenario_root: Path, exp2_root: Path,
        input_root: Path, output_root: Path) -> dict[str, Path]:
    """Run Exp1A/1B directly on Final Test artifacts, without renaming V1 files."""
    root, scenario_root, exp2_root, input_root, output_root = (
        item.resolve() for item in (root, scenario_root, exp2_root, input_root, output_root)
    )
    paths = {
        "scenario_manifest": scenario_root / "FINAL_TEST_SCENARIO_MANIFEST.json",
        "history": scenario_root / "M1_V2_FINAL_TEST_TYPED_SCENARIOS_HISTORY.parquet",
        "current": scenario_root / "M1_V2_FINAL_TEST_TYPED_SCENARIOS_CURRENT.parquet",
        "consequences": exp2_root / "M2_FINAL_TEST_CONSEQUENCES.parquet",
        "inputs": input_root / "M1_V2_FINAL_TEST_INFERENCE_INPUTS.json",
        "labels": input_root / "M1_V2_FINAL_TEST_LABELS.json",
        "input_manifest": input_root / "FINAL_TEST_INPUT_MANIFEST.json",
        "action_registry": root / ACTION_REGISTRY,
        "response_registry": root / RESPONSE_REGISTRY,
    }
    _require(all(path.is_file() for path in paths.values()), "EXP1_FINAL_TEST_INPUT_MISSING")
    scenario_manifest = json.loads(paths["scenario_manifest"].read_text(encoding="utf-8"))
    input_manifest = json.loads(paths["input_manifest"].read_text(encoding="utf-8"))
    inputs = json.loads(paths["inputs"].read_text(encoding="utf-8"))
    labels = json.loads(paths["labels"].read_text(encoding="utf-8"))
    _require(input_manifest.get("scope") == SCOPE and input_manifest.get("development_input_used") is False,
             "EXP1_FINAL_TEST_SCOPE_INVALID")
    _require(scenario_manifest.get("scope") == SCOPE and scenario_manifest.get("split") == "FINAL_TEST",
             "EXP1_FINAL_TEST_SCENARIO_SCOPE_INVALID")
    _require(scenario_manifest["cohort_hash"] == input_manifest["cohort_hash"] == labels["cohort_hash"],
             "EXP1_FINAL_TEST_COHORT_HASH_MISMATCH")

    scenario_frame = pd.read_parquet(paths["history"], columns=SCENARIO_COLUMNS)
    current_frame = pd.read_parquet(paths["current"], columns=SCENARIO_COLUMNS)
    consequence_frame = pd.read_parquet(paths["consequences"])
    registry = ActionRegistry.load(paths["action_registry"])
    response_registry = load_response_registry(
        paths["response_registry"], structural_path=paths["action_registry"],
    )
    pre_states = [state for states in inputs["pre_states_by_episode"].values() for state in states]
    _require(len(pre_states) == int(input_manifest["node_count"]), "EXP1_FINAL_TEST_PRE_STATE_COUNT_MISMATCH")
    _require(len(scenario_frame) == int(input_manifest["node_count"]) * int(scenario_manifest["scenario_count_per_node"]),
             "EXP1_FINAL_TEST_HISTORY_CARDINALITY_INVALID")
    _require(len(current_frame) == len(scenario_frame), "EXP1_FINAL_TEST_CURRENT_CARDINALITY_INVALID")

    exp1a_records, exp1a_meta = build_exp1a_records(
        consequence_rows=consequence_frame.to_dict("records"), pre_states=pre_states,
        registry=registry, response_registry=response_registry,
    )
    diagnostic_rows, diagnostic_stats = build_sorting_diagnostic(
        scenario_rows=scenario_frame.to_dict("records"), consequence_rows=consequence_frame.to_dict("records"),
    )
    history_records, history_meta = build_exp1b_records(
        scenario_rows=scenario_frame.to_dict("records"), label_rows=labels["labels"],
        pre_states=pre_states, model_id="M1_V2_GRU_H32", model_role="HISTORY",
    )
    current_records, _ = build_exp1b_records(
        scenario_rows=current_frame.to_dict("records"), label_rows=labels["labels"],
        pre_states=pre_states, model_id="M1_V2_GRU_H32_CURRENT_ONLY", model_role="CURRENT",
    )
    paired = _paired_comparison(history_records, current_records)
    output_root.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for frame, name in (
        (pd.DataFrame(exp1a_records), "EXP1A_FINAL_TEST_RECORDS"),
        (pd.DataFrame(history_records + current_records), "EXP1B_FINAL_TEST_PREDICTION_RECORDS"),
        (pd.DataFrame(diagnostic_rows), "EXP1A_FINAL_TEST_SORTING_DIAGNOSTIC"),
    ):
        csv_path, parquet_path = output_root / f"{name}.csv", output_root / f"{name}.parquet"
        frame.to_csv(csv_path, index=False)
        pq.write_table(pa.Table.from_pandas(frame), parquet_path)
        written[f"{name}_csv"] = csv_path
        written[f"{name}_parquet"] = parquet_path
    safety = {
        "FINAL_TEST_ACCESS_COUNT": sum(1 for name in ("history", "current", "consequences", "inputs", "labels", "input_manifest") if paths[name].is_file()),
        "PAPER_FULL_RUN": True, "MODEL_RETRAINED": False, "PARAMETER_RESELECTED": False,
    }
    summary: dict[str, Any] = {
        "schema_version": "AIR_SLOT_EXP1_FINAL_TEST_V1", "status": "COMPLETE",
        "scope": SCOPE, "dataset_id": "DATA2", "split": "FINAL_TEST", "paper_result": True,
        "cohort": {"cohort_hash": input_manifest["cohort_hash"], "episode_count": input_manifest["episode_count"], "node_count": input_manifest["node_count"], "scenario_count_per_node": scenario_manifest["scenario_count_per_node"]},
        "exp1a": {"per_node_records": _exp1a_summary(exp1a_records), "sorting_diagnostic": diagnostic_stats, **exp1a_meta},
        "exp1b": {"prediction_records": "HISTORY:MATERIALIZED/CURRENT:MATERIALIZED", "per_model": _exp1b_summary(history_records + current_records), "paired": paired, **history_meta},
        "safety": safety,
    }
    summary["artifact_hash"] = _content_hash(summary)
    summary_path = output_root / "EXP1_FINAL_TEST_SUMMARY.json"
    write_json(summary_path, summary)
    interpretation = output_root / "EXP1_FINAL_TEST_INTERPRETATION.md"
    interpretation.write_text(
        "# Exp1 Final Test\n\n"
        "Records were directly computed from Q4 2019 Final Test scenarios and labels. "
        "HISTORY and CURRENT use frozen checkpoints and the shared pre-Test calibration artifact; no fitting, selection, or recalibration occurred.\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "AIR_SLOT_EXP1_FINAL_TEST_MANIFEST_V1", "status": "COMPLETE",
        "scope": SCOPE, "source_scope": SCOPE, "dataset": "DATA2", "split": "FINAL_TEST",
        "episode_count": input_manifest["episode_count"], "node_count": input_manifest["node_count"],
        "input_hashes": {name: file_sha256(path) for name, path in paths.items() if name not in {"action_registry", "response_registry"}},
        "outputs": {name: str(path.relative_to(root)).replace("\\", "/") for name, path in {**written, "summary": summary_path, "interpretation": interpretation}.items()},
        "safety": safety, "paper_result": True,
    }
    manifest["artifact_hash"] = _content_hash(manifest)
    manifest_path = output_root / "EXP1_FINAL_TEST_MANIFEST.json"
    write_json(manifest_path, manifest)
    return {"manifest": manifest_path, "summary": summary_path, **written}
