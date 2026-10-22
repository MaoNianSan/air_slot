"""Exact weighted metrics used by the Exp1 protocol."""

from __future__ import annotations

from math import isfinite
from typing import Sequence


def _normalize(values: Sequence[float], weights: Sequence[float]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    if len(values) != len(weights) or len(values) == 0:
        raise ValueError("EXP1_VALUES_WEIGHTS_LENGTH_MISMATCH")
    xs = tuple(float(x) for x in values)
    ws = tuple(float(w) for w in weights)
    if any(not isfinite(x) for x in xs) or any(not isfinite(w) or w < 0 for w in ws):
        raise ValueError("EXP1_METRIC_INPUT_NOT_FINITE")
    total = sum(ws)
    if total <= 0:
        raise ValueError("EXP1_METRIC_WEIGHTS_MUST_SUM_POSITIVE")
    return xs, tuple(w / total for w in ws)


def weighted_crps(values: Sequence[float], weights: Sequence[float], observation: float) -> float:
    """CRPS for a weighted empirical predictive distribution."""
    xs, ws = _normalize(values, weights)
    y = float(observation)
    if not isfinite(y):
        raise ValueError("EXP1_OBSERVATION_NOT_FINITE")
    first = sum(w * abs(x - y) for x, w in zip(xs, ws))
    second = 0.5 * sum(
        wi * wj * abs(xi - xj)
        for xi, wi in zip(xs, ws)
        for xj, wj in zip(xs, ws)
    )
    return first - second


def weighted_wasserstein_1(
    values_a: Sequence[float],
    weights_a: Sequence[float],
    values_b: Sequence[float],
    weights_b: Sequence[float],
) -> float:
    """Exact W1 between two weighted empirical one-dimensional laws."""
    xa, wa = _normalize(values_a, weights_a)
    xb, wb = _normalize(values_b, weights_b)
    a = sorted(zip(xa, wa))
    b = sorted(zip(xb, wb))
    i = j = 0
    rem_a, rem_b = a[0][1], b[0][1]
    total = 0.0
    while i < len(a) and j < len(b):
        mass = min(rem_a, rem_b)
        total += mass * abs(a[i][0] - b[j][0])
        rem_a -= mass
        rem_b -= mass
        if rem_a <= 1e-15:
            i += 1
            if i < len(a):
                rem_a = a[i][1]
        if rem_b <= 1e-15:
            j += 1
            if j < len(b):
                rem_b = b[j][1]
    return total


def _joint_pair_expectation(
    values: Sequence[tuple[float, ...]],
    weights: Sequence[float],
    a: int,
    b: int,
    p: float,
) -> float:
    """Expectation over aligned Joint rows; dependence is preserved."""
    return sum(
        weight * abs(row[a] - row[b]) ** p
        for row, weight in zip(values, weights)
    )


def _independent_marginal_pair_expectation(
    values_a: Sequence[float],
    weights_a: Sequence[float],
    values_b: Sequence[float],
    weights_b: Sequence[float],
    p: float,
) -> float:
    """Exact expectation under the product of two empirical marginals."""
    return sum(
        wi * wj * abs(float(xi) - float(xj)) ** p
        for xi, wi in zip(values_a, weights_a)
        for xj, wj in zip(values_b, weights_b)
    )


def variogram_score(
    values: Sequence[tuple[float, ...]],
    weights: Sequence[float],
    observation: Sequence[float],
    *,
    p: float = 0.5,
    marginal_values: Sequence[Sequence[float]] | None = None,
    marginal_weights: Sequence[Sequence[float]] | None = None,
) -> float:
    """Variogram score, with optional exact product-of-marginals expectation.

    If ``marginal_values`` is supplied, pair expectations use independent
    marginal draws exactly; no random permutation is involved.
    """
    if p <= 0 or not isfinite(float(p)):
        raise ValueError("EXP1_VARIogram_P_INVALID")
    if not values:
        raise ValueError("EXP1_VARIogram_EMPTY_VALUES")
    if len(observation) != len(values[0]) or len(observation) < 2:
        raise ValueError("EXP1_VARIogram_DIMENSION_MISMATCH")
    xs, ws = _normalize([0.0] * len(values), weights)
    del xs
    y = tuple(float(v) for v in observation)
    if any(not isfinite(v) for v in y):
        raise ValueError("EXP1_OBSERVATION_NOT_FINITE")
    vectors = tuple(tuple(float(v) for v in row) for row in values)
    dimension = len(y)
    result = 0.0
    for a in range(dimension):
        for b in range(a + 1, dimension):
            observed = abs(y[a] - y[b]) ** p
            if marginal_values is None:
                expected = _joint_pair_expectation(vectors, ws, a, b, p)
            else:
                if marginal_weights is None or len(marginal_values) != dimension or len(marginal_weights) != dimension:
                    raise ValueError("EXP1_MARGINAL_ARGUMENTS_INVALID")
                _, wa = _normalize(marginal_values[a], marginal_weights[a])
                _, wb = _normalize(marginal_values[b], marginal_weights[b])
                expected = _independent_marginal_pair_expectation(
                    marginal_values[a],
                    wa,
                    marginal_values[b],
                    wb,
                    p,
                )
            result += (observed - expected) ** 2
    return result


def marginal_variogram_score(
    marginal_values: Sequence[Sequence[float]],
    marginal_weights: Sequence[Sequence[float]],
    observation: Sequence[float],
    *,
    p: float = 0.5,
) -> float:
    """Variogram score for product-of-marginals without Cartesian expansion."""
    if p <= 0 or not isfinite(float(p)):
        raise ValueError("EXP1_VARIogram_P_INVALID")
    if len(marginal_values) != len(observation) or len(observation) < 2:
        raise ValueError("EXP1_MARGINAL_VARIogram_DIMENSION_MISMATCH")
    if len(marginal_weights) != len(marginal_values):
        raise ValueError("EXP1_MARGINAL_ARGUMENTS_INVALID")
    normalized = [
        _normalize(values, weights)
        for values, weights in zip(marginal_values, marginal_weights)
    ]
    y = tuple(float(value) for value in observation)
    if any(not isfinite(value) for value in y):
        raise ValueError("EXP1_OBSERVATION_NOT_FINITE")
    result = 0.0
    for a in range(len(y)):
        for b in range(a + 1, len(y)):
            observed = abs(y[a] - y[b]) ** p
            expected = _independent_marginal_pair_expectation(
                normalized[a][0],
                normalized[a][1],
                normalized[b][0],
                normalized[b][1],
                p,
            )
            result += (observed - expected) ** 2
    return result


def energy_score(values: Sequence[tuple[float, ...]], weights: Sequence[float], observation: Sequence[float]) -> float:
    """Weighted empirical energy score for Appendix sensitivity."""
    vectors = tuple(tuple(float(v) for v in row) for row in values)
    _, ws = _normalize([0.0] * len(vectors), weights)
    y = tuple(float(v) for v in observation)
    first = sum(w * sum((a - b) ** 2 for a, b in zip(x, y)) ** 0.5 for x, w in zip(vectors, ws))
    second = 0.5 * sum(
        wi * wj * sum((a - b) ** 2 for a, b in zip(xi, xj)) ** 0.5
        for xi, wi in zip(vectors, ws)
        for xj, wj in zip(vectors, ws)
    )
    return first - second
