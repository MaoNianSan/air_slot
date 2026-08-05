from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..episode import _aircraft_group, _split_for, _time_bin
from .contracts import ChainMatchStatus, ChainSupportLevel, stable_id, utc_series


def _next_candidates(
    predecessor: pd.Series,
    group: pd.DataFrame,
    ceiling_minutes: float,
) -> pd.DataFrame:
    future = group[
        group["flight_id"].ne(predecessor["flight_id"])
        & group["firstseen_utc"].gt(predecessor["firstseen_utc"])
        & group["firstseen_utc"].le(
            predecessor["lastseen_utc"] + pd.to_timedelta(ceiling_minutes, unit="m")
        )
    ]
    if future.empty:
        return future
    earliest = future["firstseen_utc"].min()
    return future[future["firstseen_utc"].eq(earliest)].copy()


def _base_row(predecessor: pd.Series, successor: pd.Series | None, cfg: dict[str, Any]) -> dict[str, Any]:
    successor_id = successor["flight_id"] if successor is not None else pd.NA
    start = predecessor["firstseen_utc"]
    end = successor["firstseen_utc"] if successor is not None else pd.NaT
    return {
        "chain_episode_id": stable_id(predecessor["flight_id"], successor_id),
        "predecessor_flight_id": predecessor["flight_id"],
        "successor_flight_id": successor_id,
        "airline_id": pd.NA,
        "aircraft_id": predecessor["icao24"],
        "rotation_id": pd.NA,
        "turnaround_airport": predecessor["destination"],
        "episode_start_time": start,
        "episode_end_time": end,
        "split": _split_for(start, cfg["splits"]),
        "predecessor_firstseen_proxy": predecessor["firstseen_utc"],
        "predecessor_lastseen_proxy": predecessor["lastseen_utc"],
        "successor_firstseen_proxy": end,
        "successor_lastseen_proxy": (
            successor["lastseen_utc"] if successor is not None else pd.NaT
        ),
        "successor_sobt": pd.NaT,
        "successor_aobt": pd.NaT,
        "successor_atot": pd.NaT,
        "taxi_duration": np.nan,
        "y_ob": np.nan,
        "y_tx": np.nan,
        "y_to": np.nan,
        "label_missing_reason": "AOBT_PLUS_AND_SOBT_UNSUPPORTED",
        "aircraft_group": _aircraft_group(predecessor.get("typecode")),
        "episode_start_time_bin": _time_bin(start),
        "predecessor_source_record_id": predecessor.get("source_record_id", pd.NA),
        "predecessor_source_file": predecessor.get("raw_source_file", pd.NA),
        "predecessor_source_hash": predecessor.get("raw_source_hash", pd.NA),
        "successor_source_record_id": (
            successor.get("source_record_id", pd.NA) if successor is not None else pd.NA
        ),
        "successor_source_file": (
            successor.get("raw_source_file", pd.NA) if successor is not None else pd.NA
        ),
        "successor_source_hash": (
            successor.get("raw_source_hash", pd.NA) if successor is not None else pd.NA
        ),
    }


def _classify(
    predecessor: pd.Series,
    candidates: pd.DataFrame,
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    if candidates.empty:
        row = _base_row(predecessor, None, cfg)
        row.update(
            chain_support_level=ChainSupportLevel.UNSUPPORTED.value,
            chain_match_status=ChainMatchStatus.UNMATCHED.value,
            terminal_status="DATA_END",
            censoring_status="RIGHT_CENSORED",
            formal_eligible=False,
            exclusion_reason="NO_NEXT_OBSERVED_LEG_WITHIN_CEILING",
            observed_ground_gap_minutes=np.nan,
        )
        return [row]
    rows = []
    ambiguous = len(candidates) > 1
    threshold = float(cfg["predecessor_matching"]["gap_threshold_minutes"])
    for _, successor in candidates.iterrows():
        row = _base_row(predecessor, successor, cfg)
        gap = (successor["firstseen_utc"] - predecessor["lastseen_utc"]).total_seconds() / 60.0
        overlap = gap < 0
        continuity = (
            bool(predecessor["destination"])
            and bool(successor["origin"])
            and predecessor["destination"] == successor["origin"]
        )
        if ambiguous:
            status = ChainMatchStatus.AMBIGUOUS.value
            reason = "MULTIPLE_IMMEDIATE_NEXT_OBSERVED_LEGS"
        elif overlap:
            status = ChainMatchStatus.UNMATCHED.value
            reason = "TEMPORAL_OVERLAP"
        elif not continuity:
            status = ChainMatchStatus.UNMATCHED.value
            reason = "AIRPORT_DISCONTINUITY"
        elif gap > threshold:
            status = ChainMatchStatus.UNMATCHED.value
            reason = "CHAIN_GAP_THRESHOLD_EXCEEDED"
        else:
            status = ChainMatchStatus.MATCHED.value
            reason = ""
        support = (
            ChainSupportLevel.OBSERVED_CHAIN_PROXY.value
            if continuity
            else ChainSupportLevel.UNSUPPORTED.value
        )
        eligible = status == ChainMatchStatus.MATCHED.value and row["split"] is not None
        row.update(
            chain_support_level=support,
            chain_match_status=status,
            terminal_status="NORMAL" if eligible else "UNSUPPORTED",
            censoring_status="OBSERVED",
            formal_eligible=eligible,
            exclusion_reason=reason if not eligible else "",
            observed_ground_gap_minutes=gap,
        )
        rows.append(row)
    return rows


def build_chains(flights: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    ceiling = float(
        cfg["predecessor_matching"]["administrative_hard_ceiling_minutes"]
    )
    for _, group in flights.groupby("icao24", sort=False):
        group = group.sort_values(
            ["firstseen_utc", "lastseen_utc", "flight_id"], kind="mergesort"
        )
        seeds = group[group["is_predecessor_seed"]]
        for _, predecessor in seeds.iterrows():
            if pd.isna(predecessor["firstseen_utc"]) or pd.isna(predecessor["lastseen_utc"]):
                continue
            rows.extend(_classify(predecessor, _next_candidates(predecessor, group, ceiling), cfg))
    episodes = pd.DataFrame(rows)
    if episodes.empty:
        raise ValueError("CORE_CHAIN_EPISODES_EMPTY")
    for column in [
        "episode_start_time",
        "episode_end_time",
        "predecessor_firstseen_proxy",
        "predecessor_lastseen_proxy",
        "successor_firstseen_proxy",
        "successor_lastseen_proxy",
        "successor_sobt",
        "successor_aobt",
        "successor_atot",
    ]:
        episodes[column] = utc_series(episodes[column])
    return episodes.sort_values(
        ["episode_start_time", "chain_episode_id"], kind="mergesort"
    ).reset_index(drop=True)
