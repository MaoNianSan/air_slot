from __future__ import annotations

import math

from exp.common.metrics_v2 import percentile


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


def predictive_metrics(predictions, targets, distributions=()):
    errors = [abs(float(left) - float(right)) for left, right in zip(predictions, targets)]
    return {
        "MAE_MINUTES": sum(errors) / len(errors) if errors else None,
        "CRPS": None if not distributions else sum(
            abs(float(sample) - float(target))
            for sample, target in zip(distributions, targets)
        ) / len(targets),
    }


def decision_validity_rates(rows):
    values = tuple(rows)
    if not values:
        return {key: None for key in (
            "FORMAL_RECOMMENDATION_AVAILABILITY", "EXECUTION_FEASIBLE_RATE",
            "STRUCTURAL_FEASIBLE_RATE", "FACTUAL_CONSISTENCY_RATE",
            "EVIDENCE_SUPPORTED_RATE", "DECISION_TIME_LEAKAGE_RATE",
        )}
    return {
        "FORMAL_RECOMMENDATION_AVAILABILITY": sum(bool(row.get("formal_available")) for row in values) / len(values),
        "EXECUTION_FEASIBLE_RATE": sum(bool(row.get("execution_feasible")) for row in values) / len(values),
        "STRUCTURAL_FEASIBLE_RATE": sum(bool(row.get("structural_feasible")) for row in values) / len(values),
        "FACTUAL_CONSISTENCY_RATE": sum(bool(row.get("factual_consistent")) for row in values) / len(values),
        "EVIDENCE_SUPPORTED_RATE": sum(bool(row.get("evidence_supported")) for row in values) / len(values),
        "DECISION_TIME_LEAKAGE_RATE": sum(bool(row.get("leakage")) for row in values) / len(values),
    }
