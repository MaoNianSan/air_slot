from __future__ import annotations

from collections.abc import Callable

import pandas as pd


def stratified_metrics(
    frame: pd.DataFrame,
    dimensions: list[str],
    evaluator: Callable[[pd.DataFrame], dict[str, float]],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for dimension in dimensions:
        if dimension not in frame:
            continue
        for value, group in frame.groupby(dimension, observed=True, dropna=False):
            rows.append(
                {
                    "dimension": dimension,
                    "value": str(value),
                    "rows": len(group),
                    **evaluator(group),
                }
            )
    return pd.DataFrame(rows)
