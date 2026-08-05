from __future__ import annotations

import pandas as pd

from .contracts import ChainMatchStatus, ChainSupportLevel


def validate_chains(episodes: pd.DataFrame) -> dict[str, object]:
    duplicate_ids = int(episodes["chain_episode_id"].duplicated().sum())
    ambiguous_eligible = int(
        (
            episodes["chain_match_status"].eq(ChainMatchStatus.AMBIGUOUS.value)
            & episodes["formal_eligible"]
        ).sum()
    )
    invalid_order = int(
        (
            episodes["episode_end_time"].notna()
            & episodes["episode_end_time"].lt(episodes["episode_start_time"])
        ).sum()
    )
    split_counts = episodes.groupby("chain_episode_id")["split"].nunique(dropna=False)
    split_leakage = int(split_counts.gt(1).sum())
    invalid_support = int(
        (~episodes["chain_support_level"].isin([value.value for value in ChainSupportLevel])).sum()
    )
    invalid_status = int(
        (~episodes["chain_match_status"].isin([value.value for value in ChainMatchStatus])).sum()
    )
    status = (
        "PASS"
        if not any(
            [duplicate_ids, ambiguous_eligible, invalid_order, split_leakage, invalid_support, invalid_status]
        )
        else "FAIL"
    )
    support = (
        episodes.groupby(["chain_match_status", "chain_support_level"], dropna=False)
        .size()
        .rename("rows")
        .reset_index()
        .to_dict("records")
    )
    return {
        "status": status,
        "chain_rows": len(episodes),
        "formal_eligible_rows": int(episodes["formal_eligible"].sum()),
        "duplicate_chain_ids": duplicate_ids,
        "ambiguous_formal_eligible": ambiguous_eligible,
        "invalid_time_order": invalid_order,
        "chain_split_leakage": split_leakage,
        "invalid_support_levels": invalid_support,
        "invalid_match_statuses": invalid_status,
        "support": support,
    }
