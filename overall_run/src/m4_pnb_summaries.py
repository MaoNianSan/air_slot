from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .m4_pnb_contract import CHANNELS


def _group_summary(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_key: str | list[str] = keys[0] if len(keys) == 1 else keys
    for key, group in frame.groupby(group_key, sort=True, observed=True):
        values = (key,) if len(keys) == 1 else tuple(key)
        row = dict(zip(keys, values))
        row.update(
            {
                "support": int(len(group)),
                "snapshots": int(group["snapshot_id"].nunique()),
                "positive_net_benefit_probability_mean": float(
                    group["positive_net_benefit_probability"].mean()
                ),
                "positive_net_benefit_probability_median": float(
                    group["positive_net_benefit_probability"].median()
                ),
                "positive_net_benefit_pass_rate": float(
                    group["positive_net_benefit_pass"].mean()
                ),
                "expected_recovered_cost_rmb_mean": float(
                    group["expected_recovered_cost_rmb"].mean()
                ),
                "expected_implementation_cost_rmb_mean": float(
                    group["expected_implementation_cost_rmb"].mean()
                ),
                "expected_net_benefit_rmb_mean": float(
                    group["expected_net_benefit_rmb"].mean()
                ),
                "conditional_positive_probability_given_success_mean": float(
                    group["conditional_positive_probability_given_success"].mean()
                ),
                "implementation_failure_probability_mean": float(
                    group["implementation_failure_probability"].mean()
                ),
                "recovery_ratio_mean": float(group["recovery_ratio"].mean()),
                "burden_ratio_mean": float(group["burden_ratio"].mean()),
                "physical_feasible_rate": float(group["physical_feasible"].mean()),
                "decision_value_pass_rate": float(group["decision_value_pass"].mean()),
                "final_candidate_rate": float(group["final_candidate"].mean()),
                "non_null_recommendation_rate": float(
                    group["recommended"].sum() / max(group["snapshot_id"].nunique(), 1)
                ),
            }
        )
        for channel in CHANNELS:
            row[f"expected_recovered_cost_rmb_{channel}_mean"] = float(
                group[f"expected_recovered_cost_rmb_{channel}"].mean()
            )
            row[f"expected_implementation_cost_rmb_{channel}_mean"] = float(
                group[f"expected_implementation_cost_rmb_{channel}"].mean()
            )
        rows.append(row)
    return pd.DataFrame(rows)


def build_pnb_summaries(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    action = _group_summary(frame, ["action_id", "action_family"])
    family = _group_summary(frame, ["action_family"])
    stage = _group_summary(frame, ["stage"])
    cost_strata = _group_summary(frame, ["cost_stratum"])
    cost_strata["action_rows"] = cost_strata["support"]
    cost_strata["mean_pre_action_cost_rmb"] = [
        float(frame.loc[frame["cost_stratum"].eq(value), "pre_action_cost_mean_rmb"].mean())
        for value in cost_strata["cost_stratum"]
    ]
    composition = _group_summary(frame, ["channel_composition", "action_family"])
    return {
        "action": action,
        "family": family,
        "stage": stage,
        "cost_strata": cost_strata,
        "channel_composition": composition,
    }


def build_failure_decomposition(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (action_id, family), group in frame.groupby(
        ["action_id", "action_family"], sort=True, observed=True
    ):
        total = int(len(group) * 256)
        failure = int(group["failure_draws"].sum())
        failure_cost = int(
            group["failure_draws_with_positive_implementation_cost"].sum()
        )
        success_le = int(group["successful_draws_recovery_le_cost"].sum())
        success_gt = int(group["successful_draws_recovery_gt_cost"].sum())
        rows.append(
            {
                "action_id": action_id,
                "action_family": family,
                "snapshot_support": int(len(group)),
                "total_draw_observations": total,
                "failure_draw_share": failure / total,
                "failure_draws": failure,
                "failure_draws_with_positive_implementation_cost": failure_cost,
                "successful_draws_with_recovery_le_cost": success_le,
                "successful_draws_with_recovery_gt_cost": success_gt,
                "q_formal_mean": float(
                    group["positive_net_benefit_probability"].mean()
                ),
                "q_success_mean": float(
                    group["conditional_positive_probability_given_success"].mean()
                ),
                "q_success_minus_q_formal_mean": float(
                    group["q_success_minus_q_formal"].mean()
                ),
            }
        )
    return pd.DataFrame(rows)


