"""Canonical node priorities built from model-produced component CUs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from exp.shared.contracts import SupportedScore
from exp.shared.recovery_priority import (
    compute_aggregate_priority,
    compute_domain_scores,
)

from .metrics import midrank_percentiles, priority_metrics
from .protocol import (
    ACTIVE_STAGES,
    COMPONENTS,
    FLIGHT_COMPONENTS,
    MATERIAL_RANK_GAP,
    PASSENGER_COMPONENTS,
    TOP_FRACTION_PRIMARY,
)


def add_domain_scores(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    required = [f"Z_{component}" for component in COMPONENTS]
    missing = [column for column in required if column not in result]
    if missing:
        raise ValueError(f"EXP2_PRIORITY_COMPONENT_COLUMNS_MISSING:{missing}")

    def shared_scores(row: pd.Series) -> pd.Series:
        components = {}
        for component in COMPONENTS:
            value = row[f"Z_{component}"]
            components[component] = (
                SupportedScore(value=float(value), support="SUPPORTED")
                if np.isfinite(value)
                else SupportedScore(
                    value=None,
                    support="UNSUPPORTED",
                    reason_codes=(f"{component}:EXP2_INPUT_UNSUPPORTED",),
                )
            )
        domains = compute_domain_scores(components)
        aggregate = compute_aggregate_priority(domains)
        return pd.Series(
            {
                "score_F": domains["score_F"].value,
                "score_P": domains["score_P"].value,
                "score_R": domains["score_R"].value,
                "score_C": aggregate.value,
            }
        )

    result[["score_F", "score_P", "score_R", "score_C"]] = result.apply(
        shared_scores, axis=1
    )
    result["aggregate_complete"] = result[required].apply(
        lambda row: bool(np.isfinite(row.to_numpy(dtype=float)).all()), axis=1
    )
    return result


def base_sample(
    frame: pd.DataFrame, support_column: str = "inherited_support_primary"
) -> pd.DataFrame:
    required = {
        "decision_node_id",
        "episode_id",
        "operational_stage",
        "delay_to_mean",
        "score_C",
        "aggregate_complete",
        support_column,
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"EXP2_BASE_COLUMNS_MISSING:{missing}")
    mask = (
        frame["operational_stage"].isin(ACTIVE_STAGES)
        & frame[support_column].eq(True)
        & frame["aggregate_complete"].eq(True)
        & np.isfinite(frame["delay_to_mean"].astype(float))
        & np.isfinite(frame["score_C"].astype(float))
    )
    result = frame.loc[mask].copy().reset_index(drop=True)
    if (result["operational_stage"] == "COMPLETED").any():
        raise ValueError("EXP2_COMPLETED_NODE_IN_BASE")
    return result


def rank_base_sample(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["delay_rank_pct"] = midrank_percentiles(
        result["delay_to_mean"].to_numpy(dtype=float)
    )
    result["consequence_rank_pct"] = midrank_percentiles(
        result["score_C"].to_numpy(dtype=float)
    )
    result["rank_displacement"] = np.abs(
        result["consequence_rank_pct"] - result["delay_rank_pct"]
    )
    result["signed_displacement"] = (
        result["consequence_rank_pct"] - result["delay_rank_pct"]
    )
    return result


def summarize_priority(frame: pd.DataFrame) -> dict[str, float | int | None]:
    return priority_metrics(
        frame["delay_to_mean"].tolist(),
        frame["score_C"].tolist(),
        frame["decision_node_id"].astype(str).tolist(),
        top_fraction=TOP_FRACTION_PRIMARY,
        material_gap=MATERIAL_RANK_GAP,
    )
