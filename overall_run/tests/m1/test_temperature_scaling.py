from __future__ import annotations

import numpy as np
import pytest

from overall_run.src.m1.distribution import (
    TemperatureParameters,
    apply_temperature,
    fit_temperature,
)


def test_temperature_is_positive_and_probabilities_normalize() -> None:
    logits = np.array([[4.0, 1.0], [1.0, 4.0], [2.0, 0.0]])
    targets = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]])
    temperature = fit_temperature(logits, targets)
    assert temperature > 0
    probabilities = apply_temperature(logits, temperature)
    np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)
    parameters = TemperatureParameters(
        {"R_IB": temperature},
        version="temperature-1",
        model_version="model-1",
        pre_manifest_hash="a" * 64,
    )
    assert parameters.fit_partition == "calibration"


def test_nonpositive_temperature_is_rejected() -> None:
    with pytest.raises(ValueError, match="M1_TEMPERATURE_NOT_POSITIVE"):
        apply_temperature(np.zeros((1, 2)), 0.0)
