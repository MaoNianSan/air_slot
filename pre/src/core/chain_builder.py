from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..episode import _aircraft_group, _split_for, _time_bin
from .contracts import ChainMatchStatus, ChainSupportLevel, stable_id, utc_series


REJECTION_COLUMNS = [
    "predecessor_flight_id",
    "candidate_flight_id",
    "candidate_firstseen",
    "candidate_lastseen",
    "rejection_reason",
]


def _next_candidates(
    predecessor: pd.Series,
    group: pd.DataFrame,
    ceiling_minutes: float,
) -> pd.DataFrame:
    """Return every future candidate in time order.

    Qualification is intentionally performed by ``_qualify_candidates`` so an
    invalid earliest row cannot mask a later valid successor.
    """
    future = group[
        group["flight_id"].ne(predecessor["flight_id"])
        & group["firstseen_utc"].gt(predecessor["firstseen_utc"])
    ].copy()
    return future.sort_values(
        ["firstseen_utc", "lastseen_utc", "flight_id"], kind="mergesort"
    )


def _identity_conflict(predecessor: pd.Series, candidate: pd.Series, column: str) -> bool:
    left = predecessor.get(column, pd.NA)
    right = candidate.get(column, pd.NA)
    return pd.notna(left) and pd.notna(right) and str(left).strip() and str(right).strip() and str(left) != str(right)


def _qualify_candidates(
    predecessor: pd.Series,
    candidates: pd.DataFrame,
    *,
    threshold_minutes: float,
    ceiling_minutes: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    accepted: list[int] = []
    rejected: list[dict[str, Any]] = []
    for index, candidate in candidates.iterrows():
        gap = (candidate["firstseen_utc"] - predecessor["lastseen_utc"]).total_seconds() / 60.0
        reason = ""
        if gap < 0:
            reason = "TEMPORAL_OVERLAP"
        elif gap > ceiling_minutes:
            reason = "ADMINISTRATIVE_CEILING_EXCEEDED"
        elif not (
            bool(predecessor.get("destination"))
            and bool(candidate.get("origin"))
            and str(predecessor.get("destination")) == str(candidate.get("origin"))
        ):
            reason = "AIRPORT_DISCONTINUITY"
        elif _identity_conflict(predecessor, candidate, "registration"):
            reason = "REGISTRATION_CONFLICT"
        elif _identity_conflict(predecessor, candidate, "typecode"):
            reason = "TYPECODE_CONFLICT"
        elif gap > threshold_minutes:
            reason = "CHAIN_GAP_THRESHOLD_EXCEEDED"
        if reason:
            rejected.append(
                {
                    "predecessor_flight_id": predecessor.get("flight_id", pd.NA),
                    "candidate_flight_id": candidate.get("flight_id", pd.NA),
                    "candidate_firstseen": candidate.get("firstseen_utc", pd.NaT),
                    "candidate_lastseen": candidate.get("lastseen_utc", pd.NaT),
                    "rejection_reason": reason,
                }
            )
        else:
            accepted.append(index)
    accepted_frame = candidates.loc[accepted].copy() if accepted else candidates.iloc[0:0].copy()
    return accepted_frame, pd.DataFrame(rejected, columns=REJECTION_COLUMNS)


def _base_row(predecessor: pd.Series, successor: pd.Series | None, cfg: dict[str, Any]) -> dict[str, Any]:
    successor_id = successor["flight_id"] if successor is not None else pd.NA
    start = predecessor["firstseen_utc"]
    end = successor["firstseen_utc"] if successor is not None else pd.NaT
    return {
        "chain_episode_id": stable_id(predecessor["flight_id"], successor_id),
        "predecessor_flight_id": predecessor["flight_id"],
        "successor_flight_id": successor_id,
        "airline_id": predecessor.get("airline_id", pd.NA),
        "aircraft_id": predecessor["icao24"],
        "rotation_id": predecessor.get("rotation_id", pd.NA),
        "turnaround_airport": predecessor["destination"],
        "episode_start_time": start,
        "episode_end_time": end,
        "split": _split_for(start, cfg["splits"]),
        "predecessor_firstseen_proxy": predecessor["firstseen_utc"],
        "predecessor_lastseen_proxy": predecessor["lastseen_utc"],
        "successor_firstseen_proxy": end,
        "successor_lastseen_proxy": successor["lastseen_utc"] if successor is not None else pd.NaT,
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
        "successor_source_record_id": successor.get("source_record_id", pd.NA) if successor is not None else pd.NA,
        "successor_source_file": successor.get("raw_source_file", pd.NA) if successor is not None else pd.NA,
        "successor_source_hash": successor.get("raw_source_hash", pd.NA) if successor is not None else pd.NA,
    }


def _classify(predecessor: pd.Series, candidates: pd.DataFrame, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    if candidates.empty:
        row = _base_row(predecessor, None, cfg)
        row.update(
            chain_support_level=ChainSupportLevel.UNSUPPORTED.value,
            chain_match_status=ChainMatchStatus.UNMATCHED.value,
            terminal_status="DATA_END",
            censoring_status="RIGHT_CENSORED",
            core_eligible=False,
            engineering_eligible=False,
            scientific_chain_eligible=False,
            formal_eligible=False,
            formal_eligible_status="DEPRECATED_COMPATIBILITY_ALIAS",
            exclusion_reason="NO_NEXT_OBSERVED_LEG_WITHIN_CEILING",
            observed_ground_gap_minutes=np.nan,
        )
        return [row]
    earliest = candidates["firstseen_utc"].min()
    selected = candidates[candidates["firstseen_utc"].eq(earliest)].copy()
    ambiguous = len(selected) > 1
    rows = []
    for _, successor in selected.iterrows():
        row = _base_row(predecessor, successor, cfg)
        gap = (successor["firstseen_utc"] - predecessor["lastseen_utc"]).total_seconds() / 60.0
        status = ChainMatchStatus.AMBIGUOUS.value if ambiguous else ChainMatchStatus.MATCHED.value
        reason = "MULTIPLE_FIRST_VALID_SUCCESSORS" if ambiguous else ""
        row.update(
            chain_support_level=ChainSupportLevel.OBSERVED_CHAIN_PROXY.value,
            chain_match_status=status,
            terminal_status="NORMAL" if not ambiguous else "UNSUPPORTED",
            censoring_status="OBSERVED",
            core_eligible=not ambiguous and row["split"] is not None,
            engineering_eligible=not ambiguous and row["split"] is not None,
            scientific_chain_eligible=False,
            formal_eligible=not ambiguous and row["split"] is not None,
            formal_eligible_status="DEPRECATED_COMPATIBILITY_ALIAS",
            exclusion_reason=reason,
            observed_ground_gap_minutes=gap,
        )
        rows.append(row)
    return rows


def build_chains(flights: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    rejection_rows: list[pd.DataFrame] = []
    ceiling = float(cfg["predecessor_matching"]["administrative_hard_ceiling_minutes"])
    threshold = float(cfg["predecessor_matching"]["gap_threshold_minutes"])
    for _, group in flights.groupby("icao24", sort=False):
        group = group.sort_values(["firstseen_utc", "lastseen_utc", "flight_id"], kind="mergesort")
        seeds = group[group["is_predecessor_seed"]]
        for _, predecessor in seeds.iterrows():
            if pd.isna(predecessor["firstseen_utc"]) or pd.isna(predecessor["lastseen_utc"]):
                continue
            candidates = _next_candidates(predecessor, group, ceiling)
            qualified, rejected = _qualify_candidates(
                predecessor,
                candidates,
                threshold_minutes=threshold,
                ceiling_minutes=ceiling,
            )
            if not rejected.empty:
                rejection_rows.append(rejected)
            rows.extend(_classify(predecessor, qualified, cfg))
    episodes = pd.DataFrame(rows)
    if episodes.empty:
        raise ValueError("CORE_CHAIN_EPISODES_EMPTY")
    for column in [
        "episode_start_time", "episode_end_time", "predecessor_firstseen_proxy",
        "predecessor_lastseen_proxy", "successor_firstseen_proxy",
        "successor_lastseen_proxy", "successor_sobt", "successor_aobt", "successor_atot",
    ]:
        episodes[column] = utc_series(episodes[column])
    episodes = episodes.sort_values(["episode_start_time", "chain_episode_id"], kind="mergesort").reset_index(drop=True)
    episodes.attrs["candidate_rejections"] = (
        pd.concat(rejection_rows, ignore_index=True)
        if rejection_rows
        else pd.DataFrame(columns=REJECTION_COLUMNS)
    )
    return episodes
