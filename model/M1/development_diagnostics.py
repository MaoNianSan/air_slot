"""Development-only predictive diagnostics for frozen M1 V2 artifacts."""

from __future__ import annotations

from statistics import mean
from typing import Callable, Sequence

import torch

from .contracts import M1_V2_HAZARD_COORDINATE, V2_TARGETS
from .lifecycle import M1Lifecycle, M1TrainingExample


def target_coverage(examples: Sequence[M1TrainingExample]) -> dict[str, object]:
    """Count active and hurdle positive/zero labels without changing support."""
    result: dict[str, object] = {"examples": len(examples)}
    for name in V2_TARGETS:
        active = [
            row for row in examples
            if row.active.get(name) and row.targets.get(name) is not None
        ]
        result[f"active_{name}"] = len(active)
        if name in {"D_OB", "D_TX"}:
            positive = sum(float(row.targets[name]) > 0 for row in active)
            result[f"positive_{name}"] = positive
            result[f"zero_{name}"] = len(active) - positive
    return result


def require_training_target_coverage(coverage: dict[str, object]) -> None:
    for name in V2_TARGETS:
        if int(coverage[f"active_{name}"]) < 1:
            raise ValueError(f"M1_V2_FAST_TARGET_NO_ACTIVE_ROWS:{name}")
    for name in ("D_OB", "D_TX"):
        if int(coverage[f"positive_{name}"]) < 1:
            raise ValueError(f"M1_V2_FAST_TARGET_NO_POSITIVE_ROWS:{name}")
        if int(coverage[f"zero_{name}"]) < 1:
            raise ValueError(f"M1_V2_FAST_TARGET_NO_ZERO_ROWS:{name}")


def _finite_discrete_crps(values: list[float], probabilities: list[float], target: float) -> float:
    first = sum(probability * abs(value - target)
                for value, probability in zip(values, probabilities, strict=True))
    second = sum(
        left_probability * right_probability * abs(left_value - right_value)
        for left_value, left_probability in zip(values, probabilities, strict=True)
        for right_value, right_probability in zip(values, probabilities, strict=True)
    )
    return first - 0.5 * second


def _weighted_quantile(values: list[float], probabilities: list[float], level: float) -> float:
    cumulative = 0.0
    for value, probability in zip(values, probabilities, strict=True):
        cumulative += probability
        if cumulative >= level:
            return value
    return values[-1]


def _mean_or_none(values: list[float]) -> float | None:
    return None if not values else mean(values)


def _evaluate_distributions(
    examples: Sequence[M1TrainingExample],
    contracts,
    *,
    batch_size: int,
    predict: Callable,
) -> dict[str, object]:
    hazard = contracts[M1_V2_HAZARD_COORDINATE]
    representatives = [
        float(hazard.representative(index)[0])
        for index in range(hazard.finite_class_count)
    ]
    levels = {
        name: tuple(float(value) for value in contracts[name].quantile_levels)
        for name in ("D_OB", "D_TX")
    }
    errors: list[float] = []
    hazard_crps: list[float] = []
    brier: dict[str, list[float]] = {
        "T_IB_GT_30": [], "D_OB_ZERO": [], "D_TX_ZERO": [],
    }
    calibration_pairs: dict[str, list[tuple[float, float]]] = {
        key: [] for key in brier
    }
    coverage: dict[str, list[float]] = {
        M1_V2_HAZARD_COORDINATE: [], "D_OB": [], "D_TX": [],
    }
    nodes: list[dict[str, object]] = []

    for start in range(0, len(examples), batch_size):
        batch = list(examples[start:start + batch_size])
        values, lengths, _, static_values = M1Lifecycle._batch(
            batch, contracts,
        )
        distributions = predict(values, lengths, static_values)
        hazard_pmf = distributions["T_IB_A00"].detach().cpu()
        successor = {
            name: {
                "zero": distributions[name]["zero_probability"].detach().cpu(),
                "quantiles": distributions[name]["positive_quantiles_minutes"].detach().cpu(),
            }
            for name in ("D_OB", "D_TX")
        }
        for index, example in enumerate(batch):
            probabilities = [float(value) for value in hazard_pmf[index, :-1]]
            finite_mass = sum(probabilities)
            normalized = (
                [value / finite_mass for value in probabilities]
                if finite_mass > 0 else []
            )
            hazard_point = (
                sum(value * probability for value, probability in zip(
                    representatives, normalized, strict=True))
                if normalized else None
            )
            node = {
                "episode_id": example.episode_id,
                "decision_node_id": example.decision_node_id,
                "episode_date": example.episode_date.isoformat(),
                "active": dict(example.active),
                "targets": dict(example.targets),
                "predictions": {
                    "T_IB_A00_remaining_minutes_finite_support": hazard_point,
                    "T_IB_A00_finite_support_probability": finite_mass,
                },
            }
            target = example.targets.get(M1_V2_HAZARD_COORDINATE)
            if example.active.get(M1_V2_HAZARD_COORDINATE) and target is not None:
                target = float(target)
                probability_gt_30 = sum(
                    float(hazard_pmf[index, bin_index])
                    for bin_index in range(hazard.class_count)
                    if hazard.representative(bin_index)[0] > 30
                )
                outcome_gt_30 = float(target > 30)
                brier["T_IB_GT_30"].append((probability_gt_30 - outcome_gt_30) ** 2)
                calibration_pairs["T_IB_GT_30"].append((probability_gt_30, outcome_gt_30))
                if target < hazard.max_finite_minutes and normalized:
                    errors.append(abs(float(hazard_point) - target))
                    hazard_crps.append(_finite_discrete_crps(
                        representatives, normalized, target,
                    ))
                    lower = _weighted_quantile(representatives, normalized, 0.10)
                    upper = _weighted_quantile(representatives, normalized, 0.90)
                    coverage[M1_V2_HAZARD_COORDINATE].append(float(lower <= target <= upper))

            state_score = 0.0 if hazard_point is None else float(hazard_point)
            for name in ("D_OB", "D_TX"):
                zero_probability = float(successor[name]["zero"][index])
                quantiles = [float(value) for value in successor[name]["quantiles"][index]]
                median_index = min(
                    range(len(levels[name])),
                    key=lambda item: abs(levels[name][item] - 0.5),
                )
                point = 0.0 if zero_probability >= 0.5 else quantiles[median_index]
                node["predictions"][f"{name}_zero_probability"] = zero_probability
                node["predictions"][f"{name}_point_minutes"] = point
                state_score += point
                target = example.targets.get(name)
                if not example.active.get(name) or target is None:
                    continue
                target = float(target)
                zero_outcome = float(target == 0.0)
                key = f"{name}_ZERO"
                brier[key].append((zero_probability - zero_outcome) ** 2)
                calibration_pairs[key].append((zero_probability, zero_outcome))
                errors.append(abs(point - target))
                if target > 0:
                    coverage[name].append(float(quantiles[0] <= target <= quantiles[-1]))
            node["state_delay_point_minutes"] = state_score
            nodes.append(node)

    brier_by_event = {key: _mean_or_none(values) for key, values in brier.items()}
    calibration_by_event = {
        key: (
            None if not pairs else abs(
                mean(probability for probability, _ in pairs)
                - mean(outcome for _, outcome in pairs)
            )
        )
        for key, pairs in calibration_pairs.items()
    }
    coverage_by_target = {
        key: _mean_or_none(values) for key, values in coverage.items()
    }
    return {
        "node_count": len(nodes),
        "mae_minutes": _mean_or_none(errors),
        "crps_minutes": _mean_or_none(hazard_crps),
        "crps_scope": "T_IB_FINITE_SUPPORT_CONDITIONAL_ONLY",
        "brier": _mean_or_none([
            value for value in brier_by_event.values() if value is not None
        ]),
        "brier_by_event": brier_by_event,
        "calibration_absolute_gap": _mean_or_none([
            value for value in calibration_by_event.values() if value is not None
        ]),
        "calibration_by_event": calibration_by_event,
        "coverage": _mean_or_none([
            value for value in coverage_by_target.values() if value is not None
        ]),
        "coverage_by_target": coverage_by_target,
        "positive_quantile_status": "QUANTILE_CALIBRATION_NOT_APPLIED",
        "nodes": nodes,
    }


def evaluate_lifecycle(
    lifecycle: M1Lifecycle,
    examples: Sequence[M1TrainingExample],
    *,
    batch_size: int,
) -> dict[str, object]:
    lifecycle.pipeline.model.eval()

    def predict(values, lengths, static_values):
        with torch.no_grad():
            return lifecycle.pipeline.predict_distributions(
                values.to(lifecycle.device),
                lengths.to(lifecycle.device),
                static_features=(
                    None if static_values is None
                    else static_values.to(lifecycle.device)
                ),
            )

    return _evaluate_distributions(
        examples, lifecycle.pipeline.contracts,
        batch_size=batch_size, predict=predict,
    )


def evaluate_fast_predictor(predictor, examples, *, batch_size: int) -> dict[str, object]:
    return _evaluate_distributions(
        examples, predictor.contracts, batch_size=batch_size,
        predict=lambda values, lengths, static_values: predictor.predict_development(
            values, lengths, static_values,
        ),
    )


def paired_state_difference(reference: dict, comparison: dict) -> float | None:
    reference_values = {
        row["decision_node_id"]: float(row["state_delay_point_minutes"])
        for row in reference.get("nodes", ())
        if row.get("decision_node_id") is not None
    }
    differences = [
        abs(reference_values[row["decision_node_id"]]
            - float(row["state_delay_point_minutes"]))
        for row in comparison.get("nodes", ())
        if row.get("decision_node_id") in reference_values
    ]
    return _mean_or_none(differences)


__all__ = [
    "evaluate_fast_predictor", "evaluate_lifecycle", "paired_state_difference",
    "require_training_target_coverage", "target_coverage",
]
