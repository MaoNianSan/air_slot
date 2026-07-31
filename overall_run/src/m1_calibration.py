from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression


def project_quantile_monotonicity(
    qmat: np.ndarray,
    quantiles: np.ndarray,
) -> np.ndarray:
    """Apply row-wise isotonic projection after residual calibration."""
    projected = np.empty_like(qmat, dtype=float)
    for index in range(len(qmat)):
        projected[index] = IsotonicRegression(
            increasing=True,
            out_of_bounds="clip",
        ).fit_transform(quantiles, qmat[index])
    return projected


monotone_quantiles = project_quantile_monotonicity


def apply_residual_calibration(
    raw_qmat: np.ndarray,
    frame: pd.DataFrame,
    offsets: dict[str, dict[Any, np.ndarray]],
    quantiles: np.ndarray,
) -> tuple[np.ndarray, list[str]]:
    """Apply airport-stage, stage, then global offsets before projection."""
    calibrated = np.asarray(raw_qmat, dtype=float).copy()
    levels: list[str] = []
    for index, row in frame.reset_index(drop=True).iterrows():
        airport_stage = (row.get("airport"), row.get("snapshot_stage"))
        stage = row.get("snapshot_stage")
        if airport_stage in offsets.get("airport_stage", {}):
            calibrated[index] += offsets["airport_stage"][airport_stage]
            levels.append("airport_stage")
        elif stage in offsets.get("stage", {}):
            calibrated[index] += offsets["stage"][stage]
            levels.append("stage")
        else:
            calibrated[index] += offsets["global"]["global"]
            levels.append("global")
    return project_quantile_monotonicity(calibrated, quantiles), levels


def fit_residual_calibration(
    validation: pd.DataFrame,
    residuals: np.ndarray,
    quantiles: list[float],
    minimum_support: int,
) -> dict[str, dict[Any, np.ndarray]]:
    """Fit the frozen residual-offset hierarchy on validation labels."""
    offsets: dict[str, dict[Any, np.ndarray]] = {
        "airport_stage": {},
        "stage": {},
        "global": {},
    }

    def residual_offsets(values: np.ndarray) -> np.ndarray:
        return np.asarray(
            [
                np.quantile(values[:, index], quantiles[index])
                for index in range(len(quantiles))
            ],
            dtype=float,
        )

    offsets["global"]["global"] = residual_offsets(residuals)
    positions = pd.Series(np.arange(len(validation)), index=validation.index)
    for key, row_indices in validation.groupby(["airport", "snapshot_stage"]).groups.items():
        if len(row_indices) >= minimum_support:
            selected = positions.loc[list(row_indices)].to_numpy(int)
            offsets["airport_stage"][key] = residual_offsets(residuals[selected])
    for key, row_indices in validation.groupby("snapshot_stage").groups.items():
        if len(row_indices) >= minimum_support:
            selected = positions.loc[list(row_indices)].to_numpy(int)
            offsets["stage"][key] = residual_offsets(residuals[selected])
    return offsets
