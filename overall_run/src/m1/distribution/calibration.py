from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp


@dataclass(frozen=True)
class TemperatureParameters:
    values: dict[str, float]
    version: str
    model_version: str
    pre_manifest_hash: str
    fit_partition: str = "calibration"

    def __post_init__(self) -> None:
        if any(value <= 0 for value in self.values.values()):
            raise ValueError("M1_TEMPERATURE_NOT_POSITIVE")
        if not self.version or not self.model_version or not self.pre_manifest_hash:
            raise ValueError("M1_TEMPERATURE_IDENTITY_INCOMPLETE")
        if self.fit_partition != "calibration":
            raise ValueError("M1_TEMPERATURE_PARTITION_INVALID")


def apply_temperature(logits: np.ndarray, temperature: float) -> np.ndarray:
    if temperature <= 0:
        raise ValueError("M1_TEMPERATURE_NOT_POSITIVE")
    scaled = np.asarray(logits, dtype=float) / float(temperature)
    return np.exp(scaled - logsumexp(scaled, axis=-1, keepdims=True))


def fit_temperature(logits: np.ndarray, targets: np.ndarray) -> float:
    raw = np.asarray(logits, dtype=float)
    labels = np.asarray(targets, dtype=float)
    if raw.shape != labels.shape or raw.ndim != 2:
        raise ValueError("M1_TEMPERATURE_SHAPE_INVALID")

    def objective(log_temperature: float) -> float:
        temperature = float(np.exp(log_temperature))
        probabilities = apply_temperature(raw, temperature)
        return float(-(labels * np.log(np.clip(probabilities, 1e-12, 1.0))).sum(axis=1).mean())

    result = minimize_scalar(objective, bounds=(-4.0, 4.0), method="bounded")
    if not result.success:
        raise RuntimeError("M1_TEMPERATURE_FIT_FAILED")
    return float(np.exp(result.x))
