from __future__ import annotations


DEVELOPMENT_FROZEN_STRATA = (
    "disruption_severity",
    "turnaround_pressure",
    "airport_congestion",
    "information_completeness",
    "operational_stage",
)


def apply_frozen_strata(rows, *, strata: dict[str, dict]):
    """Apply development-frozen bins to principal outputs; never retrain."""
    output = []
    for row in rows:
        enriched = dict(row)
        labels = {}
        for name, definition in strata.items():
            value = row.get(name)
            labels[name] = definition.get("missing", "UNSUPPORTED") if value is None else definition.get("label", "UNBINNED")
        enriched["operational_strata"] = labels
        output.append(enriched)
    return tuple(output)
