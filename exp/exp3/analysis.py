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


def _pairs(group: pd.DataFrame, caliper: float = 5.0) -> pd.DataFrame:
    rows = []
    for _, left in group.groupby("operational_stage", sort=False):
        left = left.sort_values("D", kind="mergesort").reset_index(drop=True)
        start = 0
        for i in range(len(left)):
            value = float(left.at[i, "D"])
            while start < i and value - float(left.at[start, "D"]) > caliper:
                start += 1
            for j in range(start, i):
                a, b = left.iloc[j], left.iloc[i]
                if a.original_episode_id == b.original_episode_id:
                    continue
                rows.append({
                    "stage": a.operational_stage,
                    "episode_i": a.original_episode_id,
                    "episode_j": b.original_episode_id,
                    "node_i": a.decision_node_id,
                    "node_j": b.decision_node_id,
                    "consequence_gap": abs(float(a.S_C) - float(b.S_C)),
                })
    return pd.DataFrame(rows)


def stage_heterogeneity(frame: pd.DataFrame, caliper: float = 5.0) -> pd.DataFrame:
    data = _scores(frame)
    rows = []
    for stage, group in data.groupby("operational_stage", sort=False):
        if stage not in ACTIVE_STAGES:
            continue
        group = group.dropna(subset=["D", "S_C"])
        pairs = _pairs(group, caliper)
        if pairs.empty:
            rows.append({"stage": stage, "caliper_minutes": caliper, "status": "ABSTAIN_INSUFFICIENT_MATCHES", "candidate_pairs": 0})
            continue
        pair_balanced = pairs.groupby(["episode_i", "episode_j"], as_index=False)["consequence_gap"].median()
        rows.append({
            "stage": stage, "caliper_minutes": caliper, "status": "PASS",
            "candidate_pairs": len(pairs),
            "balanced_episode_pairs": len(pair_balanced),
            "matched_episodes": len(set(pair_balanced.episode_i) | set(pair_balanced.episode_j)),
            "median_consequence_gap": float(pair_balanced.consequence_gap.median()),
            "p90_consequence_gap": float(pair_balanced.consequence_gap.quantile(.90)),
        })
    return pd.DataFrame(rows)


def bootstrap_stage(frame: pd.DataFrame, replicates: int = 2000, seed: int = 20260906) -> pd.DataFrame:
    rng = __import__("numpy").random.default_rng(seed)
    episodes = frame.original_episode_id.astype(str).unique()
    records = []
    for replicate in range(replicates):
        sampled = rng.choice(episodes, size=len(episodes), replace=True)
        pieces = [frame[frame.original_episode_id.astype(str).eq(e)] for e in sampled]
        if not pieces:
            continue
        sample = __import__("pandas").concat(pieces, ignore_index=True)
        agreement = stage_agreement(sample)
        heterogeneity = stage_heterogeneity(sample)
        for row in agreement.to_dict("records"):
            records.append({"replicate": replicate, "metric": "top10_overlap", **row})
        for row in heterogeneity.to_dict("records"):
            records.append({"replicate": replicate, "metric": "median_consequence_gap", **row})
    return pd.DataFrame(records)


def stage_contrasts(agreement: pd.DataFrame) -> pd.DataFrame:
    values = agreement.set_index("stage")
    rows = []
    for a, b in (("PRE_IB", "POST_IB_PRE_OB"), ("POST_IB_PRE_OB", "POST_OB_PRE_TO"), ("PRE_IB", "POST_OB_PRE_TO")):
        if a not in values.index or b not in values.index:
            rows.append({"stage_a": a, "stage_b": b, "status": "ABSTAIN_MISSING_STAGE"})
            continue
        rows.append({
            "stage_a": a, "stage_b": b, "status": "PASS",
            "top10_overlap_difference": float(values.loc[a, "top10_overlap"] - values.loc[b, "top10_overlap"]),
            "median_rank_displacement_difference": float(values.loc[a, "median_rank_displacement"] - values.loc[b, "median_rank_displacement"]),
            "kendall_tau_b_difference": float(values.loc[a, "kendall_tau_b"] - values.loc[b, "kendall_tau_b"]),
        })
    return pd.DataFrame(rows)
