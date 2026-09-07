"""Stage estimands; reference and vectorized matching share occurrence semantics."""

from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd

from exp.shared.analytical import ACTIVE_STAGES, scores as _scores, primary_mask
from exp.shared.resampling import bootstrap_plan, episode_ids, expand_draw
from exp.exp2.metrics import midrank_percentiles, priority_metrics

SHARED_INPUT = Path(__file__).resolve().parents[2] / "artifacts/experiment/shared/development/SHARED_DEVELOPMENT_INPUTS.parquet"
METRICS = ("kendall_tau_b", "top10_overlap", "median_rank_displacement",
           "p90_rank_displacement", "median_consequence_priority_percentile_gap",
           "p90_consequence_priority_percentile_gap")


def _prepared(frame):
    return frame if "NO_F_EXECUTION" in frame else _scores(frame)


def _pairs(group, caliper=5., reference=False):
    n = len(group)
    d, c = group.D.to_numpy(float), group.S_C.to_numpy(float)
    ranks = midrank_percentiles(c) if n else np.array([])
    original = group.original_episode_id.astype(str).to_numpy()
    instances = group.get("bootstrap_instance_id", group.original_episode_id).astype(str).to_numpy()
    if reference:
        pairs = [(i, j) for i, j in combinations(range(n), 2)
                 if original[i] != original[j] and abs(d[i] - d[j]) <= caliper]
        i, j = np.asarray(pairs, dtype=int).reshape(-1, 2).T
    else:
        i, j = np.triu_indices(n, 1)
        keep = (original[i] != original[j]) & (np.abs(d[i] - d[j]) <= caliper)
        i, j = i[keep], j[keep]
    swap = instances[i] > instances[j]
    a, b = np.where(swap, j, i), np.where(swap, i, j)
    return pd.DataFrame({
        "episode_i": instances[a], "episode_j": instances[b],
        "original_i": original[a], "original_j": original[b],
        "consequence_gap": np.abs(ranks[i] - ranks[j]),
        "score_gap_secondary": np.abs(c[i] - c[j]),
    })


def _heterogeneity(group, caliper=5., reference=False):
    pairs = _pairs(group, caliper, reference)
    if pairs.empty:
        return {"heterogeneity_status": "ABSTAIN_INSUFFICIENT_MATCHES",
                "candidate_pairs": 0, "balanced_episode_pairs": 0,
                "median_consequence_priority_percentile_gap": None,
                "p90_consequence_priority_percentile_gap": None}
    balanced = pairs.groupby(["episode_i", "episode_j"], sort=False).consequence_gap.median()
    matched = len(set(pairs.original_i) | set(pairs.original_j))
    return {
        "heterogeneity_status": "PASS", "candidate_pairs": len(pairs),
        "balanced_episode_pairs": len(balanced), "matched_episodes": matched,
        "match_coverage": matched / group.original_episode_id.nunique(),
        "median_consequence_priority_percentile_gap": float(balanced.median()),
        "p90_consequence_priority_percentile_gap": float(balanced.quantile(.9)),
    }


def evaluate_stages(frame, caliper=5., reference=False):
    data = _prepared(frame)
    eligible = data[primary_mask(data)]
    records = []
    for stage in ACTIVE_STAGES:
        group = eligible[eligible.operational_stage.eq(stage)]
        denominator = int(data.operational_stage.eq(stage).sum())
        row = {"stage": stage, "n_nodes": len(group),
               "n_episodes": group.original_episode_id.nunique(),
               "support_coverage": len(group) / denominator if denominator else None,
               "caliper_minutes": caliper}
        if group.empty:
            row.update(status="ABSTAIN_EMPTY_SAMPLE", **{m: None for m in METRICS})
        else:
            ids = group.get("technical_node_id", group.decision_node_id).astype(str).tolist()
            if len(ids) != len(set(ids)):
                raise ValueError("EXP3_TECHNICAL_ID_COLLISION")
            row.update(priority_metrics(group.D.tolist(), group.S_C.tolist(), ids))
            row["top10_overlap"] = row.pop("top_overlap")
            row["status"] = "PASS" if len(group) >= 2 else "ABSTAIN_INSUFFICIENT_SAMPLE"
            row.update(_heterogeneity(group, caliper, reference))
            for name in ("delay", "consequence"):
                row[f"{name}_boundary_tie_fraction"] = row[f"{name}_boundary_tie_count"] / len(group)
        records.append(row)
    return pd.DataFrame(records)


def stage_agreement(frame):
    return evaluate_stages(frame)


def stage_heterogeneity(frame, caliper=5.):
    return evaluate_stages(frame, caliper)


def stage_contrasts(agreement):
    values = agreement.set_index("stage")
    rows = []
    for a, b in combinations(ACTIVE_STAGES, 2):
        row = {"stage_a": a, "stage_b": b}
        for metric in METRICS:
            x, y = values.loc[a].get(metric), values.loc[b].get(metric)
            row[f"{metric}_difference"] = None if pd.isna(x) or pd.isna(y) else float(x-y)
        rows.append(row)
    return pd.DataFrame(rows)


def common_episode_cohort(frame):
    data = _prepared(frame)
    eligible = data[primary_mask(data)]
    ids = eligible.groupby("original_episode_id").operational_stage.nunique()
    return data[data.original_episode_id.isin(ids[ids == len(ACTIVE_STAGES)].index)].copy()


def bootstrap_stage(frame, replicates=2000, seed=20260906, *, plan=None, reference=True):
    data = _prepared(frame)
    if plan is None:
        plan = bootstrap_plan(episode_ids(data), replicates, seed)
    records = []
    for replicate, draw in enumerate(plan):
        sample = expand_draw(data, draw)
        result = evaluate_stages(sample, reference=reference)
        result["replicate"] = replicate
        records.append(result)
        if (replicate + 1) % 100 == 0:
            print(f"EXP3 bootstrap {replicate+1}/{len(plan)}", flush=True)
    return pd.concat(records, ignore_index=True)


def bootstrap_stage_fast(frame, replicates=2000, seed=20260906, *, plan=None):
    return bootstrap_stage(frame, replicates, seed, plan=plan, reference=False)
