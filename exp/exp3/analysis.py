"""Development-only stage variation analysis over shared priority inputs."""

from __future__ import annotations

from math import ceil
from pathlib import Path

import pandas as pd
from scipy.stats import kendalltau, rankdata
import numpy as np

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
        group = group[
            group["support_primary"].eq(True)
            & group["conditional_aggregate_complete"].eq(True)
        ].dropna(subset=["D", "S_C"]).copy()
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
        left["consequence_priority_percentile"] = (
            left["S_C"].rank(ascending=False, method="average", pct=True)
        )
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
                    "consequence_gap": abs(
                        float(a.consequence_priority_percentile)
                        - float(b.consequence_priority_percentile)
                    ),
                    "native_consequence_gap": abs(float(a.S_C) - float(b.S_C)),
                })
    return pd.DataFrame(rows)


def stage_heterogeneity(frame: pd.DataFrame, caliper: float = 5.0) -> pd.DataFrame:
    data = _scores(frame)
    rows = []
    for stage, group in data.groupby("operational_stage", sort=False):
        if stage not in ACTIVE_STAGES:
            continue
        group = group[
            group["support_primary"].eq(True)
            & group["conditional_aggregate_complete"].eq(True)
        ].dropna(subset=["D", "S_C"])
        pairs = _pairs(group, caliper)
        if pairs.empty:
            rows.append({"stage": stage, "caliper_minutes": caliper, "status": "ABSTAIN_INSUFFICIENT_MATCHES", "candidate_pairs": 0})
            continue
        pair_balanced = (
            pairs.groupby(["episode_i", "episode_j"], as_index=False)[
                ["consequence_gap", "native_consequence_gap"]
            ]
            .median()
        )
        rows.append({
            "stage": stage, "caliper_minutes": caliper, "status": "PASS",
            "candidate_pairs": len(pairs),
            "balanced_episode_pairs": len(pair_balanced),
            "matched_episodes": len(set(pair_balanced.episode_i) | set(pair_balanced.episode_j)),
            "median_consequence_priority_percentile_gap": float(pair_balanced.consequence_gap.median()),
            "p90_consequence_priority_percentile_gap": float(pair_balanced.consequence_gap.quantile(.90)),
            "median_native_consequence_gap": float(pair_balanced.native_consequence_gap.median()),
        })
    return pd.DataFrame(rows)


def bootstrap_stage(frame: pd.DataFrame, replicates: int = 2000, seed: int = 20260906) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    episodes = frame.original_episode_id.astype(str).unique()
    records = []
    for replicate in range(replicates):
        sampled = rng.choice(episodes, size=len(episodes), replace=True)
        pieces = []
        for position, episode_id in enumerate(sampled):
            piece = frame[frame.original_episode_id.astype(str).eq(episode_id)].copy()
            piece["bootstrap_instance_id"] = f"{episode_id}#bootstrap-{position}"
            piece["technical_node_id"] = (
                piece["decision_node_id"].astype(str) + f"#bootstrap-{position}"
            )
            pieces.append(piece)
        if not pieces:
            continue
        sample = pd.concat(pieces, ignore_index=True)
        agreement = stage_agreement(sample)
        heterogeneity = stage_heterogeneity(sample)
        for row in agreement.to_dict("records"):
            records.append({"replicate": replicate, "metric": "top10_overlap", **row})
        for row in heterogeneity.to_dict("records"):
            records.append({"replicate": replicate, "metric": "median_consequence_priority_percentile_gap", **row})
    return pd.DataFrame(records)


def bootstrap_stage_fast(frame: pd.DataFrame, replicates: int = 2000, seed: int = 20260906) -> pd.DataFrame:
    """Equivalent cluster bootstrap using arrays; rebuilds ranks and matches."""
    data = _scores(frame)
    data = data[
        data.support_primary.eq(True)
        & data.conditional_aggregate_complete.eq(True)
    ].dropna(subset=["D", "S_C"])
    episodes = data.original_episode_id.astype(str).to_numpy()
    by_episode = {episode: idx for idx, episode in enumerate(sorted(set(episodes)))}
    episode_rows = [[] for _ in by_episode]
    for index, episode in enumerate(episodes):
        episode_rows[by_episode[episode]].append(index)
    stage = data.operational_stage.to_numpy()
    delay = data.D.to_numpy(float)
    consequence = data.S_C.to_numpy(float)
    rng = np.random.default_rng(seed)
    records = []
    for replicate in range(replicates):
        sampled = rng.integers(0, len(episode_rows), size=len(episode_rows))
        indices = np.asarray([i for e in sampled for i in episode_rows[e]], dtype=int)
        for stage_name in ACTIVE_STAGES:
            idx = indices[stage[indices] == stage_name]
            if len(idx) < 2:
                continue
            d = delay[idx]
            c = consequence[idx]
            d_rank = (rankdata(d, method="average") - .5) / len(d)
            c_rank = (rankdata(c, method="average") - .5) / len(c)
            k = max(1, int(np.ceil(.10 * len(idx))))
            d_top = set(idx[np.lexsort((data.decision_node_id.to_numpy()[idx], -d))[:k]])
            c_top = set(idx[np.lexsort((data.decision_node_id.to_numpy()[idx], -c))[:k]])
            tau = kendalltau(d, c, variant="b").statistic
            records.append({
                "replicate": replicate, "stage": stage_name, "metric": "stage_agreement",
                "kendall_tau_b": float(tau), "top10_overlap": len(d_top & c_top) / k,
                "median_rank_displacement": float(np.median(abs(d_rank - c_rank))),
                "p90_rank_displacement": float(np.quantile(abs(d_rank - c_rank), .90)),
            })
            order = np.argsort(d, kind="stable")
            sorted_idx = idx[order]
            gaps = []
            for pos, left in enumerate(sorted_idx):
                right = pos + 1
                while right < len(sorted_idx) and delay[sorted_idx[right]] - delay[left] <= 5:
                    if episodes[sorted_idx[right]] != episodes[left]:
                        gaps.append(abs(c_rank[order[right]] - c_rank[order[pos]]))
                    right += 1
            records.append({
                "replicate": replicate, "stage": stage_name,
                "metric": "same_delay_percentile_gap",
                "median_consequence_priority_percentile_gap": None if not gaps else float(np.median(gaps)),
                "p90_consequence_priority_percentile_gap": None if not gaps else float(np.quantile(gaps, .90)),
            })
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
