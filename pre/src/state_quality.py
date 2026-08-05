from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class StateWindowQuality:
    observation_age_minutes: float
    trajectory_coverage: float
    record_count: int
    quality_ok: bool


def coverage_status(
    coverage: pd.DataFrame, date: pd.Timestamp, hour: int
) -> str:
    if coverage.empty:
        return "SOURCE_COVERAGE_GAP"
    subset = coverage[
        (coverage["date"] == pd.Timestamp(date).normalize())
        & (coverage["hour"] == int(hour))
    ]
    return (
        str(subset.iloc[0]["coverage_status"])
        if not subset.empty
        else "SOURCE_COVERAGE_GAP"
    )


def evaluate_state_window(
    subset: pd.DataFrame, decision: pd.Timestamp, cfg: dict[str, Any]
) -> StateWindowQuality:
    latest = subset.iloc[-1]
    age = float((decision - latest["event_time"]).total_seconds() / 60.0)
    expected = max(
        1,
        int(
            float(cfg["state_vectors"]["lookback_minutes"])
            * 60
            / float(cfg["state_vectors"]["expected_interval_seconds"])
        )
        + 1,
    )
    interval = max(1, int(cfg["state_vectors"]["expected_interval_seconds"]))
    rounded = subset["event_time"].dt.floor(f"{interval}s").nunique()
    coverage = min(1.0, float(rounded / expected))
    quality = (
        len(subset) >= int(cfg["state_vectors"]["minimum_records"])
        and age
        <= float(cfg["state_vectors"]["maximum_observation_age_minutes"])
        and coverage
        >= float(cfg["state_vectors"]["minimum_trajectory_coverage"])
    )
    return StateWindowQuality(age, coverage, int(len(subset)), quality)


def finalize_snapshot_quality(
    snapshots: pd.DataFrame, cfg: dict[str, Any]
) -> pd.DataFrame:
    output = snapshots.copy()
    features = [
        column
        for column in cfg["schema"]["evidence_completeness_features"]
        if column in output.columns
    ]
    present = output[features].notna()
    output["evidence_completeness"] = present.mean(axis=1)
    output["observed_feature_count"] = present.sum(axis=1).astype(int)
    output["causally_interpolated_count"] = output["state_is_imputed"].fillna(
        False
    ).astype(int)
    output["calibration_imputed_count"] = output["weather_imputed"].fillna(
        False
    ).astype(int)
    output["structural_missing_count"] = 0
    output["temporal_missing_count"] = (~present).sum(axis=1).astype(int)

    primary_stages = set(cfg["snapshots"]["primary_stage_map"].values())
    balanced: dict[str, bool] = {}
    for episode_id, group in output[output["is_primary_snapshot"]].groupby(
        "episode_id"
    ):
        counts = group.groupby("snapshot_stage").size().to_dict()
        balanced[episode_id] = bool(
            all(counts.get(stage, 0) == 1 for stage in primary_stages)
            and group["snapshot_valid"].all()
            and group["split"].nunique() == 1
            and (group["airport"] == group["destination"]).all()
        )
    output["balanced_primary_cohort"] = (
        output["episode_id"].map(balanced).fillna(False).astype(bool)
    )
    return output
