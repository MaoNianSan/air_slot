from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CorrectionResult:
    corrected_units: float
    applied_correction_units: float
    correction_bound: float
    rho_g: float
    epsilon: float
    correction_bound_status: str


def apply_constructed_unit_correction(
    structural_units: float,
    *,
    enabled: bool = False,
    correction_units: float = 0.0,
    channel_labels_available: bool = False,
    rho_g: float | None = None,
    epsilon: float | None = None,
) -> CorrectionResult:
    structural = float(structural_units)
    if not math.isfinite(structural) or structural < 0.0:
        raise ValueError("M2_STRUCTURAL_UNITS_INVALID")
    if not enabled:
        return CorrectionResult(
            corrected_units=structural,
            applied_correction_units=0.0,
            correction_bound=0.0,
            rho_g=0.0 if rho_g is None else float(rho_g),
            epsilon=0.0 if epsilon is None else float(epsilon),
            correction_bound_status="DISABLED",
        )
    if not channel_labels_available:
        raise ValueError("M2_LEARNED_CORRECTION_LABELS_MISSING")
    if rho_g is None or epsilon is None:
        raise ValueError("M2_CORRECTION_BOUND_NOT_CONFIGURED")
    rho = float(rho_g)
    eps = float(epsilon)
    correction = float(correction_units)
    if not all(math.isfinite(value) for value in (rho, eps, correction)):
        raise ValueError("M2_CORRECTION_BOUND_INVALID")
    if not 0.0 <= rho <= 1.0 or eps < 0.0:
        raise ValueError("M2_CORRECTION_BOUND_INVALID")
    bound = rho * max(structural, eps)
    if abs(correction) > bound + 1e-12:
        raise ValueError("M2_LEARNED_CORRECTION_BOUND_EXCEEDED")
    return CorrectionResult(
        corrected_units=max(structural + correction, 0.0),
        applied_correction_units=correction,
        correction_bound=bound,
        rho_g=rho,
        epsilon=eps,
        correction_bound_status="PASS",
    )
