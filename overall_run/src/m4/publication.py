from __future__ import annotations

from .compatibility import formal_m2_blockers
from .contracts import (
    DecisionLane,
    M4ActionEvaluation,
    M4InputBundle,
    M4ResultStatus,
    PublicationGateResult,
)


M4_PUBLICATION_GATE_VERSION = "M4_PUBLICATION_GATE_V1"
_BLOCKING_STATUSES = {
    M4ResultStatus.CONTRACT_ERROR,
    M4ResultStatus.BLOCKED_BY_UPSTREAM,
    M4ResultStatus.ABSTAIN,
    M4ResultStatus.STALE,
    M4ResultStatus.CONDITIONAL_ONLY,
    M4ResultStatus.SCENARIO_ONLY,
    M4ResultStatus.A00_ONLY,
}
_CRITICAL_FORMAL_REASONS = {
    "CONTRACT_MISMATCH",
    "PRE_SCENARIO_PARAMETER_REQUIRED",
    "PRE_EVIDENCE_UNSUPPORTED",
    "M2_SUBITEM_UNSUPPORTED",
    "STAGE_CONTRACT_NOT_FROZEN",
}


def evaluate_publication_gate(
    bundle: M4InputBundle,
    evaluations: tuple[M4ActionEvaluation, ...],
    result_status: M4ResultStatus,
    *,
    contract_pass: bool = True,
) -> PublicationGateResult:
    reasons: list[str] = []
    if not bundle.formal_mode:
        reasons.append("FORMAL_MODE_REQUIRED")
    if bundle.test_only:
        reasons.append("TEST_ONLY_ARTIFACT")
    if not bundle.evidence_context.is_formal_r3:
        reasons.append("PRE_FORMAL_EVIDENCE_CONTRACT_NOT_SATISFIED")
    if bundle.evidence_context.availability_policy_status in {"", "UNKNOWN", "NOT_CONFIGURED"}:
        reasons.append("PRE_AVAILABILITY_POLICY_NOT_SATISFIED")

    m2_blockers = formal_m2_blockers(bundle.m2_input_bundle, bundle.sample_losses)
    if bundle.m2_input_bundle.audit_context.formal_reconstruction_gate != "PASS":
        reasons.append("M2_FORMAL_GATE_NOT_PASS")
    if "M2_VALUATION_NOT_FROZEN" in m2_blockers:
        reasons.append("M2_VALUATION_NOT_FROZEN")
    if "TEST_ONLY_ARTIFACT" in m2_blockers:
        reasons.append("TEST_ONLY_ARTIFACT")
    if "CONTRACT_MISMATCH" in m2_blockers:
        reasons.append("M2_CONTRACT_NOT_PASS")

    artifact = bundle.m3_artifact
    if artifact.test_only:
        reasons.append("TEST_ONLY_ARTIFACT")
    if artifact.parameter_freeze_status != "DONE":
        reasons.append("M3_PARAMETER_NOT_FROZEN")
    if artifact.formal_library_status != "READY":
        reasons.append("M3_FORMAL_LIBRARY_NOT_READY")
    publication_flag = dict(artifact.version_metadata).get("publication_allowed")
    if publication_flag not in {True, "true", "TRUE", "YES"}:
        reasons.append("M3_ARTIFACT_NOT_PUBLICATION_ALLOWED")
    if not contract_pass:
        reasons.append("M4_CONTRACT_NOT_PASS")

    formal_reasons = {
        reason
        for item in evaluations
        if item.decision_lane is DecisionLane.FORMAL
        for reason in item.reason_codes
    }
    if formal_reasons.intersection(_CRITICAL_FORMAL_REASONS):
        reasons.append("M4_CRITICAL_EVIDENCE_BLOCKER")
    if not any(
        item.action_id != "A00" and item.decision_lane is DecisionLane.FORMAL
        for item in evaluations
    ):
        reasons.append("M4_NO_FORMAL_NON_NULL_ACTION")
    if result_status in _BLOCKING_STATUSES:
        reasons.append(result_status.value)

    return PublicationGateResult(
        allowed=not reasons,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )
