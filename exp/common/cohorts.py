from __future__ import annotations

from collections import defaultdict


def episode_normalized_rows(rows):
    """Attach 1/N_i weights to repeated decision nodes within each episode."""
    counts = defaultdict(int)
    for row in rows:
        counts[row["episode_id"]] += 1
    return tuple({**row, "episode_weight": 1.0 / counts[row["episode_id"]]} for row in rows)


def cohort_hash(rows, content_id):
    return content_id(tuple(sorted((row["episode_id"], row.get("decision_node_id")) for row in rows)))
