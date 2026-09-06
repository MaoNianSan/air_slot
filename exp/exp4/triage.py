"""Frozen retrospective fixed-capacity screening primitives for Exp4."""

from __future__ import annotations

from math import ceil

import pandas as pd

ACTIVE_STAGES = ("PRE_IB", "POST_IB_PRE_OB", "POST_OB_PRE_TO")


def prepare_canonical_events(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = frame.copy()
    data["D"] = data["delay_to_mean_cs"].astype(float)
    data["S_F"] = data[["Z_F_continuity_cs", "Z_F_execution_cs", "Z_F_propagation_cs"]].mean(axis=1)
    data["S_P"] = data[["Z_P_time_cs", "Z_P_itinerary_cs", "Z_P_service_cs"]].mean(axis=1)
    data["S_R"] = data["Z_R_operating_cs"].astype(float)
    data["S_C"] = data[["S_F", "S_P", "S_R"]].mean(axis=1)
    data = data[data.operational_stage.isin(ACTIVE_STAGES)].copy()
    data = data.sort_values(["original_episode_id", "operational_stage", "decision_time", "decision_node_id"])
    canonical = data.groupby(["original_episode_id", "operational_stage"], as_index=False, sort=False).head(1).copy()
    canonical["canonical_event_status"] = "SUPPORTED"
    return canonical.reset_index(drop=True), data.reset_index(drop=True)


def screen(canonical: pd.DataFrame, q: float = 0.10) -> pd.DataFrame:
    rows = []
    for stage, group in canonical.groupby("operational_stage", sort=False):
        n = len(group)
        if not n:
            continue
        k = ceil(q * n)
        delay = set(group.nlargest(k, "D").decision_node_id)
        consequence = set(group.nlargest(k, "S_C").decision_node_id)
        overlap = len(delay & consequence)
        rows.append({"stage": stage, "q": q, "n": n, "k": k, "overlap": overlap, "slots_reassigned": k - overlap, "reassigned_rate": (k - overlap) / k})
    return pd.DataFrame(rows)
