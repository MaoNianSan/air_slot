from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from .contracts import COST_CHANNELS, SUBITEMS_M2_V2, ActionCatalogEntry


@dataclass
class M3Artifact:
    response_draw_ids: np.ndarray
    subitem_recovery_rates: Mapping[str, np.ndarray]
    implementation_costs_rmb: Mapping[str, np.ndarray]
    success_draws: Mapping[str, np.ndarray]
    response_intensities: Mapping[str, np.ndarray]
    action_catalog: Mapping[str, ActionCatalogEntry]
    footprint_table: pd.DataFrame
    response_parameter_table: pd.DataFrame
    cost_parameter_table: pd.DataFrame
    response_audit: pd.DataFrame
    version_metadata: Mapping[str, str]
    action_library_hash: str
    footprint_hash: str
    parameter_hash: str
    sample_hash: str
    artifact_hash: str
    m2_compatibility: Mapping[str, str]
    parameter_freeze_status: str
    formal_library_status: str
    test_only: bool

    @property
    def contract_version(self) -> str:
        return str(self.version_metadata["identity"])

    @property
    def n_draws(self) -> int:
        return int(len(self.response_draw_ids))

    def response_samples_frame(self) -> pd.DataFrame:
        rows: list[pd.DataFrame] = []
        footprint = self.footprint_table.set_index(["action_id", "subitem_id"])
        for action_id, catalog in self.action_catalog.items():
            recovery = np.asarray(self.subitem_recovery_rates[action_id], dtype=float)
            success = np.asarray(self.success_draws[action_id], dtype=bool)
            for index, subitem_id in enumerate(SUBITEMS_M2_V2):
                rows.append(pd.DataFrame({
                    "action_library_version": catalog.action_library_version,
                    "action_id": action_id,
                    "response_draw_id": self.response_draw_ids,
                    "subitem_id": subitem_id,
                    "footprint_role": footprint.loc[(action_id, subitem_id), "footprint_role"],
                    "subitem_recovery_rate": recovery[:, index],
                    "success_draw": success,
                    "response_intensity": self.response_intensities[action_id],
                }))
        return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

    def implementation_costs_frame(self) -> pd.DataFrame:
        rows = []
        for action_id, catalog in self.action_catalog.items():
            costs = np.asarray(self.implementation_costs_rmb[action_id], dtype=float)
            rows.append(pd.DataFrame({
                "action_library_version": catalog.action_library_version,
                "action_id": action_id,
                "response_draw_id": self.response_draw_ids,
                **{
                    f"implementation_cost_rmb_{channel}": costs[:, index]
                    for index, channel in enumerate(COST_CHANNELS)
                },
            }))
        return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
