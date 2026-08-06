from __future__ import annotations


def apply_constructed_unit_correction(
    structural_units: float,
    *,
    enabled: bool = False,
    correction_units: float = 0.0,
    channel_labels_available: bool = False,
) -> float:
    if enabled and not channel_labels_available:
        raise ValueError("M2_LEARNED_CORRECTION_LABELS_MISSING")
    if not enabled:
        return max(float(structural_units), 0.0)
    return max(float(structural_units) + float(correction_units), 0.0)
