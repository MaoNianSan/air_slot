from __future__ import annotations

from dataclasses import replace
from typing import Iterable

import pandas as pd

from ..ranking_contract import (
    RANKING_DEPTHS,
    build_ranking_prefixes_from_authoritative_order,
)
from .contracts import DecisionLane, M4ActionEvaluation


M4_RANKING_TIE_BREAK = (
    "risk_score",
    "expected_total_post_loss_rmb",
    "cvar90_post_loss_rmb",
    "expected_implementation_cost_rmb",
    "action_id",
)
_LANE_ORDER = {lane.value: index for index, lane in enumerate(DecisionLane)}


def action_evaluations_frame(
    evaluations: Iterable[M4ActionEvaluation],
) -> pd.DataFrame:
    rows = []
    for item in evaluations:
        coverage = getattr(item.m3_outcome_coverage, "value", item.m3_outcome_coverage)
        parameter = getattr(item.m3_parameter_status, "value", item.m3_parameter_status)
        rows.append({
            "episode_id": item.episode_id,
            "snapshot_id": item.snapshot_id,
            "action_id": item.action_id,
            "action_family": item.action_family,
            "decision_lane": item.decision_lane.value,
            "reason_codes": "|".join(item.reason_codes),
            "lane_rank": item.lane_rank,
            "expected_post_loss_F_rmb": item.expected_post_loss_by_channel_rmb["F"],
            "expected_post_loss_P_rmb": item.expected_post_loss_by_channel_rmb["P"],
            "expected_post_loss_R_rmb": item.expected_post_loss_by_channel_rmb["R"],
            "expected_total_post_loss_rmb": item.expected_total_post_loss_rmb,
            "expected_implementation_cost_rmb": item.expected_implementation_cost_rmb,
            "cvar90_post_loss_rmb": item.cvar90_post_loss_rmb,
            "risk_score": item.risk_score,
            "expected_improvement_vs_a00": item.expected_improvement_vs_a00,
            "tail_improvement_vs_a00": item.tail_improvement_vs_a00,
            "risk_score_improvement_vs_a00": item.risk_score_improvement_vs_a00,
            "net_benefit_probability_vs_a00": item.net_benefit_probability_vs_a00,
            "m3_outcome_coverage": str(coverage),
            "m3_parameter_status": str(parameter),
            "m2_support_status": item.m2_support_status,
            "pre_evidence_status": item.pre_evidence_status,
            "test_only": item.test_only,
        })
    return pd.DataFrame(rows)


def assign_lane_ranks(
    evaluations: tuple[M4ActionEvaluation, ...],
) -> tuple[M4ActionEvaluation, ...]:
    frame = action_evaluations_frame(evaluations)
    if frame["action_id"].astype(str).duplicated().any():
        raise ValueError("M4_RANKING_DUPLICATE_ACTION")
    frame["_lane_order"] = frame["decision_lane"].map(_LANE_ORDER)
    ordered = frame.sort_values(
        ["_lane_order", *M4_RANKING_TIE_BREAK],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)
    ordered["lane_rank"] = ordered.groupby("decision_lane", sort=False).cumcount() + 1
    by_action = {item.action_id: item for item in evaluations}
    return tuple(
        replace(by_action[str(row.action_id)], lane_rank=int(row.lane_rank))
        for row in ordered.itertuples(index=False)
    )


def build_authoritative_ranking(
    evaluations: tuple[M4ActionEvaluation, ...],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[int, pd.DataFrame]]:
    action_frame = action_evaluations_frame(evaluations)
    universe = action_frame[["episode_id", "snapshot_id"]].drop_duplicates()
    formal = action_frame[action_frame["decision_lane"].eq(DecisionLane.FORMAL.value)].copy()
    if formal.empty:
        full = pd.DataFrame()
    else:
        expected_ranks = pd.Series(range(1, len(formal) + 1), index=formal.index)
        actual_ranks = pd.to_numeric(formal["lane_rank"], errors="coerce")
        if actual_ranks.isna().any() or not actual_ranks.astype("int64").equals(
            expected_ranks.astype("int64")
        ):
            raise ValueError("M4_RANKING_NOT_AUTHORITATIVELY_ORDERED")
        full = formal.copy()
        full["score"] = full["risk_score"]
        full["expected_residual"] = full["expected_total_post_loss_rmb"]
        full["cvar_residual"] = full["cvar90_post_loss_rmb"]
        full["rank"] = range(1, len(full) + 1)
        full["rank_position"] = full["rank"]
        if full["action_id"].astype(str).eq("A00").sum() > 1:
            raise ValueError("M4_RANKING_A00_DUPLICATE")
    prefixes, views = build_ranking_prefixes_from_authoritative_order(
        universe,
        full,
        depths=RANKING_DEPTHS,
        action_library_version="M3_ATOMIC_ACTION_LIBRARY_V1",
    )
    return full, prefixes, views
