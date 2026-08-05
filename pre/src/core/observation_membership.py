from __future__ import annotations

from typing import Any

import pandas as pd

from .membership_interval_join import MEMBERSHIP_COLUMNS, interval_join_partition


def build_observation_membership(
    observations: pd.DataFrame,
    requests: pd.DataFrame,
) -> pd.DataFrame:
    """Compatibility wrapper over the partitioned interval-join implementation."""
    if observations.empty or requests.empty:
        return pd.DataFrame(columns=MEMBERSHIP_COLUMNS)
    obs = observations.copy()
    if "observation_date" not in obs:
        if "event_time" not in obs:
            raise ValueError("MEMBERSHIP_OBSERVATION_DATE_AND_EVENT_TIME_MISSING")
        obs["observation_date"] = pd.to_datetime(
            obs["event_time"], utc=True, errors="coerce"
        ).dt.strftime("%Y-%m-%d")
    pieces = [
        interval_join_partition(
            group,
            requests,
            source=str(source),
            observation_date=str(observation_date),
        )
        for (source, observation_date), group in obs.groupby(
            ["source", "observation_date"], sort=True, dropna=False
        )
        if pd.notna(source) and pd.notna(observation_date)
    ]
    nonempty = [piece for piece in pieces if not piece.empty]
    if not nonempty:
        return pd.DataFrame(columns=MEMBERSHIP_COLUMNS)
    return pd.concat(nonempty, ignore_index=True).drop_duplicates(
        ["chain_episode_id", "observation_id", "interval_type"], keep="last"
    ).sort_values(
        ["chain_episode_id", "source", "observation_id"], kind="mergesort"
    ).reset_index(drop=True)


def validate_observation_membership(membership: pd.DataFrame) -> dict[str, Any]:
    missing = sorted(set(MEMBERSHIP_COLUMNS) - set(membership.columns))
    duplicate_membership_ids = -1 if missing else int(membership["membership_id"].duplicated().sum())
    duplicate_relation = -1 if missing else int(
        membership.duplicated(
            ["chain_episode_id", "observation_id", "interval_type"]
        ).sum()
    )
    split_missing = -1 if missing else int(membership["split"].isna().sum())
    invalid_role = -1 if missing else int(
        (~membership["membership_role"].isin(
            {
                "PREDECESSOR_HISTORY", "PREDECESSOR_ACTIVE",
                "TURNAROUND_CONTEXT", "SUCCESSOR_CONTEXT",
                "AIRPORT_CONTEXT", "WEATHER_CONTEXT",
            }
        )).sum()
    )
    status = "PASS" if not missing and not any([duplicate_membership_ids, duplicate_relation, split_missing, invalid_role]) else "FAIL"
    return {
        "status": status,
        "membership_rows": len(membership),
        "missing_columns": missing,
        "duplicate_membership_ids": duplicate_membership_ids,
        "duplicate_relations": duplicate_relation,
        "missing_split": split_missing,
        "invalid_membership_roles": invalid_role,
    }
