"""True held-out Q4 2019 Final Test and RMB paper-chain orchestrator."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from exp.common.official_execution import file_sha256
from model.common.identity import content_id


ROOT = Path(__file__).resolve().parents[2]
SCOPE = "FINAL_TEST_OUT_OF_TIME_2019_10_12"
FINAL_INPUT_ROOT = Path("artifacts/experiment/final_test_inputs_v1")
PAPER_ROOT = Path("artifacts/paper_results_v2_final_test_rmb")
MANUSCRIPT_ROOT = Path("outputs/manuscript_values/section5_final_test_rmb")
TABLE_ROOT = MANUSCRIPT_ROOT / "tables"
FIGURE_ROOT = MANUSCRIPT_ROOT / "figures"
OUTPUT_SPEC = Path("codex_framework/PAPER_OUTPUT_SPEC_V2_FINAL_TEST_RMB.json")
RMB_REGISTRY = Path("registries/m4_rmb_mapping_v1.json")
CHECKPOINT = Path("artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt")
CALIBRATION = Path("artifacts/calibration/m1_v2_calibration_20260826/M1_V2_CALIBRATION_ARTIFACT.json")
ACTION_REGISTRY = Path("registries/action_templates.yaml")
RUN_STATUS = PAPER_ROOT / "RUN_STATUS.json"
CHAIN_MANIFEST = PAPER_ROOT / "FINAL_TEST_RMB_CHAIN_MANIFEST.json"
SCENARIOS, EXP1, EXP2, EXP3, M3M4, EXP4 = (
    PAPER_ROOT / "scenarios", PAPER_ROOT / "exp1", PAPER_ROOT / "exp2",
    PAPER_ROOT / "exp3", PAPER_ROOT / "m3m4", PAPER_ROOT / "exp4",
)
STAGES = ("q4_inputs", "preflight", "rmb_registry", "scenarios", "exp1", "exp2a", "exp2b", "exp3", "support_gate", "exp4", "reporting")
SCHEMA_VERSION = "AIR_SLOT_FINAL_TEST_RMB_CHAIN_MANIFEST_V2"


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def _final_test_claim_metadata(payload: Any) -> Any:
    """Migrate reporting-only scope strings without changing Exp1 numerics."""
    replacements = {
        "DEVELOPMENT_CONDITIONAL_DIAGNOSTIC": "FINAL_TEST_CONDITIONAL_DIAGNOSTIC",
        "DEVELOPMENT_COMPARATOR_ONLY": "FINAL_TEST_COMPARATOR",
    }
    if isinstance(payload, dict):
        migrated = {key: _final_test_claim_metadata(value) for key, value in payload.items()}
        if "artifact_hash" in migrated:
            migrated["artifact_hash"] = content_id({
                key: value for key, value in migrated.items() if key != "artifact_hash"
            })
        return migrated
    if isinstance(payload, list):
        return [_final_test_claim_metadata(value) for value in payload]
    return replacements.get(payload, payload)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_status() -> dict[str, Any]:
    return {"schema_version": "AIR_SLOT_FINAL_TEST_RMB_RUN_STATUS_V1", "scope": SCOPE, "updated_at": _now(), **{stage: "PENDING" for stage in STAGES}}


def _status(root: Path) -> dict[str, Any]:
    path = root / RUN_STATUS
    return _load(path) if path.is_file() else _default_status()


def _update_status(root: Path, stage: str, value: str, **details: Any) -> dict[str, Any]:
    _require(stage in STAGES, "FINAL_TEST_RUN_STATUS_STAGE_UNKNOWN")
    status = _status(root)
    status[stage], status["updated_at"] = value, _now()
    if details:
        status.setdefault("details", {})[stage] = details
    _atomic_json(root / RUN_STATUS, status)
    return status


def _run_stage(root: Path, stage: str, action: Callable[[], dict[str, Any]], *, terminal: tuple[str, ...] = ("PASS",)) -> dict[str, Any]:
    status = _status(root)
    if status.get(stage) in terminal:
        return status.get("details", {}).get(stage, {"status": status[stage], "resumed": True})
    result = action()
    value = str(result.pop("status", "PASS"))
    _require(value in {"PASS", "ABSTAIN", "ABSTAIN_MONETARY_COMPONENT_NOT_IN_SCOPE"}, f"FINAL_TEST_STAGE_NONTERMINAL:{stage}:{value}")
    _update_status(root, stage, value, **result)
    return result


def _input_paths(root: Path) -> dict[str, Path]:
    input_root = root / FINAL_INPUT_ROOT
    return {"manifest": input_root / "FINAL_TEST_INPUT_MANIFEST.json", "cohort": input_root / "DATA2_FINAL_TEST_COHORT.json", "inputs": input_root / "M1_V2_FINAL_TEST_INFERENCE_INPUTS.json", "labels": input_root / "M1_V2_FINAL_TEST_LABELS.json"}


def stage_q4_inputs(root: Path) -> dict[str, Any]:
    from exp.common.final_test_inputs import materialize
    materialize(root=root, output_root=root / FINAL_INPUT_ROOT)
    manifest = _load(_input_paths(root)["manifest"])
    _require(manifest.get("scope") == SCOPE and manifest.get("episode_count", 0) > 0 and manifest.get("decision_node_count", 0) > 0, "FINAL_TEST_Q4_INPUT_INVALID")
    return {"status": "PASS", "episode_count": manifest["episode_count"], "decision_node_count": manifest["decision_node_count"], "min_successor_service_date": manifest["min_successor_service_date"], "max_successor_service_date": manifest["max_successor_service_date"]}


def stage_rmb_registry(root: Path) -> dict[str, Any]:
    from exp.workflows.rmb_mapping_plan_materialization import materialize, verify
    registry_path = materialize(root=root)
    payload = verify(root=root)
    _require(registry_path == root / RMB_REGISTRY and payload.get("registry_hash"), "FINAL_TEST_RMB_REGISTRY_HASH_MISMATCH")
    return {"status": "PASS", "registry": str(RMB_REGISTRY).replace("\\", "/"), "registry_hash": payload["registry_hash"]}


def _overlap_audit(root: Path, cohort: dict[str, Any]) -> dict[str, int]:
    dev_path = root / "artifacts/experiment/full_development_inputs_v1/DATA2_FULL_DEVELOPMENT_COHORT.json"
    _require(dev_path.is_file(), "FINAL_TEST_DEVELOPMENT_IDENTITY_AUDIT_INPUT_MISSING")
    development = _load(dev_path)
    final_episode_ids, development_episode_ids = set(cohort["episode_ids"]), {row["episode_id"] for row in development["decision_nodes"]}
    final_rows = {(row["episode_id"], row["decision_node_id"]) for row in cohort["decision_nodes"]}
    development_rows = {(row["episode_id"], row["decision_node_id"]) for row in development["decision_nodes"]}
    return {"episode_id_overlap": len(final_episode_ids & development_episode_ids), "evaluation_row_overlap": len(final_rows & development_rows)}


def stage_preflight(root: Path) -> dict[str, Any]:
    paths = _input_paths(root)
    _require(all(path.is_file() for path in paths.values()), "FINAL_TEST_PREFLIGHT_INPUT_MISSING")
    manifest, cohort, inputs, labels = (_load(paths[name]) for name in ("manifest", "cohort", "inputs", "labels"))
    _require(manifest["scope"] == SCOPE and manifest["development_input_used"] is False, "TEST_DATE_SCOPE_OR_DEVELOPMENT_LEAKAGE")
    _require(manifest["episode_count"] > 0 and manifest["decision_node_count"] > 0, "TEST_NONEMPTY")
    _require(manifest["min_successor_service_date"] >= "2019-10-01" and manifest["max_successor_service_date"] <= "2019-12-31", "TEST_DATE_RANGE")
    dates = list(cohort["successor_service_dates"].values())
    _require(len(dates) >= 100 and all("2019-10-01" <= value <= "2019-12-31" for value in dates[:100]), "TEST_DATE_IDENTITY_SAMPLE")
    _require("full_development_inputs_v1" not in json.dumps(inputs) and "full_development_inputs_v1" not in json.dumps(labels), "NO_DEVELOPMENT_EVALUATION_INPUT")
    _require(file_sha256(root / CHECKPOINT) == manifest["frozen_hashes"]["model_hash"], "MODEL_CHECKPOINT_FROZEN")
    _require((root / CALIBRATION).is_file() and _load(root / CALIBRATION).get("artifact_hash"), "CALIBRATION_ARTIFACT_FOUND")
    _require((root / ACTION_REGISTRY).is_file(), "ACTION_REGISTRY_FOUND")
    registry = _load(root / RMB_REGISTRY)
    _require(registry.get("monetary_system") == "RMB" and registry.get("rmb_base_mapping") == "1_CU_EQUALS_1_RMB", "RMB_REGISTRY_INVALID")
    _require(tuple(registry["main_monetary_components"]) == ("F_continuity", "F_execution", "F_propagation", "P_time", "R_operating"), "RMB_SCOPE_INVALID")
    _require(inputs.get("development_input_used") is False and labels.get("development_input_used") is False, "FINAL_TEST_INPUT_LEAKAGE")
    overlap = _overlap_audit(root, cohort)
    _require(overlap["evaluation_row_overlap"] == 0, "FINAL_TEST_DEVELOPMENT_EVALUATION_ROW_OVERLAP")
    return {"status": "PASS", "checks": ["TEST_DATE_RANGE_PASS", "TEST_NONEMPTY_PASS", "NO_DEVELOPMENT_EVALUATION_INPUT_PASS", "MODEL_CHECKPOINT_FROZEN_PASS", "CALIBRATION_ARTIFACT_FOUND_PASS", "ACTION_REGISTRY_FOUND_PASS", "RMB_REGISTRY_PASS"], "evaluation_overlap": overlap, "episode_count": manifest["episode_count"], "decision_node_count": manifest["decision_node_count"]}


def stage_scenarios(root: Path) -> dict[str, Any]:
    from exp.reporting.final_test_scenarios import run
    paths = run(root=root, input_root=root / FINAL_INPUT_ROOT, output_root=root / SCENARIOS)
    manifest = _load(paths["manifest"])
    _require(manifest["scope"] == SCOPE and manifest["safety"]["FINAL_TEST_ACCESS_COUNT"] > 0, "FINAL_TEST_SCENARIOS_INVALID")
    return {"status": "PASS", "manifest": str(paths["manifest"].relative_to(root)).replace("\\", "/"), "final_test_access_count": manifest["safety"]["FINAL_TEST_ACCESS_COUNT"]}


def _materialize_exp2(root: Path) -> dict[str, Path]:
    from exp.exp2.global_development import run
    return run(root=root, scenario_root=root / SCENARIOS, input_root=root / FINAL_INPUT_ROOT, output_root=root / EXP2, final_test=True, monetary_registry=root / RMB_REGISTRY)


def stage_exp1(root: Path) -> dict[str, Any]:
    from exp.exp1.final_test import run
    _materialize_exp2(root)
    paths = run(root=root, scenario_root=root / SCENARIOS, exp2_root=root / EXP2, input_root=root / FINAL_INPUT_ROOT, output_root=root / EXP1)
    payload = _load(paths["manifest"])
    return {"status": "PASS", "manifest": str(paths["manifest"].relative_to(root)).replace("\\", "/"), "final_test_access_count": payload["safety"]["FINAL_TEST_ACCESS_COUNT"]}


def stage_exp2a(root: Path) -> dict[str, Any]:
    from exp.exp2.global_development import materialize_final_test_variogram
    paths = materialize_final_test_variogram(
        root=root, scenario_root=root / SCENARIOS,
        input_root=root / FINAL_INPUT_ROOT, output_root=root / EXP2,
    )
    return {
        "status": "PASS",
        "records": str(paths["records"].relative_to(root)).replace("\\", "/"),
        "summary": str(paths["summary"].relative_to(root)).replace("\\", "/"),
        "contrasts": str(paths["contrasts"].relative_to(root)).replace("\\", "/"),
    }


def stage_exp2b(root: Path) -> dict[str, Any]:
    from exp.exp2.downstream_consequence_distortion import materialize
    paths = materialize(
        root=root, scenario_root=root / SCENARIOS,
        input_root=root / FINAL_INPUT_ROOT,
        output_root=root / EXP2 / "downstream_distortion",
        final_test=True,
    )
    payload = _load(paths["manifest"])
    return {
        "status": "PASS",
        "manifest": str(paths["manifest"].relative_to(root)).replace("\\", "/"),
        "records": str(paths["node_parquet"].relative_to(root)).replace("\\", "/"),
        "summary": str(paths["summary_csv"].relative_to(root)).replace("\\", "/"),
        "supported_component_comparisons": sum(
            row["support_status"] == "SUPPORTED_COMMON_FINITE_SUPPORT"
            for row in payload["summary_rows"]
        ),
        "abstain_component_comparisons": sum(
            row["support_status"] == "ABSTAIN_NO_COMMON_SUPPORT"
            for row in payload["summary_rows"]
        ),
    }


def stage_exp3(root: Path) -> dict[str, Any]:
    from exp.exp3.final_test_rmb import run
    paths = run(root=root, exp2_root=root / EXP2, input_root=root / FINAL_INPUT_ROOT, output_root=root / EXP3, monetary_registry=root / RMB_REGISTRY)
    payload = _load(paths["manifest"])
    _require(payload["schema_version"] == "EXP3_FINAL_TEST_RMB_EXECUTION_MANIFEST_V2", "FINAL_TEST_EXP3_MANIFEST_VERSION_INVALID")
    return {"status": "PASS", "manifest": str(paths["manifest"].relative_to(root)).replace("\\", "/"), "final_test_access_count": payload["safety"]["FINAL_TEST_ACCESS_COUNT"]}


def stage_support_gate(root: Path) -> dict[str, Any]:
    from exp.exp3.final_test_rmb import materialize_ranking_and_a00_gate
    paths = materialize_ranking_and_a00_gate(root=root, action_risk=root / EXP3 / "EXP3_FINAL_TEST_RMB_ACTION_RISK.parquet", output_root=root / M3M4)
    gate = _load(paths["gate_summary"])
    return {"status": "PASS", "manifest": str(paths["manifest"].relative_to(root)).replace("\\", "/"), "A_num": gate["A_num"], "A_sup": gate["A_sup"]}


def stage_exp4(root: Path) -> dict[str, Any]:
    from exp.exp4.final_test import run
    paths = run(root=root, input_root=root / FINAL_INPUT_ROOT, scenario_root=root / SCENARIOS, output_root=root / EXP4)
    payload = _load(paths["manifest"])
    aggregate = _load(paths["metrics"])["aggregate"]
    _require(
        all(
            aggregate[f"{method}:T_IB_A00"]["mae_node_count"] > 0
            and aggregate[f"{method}:T_IB_A00"]["mae_episode_count"] > 0
            for method in ("HISTORICAL", "LIGHTGBM", "RANDOM_FOREST", "STATE_AWARE_H32")
        ),
        "FINAL_TEST_EXP4_PREDECESSOR_SUPPORT_MISSING",
    )
    return {"status": "PASS", "manifest": str(paths["manifest"].relative_to(root)).replace("\\", "/"), "final_test_access_count": payload["safety"]["FINAL_TEST_ACCESS_COUNT"]}


def _make_exp4_figure(aggregate: dict[str, Any], output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    # Publication palette/style follows the repository scientific-figure-making
    # contract; exports are print-safe PNG/PDF with embedded vector fonts.
    palette = {"STATE_AWARE_H32": "#0F4D92", "HISTORICAL": "#B64342", "LIGHTGBM": "#42949E", "RANDOM_FOREST": "#9A4D8E"}
    methods, targets = ["HISTORICAL", "LIGHTGBM", "RANDOM_FOREST", "STATE_AWARE_H32"], ["T_IB_A00", "D_OB", "D_TX"]
    plt.rcParams.update({"font.family": ["DejaVu Sans"], "font.size": 14, "axes.linewidth": 2.0, "pdf.fonttype": 42, "ps.fonttype": 42, "legend.frameon": False})
    fig, axis = plt.subplots(figsize=(11, 5.5)); width, x = 0.19, np.arange(len(targets))
    for offset, method in enumerate(methods):
        values = [aggregate.get(f"{method}:{target}", {}).get("mae_minutes") for target in targets]
        axis.bar(x + (offset - 1.5) * width, [np.nan if value is None else value for value in values], width, label=method, color=palette[method], edgecolor="black", linewidth=1.0)
    axis.set_xticks(x, targets); axis.set_ylabel("MAE (minutes)"); axis.set_title("Final Test predictive benchmark")
    axis.spines["top"].set_visible(False); axis.spines["right"].set_visible(False); axis.legend(frameon=False, ncol=2)
    fig.tight_layout(pad=0.4); fig.savefig(output.with_suffix(".png"), dpi=300, bbox_inches="tight"); fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight"); plt.close(fig)


def stage_reporting(root: Path) -> dict[str, Any]:
    exp1_path = root / EXP1 / "EXP1_FINAL_TEST_SUMMARY.json"
    exp1 = _final_test_claim_metadata(_load(exp1_path))
    _atomic_json(exp1_path, exp1)
    exp2 = _load(root / EXP2 / "EXP2_FINAL_TEST_METRICS.json")
    exp2a = {
        "summary": _load(root / EXP2 / "EXP2A_FINAL_TEST_VARIOGRAM_SUMMARY.json"),
        "contrasts": _load(root / EXP2 / "EXP2A_FINAL_TEST_VARIOGRAM_CONTRASTS.json"),
    }
    exp2b = _load(root / EXP2 / "downstream_distortion" / "EXP2B_FINAL_TEST_DOWNSTREAM_DISTORTION_MANIFEST.json")
    exp3, exp4, gate = (_load(root / EXP3 / "EXP3_FINAL_TEST_RMB_METRICS.json"), _load(root / EXP4 / "EXP4_FINAL_TEST_METRICS.json"), _load(root / M3M4 / "A00_FINAL_TEST_RMB_GATE_SUMMARY.json"))
    artifact_root = root / PAPER_ROOT; artifact_root.mkdir(parents=True, exist_ok=True)
    table_root, figure_root = root / TABLE_ROOT, root / FIGURE_ROOT
    table_root.mkdir(parents=True, exist_ok=True); figure_root.mkdir(parents=True, exist_ok=True)
    results = {"schema_version": "SECTION5_FINAL_TEST_RMB_RESULTS_V2", "scope": SCOPE, "source_scope": SCOPE, "split": "FINAL_TEST", "paper_result": True,
               "exp1": exp1, "exp2a": exp2a, "exp2b": exp2b, "exp2": exp2, "exp3": exp3, "support_gate": gate, "exp4": exp4,
               "claim_boundary": "Final Test evaluation with frozen models and RMB reporting mapping; no causal or operational-effect claim.",
               "reporting_abstentions": {
                   "exp2b": [
                       row for row in exp2b["summary_rows"]
                       if row["support_status"] == "ABSTAIN_NO_COMMON_SUPPORT"
                   ],
               }}
    results["artifact_hash"] = content_id(results); json_path = artifact_root / "SECTION5_FINAL_RESULTS.json"; _atomic_json(json_path, results)
    markdown_path = artifact_root / "SECTION5_FINAL_RESULTS.md"
    exp2b_supported = [
        row for row in exp2b["summary_rows"]
        if row["support_status"] == "SUPPORTED_COMMON_FINITE_SUPPORT"
    ]
    exp2b_abstain = [
        row for row in exp2b["summary_rows"]
        if row["support_status"] == "ABSTAIN_NO_COMMON_SUPPORT"
    ]
    markdown_path.write_text(
        "# Section 5 Final Test RMB Results\n\n"
        + f"Scope: `{SCOPE}`. The cohort contains {exp4['episode_count']} episodes and {exp4['node_count']} decision nodes.\n\n"
        + "The RMB reporting scope is F_continuity, F_execution, F_propagation, P_time, and R_operating with 1 CU = 1 RMB. P_itinerary and P_service remain NOT_IN_MAIN_MONETARY_SCOPE without zero-fill; they are nevertheless retained in the component-level CU diagnostic.\n\n"
        + f"Exp2B common-support component comparisons: {len(exp2b_supported)}; typed `ABSTAIN_NO_COMMON_SUPPORT`: {len(exp2b_abstain)}.\n\n"
        + f"Support gate: `{gate['A_sup']['status']}`; A00 is never emitted as a recommendation.\n",
        encoding="utf-8",
    )
    table_path = table_root / "TABLE_FINAL_TEST_EXP4.csv"
    with table_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("method", "target", "mae_minutes", "mae_ci_95", "crps_minutes", "crps_ci_95", "mae_node_count", "crps_node_count", "mae_episode_count", "crps_episode_count", "crps_status")); writer.writeheader()
        for key, value in exp4["aggregate"].items():
            method, target = key.split(":", 1); writer.writerow({"method": method, "target": target, **value})
    figure_base = figure_root / "FIGURE_FINAL_TEST_EXP4_MAE"; _make_exp4_figure(exp4["aggregate"], figure_base)
    output_spec = {"schema_version": "PAPER_OUTPUT_SPEC_V2_FINAL_TEST_RMB", "scope": SCOPE, "monetary_system": "RMB", "cu_to_rmb": 1.0,
                   "main_monetary_components": ["F_continuity", "F_execution", "F_propagation", "P_time", "R_operating"],
                    "excluded_operational_components": ["P_itinerary", "P_service"],
                   "exp2b_component_diagnostic": "SEVEN_COMPONENT_CU_LEVEL_NO_RMB_AGGREGATION",
                   "outputs": {"results": str(json_path.relative_to(root)).replace("\\", "/"), "results_markdown": str(markdown_path.relative_to(root)).replace("\\", "/"),
                               "table": str(table_path.relative_to(root)).replace("\\", "/"), "figure_png": str(figure_base.with_suffix('.png').relative_to(root)).replace("\\", "/"), "figure_pdf": str(figure_base.with_suffix('.pdf').relative_to(root)).replace("\\", "/")}}
    output_spec["artifact_hash"] = content_id(output_spec); spec_path = root / OUTPUT_SPEC; _atomic_json(spec_path, output_spec)
    return {"status": "PASS", "results": str(json_path.relative_to(root)).replace("\\", "/"), "output_spec": str(spec_path.relative_to(root)).replace("\\", "/")}


def _chain_manifest(root: Path) -> dict[str, Any]:
    import subprocess
    inputs, status = _load(_input_paths(root)["manifest"]), _status(root)
    stage_manifests = [
        root / SCENARIOS / "FINAL_TEST_SCENARIO_MANIFEST.json",
        root / EXP1 / "EXP1_FINAL_TEST_MANIFEST.json",
        root / EXP2 / "EXP2_FINAL_TEST_EXECUTION_MANIFEST.json",
        root / EXP2 / "EXP2A_FINAL_TEST_VARIOGRAM_SUMMARY.json",
        root / EXP2 / "downstream_distortion" / "EXP2B_FINAL_TEST_DOWNSTREAM_DISTORTION_MANIFEST.json",
        root / EXP3 / "EXP3_FINAL_TEST_RMB_EXECUTION_MANIFEST.json",
        root / M3M4 / "M3M4_FINAL_TEST_RMB_MANIFEST.json",
        root / EXP4 / "EXP4_FINAL_TEST_EXECUTION_MANIFEST.json",
    ]
    safety = [_load(path)["safety"] for path in stage_manifests if path.is_file()]
    registry = _load(root / RMB_REGISTRY)
    payload = {"schema_version": SCHEMA_VERSION, "status": "COMPLETE", "scope": SCOPE, "source_scope": SCOPE, "start_date": inputs["start_date"], "end_date": inputs["end_date"], "episode_count": inputs["episode_count"], "decision_node_count": inputs["decision_node_count"], "min_successor_service_date": inputs["min_successor_service_date"], "max_successor_service_date": inputs["max_successor_service_date"], "evaluation_overlap": status.get("details", {}).get("preflight", {}).get("evaluation_overlap"), "starting_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(), "rmb_registry": {"path": str(RMB_REGISTRY).replace("\\", "/"), "hash": registry["registry_hash"], "file_hash": file_sha256(root / RMB_REGISTRY)}, "safety": {"FINAL_TEST_ACCESS_COUNT": sum(int(item.get("FINAL_TEST_ACCESS_COUNT", 0)) for item in safety), "PAPER_FULL_RUN": True, "MODEL_RETRAINED": False, "PARAMETER_RESELECTED": False}, "stage_status": status, "outputs": {"section5_results": str((root / PAPER_ROOT / "SECTION5_FINAL_RESULTS.json").relative_to(root)).replace("\\", "/"), "paper_output_spec": str(OUTPUT_SPEC).replace("\\", "/")}}
    payload["artifact_hash"] = content_id(payload); return payload


def _verify_reusable_stage(root: Path, stage: str) -> None:
    """Verify existing PASS/ABSTAIN artifacts without rematerializing them."""
    status = _status(root)
    value = status.get(stage)
    _require(value in {"PASS", "ABSTAIN", "ABSTAIN_MONETARY_COMPONENT_NOT_IN_SCOPE"}, f"FINAL_TEST_RESUME_STAGE_NOT_TERMINAL:{stage}")
    if stage == "q4_inputs":
        manifest = _load(_input_paths(root)["manifest"])
        _require(manifest.get("scope") == SCOPE and manifest.get("artifact_hash", "").startswith("sha256:"), "FINAL_TEST_RESUME_Q4_MANIFEST_INVALID")
        _require(manifest.get("episode_count", 0) > 0 and manifest.get("decision_node_count", 0) > 0, "FINAL_TEST_RESUME_Q4_EMPTY")
        return
    if stage == "preflight":
        details = status.get("details", {}).get("preflight", {})
        _require(set(details.get("checks", ())) >= {"TEST_DATE_RANGE_PASS", "TEST_NONEMPTY_PASS", "NO_DEVELOPMENT_EVALUATION_INPUT_PASS", "MODEL_CHECKPOINT_FROZEN_PASS", "CALIBRATION_ARTIFACT_FOUND_PASS", "ACTION_REGISTRY_FOUND_PASS", "RMB_REGISTRY_PASS"}, "FINAL_TEST_RESUME_PREFLIGHT_INVALID")
        return
    if stage == "rmb_registry":
        registry = _load(root / RMB_REGISTRY)
        _require(registry.get("registry_hash", "").startswith("sha256:") and registry.get("monetary_system") == "RMB", "FINAL_TEST_RESUME_RMB_INVALID")
        return
    if stage == "scenarios":
        manifest = _load(root / SCENARIOS / "FINAL_TEST_SCENARIO_MANIFEST.json")
        _require(manifest.get("scope") == SCOPE and manifest.get("safety", {}).get("FINAL_TEST_ACCESS_COUNT", 0) > 0, "FINAL_TEST_RESUME_SCENARIOS_INVALID")
        for item in manifest.get("models", {}).values():
            path = root / item["artifact"]
            _require(path.is_file() and file_sha256(path) == item["artifact_hash"], "FINAL_TEST_RESUME_SCENARIO_HASH_MISMATCH")
        return
    if stage == "exp1":
        manifest = _load(root / EXP1 / "EXP1_FINAL_TEST_MANIFEST.json")
        _require(manifest.get("scope") == SCOPE and manifest.get("artifact_hash", "").startswith("sha256:"), "FINAL_TEST_RESUME_EXP1_INVALID")
        return
    if stage == "exp2a":
        paths = {
            "records": root / EXP2 / "EXP2A_FINAL_TEST_VARIOGRAM_RECORDS.csv",
            "summary": root / EXP2 / "EXP2A_FINAL_TEST_VARIOGRAM_SUMMARY.json",
            "contrasts": root / EXP2 / "EXP2A_FINAL_TEST_VARIOGRAM_CONTRASTS.json",
        }
        _require(all(path.is_file() for path in paths.values()), "FINAL_TEST_RESUME_EXP2A_OUTPUT_MISSING")
        summary, contrasts = _load(paths["summary"]), _load(paths["contrasts"])
        _require(
            summary.get("scope") == SCOPE
            and summary.get("representation_specific_inputs") is True
            and summary.get("artifact_hash", "").startswith("sha256:")
            and contrasts.get("scope") == SCOPE
            and len(contrasts.get("contrast_rows", ())) == 2,
            "FINAL_TEST_RESUME_EXP2A_INVALID",
        )
        return
    if stage == "exp2b":
        payload_path = root / EXP2 / "downstream_distortion" / "EXP2B_FINAL_TEST_DOWNSTREAM_DISTORTION_MANIFEST.json"
        _require(payload_path.is_file(), "FINAL_TEST_RESUME_EXP2B_OUTPUT_MISSING")
        payload = _load(payload_path)
        rows = payload.get("summary_rows", ())
        _require(
            payload.get("scope") == SCOPE
            and payload.get("paper_result") is True
            and payload.get("monetary_aggregation") == "NOT_PERFORMED_COMPONENT_LEVEL_CU_ONLY"
            and len(rows) == 14
            and all(row.get("support_status") in {"SUPPORTED_COMMON_FINITE_SUPPORT", "ABSTAIN_NO_COMMON_SUPPORT"} for row in rows),
            "FINAL_TEST_RESUME_EXP2B_INVALID",
        )
        return
    raise RuntimeError(f"FINAL_TEST_RESUME_STAGE_UNKNOWN:{stage}")


def _exp3_contract_valid(root: Path) -> bool:
    manifest_path, risk_path = (root / EXP3 / "EXP3_FINAL_TEST_RMB_EXECUTION_MANIFEST.json", root / EXP3 / "EXP3_FINAL_TEST_RMB_ACTION_RISK.parquet")
    if not (manifest_path.is_file() and risk_path.is_file()):
        return False
    try:
        manifest = _load(manifest_path)
        import pyarrow.parquet as pq
        fields = set(pq.ParquetFile(risk_path).schema_arrow.names)
        return (manifest.get("schema_version") == "EXP3_FINAL_TEST_RMB_EXECUTION_MANIFEST_V2"
                and manifest.get("artifact_hashes", {}).get("action_risk") == file_sha256(risk_path)
                and {"decision_time", "valuation_band", "is_A00", "chi_inst", "chi_num", "scenario_lineage_hash", "rmb_registry_hash"}.issubset(fields))
    except Exception:
        return False


def _exp4_contract_valid(root: Path) -> bool:
    path = root / EXP4 / "EXP4_FINAL_TEST_METRICS.json"
    if not path.is_file():
        return False
    try:
        aggregate = _load(path).get("aggregate", {})
        h32_dob = aggregate.get("STATE_AWARE_H32:D_OB", {})
        h32_dtx = aggregate.get("STATE_AWARE_H32:D_TX", {})
        predecessor = [aggregate.get(f"{method}:T_IB_A00", {}) for method in ("HISTORICAL", "LIGHTGBM", "RANDOM_FOREST", "STATE_AWARE_H32")]
        return (bool(aggregate) and all("mae_ci_95" in value and "crps_ci_95" in value for value in aggregate.values())
                and h32_dob.get("crps_minutes") is None and h32_dob.get("crps_status") == "NA_NOT_SAVED_BY_M1"
                and h32_dtx.get("crps_minutes") is None and h32_dtx.get("crps_status") == "NA_NOT_SAVED_BY_M1"
                and h32_dob.get("mae_minutes") is not None and h32_dtx.get("mae_minutes") is not None
                and all(item.get("mae_node_count", 0) > 0 and item.get("mae_episode_count", 0) > 0 for item in predecessor))
    except Exception:
        return False


def run_chain(*, root: Path = ROOT, preflight_only: bool = False) -> dict[str, Any]:
    root = Path(root).resolve()
    for stage in ("q4_inputs", "preflight", "rmb_registry", "scenarios", "exp1"):
        _verify_reusable_stage(root, stage)
    if preflight_only:
        return _status(root)
    _require(_exp3_contract_valid(root), "FINAL_TEST_EXP3_FROZEN_CONTRACT_INVALID")
    gate_manifest = root / M3M4 / "M3M4_FINAL_TEST_RMB_MANIFEST.json"
    _require(gate_manifest.is_file() and _load(gate_manifest).get("artifact_hash", "").startswith("sha256:"), "FINAL_TEST_M3M4_FROZEN_CONTRACT_INVALID")
    for stage, valid, reason in (
        ("exp2a", lambda: _verify_reusable_stage(root, "exp2a"), "EXP2A_REPRESENTATION_SPECIFIC_VARIAGRAM_REQUIRED"),
        ("exp2b", lambda: _verify_reusable_stage(root, "exp2b"), "EXP2B_COMPONENT_DIAGNOSTIC_REQUIRED"),
    ):
        try:
            valid()
            if _status(root).get(stage) != "PASS":
                _update_status(root, stage, "PASS", resumed_from_existing_final_test_artifact=True)
        except Exception:
            _update_status(root, stage, "PENDING", invalidated_reason=reason)
            _update_status(root, "reporting", "PENDING", invalidated_reason=f"DOWNSTREAM_OF_{stage.upper()}")
    _run_stage(root, "exp2a", lambda: stage_exp2a(root))
    _run_stage(root, "exp2b", lambda: stage_exp2b(root))
    if not _exp4_contract_valid(root):
        _update_status(root, "exp4", "PENDING", invalidated_reason="EXP4_PREDECESSOR_INTERNAL_LABEL_FIX_REQUIRED")
        _update_status(root, "reporting", "PENDING", invalidated_reason="DOWNSTREAM_OF_EXP4_REPUBLICATION")
    _run_stage(root, "exp4", lambda: stage_exp4(root))
    _run_stage(root, "reporting", lambda: stage_reporting(root))
    manifest = _chain_manifest(root); _atomic_json(root / CHAIN_MANIFEST, manifest); return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv); result = run_chain(preflight_only=args.preflight_only)
    print(json.dumps({"scope": SCOPE, "status": result.get("status", "COMPLETE")}, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
