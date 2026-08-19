from model.M3.contracts import (
    ActionResponseSupportState,
    ResponseParameterStatus,
)


def assign_lane(
    candidate,
    opportunity_probability,
    *,
    baseline_valid=True,
    material_coverage_valid=True,
    monetary_mapping_frozen=True,
):
    """Lane = formal model comparability, never an evidence-status claim.

    Round 2 (spec 7): response provenance constrains interpretation only and
    must not substitute for comparison eligibility.  A candidate is FORMAL-
    comparable when it has a declared response contract with frozen parameters,
    resolved structural preconditions, an execution opportunity, material
    consequence coverage and a common frozen monetary basis.  Missing or
    unsupported response contracts cannot form a supported model comparison.
    The interpretation class is carried separately on the result object.
    """
    if candidate.precondition_state == "FALSE" or opportunity_probability == 0:
        return "EXCLUDED"
    if candidate.precondition_state == "UNKNOWN":
        return "CONDITIONAL"
    if not baseline_valid:
        return "SCENARIO"
    if not monetary_mapping_frozen:
        # No authoritative ranking exists without a frozen monetary mapping;
        # raw CU ranking is disabled and must never silently replace it.
        return "SCENARIO"
    if candidate.template_id == "A00":
        return "FORMAL"
    if not material_coverage_valid:
        return "SCENARIO"
    if candidate.response_parameter_status is not ResponseParameterStatus.FROZEN:
        return "SCENARIO"
    if candidate.response_support is not None and (
        candidate.response_support.support_state
        is ActionResponseSupportState.UNSUPPORTED
    ):
        # Contract absent/unsupported: cannot form a supported model comparison.
        return "SCENARIO"
    return "FORMAL"

