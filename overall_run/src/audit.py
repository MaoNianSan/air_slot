from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class AuditDecision:
    final_status: str
    checks: pd.DataFrame
    warnings: list[str]
    failures: list[str]


def build_scientific_gate(
    metrics: dict[str, Any],
    acceptance: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], str, list[str], list[str]]:
    """Build the authoritative machine-readable scientific acceptance result."""

    performance = acceptance["performance"]
    gate_cfg = acceptance["gates"]
    contract = acceptance.get("m1_acceptance_contract", {})
    specs = [
        ("coverage_90", metrics.get("coverage_90"), float(performance["coverage_90_lower"]), float(performance["coverage_90_upper"]), True, metrics.get("coverage_evidence", "metrics/m1_summary_evaluation.parquet")),
        ("outcome_selected_tail_coverage", metrics.get("tail_coverage_90"), float(gate_cfg["tail_coverage_90_lower"]["value"]), None, False, metrics.get("tail_evidence", "metrics/m1_predictions_evaluation.parquet")),
        ("projected_crossing_rate", metrics.get("quantile_crossing_rate"), None, float(contract.get("projected_crossing_rate", {}).get("required_value", gate_cfg["quantile_crossing_rate_max"]["value"])), True, metrics.get("crossing_evidence", "metrics/m1_predictions_evaluation.parquet")),
        ("pairwise_channel_corr", metrics.get("pairwise_channel_corr"), None, float(gate_cfg["pairwise_channel_corr"]["value"]), bool(gate_cfg["pairwise_channel_corr"]["required"]), metrics.get("m2_evidence", "metrics/m2_channel_correlation.parquet")),
        ("channel_dominance_share", metrics.get("channel_dominance_share"), None, float(gate_cfg["channel_dominance_share"]["value"]), bool(gate_cfg["channel_dominance_share"]["required"]), metrics.get("m2_evidence", "metrics/m2_channel_summary.parquet")),
        ("passenger_proxy_support", metrics.get("passenger_proxy_support"), float(gate_cfg["passenger_proxy_support_required"]["value"]), None, bool(gate_cfg["passenger_proxy_support_required"]["required"]), metrics.get("passenger_evidence", "metrics/m2_summary.parquet")),
        ("artifact_contract", metrics.get("artifact_contract"), True, True, bool(gate_cfg["artifact_contract_required"]["required"]), "artifact_registry.json"),
        ("config_contract", metrics.get("config_contract"), True, True, bool(gate_cfg["config_contract_required"]["required"]), "merged_config.json"),
    ]
    # Once D6 freezes a numeric definition, the same authority can evaluate it
    # without changing the model path.  Until then these remain unresolved.
    for metric_name in ("twcrps", "upper_quantile_calibration", "q95_pinball", "q99_pinball", "upper_shortfall"):
        definition = contract.get(metric_name, {})
        bounds = definition.get("accepted_range")
        if bounds is not None:
            specs.append((metric_name, metrics.get(metric_name), bounds.get("lower"), bounds.get("upper"), True, metrics.get(f"{metric_name}_evidence", "metrics/m1_summary_evaluation.parquet")))
    gates: dict[str, dict[str, Any]] = {}
    blocking: list[str] = []
    warnings: list[str] = []
    for name, value, lower, upper, required, evidence in specs:
        finite = isinstance(value, (bool, np.bool_)) or (
            isinstance(value, (int, float, np.integer, np.floating)) and np.isfinite(value)
        )
        if not finite:
            status = "UNRESOLVED"
            reason = "Metric is unavailable or non-finite."
        else:
            if isinstance(lower, bool):
                passed = bool(value) is lower
            else:
                passed = (lower is None or float(value) >= float(lower)) and (upper is None or float(value) <= float(upper))
            status = "PASS" if passed else "FAIL"
            reason = "Within configured acceptance bounds." if passed else "Outside configured acceptance bounds."
        gates[name] = {
            "value": value,
            "lower": lower,
            "upper": upper,
            "required": required,
            "status": status,
            "evidence_artifact": evidence,
            "reason": reason,
        }
        if status != "PASS":
            code = f"{name.upper()}_{status}"
            (blocking if required else warnings).append(code)
    proper_score_names = ("twcrps", "upper_quantile_calibration", "q95_pinball", "q99_pinball", "upper_shortfall")
    if contract and any("accepted_range" not in contract.get(name, {}) for name in proper_score_names):
        blocking.append("M1_V2_NUMERIC_THRESHOLDS_PENDING_D6")
    scientific_status = "PASS" if not blocking else "STOP_AND_REVIEW"
    return gates, scientific_status, blocking, warnings


def evaluate_precision_audit(summary: pd.DataFrame, acceptance: dict[str, Any]) -> AuditDecision:
    thresholds = acceptance["performance"]["precision"]
    checks = []
    failures = []
    warnings = []
    values = summary.set_index("metric")["estimate"].to_dict()
    directions = {
        "median_relative_score_error": "max",
        "p95_relative_score_error": "max",
        "top1_agreement": "min",
        "top3_overlap": "min",
        "median_kendall_tau": "min",
    }
    for metric, direction in directions.items():
        value = float(values[metric])
        threshold = float(thresholds[metric])
        passed = value <= threshold if direction == "max" else value >= threshold
        checks.append({"check": metric, "value": value, "criterion": f"{direction} {threshold}", "status": "PASS" if passed else "FAIL"})
        if not passed: failures.append(metric)
    status = "PRECISION_COMPLETED" if not failures else "MC_BUDGET_INSUFFICIENT"
    return AuditDecision(status, pd.DataFrame(checks), warnings, failures)
