"""Pre-specified no-F_execution robustness."""

from __future__ import annotations

import pandas as pd

from .metrics import priority_metrics


def no_f_execution(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    result = frame.copy()
    result["score_F_no_execution"] = result[["Z_F_continuity", "Z_F_propagation"]].mean(
        axis=1, skipna=False
    )
    result["score_C_no_execution"] = result[
        ["score_F_no_execution", "score_P", "score_R"]
    ].mean(axis=1, skipna=False)
    summary = priority_metrics(
        result["delay_to_mean"].tolist(),
        result["score_C_no_execution"].tolist(),
        result["decision_node_id"].astype(str).tolist(),
    )
    return result, summary
