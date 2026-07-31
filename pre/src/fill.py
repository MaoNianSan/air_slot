from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


FILL_COLUMNS = ["latitude", "longitude", "altitude", "velocity", "vertical_rate", "heading"]


def apply_fill(observations: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Apply optional past-only filling to existing observation rows.

    The default is a no-op. This function never fills source-level coverage gaps and
    never creates observations outside an existing readable source file.
    """
    result = observations.copy()
    fill_cfg = cfg["state_vectors"].get("fill", {})
    enabled = bool(fill_cfg.get("enabled", False))
    method = str(fill_cfg.get("method", "none")).lower()
    max_gap = float(fill_cfg.get("max_gap_minutes", 5))

    result["state_is_imputed"] = False
    result["state_imputation_method"] = "none"
    result["state_imputation_gap_minutes"] = np.nan

    if not enabled or method == "none" or result.empty:
        return result
    if method not in {"forward_fill", "past_trend"}:
        raise ValueError(f"unsupported fill method: {method}")

    result = result.sort_values(["icao24", "event_time"]).reset_index(drop=True)
    for _, idx in result.groupby("icao24", sort=False).groups.items():
        group = result.loc[idx].copy()
        gaps = group["event_time"].diff().dt.total_seconds().div(60)
        eligible = gaps.le(max_gap) & gaps.notna()
        before = group[FILL_COLUMNS].isna()

        if method == "forward_fill":
            filled = group[FILL_COLUMNS].ffill()
        else:
            filled = group[FILL_COLUMNS].copy()
            for column in FILL_COLUMNS:
                values = pd.to_numeric(group[column], errors="coerce")
                previous = values.shift(1)
                previous2 = values.shift(2)
                delta_minutes = group["event_time"].diff().dt.total_seconds().div(60)
                previous_delta = group["event_time"].shift(1).sub(group["event_time"].shift(2)).dt.total_seconds().div(60)
                slope = (previous - previous2) / previous_delta.replace(0, np.nan)
                estimate = previous + slope * delta_minutes
                filled[column] = values.where(values.notna(), estimate)
                filled[column] = filled[column].where(filled[column].notna(), previous)

        after = filled.isna()
        changed = before & ~after
        changed_rows = changed.any(axis=1) & eligible
        for column in FILL_COLUMNS:
            mask = changed[column] & eligible
            group.loc[mask, column] = filled.loc[mask, column]
        group.loc[changed_rows, "state_is_imputed"] = True
        group.loc[changed_rows, "state_imputation_method"] = method
        group.loc[changed_rows, "state_imputation_gap_minutes"] = gaps.loc[changed_rows]
        result.loc[idx] = group

    return result
