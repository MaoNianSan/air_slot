from __future__ import annotations

import math


def top1_agreement(reference_rankings, sensitivity_rankings) -> float | None:
    pairs = [(left, right) for left, right in zip(reference_rankings, sensitivity_rankings)
             if left and right]
    return None if not pairs else sum(left[0] == right[0] for left, right in pairs) / len(pairs)


def ranking_at_3_overlap(reference, sensitivity) -> float | None:
    if len(reference) < 3 or len(sensitivity) < 3:
        return None
    return len(set(reference[:3]) & set(sensitivity[:3])) / 3.0


def risk_sensitive_episode_rate(reference_rankings, sensitivity_rankings) -> float | None:
    pairs = list(zip(reference_rankings, sensitivity_rankings))
    return None if not pairs else sum(left != right for left, right in pairs) / len(pairs)


def latency_percentiles(rows, key: str) -> dict[str, float | None]:
    values = sorted(float(row[key]) for row in rows if row.get(key) is not None)
    if not values:
        return {"p50": None, "p95": None, "p99": None}
    def percentile(q):
        index = min(len(values) - 1, max(0, math.ceil(q * len(values)) - 1))
        return values[index]
    return {"p50": percentile(.50), "p95": percentile(.95), "p99": percentile(.99)}


def deployment_gate(rows) -> dict:
    stats = latency_percentiles(rows, "E2E_latency")
    return {**stats, "gate_seconds": 300,
            "scientific_runtime_gate": "PASS" if stats["p95"] is not None and stats["p95"] < 300 else "FAIL"}
