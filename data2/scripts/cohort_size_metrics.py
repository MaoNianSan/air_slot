# -*- coding: utf-8 -*-
"""Cohort-size stability battery - PRE-observable layer (M5 Phase D/E).

    python data2/scripts/cohort_size_metrics.py --years 2019
    python data2/scripts/cohort_size_metrics.py --years 2017 2018 2019 2020 2021 2022

Computes, per (year, N), the decision-relevant observable battery from the
already-materialized PRE development states (N{n}/PRE_DEVELOPMENT_STATES.jsonl)
and measures stability across the nested N grid:

  * structural: nodes per episode, operational-stage mix
  * evidence admissibility: weather-admissible share, stage-eligible shares
  * reference support: taxi/turnaround support-state mix and fallback-level mix
  * target support: R_IB / DELTA_OB / T_TX support-state mix
  * ranking stability: node ranking by connection-airport reference minutes
    (Kendall tau-b, top-decile overlap, rank displacement) against N_max
  * bootstrap CI width (episode-level, B=2000, seed 20260906) for the headline
    shares, and the width ratio w(2N)/w(N)

DEVELOPMENT ONLY: this script never reads Oct-Dec (final-test) data. The
consequence-side battery (seven components, action/regret) additionally needs
M1_N training plus the per-year M2 CU registry and is tracked separately.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

REPO = _REPO_ROOT
DATA2 = REPO / "data2"
STUDY_ROOT = DATA2 / "reports" / "cohort_size_stability"
N_GRID = (128, 256, 512, 1024, 2048, 4096)
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20260906
TOP_FRACTION = 0.10
# stability thresholds (the N* rule; user-confirmed values pending)
TAU_EPS = 0.02
TOPK_MIN = 0.95
CI_WIDTH_RATIO_MAX = 1.10
SHARE_EPS = 0.015          # headline-share deviation vs largest-N cohort
CI_SHRINK_EPS = 0.25       # relative CI-width shrink allowed at the next doubling


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(message: str) -> None:
    print(f"[{now_iso()}] {message}", flush=True)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")


def _state_support(state: dict, key: str) -> str | None:
    node = state.get(key)
    if isinstance(node, dict):
        value = node.get("support_state")
        return str(value) if value is not None else None
    return None


def load_node_observables(year: int, n: int) -> dict:
    """Per-node observables for one (year, N) development cohort."""
    path = STUDY_ROOT / str(year) / f"N{n}" / "PRE_DEVELOPMENT_STATES.jsonl"
    if not path.is_file():
        return {"status": "MISSING_FILE", "path": str(path)}
    episode_ids: set[str] = set()
    nodes = 0
    stages: Counter = Counter()
    weather_admissible = 0
    ledger_admissible = 0
    ledger_entries = 0
    reference_minutes: list[tuple[str, float]] = []
    taxi_support: Counter = Counter()
    taxi_fallback: Counter = Counter()
    turnaround_support: Counter = Counter()
    turnaround_fallback: Counter = Counter()
    targets: dict[str, Counter] = defaultdict(Counter)
    per_episode_nodes: Counter = Counter()
    grid = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            state = json.loads(line)
            nodes += 1
            node = state["decision_node"]
            episode_id = node["episode_id"]
            episode_ids.add(episode_id)
            per_episode_nodes[episode_id] += 1
            stages[str(node.get("operational_stage"))] += 1
            current = state.get("current_state", {})
            if _state_support(current, "current_weather") == "SUPPORTED":
                weather_admissible += 1
            for entry in state.get("evidence_ledger", ()):
                ledger_entries += 1
                if entry.get("admissible"):
                    ledger_admissible += 1
            references = state.get("reference_state", {}).get("entries", {})
            for name, support_counter, fallback_counter in (
                    ("taxi_reference", taxi_support, taxi_fallback),
                    ("turnaround_reference", turnaround_support,
                     turnaround_fallback)):
                entry = references.get(name) or {}
                support_counter[str(entry.get("support_state"))] += 1
                fallback_counter[str(entry.get("fallback_level"))] += 1
                value = entry.get("value") or {}
                minutes = value.get("value_minutes")
                if isinstance(minutes, (int, float)):
                    reference_minutes.append((node["decision_node_id"],
                                              float(minutes)))
            for target in state.get("target_support", ()):
                targets[str(target.get("target_name"))][
                    str(target.get("support_state"))] += 1
            grid += 1
    shares = {
        "weather_admissible_share": weather_admissible / nodes if nodes else None,
        "ledger_admissible_share": ledger_admissible / ledger_entries
        if ledger_entries else None,
    }
    return {
        "status": "OK",
        "year": year, "n": n,
        "nodes": nodes, "episodes": len(episode_ids),
        "nodes_per_episode_mean": round(nodes / len(episode_ids), 4)
        if episode_ids else None,
        "stage_mix": dict(stages),
        "stage_shares": {k: v / nodes for k, v in stages.items()} if nodes else {},
        "shares": shares,
        "taxi_support": dict(taxi_support),
        "taxi_fallback": dict(taxi_fallback),
        "turnaround_support": dict(turnaround_support),
        "turnaround_fallback": dict(turnaround_fallback),
        "targets": {name: dict(counter) for name, counter in targets.items()},
        "reference_minutes_n": len(reference_minutes),
        "_reference_minutes": reference_minutes,
        "_per_episode_nodes": dict(per_episode_nodes),
    }


def tie_share(scores: dict[str, float]) -> float:
    """Share of keys sharing their score with at least one other key."""
    counts = Counter(scores.values())
    tied = sum(n for n in counts.values() if n > 1)
    return tied / len(scores) if scores else 1.0


def kendall_tau_b(rank_a: dict[str, float], rank_b: dict[str, float]) -> float:
    """Kendall tau-b between two score maps over their common keys."""
    keys = sorted(set(rank_a) & set(rank_b))
    if len(keys) < 2:
        return 1.0
    a = [rank_a[k] for k in keys]
    b = [rank_b[k] for k in keys]
    concordant = discordant = ties_a = ties_b = 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            da = a[i] - a[j]
            db = b[i] - b[j]
            if da == 0 and db == 0:
                ties_a += 1
                ties_b += 1
            elif da == 0:
                ties_a += 1
            elif db == 0:
                ties_b += 1
            elif (da > 0) == (db > 0):
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    if total == 0:
        return 1.0
    denom = ((total + ties_a) * (total + ties_b)) ** 0.5
    return (concordant - discordant) / denom if denom else 1.0


def top_fraction_overlap(scores_a: dict[str, float],
                         scores_b: dict[str, float],
                         fraction: float = TOP_FRACTION) -> float:
    keys = sorted(set(scores_a) & set(scores_b))
    if not keys:
        return 1.0
    k = max(1, int(len(keys) * fraction))
    top_a = {key for key, _ in sorted(
        ((k_, scores_a[k_]) for k_ in keys), key=lambda item: (-item[1], item[0]))[:k]}
    top_b = {key for key, _ in sorted(
        ((k_, scores_b[k_]) for k_ in keys), key=lambda item: (-item[1], item[0]))[:k]}
    return len(top_a & top_b) / k


def max_decile_displacement(scores_a: dict[str, float],
                            scores_b: dict[str, float]) -> int:
    keys = sorted(set(scores_a) & set(scores_b))
    if not keys:
        return 0

    def deciles(scores):
        ordered = sorted(keys, key=lambda key: (-scores[key], key))
        step = max(1, len(ordered) // 10)
        return {key: min(9, position // step)
                for position, key in enumerate(ordered)}

    da, db = deciles(scores_a), deciles(scores_b)
    return sum(1 for key in keys if abs(da[key] - db[key]) >= 3)


def bootstrap_ci(values: list[float]) -> dict:
    if not values:
        return {"mean": None, "ci_low": None, "ci_high": None, "width": None}
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(values)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    low = means[int(0.025 * len(means))]
    high = means[int(0.975 * len(means)) - 1]
    return {"mean": sum(values) / n, "ci_low": low, "ci_high": high,
            "width": high - low}


def episode_level_share(per_episode_nodes: dict[str, int]) -> list[float]:
    return [float(value) for value in per_episode_nodes.values()]


def compute_metrics(year: int) -> dict:
    per_n: dict[int, dict] = {}
    raw: dict[int, dict] = {}
    for n in N_GRID:
        result = load_node_observables(year, n)
        if result.get("status") != "OK":
            per_n[n] = {"status": result.get("status", "UNKNOWN")}
            continue
        raw[n] = result
        summary = {key: value for key, value in result.items()
                   if not key.startswith("_")}
        per_n[n] = summary
    if not raw:
        return {"year": year, "status": "NO_MATERIALIZED_COHORTS"}

    reference_n = max(raw)
    ref_scores = dict(raw[reference_n]["_reference_minutes"])
    ref_episode_values = episode_level_share(
        raw[reference_n]["_per_episode_nodes"])

    stability = {}
    for n in sorted(raw):
        scores = dict(raw[n]["_reference_minutes"])
        episode_values = episode_level_share(raw[n]["_per_episode_nodes"])
        ci = bootstrap_ci(episode_values)
        ref_ci = bootstrap_ci(ref_episode_values)
        stability[n] = {
            "kendall_tau_b_vs_maxN": round(kendall_tau_b(scores, ref_scores), 6),
            "top_decile_overlap_vs_maxN": round(
                top_fraction_overlap(scores, ref_scores), 6),
            "max_decile_displacement_vs_maxN": max_decile_displacement(
                scores, ref_scores),
            "nodes_per_episode_ci": ci,
            "nodes_per_episode_ci_width": ci["width"],
            "ci_width_ratio_vs_maxN": (
                round(ci["width"] / ref_ci["width"], 6)
                if ci["width"] and ref_ci["width"] else None),
        }
    # sequential doubling checks
    doubling = {}
    for n in sorted(raw):
        if 2 * n in raw:
            stability_n = stability[n]
            stability_2n = stability[2 * n]
            doubling[f"{n}->{2 * n}"] = {
                "tau_delta": round(abs(stability_n["kendall_tau_b_vs_maxN"]
                                       - stability_2n["kendall_tau_b_vs_maxN"]), 6),
                "topk_ok": stability_n["top_decile_overlap_vs_maxN"] >= TOPK_MIN,
                "displacement_delta": (stability_n[
                    "max_decile_displacement_vs_maxN"]
                    - stability_2n["max_decile_displacement_vs_maxN"]),
                "ci_width_ratio": stability_n["ci_width_ratio_vs_maxN"],
            }

    def stable_at(n: int) -> bool:
        s = stability.get(n)
        if s is None:
            return False
        if abs(s["kendall_tau_b_vs_maxN"] - 1.0) > TAU_EPS:
            return False
        if s["top_decile_overlap_vs_maxN"] < TOPK_MIN:
            return False
        if s["max_decile_displacement_vs_maxN"] != 0:
            return False
        ratio = s["ci_width_ratio_vs_maxN"]
        if ratio is not None and ratio > CI_WIDTH_RATIO_MAX:
            return False
        return True

    # distributional convergence: headline shares within SHARE_EPS of the
    # largest-N cohort (the closest available reference for the pool truth)
    share_metrics = ("weather_admissible_share", "ledger_admissible_share")
    ref_shares = {name: per_n[reference_n]["shares"].get(name)
                  for name in share_metrics}
    share_deviation = {}
    for n in sorted(raw):
        deviation = {}
        for name in share_metrics:
            value = per_n[n]["shares"].get(name)
            ref = ref_shares.get(name)
            deviation[name] = (None if value is None or ref is None
                               else round(abs(value - ref), 6))
        share_deviation[n] = deviation
    tie_shares = {n: round(tie_share(dict(raw[n]["_reference_minutes"])), 4)
                  for n in sorted(raw)}
    ranking_observable_degenerate = all(
        value >= 0.99 for value in tie_shares.values())

    # corrected N* rule: N is stable when (a) every headline share is within
    # SHARE_EPS of the largest-N cohort, and (b) the nodes-per-episode CI
    # width no longer shrinks materially at the next doubling.
    def share_stable(n: int) -> bool:
        return all(value is not None and value <= SHARE_EPS
                   for value in share_deviation.get(n, {}).values())

    # NOTE: CI width shrinks like 1/sqrt(N) for any mean and therefore never
    # stops shrinking; a "no further shrink" criterion is unsatisfiable by
    # construction. The PRE-layer stability rule is therefore distributional
    # convergence of headline shares (with doubling persistence). The CI table
    # is reported as supporting precision evidence only, and the authoritative
    # N* must come from the consequence-side battery (M1/M2), which this layer
    # cannot substitute for.
    stable_flags = {n: share_stable(n) for n in sorted(raw)}
    stable_n = None
    for n in sorted(raw):
        if stable_flags[n] and (2 * n in raw and stable_flags[2 * n]):
            stable_n = n
            break
    if stable_n is None and stable_flags.get(reference_n):
        stable_n = reference_n     # stable only at the grid top
    report = {
        "year": year, "status": "OK",
        "reference_N": reference_n,
        "per_n": per_n, "stability": stability, "doubling_checks": doubling,
        "share_deviation_vs_maxN": share_deviation,
        "reference_minutes_tie_share": tie_shares,
        "ranking_observable_degenerate": ranking_observable_degenerate,
        "stable_flags": stable_flags,
        "stable_N_y": stable_n,
        "stable_N_y_semantics": (
            "PRE-observable layer lower bound: smallest N whose headline "
            "shares sit within share_eps of the largest-N cohort and remain "
            "stable at the next doubling. The authoritative N* requires the "
            "consequence-side (M1/M2) battery."),
        "thresholds": {"share_eps": SHARE_EPS,
                       "tau_eps": TAU_EPS, "topk_min": TOPK_MIN},
        "note": ("PRE-observable layer only (no M1/M2 consequence side); "
                 "development window only."),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", type=int, nargs="*", default=[2019])
    args = parser.parse_args()
    reports = {}
    for year in args.years:
        log(f"{year}: computing PRE-observable stability battery")
        report = compute_metrics(year)
        reports[str(year)] = report
        write_json(STUDY_ROOT / str(year) / "COHORT_SIZE_STABILITY_PRE.json",
                   report)
        log(f"  {year}: stable_N_y={report.get('stable_N_y')}")
    if len(reports) > 1:
        stable_values = [r.get("stable_N_y") for r in reports.values()
                         if r.get("stable_N_y")]
        summary = {
            "years": sorted(reports),
            "stable_N_y": {year: r.get("stable_N_y")
                           for year, r in reports.items()},
            "N_star_max": max(stable_values) if stable_values else None,
            "rule": "N* = max_year(stable_N_y)",
            "status": "AWAITING_HUMAN_CONFIRMATION",
        }
        write_json(STUDY_ROOT / "COHORT_SIZE_FREEZE_RECOMMENDATION.json", summary)
        log(f"N* recommendation: {summary['N_star_max']} "
            f"(per-year {summary['stable_N_y']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
