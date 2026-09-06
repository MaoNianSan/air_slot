"""Development-only stage variation analysis over shared priority inputs."""

from __future__ import annotations

from math import ceil
from pathlib import Path

import pandas as pd
from scipy.stats import kendalltau

ACTIVE_STAGES = ("PRE_IB", "POST_IB_PRE_OB", "POST_OB_PRE_TO")
SHARED_INPUT = (
    Path(__file__).resolve().parents[2]
    / "artifacts"
    / "experiment"
    / "shared"
    / "development"
    / "SHARED_DEVELOPMENT_INPUTS.parquet"
)


def _scores(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["D"] = out["delay_to_mean_cs"].astype(float)
    out["S_F"] = out[["Z_F_continuity_cs", "Z_F_execution_cs", "Z_F_propagation_cs"]].mean(axis=1)
    out["S_P"] = out[["Z_P_time_cs", "Z_P_itinerary_cs", "Z_P_service_cs"]].mean(axis=1)
    out["S_R"] = out["Z_R_operating_cs"].astype(float)
    out["S_C"] = out[["S_F", "S_P", "S_R"]].mean(axis=1)
    return out


def stage_agreement(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for stage, group in _scores(frame).groupby("operational_stage", sort=False):
        if stage not in ACTIVE_STAGES:
            continue
        group = group.dropna(subset=["D", "S_C"]).copy()
        n = len(group)
        if n < 2:
            rows.append({"stage": stage, "status": "ABSTAIN_INSUFFICIENT_SAMPLE", "n_nodes": n})
            continue
        group["d_rank"] = group["D"].rank(ascending=False, method="average", pct=True)
        group["c_rank"] = group["S_C"].rank(ascending=False, method="average", pct=True)
        displacement = (group.d_rank - group.c_rank).abs()
        k = max(1, ceil(0.10 * n))
        delay_top = set(group.nlargest(k, "D").decision_node_id)
        consequence_top = set(group.nlargest(k, "S_C").decision_node_id)
        tau = kendalltau(group["D"], group["S_C"], variant="b")
        rows.append({
            "stage": stage, "status": "PASS", "n_nodes": n,
            "n_episodes": group.original_episode_id.nunique(),
            "kendall_tau_b": float(tau.statistic),
            "top10_overlap": len(delay_top & consequence_top) / k,
            "median_rank_displacement": float(displacement.median()),
            "p90_rank_displacement": float(displacement.quantile(.90)),
            "support_coverage": float(n / len(frame[frame.operational_stage == stage])),
        })
    return pd.DataFrame(rows)
