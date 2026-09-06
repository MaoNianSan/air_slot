"""Same-stage, different-episode similar-delay comparisons."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .protocol import COMPONENTS, MATERIAL_RANK_GAP


def build_similar_delay_pairs(frame: pd.DataFrame, *, caliper: float) -> pd.DataFrame:
    required = {
        "episode_id",
        "decision_node_id",
        "operational_stage",
        "delay_to_mean",
        "consequence_rank_pct",
        *(f"Z_{component}" for component in COMPONENTS),
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"EXP2_PAIR_COLUMNS_MISSING:{missing}")
    working = frame.copy()
    if "original_episode_id" not in working:
        working["original_episode_id"] = working["episode_id"].astype(str)
    if "bootstrap_instance_id" not in working:
        working["bootstrap_instance_id"] = working["episode_id"].astype(str)
    rows: list[dict[str, object]] = []
    for stage, group in working.groupby("operational_stage", sort=True):
        ordered = group.sort_values(
            ["delay_to_mean", "decision_node_id"], kind="stable"
        ).reset_index(drop=True)
        delays = ordered["delay_to_mean"].to_numpy(dtype=float)
        for left_index in range(len(ordered)):
            right_index = left_index + 1
            while (
                right_index < len(ordered)
                and delays[right_index] - delays[left_index] <= caliper
            ):
                left = ordered.iloc[left_index]
                right = ordered.iloc[right_index]
                if str(left["original_episode_id"]) != str(
                    right["original_episode_id"]
                ):
                    left_key = (
                        str(left["bootstrap_instance_id"]),
                        str(left["decision_node_id"]),
                    )
                    right_key = (
                        str(right["bootstrap_instance_id"]),
                        str(right["decision_node_id"]),
                    )
                    if right_key < left_key:
                        left, right = right, left
                    row = {
                        "node_a": str(left["decision_node_id"]),
                        "node_b": str(right["decision_node_id"]),
                        "episode_a": str(left["bootstrap_instance_id"]),
                        "episode_b": str(right["bootstrap_instance_id"]),
                        "original_episode_a": str(left["original_episode_id"]),
                        "original_episode_b": str(right["original_episode_id"]),
                        "operational_stage": stage,
                        "abs_delay_gap": abs(
                            float(left["delay_to_mean"]) - float(right["delay_to_mean"])
                        ),
                        "abs_consequence_rank_gap": abs(
                            float(left["consequence_rank_pct"])
                            - float(right["consequence_rank_pct"])
                        ),
                    }
                    for component in COMPONENTS:
                        row[f"abs_Z_{component}"] = abs(
                            float(left[f"Z_{component}"])
                            - float(right[f"Z_{component}"])
                        )
                    rows.append(row)
                right_index += 1
    columns = [
        "node_a",
        "node_b",
        "episode_a",
        "episode_b",
        "original_episode_a",
        "original_episode_b",
        "operational_stage",
        "abs_delay_gap",
        "abs_consequence_rank_gap",
        *(f"abs_Z_{component}" for component in COMPONENTS),
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame(rows)
        .drop_duplicates(["episode_a", "node_a", "episode_b", "node_b"])
        .reset_index(drop=True)
    )


def aggregate_episode_pairs(pairs: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "abs_consequence_rank_gap",
        *(f"abs_Z_{component}" for component in COMPONENTS),
    ]
    if pairs.empty:
        return pd.DataFrame(
            columns=["episode_a", "episode_b", "qualifying_node_pair_count", *columns]
        )
    grouped = pairs.groupby(["episode_a", "episode_b"], as_index=False, sort=True)
    medians = grouped[columns].median()
    counts = grouped.size().rename(columns={"size": "qualifying_node_pair_count"})
    return medians.merge(counts, on=["episode_a", "episode_b"], validate="one_to_one")


def summarize_episode_pairs(frame: pd.DataFrame) -> dict[str, float | int | None]:
    if frame.empty:
        return {
            "support_status": "ABSTAIN_NO_SIMILAR_DELAY_EPISODE_PAIRS",
            "unique_episode_pairs": 0,
        }
    result: dict[str, float | int | None] = {
        "support_status": "SUPPORTED",
        "unique_episode_pairs": int(len(frame)),
        "median_priority_separation": float(
            np.median(frame["abs_consequence_rank_gap"])
        ),
        "share_priority_separation_ge_030": float(
            np.mean(frame["abs_consequence_rank_gap"] >= MATERIAL_RANK_GAP)
        ),
    }
    for component in COMPONENTS:
        result[f"median_component_gap_{component}"] = float(
            np.median(frame[f"abs_Z_{component}"])
        )
    return result
