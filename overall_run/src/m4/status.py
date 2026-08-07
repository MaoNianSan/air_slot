from __future__ import annotations

from .contracts import DecisionLane, M4ActionEvaluation, M4ResultStatus


_UPSTREAM_BLOCKERS = frozenset({
    "M2_VALUATION_NOT_FROZEN",
    "M3_PARAMETER_NOT_FROZEN",
    "M3_FORMAL_LIBRARY_NOT_READY",
    "PRE_R2_COMPATIBILITY_ONLY",
    "PRE_R3_NOT_AVAILABLE",
    "PRE_R3_REGISTRY_MISSING",
    "STAGE_CONTRACT_NOT_FROZEN",
})


def determine_result_status(
    evaluations: tuple[M4ActionEvaluation, ...],
    *,
    test_only: bool,
) -> M4ResultStatus:
    if test_only:
        return M4ResultStatus.TEST_ONLY_VALID

    non_null = tuple(item for item in evaluations if item.action_id != "A00")
    reasons = {reason for item in non_null for reason in item.reason_codes}
    if "CONTRACT_MISMATCH" in reasons:
        return M4ResultStatus.CONTRACT_ERROR
    if reasons.intersection(_UPSTREAM_BLOCKERS):
        return M4ResultStatus.BLOCKED_BY_UPSTREAM
    if "M2_INPUT_ABSTAIN" in reasons:
        return M4ResultStatus.ABSTAIN
    if "STALE" in reasons:
        return M4ResultStatus.STALE
    if any(item.decision_lane is DecisionLane.FORMAL for item in non_null):
        return M4ResultStatus.VALID
    if any(item.decision_lane is DecisionLane.CONDITIONAL for item in non_null):
        return M4ResultStatus.CONDITIONAL_ONLY
    if any(item.decision_lane is DecisionLane.SCENARIO for item in non_null):
        return M4ResultStatus.SCENARIO_ONLY
    return M4ResultStatus.A00_ONLY
