from __future__ import annotations

import pandas as pd


def compare_rolling_rankings(episode_decisions: pd.DataFrame) -> pd.DataFrame:
    required = {"episode_id", "snapshot_id", "decision_time", "ranking_at_5"}
    missing = sorted(required - set(episode_decisions.columns))
    if missing:
        raise ValueError("M4_ROLLING_SCHEMA_MISSING:" + ",".join(missing))
    rows: list[dict[str, object]] = []
    for episode_id, group in episode_decisions.groupby("episode_id", sort=False):
        ordered = group.sort_values("decision_time", kind="mergesort")
        previous: list[str] | None = None
        previous_snapshot: str | None = None
        for item in ordered.itertuples(index=False):
            current = [str(value) for value in getattr(item, "ranking_at_5") if value is not None]
            if previous is not None:
                overlap = len(set(previous) & set(current))
                denominator = max(len(previous), len(current), 1)
                rows.append({
                    "episode_id": str(episode_id),
                    "previous_snapshot_id": previous_snapshot,
                    "snapshot_id": str(item.snapshot_id),
                    "exact_prefix_match": previous == current,
                    "overlap_rate": overlap / denominator,
                    "top1_changed": (previous[:1] != current[:1]),
                })
            previous = current
            previous_snapshot = str(item.snapshot_id)
    return pd.DataFrame(rows)
