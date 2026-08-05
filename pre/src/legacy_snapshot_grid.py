from __future__ import annotations

from typing import Any

import pandas as pd


def _time_bin(value: pd.Timestamp) -> str:
    hour = int(value.hour)
    return "00_06" if hour < 6 else "06_12" if hour < 12 else "12_18" if hour < 18 else "18_24"


def build_snapshot_grid(
    episodes: pd.DataFrame, legs: pd.DataFrame, cfg: dict[str, Any]
) -> pd.DataFrame:
    attributes = legs[
        ["episode_id", "aircraft_group", "aircraft_type_unknown"]
    ].drop_duplicates("episode_id")
    rows: list[dict[str, Any]] = []
    ratios = [float(value) for value in cfg["snapshots"]["ratios"]]
    stage_map = cfg["snapshots"]["dense_stage_map"]
    primary_stages = set(cfg["snapshots"]["primary_stage_map"].values())
    for episode in episodes.itertuples(index=False):
        if not bool(episode.episode_valid):
            continue
        for ratio in ratios:
            stage = stage_map[f"{ratio:.1f}"]
            elapsed = ratio * float(episode.reference_movement_time)
            decision = episode.firstseen_utc + pd.to_timedelta(elapsed, unit="m")
            valid = bool(episode.lastseen_utc > decision)
            rows.append(
                {
                    "episode_id": episode.episode_id,
                    "snapshot_id": f"{episode.episode_id}__{stage}",
                    "snapshot_stage": stage,
                    "snapshot_ratio": ratio,
                    "elapsed_ratio": ratio,
                    "is_primary_snapshot": stage in primary_stages,
                    "decision_time_utc": decision,
                    "elapsed_minutes": elapsed,
                    "split": episode.split,
                    "airport": episode.airport,
                    "origin": episode.origin,
                    "destination": episode.destination,
                    "month": int(episode.firstseen_utc.month),
                    "decision_month": int(decision.month),
                    "period": str(decision.tz_localize(None).to_period("M")),
                    "time_bin": _time_bin(decision),
                    "firstseen_time_bin": _time_bin(episode.firstseen_utc),
                    "icao24": episode.icao24,
                    "reference_movement_time": episode.reference_movement_time,
                    "firstseen_utc": episode.firstseen_utc,
                    "lastseen_utc": episode.lastseen_utc,
                    "snapshot_valid": valid,
                    "snapshot_exclusion_reason": (
                        "" if valid else "FLIGHT_COMPLETED_BEFORE_SNAPSHOT"
                    ),
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.merge(attributes, on="episode_id", how="left", validate="many_to_one")


def derive_state_requests(
    snapshots: pd.DataFrame, cfg: dict[str, Any]
) -> pd.DataFrame:
    """Materialize the minimal state-vector windows required by legacy snapshots."""
    columns = ["episode_id", "snapshot_id", "icao24", "decision_time_utc"]
    frame = snapshots.loc[
        snapshots["snapshot_valid"].fillna(False), columns
    ].copy()
    lookback = pd.to_timedelta(
        float(cfg["state_vectors"]["lookback_minutes"]), unit="m"
    )
    frame["request_start"] = frame["decision_time_utc"] - lookback
    frame["request_end"] = frame["decision_time_utc"]
    frame["date"] = (
        frame["decision_time_utc"]
        .dt.tz_convert("UTC")
        .dt.normalize()
        .dt.tz_localize(None)
    )
    frame["hour"] = frame["decision_time_utc"].dt.hour.astype(int)
    return frame.sort_values(
        ["date", "hour", "icao24", "request_start"], kind="mergesort"
    ).reset_index(drop=True)
