from __future__ import annotations

from ..m3.contracts import OutcomeCoverage, ParameterStatus
from .compatibility import formal_m2_blockers
from .contracts import DecisionLane, M4InputBundle
from .evidence import evidence_reasons_for_action
from .opportunity import OpportunityResult
from .stage_adapter import StageCompatibility


_SCENARIO_REASONS = {
    "PRE_SCENARIO_PARAMETER_REQUIRED",
    "PRE_ASSUMPTION_MISMATCH",
    "RESOURCE_NETWORK_NOT_AVAILABLE",
    "TAXI_REFERENCE_UNSUPPORTED",
    "M3_SCENARIO_ONLY",
}
_EXCLUDED_REASONS = {"CONTRACT_MISMATCH", "ACTION_DISABLED", "STAGE_NOT_APPLICABLE"}


def assign_decision_lane(
    *,
    action_id: str,
    bundle: M4InputBundle,
    stage: StageCompatibility,
    opportunity: OpportunityResult,
) -> tuple[DecisionLane, tuple[str, ...]]:
    action = bundle.m3_artifact.action_catalog[action_id]
    reasons: list[str] = list(evidence_reasons_for_action(action_id, bundle.evidence_context))
    reasons.extend(formal_m2_blockers(bundle.m2_input_bundle, bundle.sample_losses))
    if action.outcome_coverage is OutcomeCoverage.PARTIAL_SUPPORTED:
        reasons.append("M3_PARTIAL_SUPPORTED")
    elif action.outcome_coverage is OutcomeCoverage.SCENARIO_ONLY:
        reasons.append("M3_SCENARIO_ONLY")
    if action.parameter_status is ParameterStatus.NOT_CONFIGURED:
        reasons.append("M3_PARAMETER_NOT_CONFIGURED")
    if bundle.m3_artifact.parameter_freeze_status != "DONE":
        reasons.append("M3_PARAMETER_NOT_FROZEN")
    if bundle.m3_artifact.formal_library_status != "READY":
        reasons.append("M3_FORMAL_LIBRARY_NOT_READY")
    if bundle.test_only:
        reasons.append("TEST_ONLY_ARTIFACT")
    if stage.reason_code != "FORMAL_SUPPORTED":
        reasons.append(stage.reason_code)
    if opportunity.reason_code != "FORMAL_SUPPORTED":
        reasons.append(opportunity.reason_code)
    reasons = list(dict.fromkeys(reasons))

    if action_id == "A00":
        retained = [reason for reason in reasons if reason in {"TEST_ONLY_ARTIFACT"}]
        return DecisionLane.FORMAL, tuple(retained or ["FORMAL_SUPPORTED"])
    if any(reason in _EXCLUDED_REASONS for reason in reasons):
        return DecisionLane.EXCLUDED, tuple(reasons)
    if action.outcome_coverage is OutcomeCoverage.SCENARIO_ONLY:
        return DecisionLane.SCENARIO, tuple(reasons)
    if any(reason in _SCENARIO_REASONS for reason in reasons):
        return DecisionLane.SCENARIO, tuple(reasons)
    if action_id == "A31" and "PASSENGER_CONNECTION_NOT_FORMAL" in reasons:
        return DecisionLane.SCENARIO, tuple(reasons)
    if action.outcome_coverage is OutcomeCoverage.PARTIAL_SUPPORTED:
        return DecisionLane.CONDITIONAL, tuple(reasons)

    blocking_conditional = {
        "M2_INPUT_PARTIAL",
        "M2_INPUT_ABSTAIN",
        "M2_TAIL_UNRESOLVED",
        "M2_VALUATION_NOT_FROZEN",
        "M2_PROXY_DEPENDENT",
        "PRE_R2_COMPATIBILITY_ONLY",
        "PRE_R3_NOT_AVAILABLE",
        "PRE_R3_REGISTRY_MISSING",
        "PRE_EVIDENCE_UNSUPPORTED",
        "PASSENGER_CONNECTION_NOT_FORMAL",
        "STAGE_CONTRACT_NOT_FROZEN",
        "OPPORTUNITY_CONTRACT_NOT_CONFIGURED",
    }
    if not bundle.test_only:
        blocking_conditional.update({
            "M3_PARAMETER_NOT_CONFIGURED",
            "M3_PARAMETER_NOT_FROZEN",
            "M3_FORMAL_LIBRARY_NOT_READY",
        })
    if any(reason in blocking_conditional for reason in reasons):
        return DecisionLane.CONDITIONAL, tuple(reasons)
    return DecisionLane.FORMAL, tuple(reasons or ["FORMAL_SUPPORTED"])
