from __future__ import annotations

import numpy as np

from .contracts import M4ContractError, M4RiskConfig


def validate_risk_config(config: M4RiskConfig) -> None:
    if config.expected_weight < 0.0 or config.cvar_weight < 0.0:
        raise M4ContractError("M4_RISK_WEIGHT_NEGATIVE")
    if not np.isclose(config.expected_weight + config.cvar_weight, 1.0):
        raise M4ContractError("M4_RISK_WEIGHTS_MUST_SUM_TO_ONE")
    if not 0.0 < config.cvar_alpha < 1.0:
        raise M4ContractError("M4_CVAR_ALPHA_INVALID")


def normalize_weights(weights: np.ndarray) -> np.ndarray:
    values = np.asarray(weights, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all() or np.any(values < 0.0):
        raise M4ContractError("M4_SAMPLE_WEIGHTS_INVALID")
    total = float(values.sum())
    if total <= 0.0:
        raise M4ContractError("M4_SAMPLE_WEIGHT_SUM_NONPOSITIVE")
    return values / total


def _values_and_weights(values: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    sample_values = np.asarray(values, dtype=float)
    normalized = normalize_weights(weights)
    if sample_values.ndim != 1 or sample_values.shape != normalized.shape:
        raise M4ContractError("M4_WEIGHTED_RISK_SHAPE_MISMATCH")
    if not np.isfinite(sample_values).all():
        raise M4ContractError("M4_WEIGHTED_RISK_VALUE_NONFINITE")
    return sample_values, normalized


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    sample_values, normalized = _values_and_weights(values, weights)
    return float(np.dot(sample_values, normalized))


def weighted_var(values: np.ndarray, weights: np.ndarray, alpha: float) -> float:
    if not 0.0 < alpha < 1.0:
        raise M4ContractError("M4_WEIGHTED_VAR_ALPHA_INVALID")
    sample_values, normalized = _values_and_weights(values, weights)
    order = np.argsort(sample_values, kind="mergesort")
    ordered_values = sample_values[order]
    cumulative = np.cumsum(normalized[order])
    index = min(int(np.searchsorted(cumulative, alpha, side="left")), len(ordered_values) - 1)
    return float(ordered_values[index])


def weighted_cvar(values: np.ndarray, weights: np.ndarray, alpha: float) -> float:
    if not 0.0 < alpha < 1.0:
        raise M4ContractError("M4_WEIGHTED_CVAR_ALPHA_INVALID")
    sample_values, normalized = _values_and_weights(values, weights)
    order = np.argsort(sample_values, kind="mergesort")[::-1]
    remaining = 1.0 - alpha
    numerator = 0.0
    for index in order:
        if remaining <= 1e-15:
            break
        take = min(float(normalized[index]), remaining)
        numerator += take * float(sample_values[index])
        remaining -= take
    if remaining > 1e-12:
        raise M4ContractError("M4_WEIGHTED_CVAR_TAIL_MASS_FAILURE")
    return numerator / (1.0 - alpha)


def risk_score(values: np.ndarray, weights: np.ndarray, config: M4RiskConfig) -> tuple[float, float, float]:
    validate_risk_config(config)
    expected = weighted_mean(values, weights)
    cvar = weighted_cvar(values, weights, config.cvar_alpha)
    score = config.expected_weight * expected + config.cvar_weight * cvar
    return float(score), expected, cvar


def weighted_positive_probability(values: np.ndarray, weights: np.ndarray) -> float:
    sample_values, normalized = _values_and_weights(values, weights)
    return float(normalized[sample_values > 0.0].sum())
