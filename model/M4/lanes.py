from model.M3.contracts import (
    ActionResponseSupportState,
    ResponseParameterStatus,
    ResponseProvenance,
)


def assign_lane(
    candidate,
    opportunity_probability,
    *,
    baseline_valid=True,
    material_coverage_valid=True,
    monetary_mapping_frozen=True,
):
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
    if candidate.response_support is not None:
        if (
            candidate.response_support.support_state
            is not ActionResponseSupportState.SUPPORTED
        ):
            # Conditional or unsupported Pi_a never grants FORMAL authority.
            return "SCENARIO"
    elif candidate.response_provenance in {
        ResponseProvenance.PURE_SCENARIO,
        ResponseProvenance.STRUCTURAL_BOUNDED_SCENARIO,
        ResponseProvenance.UNSUPPORTED,
    }:
        return "SCENARIO"
    if candidate.response_parameter_status is not ResponseParameterStatus.FROZEN:
        return "SCENARIO"
    return "FORMAL"

