"""Pre-specified no-F_execution robustness."""

from __future__ import annotations

import numpy as np
import pandas as pd

from exp.shared.contracts import SupportedScore
from exp.shared.recovery_priority import (
    compute_domain_scores,
    compute_no_f_execution_priority,
)

from .metrics import priority_metrics
from .protocol import COMPONENTS


def no_f_execution_scores(frame: pd.DataFrame) -> pd.Series:
    values: list[float] = []
    for row in frame.to_dict("records"):
        components = {
            component: (
                SupportedScore(
                    value=float(row[f"Z_{component}"]), support="SUPPORTED"
                )
                if np.isfinite(row[f"Z_{component}"])
                else SupportedScore(
                    value=None,
                    support="UNSUPPORTED",
                    reason_codes=(f"{component}:INPUT_UNSUPPORTED",),
                )
            )
            for component in COMPONENTS
        }
        score = compute_no_f_execution_priority(
            components, compute_domain_scores(components)
        )
        values.append(float(score.value) if score.value is not None else np.nan)
    return pd.Series(values, index=frame.index, dtype=float)


def no_f_execution(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    result = frame.copy()
    result["score_C_no_execution"] = no_f_execution_scores(result)
    summary = priority_metrics(
        result["delay_to_mean"].tolist(),
        result["score_C_no_execution"].tolist(),
        result["decision_node_id"].astype(str).tolist(),
    )
    return result, summary
