"""Formal Development Exp1 closure over frozen H16 and PRE artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from model.M1.development_diagnostics import evaluate_lifecycle
from model.M1.lifecycle import M1Lifecycle

from exp.shared.output import GUARDS, write_json
from exp.shared.resampling import bootstrap_plan

from .formal_inputs import load_exact_inputs
from .paired import hazard_crps_records, paired_records, summarize_targets
from .scenarios import SCENARIO_PATH, analyze_nodes, load_scenario_artifact


ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "artifacts/models/m1"
PRE_AUDIT = ROOT / (
    "artifacts/models/pre/PRE_FORMAL_DEVELOPMENT_V1/"
    "PRE_FORMAL_DEVELOPMENT_AUDIT.json"
)
CACHE_MANIFEST = MODEL / (
    "M1_FROZEN_H16/DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3_MANIFEST.json"
)
OUT_ROOT = ROOT / "artifacts/experiment/exp1"
LEAD_GRID = (0, 30, 60, 120, 180, 240, 300, 360, 420, 480)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _lead_table(records: pd.DataFrame, evaluation_map: pd.DataFrame) -> pd.DataFrame:
    """Summarize paired target errors by the frozen evaluation lead grid."""
    keys = ["episode_id", "decision_node_id"]
    mapped = evaluation_map[keys + [
        f"{target}_lead_grid" for target in ("R_IB", "D_OB", "D_TX")
    ]].copy()
    if mapped.duplicated(keys).any():
        raise ValueError("EXP1_EVALUATION_MAP_NODE_DUPLICATE")
    merged = records.merge(mapped, on=keys, how="left", validate="many_to_one")
    rows = []
    for target in ("R_IB", "D_OB", "D_TX"):
        lead_column = f"{target}_lead_grid"
        for lead in LEAD_GRID:
            subset = merged[
                merged.target.eq(target)
                & merged.paired_status.eq("MATCHED_TARGET_SUPPORT")
                & merged[lead_column].eq(lead)
            ]
            if subset.empty:
                rows.append({
                    "target": target,
                    "evaluation_lead_grid_minutes": lead,
                    "status": "ABSTAIN_EMPTY_TARGET_LEAD_SLICE",
                    "N_nodes": 0,
                    "N_episodes": 0,
                })
                continue
            rows.append({
                "target": target,
                "evaluation_lead_grid_minutes": lead,
                "status": "PASS",
                "N_nodes": int(len(subset)),
                "N_episodes": int(subset.episode_id.nunique()),
                "History_MAE": float(subset.History_AE.mean()),
                "Current_MAE": float(subset.Current_AE.mean()),
                "Delta_MAE": float((subset.History_AE - subset.Current_AE).mean()),
                "History_P90AE": float(np.quantile(subset.History_AE, .9)),
                "Current_P90AE": float(np.quantile(subset.Current_AE, .9)),
            })
    return pd.DataFrame(rows)


def _attach_crps(records: pd.DataFrame, history_crps: dict, current_crps: dict) -> pd.DataFrame:
    out = records.copy()
    for mode, values in (("History", history_crps), ("Current", current_crps)):
        out[f"{mode}_R_IB_CRPS"] = [
            values.get((str(row.episode_id), str(row.decision_node_id)), (None, None))[0]
            for row in out.itertuples()
        ]
        out[f"{mode}_R_IB_finite_support_mass"] = [
            values.get((str(row.episode_id), str(row.decision_node_id)), (None, None))[1]
            for row in out.itertuples()
        ]
    out["CRPS_scope"] = np.where(
        out.target.eq("R_IB"),
        "R_IB_T_IB_FINITE_SUPPORT_CONDITIONAL_ONLY",
        "NOT_APPLICABLE_D_OB_D_TX_NO_FROZEN_CRPS",
    )
    return out


def _status_from_outputs(summary, lead, representation, scenarios) -> tuple[str, list[str]]:
    blockers = []
    if summary.empty or not set(("R_IB", "D_OB", "D_TX")) <= set(summary.target):
        blockers.append("EXP1A_TARGET_SUMMARY_INCOMPLETE")
    if lead.empty:
        blockers.append("EXP1_LEAD_TIME_TABLE_EMPTY")
    if representation.empty or not representation.status.eq("PASS").any():
        blockers.append("EXP1B_REPRESENTATION_UNAVAILABLE")
    if scenarios.empty or not scenarios.status.eq("PASS").any():
        blockers.append("EXP1B_DOWNSTREAM_NATIVE_DISTORTION_UNAVAILABLE")
    return ("PASS" if not blockers else "BLOCKED", blockers)


def run(mode: str = "development") -> dict:
    pre = _read(PRE_AUDIT)
    if pre.get("status") != "PASS" or pre.get("cache_nodes_missing_prestate") != 0:
        return {"status": "BLOCKED", "reason": "EXP1_FORMAL_PRE_AUDIT_NOT_PASS", **GUARDS}

    cache, exact_rows, evaluation_map, taxi, _ = load_exact_inputs()
    manifest_json = _read(CACHE_MANIFEST)
    history = M1Lifecycle.load(
        MODEL / "M1_H16_HISTORY_PRIMARY/M1_H16_HISTORY_PRIMARY.pt", device="cpu"
    )
    current = M1Lifecycle.load(
        MODEL / "M1_H16_CURRENT_COMPARATOR/M1_H16_CURRENT_COMPARATOR.pt", device="cpu"
    )
    history_examples = tuple(cache.partition("development", representation="ADAPTIVE_HISTORY"))
    current_examples = tuple(cache.partition("development", representation="CURRENT"))
    history_result = evaluate_lifecycle(history, history_examples, batch_size=64)
    current_result = evaluate_lifecycle(current, current_examples, batch_size=64)
    records = paired_records(history_result["nodes"], current_result["nodes"])
    records = _attach_crps(
        records,
        hazard_crps_records(history, history_examples),
        hazard_crps_records(current, current_examples),
    )

    reps = 20 if mode == "fast" else 2000
    plan = bootstrap_plan(tuple(sorted(records.episode_id.unique())), reps, 20260906)
    summary, bootstrap = summarize_targets(records, plan)
    lead = _lead_table(records, evaluation_map)
    supports = (
        float(history.pipeline.contracts["T_IB_REMAINING_HAZARD"].max_finite_minutes),
        float(history.pipeline.contracts["D_OB"].max_finite_minutes),
        float(history.pipeline.contracts["D_TX"].max_finite_minutes),
    )

    representation = pd.DataFrame()
    scenarios = pd.DataFrame()
    scenario_status = "NOT_RUN"
    try:
        scenario_frame = load_scenario_artifact(exact_rows, allow_materialize=mode == "development")
        selected_rows = exact_rows
        if mode == "fast":
            allowed = set(str(row[0].episode_id) for row in exact_rows[:64])
            scenario_frame = scenario_frame[scenario_frame.episode_id.isin(allowed)]
            selected_rows = [row for row in exact_rows if str(row[0].episode_id) in allowed]
        representation, scenarios = analyze_nodes(
            scenario_frame, selected_rows, taxi, supports=supports
        )
        scenario_status = "PASS"
    except (RuntimeError, ValueError, KeyError) as exc:
        scenario_status = f"BLOCKED:{type(exc).__name__}:{exc}"

    out = OUT_ROOT / ("fast" if mode == "fast" else "development")
    out.mkdir(parents=True, exist_ok=True)
    status, blockers = _status_from_outputs(summary, lead, representation, scenarios)
    if scenario_status != "PASS":
        blockers.append(scenario_status)
        status = "BLOCKED"
    payload = {
        "schema_version": "EXP1_FORMAL_DEVELOPMENT_MANIFEST_V2",
        "experiment_id": "EXP1",
        "mode": mode,
        "status": status,
        "blockers": blockers,
        "matched_node_count": int(pre["matched_node_count"]),
        "exact_input_rows": len(exact_rows),
        "evaluation_map_rows": len(evaluation_map),
        "m1_artifact_hash": manifest_json.get("artifact_hash", manifest_json.get("cache_hash")),
        "history_current": summary.to_dict("records"),
        "bootstrap_replicates_required": reps,
        "bootstrap_replicates_completed": int(bootstrap.replicate.nunique()) if not bootstrap.empty else 0,
        "bootstrap_seed": 20260906,
        "evaluation_lead_grid_minutes": list(LEAD_GRID),
        "exp1b_scenario_status": scenario_status,
        "exp1b_representation_rows": int(len(representation)),
        "exp1b_downstream_rows": int(len(scenarios)),
        "pre_audit_matched_node_count": int(pre["matched_node_count"]),
        **GUARDS,
    }
    records.to_csv(out / "EXP1_HISTORY_CURRENT_MATCHED_RECORDS.csv", index=False)
    summary.to_csv(out / "EXP1_HISTORY_CURRENT_TARGET_SUMMARY.csv", index=False)
    summary.to_csv(out / "EXP1_HISTORY_CURRENT_SUMMARY.csv", index=False)
    bootstrap.to_csv(out / "EXP1_HISTORY_CURRENT_BOOTSTRAP.csv", index=False)
    lead.to_csv(out / "EXP1_EVALUATION_LEAD_TIME.csv", index=False)
    if not representation.empty:
        representation.to_csv(out / "EXP1B_REPRESENTATION_SUMMARY.csv", index=False)
        scenarios.to_csv(out / "EXP1B_DOWNSTREAM_NATIVE_DISTORTION.csv", index=False)
        representation.to_parquet(out / "EXP1_REPRESENTATION_RECORDS.parquet", index=False)
        representation_summary = (
            representation[representation.status.eq("PASS")]
            .groupby("status", as_index=False)
            .agg(
                N_nodes=("status", "size"),
                Point_minus_Joint_VS=("Point_minus_Joint_VS", "mean"),
                Marginal_minus_Joint_VS=("Marginal_minus_Joint_VS", "mean"),
                Joint_VS=("Joint_VS", "mean"),
            )
        )
        representation_summary.to_csv(out / "EXP1_REPRESENTATION_SUMMARY.csv", index=False)
        representation[[
            "episode_id", "decision_node_id", "status",
            "Point_minus_Joint_VS", "Marginal_minus_Joint_VS", "Joint_VS",
        ]].to_csv(out / "EXP1_REPRESENTATION_CONTRASTS.csv", index=False)
    records.to_parquet(out / "EXP1_HISTORY_CURRENT_NODE_RECORDS.parquet", index=False)
    write_json(out / "EXP1_ANALYSIS_CONTRACT.json", {
        "schema_version": "EXP1_ANALYSIS_CONTRACT_V2",
        "targets": ["R_IB", "D_OB", "D_TX"],
        "evaluation_lead_grid_minutes": list(LEAD_GRID),
        "representations": ["Joint", "Marginal", "Point"],
        "variogram_p": 0.5,
        "support_policy_id": "COMMON_SUPPORT_CONDITIONAL_090",
        "bootstrap_replicates": reps,
        "bootstrap_seed": 20260906,
        **GUARDS,
    })
    write_json(out / "EXP1_INPUT_MANIFEST.json", {
        "schema_version": "EXP1_INPUT_MANIFEST_V2",
        "matched_node_count": len(exact_rows),
        "pre_audit_path": str(PRE_AUDIT),
        "cache_manifest_path": str(CACHE_MANIFEST),
        "scenario_artifact_path": str(SCENARIO_PATH),
        "exact_node_identity": "cache canonical node id + PRE node index lineage",
        **GUARDS,
    })
    write_json(out / "EXP1_SUPPORT_AUDIT.json", {
        "support_policy_id": "COMMON_SUPPORT_CONDITIONAL_090",
        "scenario_node_count": int(len(scenarios)),
        "representation_pass_nodes": int((representation.status == "PASS").sum()) if not representation.empty else 0,
        "representation_excluded_nodes": int((representation.status != "PASS").sum()) if not representation.empty else 0,
        **GUARDS,
    })
    write_json(out / "EXP1_OUTPUT_MANIFEST.json", payload)
    return payload


__all__ = ["run"]
