from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..m3.contracts import ActionCatalogEntry
from .contracts import M4ContractError


@dataclass(frozen=True)
class OpportunityResult:
    configured: bool
    probability: float | None
    reason_code: str
    test_only: bool = False


def evaluate_opportunity(
    action: ActionCatalogEntry,
    *,
    overrides: Mapping[str, float] | None = None,
) -> OpportunityResult:
    if action.action_id == "A00":
        return OpportunityResult(True, 1.0, "FORMAL_SUPPORTED", False)
    if overrides and action.action_id in overrides:
        value = float(overrides[action.action_id])
        if not 0.0 <= value <= 1.0:
            raise M4ContractError(f"M4_OPPORTUNITY_PROBABILITY_INVALID:{action.action_id}")
        return OpportunityResult(True, value, "TEST_ONLY_ARTIFACT", True)
    return OpportunityResult(
        configured=False,
        probability=None,
        reason_code="OPPORTUNITY_CONTRACT_NOT_CONFIGURED",
        test_only=False,
    )
