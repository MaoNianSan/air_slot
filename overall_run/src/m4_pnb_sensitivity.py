from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .m4_pnb_contract import NON_NULL_ACTIONS, FrozenInputs
from .m4_pnb_formula import risk_score

PARAMETER_GRIDS: dict[str, list[float]] = {
    "b0": [0.75, 1.00, 1.25, 1.50],
    "q0": [0.20, 0.40, 0.50, 0.60, 0.70],
    "lambda": [0.00, 0.10, 0.25, 0.50],
    "alpha": [0.85, 0.90, 0.95],
    "near_equivalent_relative": [0.01, 0.02, 0.05],
}


def _scenario_evaluation(
    frame: pd.DataFrame,
    snapshot: pd.DataFrame,
    draw_cache: dict[tuple[str, str], dict[str, np.ndarray]],
    formal: dict[str, float],
    overrides: dict[str, float],
    parameter: str,
    value_label: str,
) -> tuple[dict[str, Any], pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    values = {**formal, **overrides}
    work = frame.copy()
    work["scenario_decision_pass"] = (
        work["burden_ratio"].le(values["b0"])
        & work["positive_net_benefit_probability"].ge(values["q0"])
    )
    if parameter in {"lambda", "alpha", "near_equivalent_relative"}:
        work["scenario_candidate"] = work["formal_final_candidate"].astype(bool)
    else:
        work["scenario_candidate"] = (
            work["physical_feasible"] & work["scenario_decision_pass"]
        )
    if parameter in {"lambda", "alpha"}:
        work["scenario_score"] = [
            risk_score(
                draw_cache[(str(row.snapshot_id), str(row.action_id))]["post_action_total"],
                values["lambda"],
                values["alpha"],
            )
            for row in work.itertuples(index=False)
        ]
    else:
        work["scenario_score"] = work["risk_score"]

    selected_actions: dict[str, str] = {}
    selected_records: list[dict[str, Any]] = []
    near_sizes: list[int] = []
    for snapshot_id, group in work.groupby("snapshot_id", sort=False):
        pre_total = draw_cache[(str(snapshot_id), NON_NULL_ACTIONS[0])]["pre_total"]
        a00_score = risk_score(pre_total, values["lambda"], values["alpha"])
        options = [
            {
                "action_id": "A00", "action_family": "null", "score": a00_score,
                "implementation": 0.0, "priority": 0, "recovered": 0.0,
                "post": float(pre_total.mean()), "net": 0.0,
            }
        ]
        for row in group[group["scenario_candidate"]].itertuples(index=False):
            options.append(
                {
                    "action_id": str(row.action_id),
                    "action_family": str(row.action_family),
                    "score": float(row.scenario_score),
                    "implementation": float(row.expected_implementation_cost_rmb),
                    "priority": int(row.priority),
                    "recovered": float(row.expected_recovered_cost_rmb),
                    "post": float(row.expected_post_action_cost_rmb),
                    "net": float(row.expected_net_benefit_rmb),
                }
            )
        options.sort(
            key=lambda item: (
                item["score"], item["implementation"], item["priority"], item["action_id"]
            )
        )
        selected = options[0]
        selected_actions[str(snapshot_id)] = str(selected["action_id"])
        selected_records.append({"snapshot_id": str(snapshot_id), **selected})
        tolerance = values["near_equivalent_relative"] * max(
            abs(float(selected["score"])), 1e-9
        )
        near_sizes.append(
            sum(float(option["score"]) - float(selected["score"]) <= tolerance for option in options)
        )
    work["scenario_recommended_action"] = work["snapshot_id"].map(selected_actions)
    work["scenario_selected"] = work["action_id"].eq(
        work["scenario_recommended_action"]
    )
    selected = pd.DataFrame(selected_records)
    counts = work.groupby("snapshot_id", observed=True)["scenario_candidate"].sum()
    formal_recommendation = snapshot["formal_recommended_action"].astype(str)
    selected_series = pd.Series(selected_actions)
    recommendation_disagreement = selected_series.ne(formal_recommendation).mean()
    candidate_rows = work[work["scenario_candidate"]]
    family_distribution = (
        selected[selected["action_id"].ne("A00")]["action_family"]
        .value_counts()
        .sort_index()
        .to_dict()
    )
    metrics = {
        "parameter": parameter,
        "diagnostic_value": value_label,
        "formal_value": formal.get(parameter, np.nan),
        "triggered_snapshots": int(work["snapshot_id"].nunique()),
        "non_null_action_rows": int(len(work)),
        "physical_feasible_rate": float(work["physical_feasible"].mean()),
        "decision_value_pass_rate": float(work["scenario_decision_pass"].mean()),
        "final_candidate_rate": float(work["scenario_candidate"].mean()),
        "zero_non_null_candidate_snapshot_rate": float(counts.eq(0).mean()),
        "one_candidate_snapshot_rate": float(counts.eq(1).mean()),
        "two_or_more_candidate_snapshot_rate": float(counts.ge(2).mean()),
        "A00_recommendation_rate": float(selected["action_id"].eq("A00").mean()),
        "non_null_recommendation_rate": float(selected["action_id"].ne("A00").mean()),
        "action_family_distribution": json.dumps(
            family_distribution, sort_keys=True, separators=(",", ":")
        ),
        "mean_expected_net_benefit_rmb": float(
            candidate_rows["expected_net_benefit_rmb"].mean()
        ) if len(candidate_rows) else np.nan,
        "median_expected_net_benefit_rmb": float(
            candidate_rows["expected_net_benefit_rmb"].median()
        ) if len(candidate_rows) else np.nan,
        "positive_expected_net_benefit_rate": float(
            candidate_rows["expected_net_benefit_rmb"].gt(0.0).mean()
        ) if len(candidate_rows) else np.nan,
        "mean_selected_implementation_cost_rmb": float(selected["implementation"].mean()),
        "mean_selected_recovered_cost_rmb": float(selected["recovered"].mean()),
        "mean_selected_post_action_cost_rmb": float(selected["post"].mean()),
        "recommendation_disagreement_vs_formal": float(recommendation_disagreement),
        "candidate_set_disagreement_vs_formal": float(
            work["scenario_candidate"].ne(work["formal_final_candidate"]).mean()
        ),
        "top_action_stability": float(1.0 - recommendation_disagreement),
        "near_equivalent_set_size": float(np.mean(near_sizes)),
        "diagnostic_status": "OFFLINE COUNTERFACTUAL DIAGNOSTIC",
        "formal_use": "not used for formal recommendation",
        "validation_status": "not a validation-frozen specification",
    }

    strata_rows: list[dict[str, Any]] = []
    family_rows: list[dict[str, Any]] = []
    for stratum, group in work.groupby("cost_stratum", sort=True, observed=True):
        snapshot_ids = set(group["snapshot_id"].astype(str))
        selected_stratum = selected[selected["snapshot_id"].isin(snapshot_ids)]
        strata_rows.append(
            {
                "parameter": parameter,
                "diagnostic_value": value_label,
                "cost_stratum": str(stratum),
                "action_rows": int(len(group)),
                "snapshots": int(len(snapshot_ids)),
                "decision_value_pass_rate": float(group["scenario_decision_pass"].mean()),
                "q_pass_rate": float(
                    group["positive_net_benefit_probability"].ge(values["q0"]).mean()
                ),
                "final_candidate_rate": float(group["scenario_candidate"].mean()),
                "non_null_recommendation_rate": float(
                    selected_stratum["action_id"].ne("A00").mean()
                ),
                "diagnostic_status": "OFFLINE COUNTERFACTUAL DIAGNOSTIC",
            }
        )
    for family, group in work.groupby("action_family", sort=True, observed=True):
        family_rows.append(
            {
                "parameter": parameter,
                "diagnostic_value": value_label,
                "action_family": str(family),
                "support": int(len(group)),
                "q_pass_rate": float(
                    group["positive_net_benefit_probability"].ge(values["q0"]).mean()
                ),
                "decision_value_pass_rate": float(group["scenario_decision_pass"].mean()),
                "final_candidate_rate": float(group["scenario_candidate"].mean()),
                "selected_snapshot_count": int(group["scenario_selected"].sum()),
                "diagnostic_status": "OFFLINE COUNTERFACTUAL DIAGNOSTIC",
            }
        )
    return metrics, work, strata_rows, family_rows


def build_parameter_sensitivity(
    frozen: FrozenInputs,
    frame: pd.DataFrame,
    snapshot: pd.DataFrame,
    draw_cache: dict[tuple[str, str], dict[str, np.ndarray]],
) -> dict[str, Any]:
    m4 = frozen.config["m4"]
    decision = m4["decision_value"]
    formal = {
        "b0": float(decision["burden_ratio_max"]),
        "q0": float(decision["positive_net_benefit_probability_min"]),
        "lambda": float(m4["risk_aversion"]),
        "alpha": float(m4["cvar_alpha"]),
        "near_equivalent_relative": float(m4["near_equivalent_relative"]),
    }
    tables: dict[str, pd.DataFrame] = {}
    strata_rows: list[dict[str, Any]] = []
    family_rows: list[dict[str, Any]] = []
    all_metrics: list[dict[str, Any]] = []
    for parameter, grid in PARAMETER_GRIDS.items():
        metrics_rows: list[dict[str, Any]] = []
        for value in grid:
            metrics, _, strata, families = _scenario_evaluation(
                frame,
                snapshot,
                draw_cache,
                formal,
                {parameter: float(value)},
                parameter,
                f"{value:.6g}",
            )
            metrics_rows.append(metrics)
            all_metrics.append(metrics)
            strata_rows.extend(strata)
            family_rows.extend(families)
        tables[parameter] = pd.DataFrame(metrics_rows)

    tables["cost_strata"] = pd.DataFrame(strata_rows)
    tables["action_family"] = pd.DataFrame(family_rows)
    tables["all_oat"] = pd.DataFrame(all_metrics)
    tables["formal_values"] = pd.DataFrame(
        [{"parameter": key, "formal_value": value} for key, value in formal.items()]
    )
    return tables


