"""Exact weighted forecast metrics (exp.shared.forecast_metrics).

Salvaged from tests/exp1/test_fast_primitives.py when the Exp1 driver package
was retired; only the pure-metric assertions are kept.
"""

from __future__ import annotations

import pytest

from exp.shared.forecast_metrics import (
    energy_score,
    marginal_variogram_score,
    variogram_score,
    weighted_crps,
    weighted_wasserstein_1,
)


def test_weighted_crps_and_wasserstein_exact_toy_values():
    assert weighted_crps((0.0, 2.0), (0.5, 0.5), 1.0) == 0.5
    assert weighted_wasserstein_1((0.0,), (1.0,), (2.0,), (1.0,)) == 2.0


def test_metric_inputs_fail_closed():
    with pytest.raises(ValueError, match="EXP1_VALUES_WEIGHTS_LENGTH_MISMATCH"):
        weighted_crps((0.0,), (0.5, 0.5), 1.0)
    with pytest.raises(ValueError, match="EXP1_METRIC_INPUT_NOT_FINITE"):
        weighted_crps((float("nan"),), (1.0,), 1.0)
    with pytest.raises(ValueError, match="EXP1_METRIC_WEIGHTS_MUST_SUM_POSITIVE"):
        weighted_crps((0.0,), (0.0,), 1.0)


def test_variogram_preserves_joint_dependence_with_exact_toy_values():
    values = ((0.0, 0.0), (1.0, 1.0))
    weights = (0.5, 0.5)
    observation = (0.0, 1.0)
    joint = variogram_score(values, weights, observation, p=0.5)
    marginal = marginal_variogram_score(
        ((0.0, 1.0), (0.0, 1.0)),
        ((0.5, 0.5), (0.5, 0.5)),
        observation,
        p=0.5,
    )
    assert joint == 1.0
    assert marginal == 0.25
    assert joint != marginal


def test_marginal_variogram_uses_product_expectation():
    score = marginal_variogram_score(
        ((0.0, 1.0), (1.0, 2.0), (2.0, 3.0)),
        ((0.5, 0.5), (0.5, 0.5), (0.5, 0.5)),
        (1.0, 2.0, 3.0),
    )
    assert score >= 0.0


def test_energy_score_is_zero_for_exact_fit():
    values = ((1.0, 2.0), (1.0, 2.0))
    assert energy_score(values, (0.5, 0.5), (1.0, 2.0)) == 0.0
