from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

from .utils import stable_seed


def cluster_bootstrap_mean(
    df: pd.DataFrame,
    value_col: str,
    cluster_col: str,
    replicates: int,
    seed: int,
) -> tuple[float, float, float]:
    estimate = float(df[value_col].mean())
    if replicates <= 0 or df.empty:
        return estimate, np.nan, np.nan
    clusters = np.asarray(df[cluster_col].dropna().unique())
    if not len(clusters):
        return estimate, np.nan, np.nan
    values = []
    rng = np.random.default_rng(seed)
    grouped = {k: float(g[value_col].mean()) for k, g in df.groupby(cluster_col)}
    cluster_values = np.asarray([grouped[x] for x in clusters], dtype=float)
    estimate = float(cluster_values.mean())
    for _ in range(replicates):
        sampled_idx = rng.integers(0, len(cluster_values), size=len(cluster_values))
        values.append(float(cluster_values[sampled_idx].mean()))
    lo, hi = np.quantile(values, [0.025, 0.975])
    return estimate, float(lo), float(hi)


def cohort_summary(
    cohorts: dict[str, pd.DataFrame],
    rankings: pd.DataFrame | None = None,
    m3_audit: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows = []
    ranking_keys = set()
    choice_keys = set()
    choice_flights_by_key: dict[tuple[str, str], str] = {}
    choice_airports_by_key: dict[tuple[str, str], str] = {}
    if rankings is not None and not rankings.empty:
        ranking_keys = set(zip(rankings["episode_id"], rankings["snapshot_id"]))
        counts = rankings.groupby(["episode_id", "snapshot_id"])["action_id"].nunique()
        choice_keys = set(counts[counts >= 2].index)
        key_meta = rankings[["episode_id", "snapshot_id", "flight_id", "airport"]].drop_duplicates(
            ["episode_id", "snapshot_id"]
        )
        choice_flights_by_key = {
            (str(row.episode_id), str(row.snapshot_id)): str(row.flight_id)
            for row in key_meta.itertuples(index=False)
        }
        choice_airports_by_key = {
            (str(row.episode_id), str(row.snapshot_id)): str(row.airport)
            for row in key_meta.itertuples(index=False)
        }
    null_only_keys = set()
    triggered_keys = set()
    if m3_audit is not None and not m3_audit.empty:
        evaluated = m3_audit[m3_audit["is_evaluated"]]
        n_eval = evaluated.groupby(["episode_id", "snapshot_id"])["action_id"].nunique()
        null_only_keys = set(n_eval[n_eval == 1].index)
        triggered = m3_audit.groupby(["episode_id", "snapshot_id"])["trigger"].max()
        triggered_keys = set(triggered[triggered].index)
    for name, df in cohorts.items():
        keys = list(zip(df["episode_id"], df["snapshot_id"]))
        denom = max(len(keys), 1)
        decision_keys = [k for k in keys if k in ranking_keys]
        has_complete_decision_coverage = bool(keys) and len(decision_keys) == len(keys)
        completion = (
            sum(k in ranking_keys for k in keys) / denom if name != "all_valid" and ranking_keys else np.nan
        )
        if has_complete_decision_coverage:
            triggered_rate = sum(k in triggered_keys for k in keys) / denom
            choice_rate = sum(k in choice_keys for k in keys) / denom
            null_only_rate = sum(k in null_only_keys for k in keys) / denom
        else:
            triggered_rate = np.nan
            choice_rate = np.nan
            null_only_rate = np.nan
        cohort_choice_keys = [k for k in keys if k in choice_keys]
        choice_flights = {choice_flights_by_key[k] for k in cohort_choice_keys if k in choice_flights_by_key}
        per_airport: dict[str, set[str]] = {}
        for key in cohort_choice_keys:
            if key not in choice_airports_by_key or key not in choice_flights_by_key:
                continue
            per_airport.setdefault(choice_airports_by_key[key], set()).add(choice_flights_by_key[key])
        # Count airports with zero choice support as zero rather than omitting
        # them from the minimum.  Otherwise downstream readiness can appear
        # stronger when one core airport has no valid choice flight.
        cohort_airports = sorted(df["airport"].astype(str).unique())
        min_choice_airport = min(
            (len(per_airport.get(airport, set())) for airport in cohort_airports),
            default=0,
        )
        rows.append({
            "cohort": name,
            "flights": int(df["flight_id"].nunique()),
            "snapshots": int(len(df)),
            "airports": int(df["airport"].nunique()),
            "completion": completion,
            "triggered": triggered_rate,
            "choice": choice_rate,
            "null_only": null_only_rate,
            "triggered_null_only": (sum(k in null_only_keys for k in keys if k in triggered_keys) / max(sum(k in triggered_keys for k in keys), 1)) if has_complete_decision_coverage else np.nan,
            "triggered_choice_rate": (sum(k in choice_keys for k in keys if k in triggered_keys) / max(sum(k in triggered_keys for k in keys), 1)) if has_complete_decision_coverage else np.nan,
            "choice_snapshots": int(len(cohort_choice_keys)) if has_complete_decision_coverage else 0,
            "choice_flights": int(len(choice_flights)) if has_complete_decision_coverage else 0,
            "min_choice_flights_per_airport": int(min_choice_airport) if has_complete_decision_coverage else 0,
        })
    return pd.DataFrame(rows)


def precision_metrics(full_rankings: pd.DataFrame, precision_rankings: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = ["episode_id", "snapshot_id", "action_id"]
    merged = full_rankings.merge(
        precision_rankings,
        on=keys,
        suffixes=("_full", "_precision"),
        validate="one_to_one",
    )
    denom = np.maximum(np.abs(merged["score_precision"].to_numpy(float)), 1e-9)
    merged["relative_score_error"] = np.abs(merged["score_full"] - merged["score_precision"]) / denom

    per_snapshot = []
    for key, g in merged.groupby(["episode_id", "snapshot_id"], sort=False):
        g = g.sort_values("action_id")
        full_top = g.loc[g["rank_full"].idxmin(), "action_id"]
        precision_top = g.loc[g["rank_precision"].idxmin(), "action_id"]
        full_top3 = set(g.nsmallest(3, "rank_full")["action_id"])
        precision_top3 = set(g.nsmallest(3, "rank_precision")["action_id"])
        k = max(min(3, len(g)), 1)
        overlap = len(full_top3 & precision_top3) / k
        if len(g) < 2:
            tau = 1.0
        else:
            tau = kendalltau(g["rank_full"], g["rank_precision"]).statistic
        per_snapshot.append({
            "episode_id": key[0], "snapshot_id": key[1],
            "top1_agreement": float(full_top == precision_top),
            "top3_overlap": float(overlap),
            "kendall_tau": float(tau if np.isfinite(tau) else 1.0),
            "median_relative_score_error": float(g["relative_score_error"].median()),
            "p95_relative_score_error": float(g["relative_score_error"].quantile(0.95)),
        })
    per = pd.DataFrame(per_snapshot)
    summary = pd.DataFrame([
        {"metric": "median_relative_score_error", "estimate": float(merged["relative_score_error"].median())},
        {"metric": "p95_relative_score_error", "estimate": float(merged["relative_score_error"].quantile(0.95))},
        {"metric": "top1_agreement", "estimate": float(per["top1_agreement"].mean())},
        {"metric": "top3_overlap", "estimate": float(per["top3_overlap"].mean())},
        {"metric": "median_kendall_tau", "estimate": float(per["kendall_tau"].median())},
    ])
    return merged, summary
