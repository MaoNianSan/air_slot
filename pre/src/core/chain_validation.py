from __future__ import annotations

import pandas as pd

from .contracts import ChainMatchStatus, ChainSupportLevel


def validate_chains(episodes: pd.DataFrame) -> dict[str, object]:
    engineering = episodes["engineering_eligible"].fillna(False).astype(bool)
    duplicate_ids = int(episodes["chain_episode_id"].duplicated().sum())
    ambiguous_eligible = int(
        (
            episodes["chain_match_status"].eq(ChainMatchStatus.AMBIGUOUS.value)
            & engineering
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
    eligibility_semantics_errors = 0
    if {"core_eligible", "engineering_eligible", "scientific_chain_eligible", "formal_eligible"}.issubset(episodes.columns):
        eligibility_semantics_errors = int(
            (~episodes["core_eligible"].astype(bool).ge(episodes["engineering_eligible"].astype(bool))).sum()
            + (~episodes["engineering_eligible"].astype(bool).eq(episodes["formal_eligible"].astype(bool))).sum()
            + (episodes["chain_support_level"].eq(ChainSupportLevel.OBSERVED_CHAIN_PROXY.value) & episodes["scientific_chain_eligible"].astype(bool)).sum()
        )
    status = (
        "PASS"
        if not any(
            [duplicate_ids, ambiguous_eligible, invalid_order, split_leakage, invalid_support, invalid_status, eligibility_semantics_errors]
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
        "formal_eligible_rows": int(engineering.sum()),
        "core_eligible_rows": int(episodes.get("core_eligible", engineering).fillna(False).astype(bool).sum()),
        "engineering_eligible_rows": int(engineering.sum()),
        "scientific_chain_eligible_rows": int(episodes.get("scientific_chain_eligible", pd.Series(False, index=episodes.index)).fillna(False).astype(bool).sum()),
        "duplicate_chain_ids": duplicate_ids,
        "ambiguous_formal_eligible": ambiguous_eligible,
        "invalid_time_order": invalid_order,
        "chain_split_leakage": split_leakage,
        "invalid_support_levels": invalid_support,
        "invalid_match_statuses": invalid_status,
        "eligibility_semantics_errors": eligibility_semantics_errors,
        "support": support,
    }
