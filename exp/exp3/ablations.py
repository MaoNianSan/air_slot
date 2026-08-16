from __future__ import annotations

from copy import deepcopy

from model.common.errors import ContractError
from model.common.identity import content_id


ABLATIONS = {
    "no_induced", "no_evidence_distinction", "no_coverage_restriction",
    "NO_INDUCED_CONSEQUENCE", "NO_EVIDENCE_DISTINCTION", "NO_MATERIAL_COVERAGE_GATE",
}


def transformed_ablation(formal_artifact: dict, ablation: str) -> dict:
    if ablation not in ABLATIONS:
        raise ContractError("EXP3_ABLATION_UNKNOWN")
    before = content_id(formal_artifact)
    transformed = deepcopy(formal_artifact)
    canonical = {
        "no_induced": "NO_INDUCED_CONSEQUENCE",
        "no_evidence_distinction": "NO_EVIDENCE_DISTINCTION",
        "no_coverage_restriction": "NO_MATERIAL_COVERAGE_GATE",
    }.get(ablation, ablation)
    if canonical == "NO_INDUCED_CONSEQUENCE":
        transformed["evaluation_delta_plus_override"] = 0.0
        transformed["changed_fields"] = ("Delta_plus",)
    elif canonical == "NO_EVIDENCE_DISTINCTION":
        for row in transformed.get("consequence_rows", ()):
            row["evaluation_evidence_class"] = "COLLAPSED"
        transformed["evaluation_lane_label"] = "PSEUDO_FORMAL_EVAL"
        transformed["changed_fields"] = ("decision_eligibility_evidence_distinction",)
    else:
        transformed["evaluation_coverage_override"] = "NO_MATERIAL_COVERAGE_GATE"
        transformed["unsupported_value_policy"] = "PRESERVE_NULL_NOT_ZERO"
        transformed["changed_fields"] = ("material_coverage_gate",)
    transformed["evaluation_ablation"] = ablation
    transformed["protocol_ablation"] = canonical
    if content_id(formal_artifact) != before:
        raise ContractError("EXP3_MUTATED_FORMAL_ARTIFACT")
    return transformed
