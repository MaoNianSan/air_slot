from __future__ import annotations

from copy import deepcopy

from model.common.errors import ContractError
from model.common.identity import content_id


LEGACY_EXP1_VARIANTS = (
    "empirical",
    "current",
    "fixed_history",
    "adaptive_history",
    "independent_heads",
    "leakage_diagnostic",
)

EXP1_VARIANTS = (
    "CURRENT",
    "FIXED_HISTORY",
    "ADAPTIVE_HISTORY",
    "RETROSPECTIVE_LEAKAGE_DIAGNOSTIC",
)

EXP1_VARIANT_ALIASES = {
    "current": "CURRENT",
    "fixed_history": "FIXED_HISTORY",
    "adaptive_history": "ADAPTIVE_HISTORY",
    "leakage_diagnostic": "RETROSPECTIVE_LEAKAGE_DIAGNOSTIC",
}


def construct_exp1_variant(formal_artifact: dict, variant: str) -> dict:
    canonical = EXP1_VARIANT_ALIASES.get(variant, variant)
    if canonical not in EXP1_VARIANTS:
        raise ContractError("EXP1_VARIANT_UNKNOWN")
    before = content_id(formal_artifact)
    transformed = deepcopy(formal_artifact)
    transformed["evaluation_variant"] = variant
    transformed["protocol_variant"] = canonical
    leakage = canonical == "RETROSPECTIVE_LEAKAGE_DIAGNOSTIC"
    transformed["evaluation_only"] = leakage
    transformed["EVALUATION_ONLY"] = leakage
    transformed["INVALID_INFORMATION_STATE"] = leakage
    transformed["MODEL_CANDIDATE"] = not leakage
    transformed["NOT_A_MODEL_CANDIDATE"] = leakage
    if content_id(formal_artifact) != before:
        raise ContractError("EXP1_MUTATED_FORMAL_ARTIFACT")
    return transformed
