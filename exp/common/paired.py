from __future__ import annotations

from collections import defaultdict


def paired_variant_rows(rows, *, baseline_variant: str):
    grouped = defaultdict(dict)
    for row in rows:
        grouped[(row["episode_id"], row.get("decision_node_id"))][row["variant"]] = row
    return tuple(
        {
            "episode_id": episode_id,
            "decision_node_id": node_id,
            "baseline_variant": baseline_variant,
            "baseline_metric": values[baseline_variant]["metric"],
            "variant_metrics": {name: item["metric"] for name, item in values.items()},
        }
        for (episode_id, node_id), values in grouped.items()
        if baseline_variant in values
    )
