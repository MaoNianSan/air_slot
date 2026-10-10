"""Shared Section 5 contract constants.

These values describe the fixed comparison surface used by the formal
executor and the Section 5 development layer.  Keeping them in ``model.common``
prevents the formal layer from depending on the historical ``exp`` package.
The module contains identifiers only; it does not implement an estimand.
"""

from __future__ import annotations

from model.common.enums import OperationalStage


STAGE1_ACTIONABLE_STAGES: tuple[OperationalStage, ...] = (
    OperationalStage.PRE_IB,
    OperationalStage.POST_IB_PRE_OB,
)

STAGE1_ACTIONABLE_STAGE_CLASSES: tuple[str, ...] = ("PRE", "TURN")

FLATTENED_UNION_SEMANTICS = (
    "COMPATIBILITY_FLATTENED_UNION_NOT_A_POOLED_STAGE1_DECISION"
)

REPRESENTATIONS: tuple[str, ...] = (
    "HISTORY_JOINT",
    "CURRENT_JOINT",
    "HISTORY_POINT",
    "HISTORY_MARGINAL",
)


__all__ = [
    "FLATTENED_UNION_SEMANTICS",
    "REPRESENTATIONS",
    "STAGE1_ACTIONABLE_STAGE_CLASSES",
    "STAGE1_ACTIONABLE_STAGES",
]
