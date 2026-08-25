"""DEPRECATED (2026-08-24): superseded by exp.common.metrics_v2 (2026-08-24); no live importer.
"""

from __future__ import annotations



def episode_normalized_mean(rows, metric: str) -> float:
    by_episode = {}
    for row in rows:
        by_episode.setdefault(row["episode_id"], []).append(float(row[metric]))
    if not by_episode:
        raise ValueError("NO_EPISODE_ROWS")
    return sum(sum(values) / len(values) for values in by_episode.values()) / len(by_episode)
