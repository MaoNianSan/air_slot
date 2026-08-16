from __future__ import annotations

from copy import deepcopy

from model.common.errors import ContractError
from model.common.identity import content_id


ABLATIONS = {"no_induced", "no_evidence_distinction", "no_coverage_restriction"}


def transformed_ablation(formal_artifact: dict, ablation: str) -> dict:
    if ablation not in ABLATIONS:
        raise ContractError("EXP3_ABLATION_UNKNOWN")
    before = content_id(formal_artifact)
    transformed = deepcopy(formal_artifact)
    if ablation == "no_induced":
        for candidate in transformed.get("candidates", ()):
            candidate["induced"] = {}
            candidate["induced_response"] = {}
    elif ablation == "no_evidence_distinction":
        for row in transformed.get("consequence_rows", ()):
            row["evaluation_evidence_class"] = "COLLAPSED"
    else:
        transformed["evaluation_coverage_override"] = "NO_RESTRICTION"
    transformed["evaluation_ablation"] = ablation
    if content_id(formal_artifact) != before:
        raise ContractError("EXP3_MUTATED_FORMAL_ARTIFACT")
    return transformed
