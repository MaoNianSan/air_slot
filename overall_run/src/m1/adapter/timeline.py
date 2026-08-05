from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


FORMAL_HORIZONS_MINUTES = (0, 30, 60, 120, 180, 240, 300, 360, 420, 480)
FORMAL_DELAY_THRESHOLDS_MINUTES = (15, 30, 60)


def build_timeline(
    episode_anchor: object,
    *,
    roll_minutes: int = 5,
    maximum_minutes: int = 480,
    stop_time: object | None = None,
) -> tuple[pd.Timestamp, ...]:
    if roll_minutes <= 0 or maximum_minutes < 0:
        raise ValueError("M1_TIMELINE_CONFIGURATION_INVALID")
    anchor = pd.Timestamp(episode_anchor)
    anchor = anchor.tz_localize("UTC") if anchor.tzinfo is None else anchor.tz_convert("UTC")
    stop = None if stop_time is None else pd.Timestamp(stop_time)
    if stop is not None:
        stop = stop.tz_localize("UTC") if stop.tzinfo is None else stop.tz_convert("UTC")
    points = []
    for offset in range(0, maximum_minutes + 1, roll_minutes):
        query = anchor + pd.Timedelta(minutes=offset)
        if stop is not None and query > stop:
            break
        points.append(query)
    return tuple(points)


def deterministic_validation_split(
    episodes: pd.DataFrame,
    *,
    tail_fraction: float = 0.5,
    minimum_episodes: int = 2,
) -> dict[str, tuple[str, ...]]:
    if not 0 < tail_fraction < 1:
        raise ValueError("M1_CALIBRATION_SPLIT_INVALID")
    required = {"chain_episode_id", "episode_start_time", "split"}
    if not required.issubset(episodes.columns):
        raise ValueError("M1_CALIBRATION_SPLIT_UNAVAILABLE")
    validation = episodes[episodes["split"].astype(str).str.lower().eq("validation")].copy()
    validation["episode_start_time"] = pd.to_datetime(
        validation["episode_start_time"], utc=True, errors="coerce"
    )
    validation = validation.dropna(subset=["episode_start_time"]).sort_values(
        ["episode_start_time", "chain_episode_id"], kind="mergesort"
    )
    cut = int(round(len(validation) * (1.0 - tail_fraction)))
    if cut < minimum_episodes or len(validation) - cut < minimum_episodes:
        raise ValueError("M1_CALIBRATION_SPLIT_UNAVAILABLE")
    return {
        "validation_model": tuple(validation.iloc[:cut]["chain_episode_id"].astype(str)),
        "calibration": tuple(validation.iloc[cut:]["chain_episode_id"].astype(str)),
    }


def episode_partition_integrity(
    rows: pd.DataFrame,
    partition_column: str = "partition",
) -> bool:
    if rows.empty:
        return True
    return bool(
        rows.groupby("episode_id", observed=True)[partition_column].nunique().le(1).all()
    )
