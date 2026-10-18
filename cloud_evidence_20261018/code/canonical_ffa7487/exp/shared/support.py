"""Versioned analysis-level support views for Exp1-Exp4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

SupportPolicyId = Literal[
    "FULL",
    "COMMON_SUPPORT_CONDITIONAL_090",
    "COMMON_SUPPORT_CONDITIONAL_050",
]


@dataclass(frozen=True)
class SupportPolicy:
    policy_id: SupportPolicyId
    minimum_mass: float
    conditional: bool


FULL = SupportPolicy("FULL", 1.0, False)
COMMON_SUPPORT_090 = SupportPolicy("COMMON_SUPPORT_CONDITIONAL_090", 0.90, True)
COMMON_SUPPORT_050 = SupportPolicy("COMMON_SUPPORT_CONDITIONAL_050", 0.50, True)


def policy(policy_id: SupportPolicyId) -> SupportPolicy:
    values = {
        FULL.policy_id: FULL,
        COMMON_SUPPORT_090.policy_id: COMMON_SUPPORT_090,
        COMMON_SUPPORT_050.policy_id: COMMON_SUPPORT_050,
    }
    return values[policy_id]


def apply_node_support_policy(
    rows: pd.DataFrame,
    *,
    support_policy: SupportPolicy,
    support_column: str = "common_support_mass",
) -> pd.DataFrame:
    """Return an analysis view without mutating or renormalizing source rows."""
    if support_column not in rows.columns:
        raise ValueError(f"SHARED_SUPPORT_COLUMN_MISSING:{support_column}")
    if rows.empty:
        result = rows.copy()
        result["support_policy_id"] = support_policy.policy_id
        result["support_policy_eligible"] = False
        return result
    masses = pd.to_numeric(rows[support_column], errors="coerce")
    if masses.isna().any() or ((masses < 0) | (masses > 1)).any():
        raise ValueError("SHARED_SUPPORT_MASS_INVALID")
    result = rows.copy()
    result["support_policy_id"] = support_policy.policy_id
    result["support_policy_eligible"] = masses >= support_policy.minimum_mass
    return result


__all__ = [
    "COMMON_SUPPORT_050",
    "COMMON_SUPPORT_090",
    "FULL",
    "SupportPolicy",
    "SupportPolicyId",
    "apply_node_support_policy",
    "policy",
]
