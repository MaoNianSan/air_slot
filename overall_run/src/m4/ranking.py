from __future__ import annotations

from dataclasses import replace
from typing import Iterable

import pandas as pd

from ..ranking_contract import RANKING_DEPTHS, build_ranking_prefixes, full_ranking_from_scores
from .contracts import DecisionLane, M4ActionEvaluation


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
    ranks: dict[str, int] = {}
    frame = action_evaluations_frame(evaluations)
    for _, group in frame.groupby("decision_lane", sort=False):
        ordered = group.sort_values(
            [
                "risk_score",
                "expected_total_post_loss_rmb",
                "cvar90_post_loss_rmb",
                "expected_implementation_cost_rmb",
                "action_id",
            ],
            kind="mergesort",
        )
        for rank, action_id in enumerate(ordered["action_id"].astype(str), 1):
            ranks[action_id] = rank
    return tuple(replace(item, lane_rank=ranks[item.action_id]) for item in evaluations)


def build_authoritative_ranking(
    evaluations: tuple[M4ActionEvaluation, ...],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[int, pd.DataFrame]]:
    action_frame = action_evaluations_frame(evaluations)
    universe = action_frame[["episode_id", "snapshot_id"]].drop_duplicates()
    formal = action_frame[action_frame["decision_lane"].eq(DecisionLane.FORMAL.value)].copy()
    if formal.empty:
        full = pd.DataFrame()
    else:
        formal["expected_residual"] = formal["expected_total_post_loss_rmb"]
        formal["cvar_residual"] = formal["cvar90_post_loss_rmb"]
        full = full_ranking_from_scores(formal, "risk_score")
        if full["action_id"].astype(str).eq("A00").sum() > 1:
            raise ValueError("M4_RANKING_A00_DUPLICATE")
    prefixes, views = build_ranking_prefixes(
        universe,
        full,
        depths=RANKING_DEPTHS,
        action_library_version="M3_ATOMIC_ACTION_LIBRARY_V1",
    )
    return full, prefixes, views
