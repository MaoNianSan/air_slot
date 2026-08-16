from __future__ import annotations

from collections import defaultdict


def sustained_warning_lead_time(rows, *, probability_key: str, threshold: float,
                                step_minutes: int = 5) -> float:
    ordered = sorted(rows, key=lambda row: float(row["lead_time_minutes"]), reverse=True)
    by_lead = {float(row["lead_time_minutes"]): float(row[probability_key]) for row in ordered}
    candidates = [lead for lead, probability in by_lead.items()
                  if probability >= threshold and by_lead.get(lead - step_minutes, -1.0) >= threshold]
    return max(candidates, default=0.0)


def decision_window_gain(rows, *, adaptive_key: str = "adaptive_probability",
                         fixed_key: str = "fixed_probability",
                         adaptive_threshold: float, fixed_threshold: float) -> dict:
    by_episode = defaultdict(list)
    for row in rows:
        if row.get("material_risk"):
            by_episode[row["episode_id"]].append(row)
    gains = []
    for episode_rows in by_episode.values():
        adaptive = sustained_warning_lead_time(
            episode_rows, probability_key=adaptive_key, threshold=adaptive_threshold)
        fixed = sustained_warning_lead_time(
            episode_rows, probability_key=fixed_key, threshold=fixed_threshold)
        gains.append(adaptive - fixed)
    if not gains:
        return {"DecisionWindowGain": None, "episode_denominator": 0}
    ordered = sorted(gains)
    return {
        "DecisionWindowGain": sum(gains) / len(gains),
        "median": ordered[len(ordered) // 2],
        "share_gt_0": sum(value > 0 for value in gains) / len(gains),
        "share_ge_15": sum(value >= 15 for value in gains) / len(gains),
        "share_ge_30": sum(value >= 30 for value in gains) / len(gains),
        "episode_denominator": len(gains),
    }


def warning_recall_at_fixed_fpr(rows, *, probability_key: str, threshold: float) -> dict[float, float]:
    by_lead = defaultdict(list)
    for row in rows:
        if row.get("material_risk"):
            by_lead[float(row["lead_time_minutes"])].append(float(row[probability_key]) >= threshold)
    return {lead: sum(values) / len(values) for lead, values in sorted(by_lead.items(), reverse=True)}


def episode_false_warning_rate(rows, *, probability_key: str, threshold: float) -> float | None:
    by_episode = defaultdict(list)
    for row in rows:
        if not row.get("material_risk"):
            by_episode[row["episode_id"]].append(float(row[probability_key]) >= threshold)
    if not by_episode:
        return None
    return sum(any(flags) for flags in by_episode.values()) / len(by_episode)
