from __future__ import annotations

LEGACY_M4_NOT_FORMAL = True

from typing import Any, Mapping

import numpy as np
import pandas as pd

from .m4_pnb_contract import (
    CHANNELS,
    FLOAT32_RECONSTRUCTION_ATOL_RMB,
    FLOAT32_RATIO_ATOL,
    FORMAL_Q_TOLERANCE,
    NON_NULL_ACTIONS,
    FrozenInputs,
)
from .m4_pnb_formula import manual_pnb_reconstruction, nonnull_triggered_rows, risk_score


def _assign_cost_strata(snapshot: pd.DataFrame) -> tuple[pd.Series, list[float]]:
    values = snapshot["pre_action_cost_mean_rmb"].astype(float)
    q1, q2 = (float(value) for value in values.quantile([1 / 3, 2 / 3]))
    labels = pd.cut(
        values,
        bins=[-np.inf, q1, q2, np.inf],
        labels=["LOW", "MEDIUM", "HIGH"],
        include_lowest=True,
    ).astype("string")
    return labels, [float(values.min()), q1, q2, float(values.max())]


def _channel_composition(row: pd.Series) -> str:
    values = {channel: float(row[f"pre_action_cost_mean_rmb_{channel}"]) for channel in CHANNELS}
    total = sum(values.values())
    if total <= 0.0:
        return "balanced"
    shares = {channel: value / total for channel, value in values.items()}
    dominant = max(shares, key=shares.get)
    return f"{dominant}-dominant" if shares[dominant] >= 0.50 else "balanced"


def _rank_snapshot(
    snapshot_id: str,
    rows: pd.DataFrame,
    snapshot_context: pd.DataFrame,
    score_column: str,
    candidate_column: str,
    context_score_column: str | None = None,
) -> tuple[str, int, float, list[str]]:
    context = snapshot_context.loc[snapshot_id]
    a00_score_column = context_score_column or score_column
    candidates = rows[rows[candidate_column]].copy()
    options = [
        {
            "action_id": "A00",
            "action_family": "null",
            "score": float(context[a00_score_column]),
            "implementation": 0.0,
            "priority": 0,
            "expected_recovered": 0.0,
            "expected_post": float(context["pre_action_cost_mean_rmb"]),
        }
    ]
    for record in candidates.itertuples(index=False):
        options.append(
            {
                "action_id": str(record.action_id),
                "action_family": str(record.action_family),
                "score": float(getattr(record, score_column)),
                "implementation": float(record.expected_implementation_cost_rmb),
                "priority": int(record.priority),
                "expected_recovered": float(record.expected_recovered_cost_rmb),
                "expected_post": float(record.expected_post_action_cost_rmb),
            }
        )
    options.sort(
        key=lambda item: (
            item["score"], item["expected_post"], item["priority"], item["action_id"]
        )
    )
    best = options[0]
    return (
        str(best["action_id"]),
        len(candidates),
        float(best["score"]),
        [str(option["action_id"]) for option in options],
    )


def build_snapshot_action_audit(
    frozen: FrozenInputs,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[tuple[str, str], dict[str, np.ndarray]]]:
    config_m4 = frozen.config["m4"]
    decision = config_m4["decision_value"]
    b0 = float(decision["burden_ratio_max"])
    q0 = float(decision["positive_net_benefit_probability_min"])
    risk_aversion = float(config_m4["risk_aversion"])
    cvar_alpha = float(config_m4["cvar_alpha"])

    summary = frozen.summary.reset_index(drop=True)
    snapshot_index = {
        str(snapshot_id): index
        for index, snapshot_id in enumerate(summary["snapshot_id"])
    }
    action_metadata = frozen.actions.set_index("id")
    formal_recommendation = frozen.recommendations.set_index("snapshot_id")[
        "action_id"
    ].astype(str).to_dict()
    triggered = nonnull_triggered_rows(frozen.candidates)
    if len(triggered) != 2160:
        raise RuntimeError(f"PNB_TRIGGERED_NON_NULL_SUPPORT_CHANGED:{len(triggered)}")

    rows: list[dict[str, Any]] = []
    draw_cache: dict[tuple[str, str], dict[str, np.ndarray]] = {}
    for candidate in triggered.itertuples(index=False):
        snapshot_id = str(candidate.snapshot_id)
        action_id = str(candidate.action_id)
        index = snapshot_index[snapshot_id]
        reconstructed = manual_pnb_reconstruction(
            {
                channel: frozen.costs_rmb[channel][index]
                for channel in CHANNELS
            },
            {
                channel: frozen.m3_recovery[action_id][:, channel_index]
                for channel_index, channel in enumerate(CHANNELS)
            },
            {
                channel: frozen.m3_implementation[action_id][:, channel_index]
                for channel_index, channel in enumerate(CHANNELS)
            },
        )
        success = frozen.m3_success[action_id]
        net = reconstructed["net_benefit"]
        conditional_probability = float((net[success] > 0.0).mean()) if success.any() else np.nan
        gate_burden = reconstructed["burden_ratio"] <= b0
        gate_positive = reconstructed["positive_net_benefit_probability"] >= q0
        decision_pass = bool(gate_burden and gate_positive)
        final_candidate = bool(candidate.physical_feasible and decision_pass)
        post = reconstructed["post_action_total"]
        score = risk_score(post, risk_aversion, cvar_alpha)
        metadata = action_metadata.loc[action_id]
        record: dict[str, Any] = {
            "episode_id": str(candidate.episode_id),
            "snapshot_id": snapshot_id,
            "flight_id": str(candidate.flight_id),
            "stage": str(candidate.snapshot_stage),
            "snapshot_stage": str(candidate.snapshot_stage),
            "action_id": action_id,
            "action_family": str(candidate.action_family),
            "priority": int(metadata["priority"]),
            "pre_action_cost_mean_rmb": reconstructed["expected_pre_action_cost_rmb"],
            "pre_action_cost_p90_rmb": float(np.quantile(reconstructed["pre_total"], 0.90)),
            "expected_recovered_cost_rmb": reconstructed["expected_recovered_cost_rmb"],
            "expected_implementation_cost_rmb": reconstructed["expected_implementation_cost_rmb"],
            "expected_net_benefit_rmb": reconstructed["expected_net_benefit_rmb"],
            "expected_post_action_cost_rmb": float(post.mean()),
            "median_net_benefit_rmb": float(np.quantile(net, 0.50)),
            "q10_net_benefit_rmb": float(np.quantile(net, 0.10)),
            "q25_net_benefit_rmb": float(np.quantile(net, 0.25)),
            "q75_net_benefit_rmb": float(np.quantile(net, 0.75)),
            "q90_net_benefit_rmb": float(np.quantile(net, 0.90)),
            "positive_net_benefit_probability": reconstructed["positive_net_benefit_probability"],
            "conditional_positive_probability_given_success": conditional_probability,
            "implementation_failure_probability": float((~success).mean()),
            "q_success_minus_q_formal": conditional_probability
            - reconstructed["positive_net_benefit_probability"],
            "recovery_ratio": reconstructed["recovery_ratio"],
            "burden_ratio": reconstructed["burden_ratio"],
            "physical_feasible": bool(candidate.physical_feasible),
            "positive_net_benefit_pass": bool(gate_positive),
            "gate_burden_ratio": bool(gate_burden),
            "decision_value_pass": decision_pass,
            "final_candidate": final_candidate,
            "formal_final_candidate": bool(candidate.is_evaluated),
            "formal_recommended_action": formal_recommendation[snapshot_id],
            "recommended": formal_recommendation[snapshot_id] == action_id,
            "risk_score": score,
            "strict_positive_draws": int((net > 0.0).sum()),
            "nonnegative_draws": int((net >= 0.0).sum()),
            "equal_recovered_implementation_draws": int((net == 0.0).sum()),
            "failure_draws": int((~success).sum()),
            "failure_draws_with_positive_implementation_cost": int(
                ((~success) & (reconstructed["implementation_total"] > 0.0)).sum()
            ),
            "successful_draws_recovery_le_cost": int(
                (success & (net <= 0.0)).sum()
            ),
            "successful_draws_recovery_gt_cost": int(
                (success & (net > 0.0)).sum()
            ),
        }
        for channel in CHANNELS:
            record[f"pre_action_cost_mean_rmb_{channel}"] = float(
                np.asarray(frozen.costs_rmb[channel][index], dtype=float).mean()
            )
            record[f"expected_recovered_cost_rmb_{channel}"] = float(
                reconstructed["recovered_by_channel"][channel].mean()
            )
            record[f"expected_implementation_cost_rmb_{channel}"] = float(
                reconstructed["implementation_by_channel"][channel].mean()
            )
        rows.append(record)
        draw_cache[(snapshot_id, action_id)] = {
            key: np.asarray(reconstructed[key])
            for key in (
                "pre_total", "recovered_total", "implementation_total",
                "net_benefit", "post_action_total",
            )
        }

    frame = pd.DataFrame(rows)
    snapshot = (
        frame.groupby("snapshot_id", sort=False)
        .first()[
            [
                "episode_id", "flight_id", "stage", "pre_action_cost_mean_rmb",
                "pre_action_cost_mean_rmb_F", "pre_action_cost_mean_rmb_P",
                "pre_action_cost_mean_rmb_R", "formal_recommended_action",
            ]
        ]
        .copy()
    )
    snapshot["a00_score"] = [
        risk_score(
            draw_cache[(snapshot_id, NON_NULL_ACTIONS[0])]["pre_total"],
            risk_aversion,
            cvar_alpha,
        )
        for snapshot_id in snapshot.index
    ]
    cost_strata, boundaries = _assign_cost_strata(snapshot.reset_index())
    snapshot["cost_stratum"] = cost_strata.to_numpy()
    snapshot["channel_composition"] = snapshot.apply(_channel_composition, axis=1)
    frame = frame.merge(
        snapshot[["cost_stratum", "channel_composition"]],
        left_on="snapshot_id",
        right_index=True,
        validate="many_to_one",
    )

    manual_recommendations: dict[str, str] = {}
    for snapshot_id, group in frame.groupby("snapshot_id", sort=False):
        action_id, _, _, _ = _rank_snapshot(
            str(snapshot_id), group, snapshot, "risk_score", "final_candidate",
            context_score_column="a00_score",
        )
        manual_recommendations[str(snapshot_id)] = action_id
    frame["manual_recommended_action"] = frame["snapshot_id"].map(
        manual_recommendations
    )

    formal = triggered[
        [
            "episode_id", "snapshot_id", "action_id", "expected_pre_action_cost_rmb",
            "expected_recovery_rmb", "expected_implementation_cost_rmb", "recovery_ratio",
            "burden_ratio", "positive_net_benefit_probability",
            "gate_burden_ratio", "gate_positive_net_benefit", "decision_value_pass",
            "is_evaluated",
        ]
    ].copy()
    identity = frame.merge(
        formal,
        on=["episode_id", "snapshot_id", "action_id"],
        suffixes=("_manual", "_formal"),
        validate="one_to_one",
    )
    identity["expected_recovered_cost_abs_error_rmb"] = (
        identity["expected_recovered_cost_rmb"] - identity["expected_recovery_rmb"]
    ).abs()
    identity["expected_implementation_cost_abs_error_rmb"] = (
        identity["expected_implementation_cost_rmb_manual"]
        - identity["expected_implementation_cost_rmb_formal"]
    ).abs()
    identity["recovery_ratio_abs_error"] = (
        identity["recovery_ratio_manual"] - identity["recovery_ratio_formal"]
    ).abs()
    identity["burden_ratio_abs_error"] = (
        identity["burden_ratio_manual"] - identity["burden_ratio_formal"]
    ).abs()
    identity["positive_net_benefit_probability_abs_error"] = (
        identity["positive_net_benefit_probability_manual"]
        - identity["positive_net_benefit_probability_formal"]
    ).abs()
    identity["gate_disagreement"] = (
        identity["gate_burden_ratio_manual"].ne(identity["gate_burden_ratio_formal"])
        | identity["positive_net_benefit_pass"].ne(identity["gate_positive_net_benefit"])
        | identity["decision_value_pass_manual"].ne(identity["decision_value_pass_formal"])
    )
    identity["candidate_disagreement"] = identity["final_candidate"].ne(
        identity["is_evaluated"]
    )
    identity["recommendation_disagreement"] = identity[
        "manual_recommended_action"
    ].ne(identity["formal_recommended_action"])
    identity["expected_recovered_cost_mismatch"] = identity[
        "expected_recovered_cost_abs_error_rmb"
    ].gt(FLOAT32_RECONSTRUCTION_ATOL_RMB)
    identity["positive_net_benefit_probability_mismatch"] = identity[
        "positive_net_benefit_probability_abs_error"
    ].gt(FORMAL_Q_TOLERANCE)
    snapshot.attrs["cost_strata_boundaries"] = boundaries
    return frame, identity, snapshot, draw_cache


