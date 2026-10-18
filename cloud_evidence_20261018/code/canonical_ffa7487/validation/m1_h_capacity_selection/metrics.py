"""Predictive metrics for the M1 history-capacity selection experiment.

Only quantities supported by the frozen representation are computed:

- T_IB carries a discrete PMF over finite support, so finite-support CRPS and
  interval coverage at 50 / 80 / 90 percent are formally defined.
- D_OB / D_TX carry a logit hurdle (zero mass) plus a five-level positive
  quantile grid (0.1, 0.3, 0.5, 0.7, 0.9).  Cov50 uses [q30, q70] and Cov80
  uses [q10, q90]; the 90 percent interval would need q05/q95, which the frozen
  grid does not define, so Cov90 is reported as
  ``NOT_DEFINED_FROZEN_QUANTILE_GRID``.  Positive-quantile coverage follows the
  frozen convention of being evaluated on positive outcomes with the target
  active.
"""

from __future__ import annotations

from statistics import mean, median
from typing import Any, Iterable, Mapping, Sequence

import torch

from model.M1.contracts import M1_V2_HAZARD_COORDINATE
from model.M1.development_diagnostics import _finite_discrete_crps
from model.M1.lifecycle import M1Lifecycle

TARGET_HAZARD = M1_V2_HAZARD_COORDINATE
TARGETS: tuple[str, ...] = (TARGET_HAZARD, "D_OB", "D_TX")
COVERAGE_LEVELS: tuple[float, ...] = (0.5, 0.8, 0.9)
_NOT_DEFINED = "NOT_DEFINED_FROZEN_QUANTILE_GRID"
_HURDLE_BOUNDS = {0.5: (0.25, 0.75), 0.8: (0.10, 0.90), 0.9: (0.05, 0.95)}


def _weighted_quantile(
    values: Sequence[float], weights: Sequence[float], level: float
) -> float:
    cumulative = 0.0
    for value, weight in zip(values, weights, strict=True):
        cumulative += weight
        if cumulative >= level:
            return float(value)
    return float(values[-1])


def _interpolated_quantile(
    levels: Sequence[float], quantiles: Sequence[float], level: float
) -> float:
    if level <= levels[0]:
        return float(quantiles[0])
    if level >= levels[-1]:
        return float(quantiles[-1])
    for index in range(1, len(levels)):
        if level <= levels[index]:
            left, right = levels[index - 1], levels[index]
            span = right - left
            weight = 0.0 if span == 0 else (level - left) / span
            return float(
                quantiles[index - 1]
                + weight * (quantiles[index] - quantiles[index - 1])
            )
    return float(quantiles[-1])


def _percentile(values: Sequence[float], level: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("M1_CAPACITY_PERCENTILE_EMPTY")
    position = min(
        len(ordered) - 1, max(0, int(round(level * (len(ordered) - 1))))
    )
    return float(ordered[position])


def predict_nodes(
    lifecycle: M1Lifecycle,
    examples: Sequence[Any],
    metadata: Sequence[Mapping[str, Any]],
    *,
    batch_size: int = 64,
) -> list[dict[str, Any]]:
    """Calibrated per-node predictions plus frozen target labels."""

    contracts = lifecycle.pipeline.contracts
    hazard = contracts[TARGET_HAZARD]
    levels = {
        name: tuple(float(value) for value in contracts[name].quantile_levels)
        for name in ("D_OB", "D_TX")
    }
    representatives = [
        float(hazard.representative(index)[0])
        for index in range(hazard.finite_class_count)
    ]
    lifecycle.pipeline.model.eval()
    records: list[dict[str, Any]] = []
    with torch.no_grad():
        for start in range(0, len(examples), batch_size):
            batch = list(examples[start : start + batch_size])
            values, lengths, _, static_values = M1Lifecycle._batch(
                batch, contracts, device=lifecycle.device
            )
            distributions = lifecycle.pipeline.predict_distributions(
                values, lengths, static_features=static_values
            )
            hazard_pmf = distributions["T_IB_A00"].detach().cpu()
            successor = {
                name: {
                    "zero": distributions[name]["zero_probability"]
                    .detach()
                    .cpu(),
                    "quantiles": distributions[name][
                        "positive_quantiles_minutes"
                    ]
                    .detach()
                    .cpu(),
                }
                for name in ("D_OB", "D_TX")
            }
            for offset, example in enumerate(batch):
                index = start + offset
                probabilities = [
                    float(value)
                    for value in hazard_pmf[offset, : len(representatives)]
                ]
                finite_mass = sum(probabilities)
                normalized = (
                    [value / finite_mass for value in probabilities]
                    if finite_mass > 0
                    else []
                )
                record: dict[str, Any] = {
                    "episode_id": example.episode_id,
                    "decision_node_id": example.decision_node_id,
                    "operational_stage": metadata[index]["operational_stage"],
                    "lead_bins": {
                        name: metadata[index]["leads"][name]["lead_bin"]
                        for name in TARGETS
                    },
                    "lead_minutes": {
                        name: metadata[index]["leads"][name]["lead_minutes"]
                        for name in TARGETS
                    },
                    "active": dict(example.active),
                    "targets": dict(example.targets),
                    "hazard": {
                        "representatives": representatives,
                        "probabilities": normalized,
                    },
                    "successor": {},
                }
                for name in ("D_OB", "D_TX"):
                    record["successor"][name] = {
                        "zero_probability": float(successor[name]["zero"][offset]),
                        "quantiles": [
                            float(value)
                            for value in successor[name]["quantiles"][offset]
                        ],
                        "levels": list(levels[name]),
                    }
                records.append(record)
    return records


def point_prediction(record: Mapping[str, Any], target: str) -> float | None:
    if target == TARGET_HAZARD:
        probabilities = record["hazard"]["probabilities"]
        if not probabilities:
            return None
        return float(
            sum(
                value * weight
                for value, weight in zip(
                    record["hazard"]["representatives"],
                    probabilities,
                    strict=True,
                )
            )
        )
    successor = record["successor"][target]
    if successor["zero_probability"] >= 0.5:
        return 0.0
    levels = successor["levels"]
    median_index = min(
        range(len(levels)), key=lambda item: abs(levels[item] - 0.5)
    )
    return float(successor["quantiles"][median_index])


def active_pairs(
    records: Iterable[Mapping[str, Any]], target: str
) -> list[tuple[Mapping[str, Any], float]]:
    pairs = []
    for record in records:
        if not record["active"].get(target, False):
            continue
        value = record["targets"].get(target)
        if value is None:
            continue
        pairs.append((record, float(value)))
    return pairs


def point_metrics(
    records: Sequence[Mapping[str, Any]], target: str
) -> dict[str, Any]:
    pairs = active_pairs(records, target)
    errors = []
    for record, value in pairs:
        point = point_prediction(record, target)
        if point is None:
            continue
        errors.append(abs(point - value))
    if not errors:
        return {"n": 0, "mae": None, "median_ae": None, "p90_ae": None}
    return {
        "n": len(errors),
        "mae": float(mean(errors)),
        "median_ae": float(median(errors)),
        "p90_ae": _percentile(errors, 0.9),
    }


def _hazard_interval(
    record: Mapping[str, Any], level: float
) -> tuple[float, float] | None:
    probabilities = record["hazard"]["probabilities"]
    if not probabilities:
        return None
    representatives = record["hazard"]["representatives"]
    lower = _weighted_quantile(
        representatives, probabilities, 0.5 - level / 2.0
    )
    upper = _weighted_quantile(
        representatives, probabilities, 0.5 + level / 2.0
    )
    return lower, upper


def _hurdle_interval(
    record: Mapping[str, Any], target: str, level: float
) -> tuple[float, float] | None:
    successor = record["successor"][target]
    bounds = _HURDLE_BOUNDS[level]
    if (
        bounds[0] < successor["levels"][0]
        or bounds[1] > successor["levels"][-1]
    ):
        return None
    lower = _interpolated_quantile(
        successor["levels"], successor["quantiles"], bounds[0]
    )
    upper = _interpolated_quantile(
        successor["levels"], successor["quantiles"], bounds[1]
    )
    return lower, upper


def coverage_metrics(
    records: Sequence[Mapping[str, Any]], target: str
) -> dict[str, Any]:
    pairs = active_pairs(records, target)
    if target != TARGET_HAZARD:
        pairs = [(record, value) for record, value in pairs if value > 0.0]
    output: dict[str, Any] = {"n": len(pairs), "level_status": {}}
    for level in COVERAGE_LEVELS:
        label = int(round(level * 100))
        covered = []
        widths = []
        status = None
        for record, value in pairs:
            if target == TARGET_HAZARD:
                interval = _hazard_interval(record, level)
            else:
                interval = _hurdle_interval(record, target, level)
            if interval is None:
                status = _NOT_DEFINED
                continue
            covered.append(float(interval[0] <= value <= interval[1]))
            widths.append(float(interval[1] - interval[0]))
        output[f"Cov{label}"] = float(mean(covered)) if covered else None
        output[f"W{label}"] = float(mean(widths)) if widths else None
        if status is not None:
            output["level_status"][f"Cov{label}"] = status
    available = [
        abs(output[f"Cov{int(round(level * 100))}"] - level)
        for level in COVERAGE_LEVELS
        if output.get(f"Cov{int(round(level * 100))}") is not None
    ]
    for level in COVERAGE_LEVELS:
        label = int(round(level * 100))
        value = output.get(f"Cov{label}")
        output[f"ACE{label}"] = None if value is None else abs(value - level)
    output["mean_ace"] = float(mean(available)) if available else None
    return output


def crps_metrics(
    records: Sequence[Mapping[str, Any]], target: str
) -> dict[str, Any]:
    if target != TARGET_HAZARD:
        return {"n": 0, "crps": None, "status": "NOT_DEFINED_FROZEN_CONTRACT"}
    scores = []
    for record, value in active_pairs(records, target):
        probabilities = record["hazard"]["probabilities"]
        if not probabilities:
            continue
        scores.append(
            _finite_discrete_crps(
                record["hazard"]["representatives"], probabilities, value
            )
        )
    return {
        "n": len(scores),
        "crps": float(mean(scores)) if scores else None,
        "status": (
            "T_IB_FINITE_SUPPORT"
            if scores
            else "NO_ACTIVE_FINITE_SUPPORT_NODES"
        ),
    }


def zero_calibration(
    records: Sequence[Mapping[str, Any]], target: str
) -> dict[str, Any]:
    probabilities = []
    outcomes = []
    for record, value in active_pairs(records, target):
        probabilities.append(record["successor"][target]["zero_probability"])
        outcomes.append(float(value == 0.0))
    if not probabilities:
        return {"n": 0, "zero_probability_gap": None, "brier_zero": None}
    return {
        "n": len(probabilities),
        "zero_probability_gap": abs(mean(probabilities) - mean(outcomes)),
        "brier_zero": float(
            mean(
                (p - o) ** 2
                for p, o in zip(probabilities, outcomes, strict=True)
            )
        ),
    }
