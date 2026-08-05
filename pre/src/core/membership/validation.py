from __future__ import annotations

from typing import Any

import pandas as pd

from .interval_join import MEMBERSHIP_COLUMNS


VALID_ROLES = {
    "PREDECESSOR_HISTORY",
    "PREDECESSOR_ACTIVE",
    "TURNAROUND_CONTEXT",
    "SUCCESSOR_CONTEXT",
    "AIRPORT_CONTEXT",
    "WEATHER_CONTEXT",
}


def validate_observation_membership(
    membership: pd.DataFrame,
) -> dict[str, Any]:
    missing = sorted(set(MEMBERSHIP_COLUMNS) - set(membership.columns))
    duplicate_ids = -1 if missing else int(membership["membership_id"].duplicated().sum())
    duplicate_relations = -1 if missing else int(
        membership.duplicated(
            ["chain_episode_id", "observation_id", "interval_type"]
        ).sum()
    )
    split_missing = -1 if missing else int(membership["split"].isna().sum())
    invalid_role = -1 if missing else int(
        (~membership["membership_role"].isin(VALID_ROLES)).sum()
    )
    status = (
        "PASS"
        if not missing
        and not any([duplicate_ids, duplicate_relations, split_missing, invalid_role])
        else "FAIL"
    )
    return {
        "status": status,
        "membership_rows": len(membership),
        "missing_columns": missing,
        "duplicate_membership_ids": duplicate_ids,
        "duplicate_relations": duplicate_relations,
        "missing_split": split_missing,
        "invalid_membership_roles": invalid_role,
    }
