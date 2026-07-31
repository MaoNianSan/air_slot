from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class HistoricalBaseline:
    """Frozen hierarchical empirical-quantile comparator."""

    quantiles: list[float]
    minimum_support: int
    tables: dict[str, dict[tuple[Any, ...], np.ndarray]] = field(default_factory=dict)
    global_quantiles: np.ndarray | None = None

    def fit(self, frame: pd.DataFrame, target: str = "target") -> "HistoricalBaseline":
        values = frame[target].to_numpy(float)
        self.global_quantiles = np.quantile(values, self.quantiles)
        specifications = {
            "airport_stage_time_bin": ["airport", "snapshot_stage", "time_bin"],
            "airport_stage": ["airport", "snapshot_stage"],
            "stage": ["snapshot_stage"],
        }
        for name, columns in specifications.items():
            if not all(column in frame.columns for column in columns):
                continue
            table: dict[tuple[Any, ...], np.ndarray] = {}
            for key, group in frame.groupby(columns, dropna=False):
                key = key if isinstance(key, tuple) else (key,)
                if len(group) >= self.minimum_support:
                    table[key] = np.quantile(
                        group[target].to_numpy(float), self.quantiles
                    )
            self.tables[name] = table
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        assert self.global_quantiles is not None
        result = np.tile(self.global_quantiles, (len(frame), 1)).astype(float)
        hierarchy = [
            ("airport_stage_time_bin", ["airport", "snapshot_stage", "time_bin"]),
            ("airport_stage", ["airport", "snapshot_stage"]),
            ("stage", ["snapshot_stage"]),
        ]
        unresolved = np.ones(len(frame), dtype=bool)
        for name, columns in hierarchy:
            table = self.tables.get(name, {})
            if not table or not all(column in frame.columns for column in columns):
                continue
            for index in np.flatnonzero(unresolved):
                key = tuple(frame.iloc[index][column] for column in columns)
                if key in table:
                    result[index] = table[key]
                    unresolved[index] = False
        return result
