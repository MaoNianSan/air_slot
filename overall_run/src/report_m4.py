from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .report_contract import _save_table


def write_audit_report(run_dir: Path, manifest: dict[str, Any], status: str, warnings: list[str], failures: list[str]) -> None:
    cohort = pd.read_parquet(run_dir / "metrics" / "cohort_summary.parquet") if (run_dir / "metrics" / "cohort_summary.parquet").exists() else pd.DataFrame()
    checks = pd.read_parquet(run_dir / "audits" / "acceptance_checks.parquet") if (run_dir / "audits" / "acceptance_checks.parquet").exists() else pd.DataFrame()
    lines = [
        "# OVERALL_RUN_AUDIT_REPORT",
        "",
        f"- Run ID: `{manifest.get('run_id')}`",
        f"- Mode: `{manifest.get('mode')}`",
        f"- Status: **{status}**",
        f"- Config hash: `{manifest.get('config_hash')}`",
        "",
        "## 1. Input and cohort",
        "",
    ]
    if not cohort.empty:
        lines.append(cohort.to_markdown(index=False))
    lines.extend(["", "## 2. Acceptance checks", ""])
    if not checks.empty:
        lines.append(checks.to_markdown(index=False))
    lines.extend(["", "## 3. Warnings", ""])
    lines.extend([f"- {x}" for x in warnings] or ["- None"])
    lines.extend(["", "## 4. Failures", ""])
    lines.extend([f"- {x}" for x in failures] or ["- None"])
    lines.extend([
        "",
        "## 5. Claim boundary",
        "",
        "This run validates interface legality, distributional risk quality, feasibility auditing, and numerical ranking stability under the declared scenario-response system. It does not identify real-world counterfactual action effects.",
        "",
        "## 6. Downstream readiness",
        "",
        "Readiness is blocked by any hard failure or non-degeneracy warning; downstream studies must consume these frozen formal artifacts and must not rebuild PRE, M1, M2, M3, or M4 inputs.",
        "",
    ])
    (run_dir / "OVERALL_RUN_AUDIT_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def build_m4_diagnostics(
    candidates: pd.DataFrame,
    rankings: pd.DataFrame,
    *,
    recovery_ratio_min: float,
    burden_ratio_max: float,
    positive_net_benefit_probability_min: float,
    near_tolerance: float = 0.02,
) -> dict[str, pd.DataFrame]:
    """Build diagnostics from frozen M4 outputs without changing eligibility."""
    keys = ["episode_id", "snapshot_id"]
    identity = ["flight_id", "airport", "snapshot_stage"]
    nonnull = candidates[
        candidates["trigger"].fillna(False).astype(bool)
        & candidates["action_id"].astype(str).ne("A00")
    ].copy()
    if nonnull.empty:
        empty = pd.DataFrame()
        return {
            "gate": empty,
            "decision": empty,
            "snapshot_counts": empty,
            "snapshot_summary": empty,
            "concentration": empty,
            "margin_rows": empty,
            "margin_summary": empty,
            "score_gaps": empty,
        }

    gate_columns = {
        "capacity_gate": "gate_capacity",
        "window_gate": "gate_window",
        "resource_gate": "gate_resource",
        "authority_gate": "gate_authority",
        "lead_time_gate": "gate_lead",
        "physical_feasible": "physical_feasible",
    }
    gate = pd.DataFrame([
        {
            "metric": label,
            "pass_rate": float(nonnull[column].fillna(False).astype(bool).mean()),
            "support": int(len(nonnull)),
            "cohort": "TRIGGERED_NON_NULL_ACTION_ROWS",
        }
        for label, column in gate_columns.items()
    ])

    decision_columns = {
        "recovery_ratio": "gate_recovery_ratio",
        "burden_ratio": "gate_burden_ratio",
        "positive_net_benefit_probability": "gate_positive_net_benefit",
        "all_decision_value_conditions": "decision_value_pass",
    }
    decision = pd.DataFrame([
        {
            "metric": label,
            "pass_rate": float(nonnull[column].fillna(False).astype(bool).mean()),
            "support": int(len(nonnull)),
            "cohort": "TRIGGERED_NON_NULL_ACTION_ROWS",
        }
        for label, column in decision_columns.items()
    ])

    working = nonnull.copy()
    working["_physical"] = working["physical_feasible"].fillna(False).astype(bool)
    working["_recovery"] = working["gate_recovery_ratio"].fillna(False).astype(bool)
    working["_burden"] = working["gate_burden_ratio"].fillna(False).astype(bool)
    working["_benefit"] = working["gate_positive_net_benefit"].fillna(False).astype(bool)
    working["_decision"] = working["_physical"] & working["decision_value_pass"].fillna(False).astype(bool)
    working["_candidate"] = working["candidate_flag"].fillna(False).astype(bool)
    aggregation: dict[str, tuple[str, str]] = {
        "non_null_actions_total": ("action_id", "size"),
        "non_null_physical_feasible": ("_physical", "sum"),
        "non_null_recovery_ratio_pass": ("_recovery", "sum"),
        "non_null_burden_ratio_pass": ("_burden", "sum"),
        "non_null_positive_net_benefit_pass": ("_benefit", "sum"),
        "non_null_decision_value_pass": ("_decision", "sum"),
        "non_null_final_candidates": ("_candidate", "sum"),
    }
    for column in identity:
        if column in working:
            aggregation[column] = (column, "first")
    snapshot_counts = (
        working.groupby(keys, sort=True, observed=True)
        .agg(**aggregation)
        .reset_index()
    )
    count_columns = [column for column in aggregation if column.startswith("non_null_")]
    summary_rows: list[dict[str, Any]] = []
    for column in count_columns:
        values = pd.to_numeric(snapshot_counts[column], errors="coerce")
        summary_rows.append({
            "metric": column,
            "support": int(values.notna().sum()),
            "mean": float(values.mean()),
            "median": float(values.median()),
            "q25": float(values.quantile(0.25)),
            "q75": float(values.quantile(0.75)),
            "zero_rate": float(values.eq(0).mean()),
            "one_rate": float(values.eq(1).mean()),
            "two_or_more_rate": float(values.ge(2).mean()),
        })
    snapshot_summary = pd.DataFrame(summary_rows)

    recommended = rankings[rankings["recommended"].fillna(False).astype(bool)][
        keys + ["action_id"]
    ].rename(columns={"action_id": "recommended_action"})
    classified = snapshot_counts.merge(recommended, on=keys, how="left", validate="one_to_one")

    def concentration_category(row: pd.Series) -> str:
        if int(row["non_null_physical_feasible"]) == 0:
            return "A_NO_NON_NULL_PHYSICALLY_FEASIBLE"
        if int(row["non_null_decision_value_pass"]) == 0:
            return "B_PHYSICAL_EXISTS_NONE_PASS_DECISION_VALUE"
        if str(row.get("recommended_action", "")) == "A00":
            return "C_NON_NULL_CANDIDATE_EXISTS_A00_LOWER_SCORE"
        return "D_NON_NULL_ACTION_RECOMMENDED"

    classified["concentration_category"] = classified.apply(concentration_category, axis=1)
    concentration_order = [
        "A_NO_NON_NULL_PHYSICALLY_FEASIBLE",
        "B_PHYSICAL_EXISTS_NONE_PASS_DECISION_VALUE",
        "C_NON_NULL_CANDIDATE_EXISTS_A00_LOWER_SCORE",
        "D_NON_NULL_ACTION_RECOMMENDED",
    ]
    concentration_counts = classified["concentration_category"].value_counts()
    concentration = pd.DataFrame([
        {
            "category": category,
            "snapshot_count": int(concentration_counts.get(category, 0)),
            "snapshot_rate": float(concentration_counts.get(category, 0) / len(classified)),
            "support": int(len(classified)),
        }
        for category in concentration_order
    ])

    margin_rows = nonnull[keys + identity + ["action_id"]].copy()
    margin_rows["recovery_ratio_margin"] = (
        pd.to_numeric(nonnull["recovery_ratio"], errors="coerce") - recovery_ratio_min
    )
    margin_rows["burden_ratio_margin"] = (
        burden_ratio_max - pd.to_numeric(nonnull["burden_ratio"], errors="coerce")
    )
    margin_rows["positive_net_benefit_probability_margin"] = (
        pd.to_numeric(nonnull["positive_net_benefit_probability"], errors="coerce")
        - positive_net_benefit_probability_min
    )
    margin_summary_rows: list[dict[str, Any]] = []
    for action_id, group in margin_rows.groupby("action_id", sort=True):
        for column in (
            "recovery_ratio_margin",
            "burden_ratio_margin",
            "positive_net_benefit_probability_margin",
        ):
            numeric = pd.to_numeric(group[column], errors="coerce")
            finite = numeric[np.isfinite(numeric)]
            margin_summary_rows.append({
                "action_id": str(action_id),
                "margin": column,
                "support": int(numeric.notna().sum()),
                "finite_support": int(len(finite)),
                "q10": float(finite.quantile(0.10)) if len(finite) else np.nan,
                "q25": float(finite.quantile(0.25)) if len(finite) else np.nan,
                "median": float(finite.median()) if len(finite) else np.nan,
                "q75": float(finite.quantile(0.75)) if len(finite) else np.nan,
                "q90": float(finite.quantile(0.90)) if len(finite) else np.nan,
                "below_zero_rate": float(numeric.lt(0).mean()),
                "near_threshold_rate": float(numeric.abs().le(near_tolerance).mean()),
                "near_tolerance": float(near_tolerance),
            })
    margin_summary = pd.DataFrame(margin_summary_rows)

    eligible_keys = classified.loc[
        classified["non_null_final_candidates"].gt(0), keys
    ]
    eligible_rankings = rankings.merge(eligible_keys, on=keys, how="inner", validate="many_to_one")
    score_gap_rows: list[dict[str, Any]] = []
    for key, group in eligible_rankings.groupby(keys, sort=True, observed=True):
        a00 = group[group["action_id"].astype(str).eq("A00")]
        non_null = group[group["action_id"].astype(str).ne("A00")]
        if a00.empty or non_null.empty:
            continue
        best_non_null = non_null.sort_values(
            ["score", "action_id"], kind="mergesort"
        ).iloc[0]
        selected = group[group["recommended"].fillna(False).astype(bool)]
        score_gap_rows.append({
            "episode_id": key[0],
            "snapshot_id": key[1],
            "flight_id": group["flight_id"].iloc[0] if "flight_id" in group else "",
            "airport": group["airport"].iloc[0] if "airport" in group else "",
            "snapshot_stage": group["snapshot_stage"].iloc[0] if "snapshot_stage" in group else "",
            "a00_score": float(a00["score"].iloc[0]),
            "best_non_null_action": str(best_non_null["action_id"]),
            "best_non_null_score": float(best_non_null["score"]),
            "best_non_null_minus_a00": float(best_non_null["score"] - a00["score"].iloc[0]),
            "recommended_action": str(selected["action_id"].iloc[0]) if len(selected) else "",
        })
    score_gaps = pd.DataFrame(score_gap_rows)
    return {
        "gate": gate,
        "decision": decision,
        "snapshot_counts": snapshot_counts,
        "snapshot_summary": snapshot_summary,
        "concentration": concentration,
        "margin_rows": margin_rows,
        "margin_summary": margin_summary,
        "score_gaps": score_gaps,
    }


def _publish_m4_diagnostics(
    run_dir: Path,
    candidates: pd.DataFrame,
    rankings: pd.DataFrame,
    scientific: dict[str, Any],
) -> dict[str, pd.DataFrame]:
    decision = scientific["m4"]["decision_value"]
    diagnostics = build_m4_diagnostics(
        candidates,
        rankings,
        recovery_ratio_min=float(decision["recovery_ratio_min"]),
        burden_ratio_max=float(decision["burden_ratio_max"]),
        positive_net_benefit_probability_min=float(
            decision["positive_net_benefit_probability_min"]
        ),
    )
    paths = {
        "gate": "m4_gate_decomposition",
        "decision": "m4_decision_value_decomposition",
        "snapshot_counts": "m4_snapshot_retained_action_count",
        "snapshot_summary": "m4_snapshot_retained_action_summary",
        "concentration": "m4_a00_concentration_decomposition",
        "margin_rows": "m4_threshold_margin_rows",
        "margin_summary": "m4_threshold_margin_summary",
        "score_gaps": "m4_score_gap_analysis",
    }
    for key, name in paths.items():
        _save_table(diagnostics[key], run_dir / "audits" / name)
        _save_table(diagnostics[key], run_dir / "tables" / "core" / name)
    return diagnostics


