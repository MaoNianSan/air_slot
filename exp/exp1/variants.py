from __future__ import annotations

from copy import deepcopy

from model.common.errors import ContractError
from model.common.identity import content_id


EXP1_VARIANTS = (
    "empirical",
    "current",
    "fixed_history",
    "adaptive_history",
    "independent_heads",
    "leakage_diagnostic",
)


def construct_exp1_variant(formal_artifact: dict, variant: str) -> dict:
    if variant not in EXP1_VARIANTS:
        raise ContractError("EXP1_VARIANT_UNKNOWN")
    before = content_id(formal_artifact)
    transformed = deepcopy(formal_artifact)
    transformed["evaluation_variant"] = variant
    transformed["evaluation_only"] = variant == "leakage_diagnostic"
    if content_id(formal_artifact) != before:
        raise ContractError("EXP1_MUTATED_FORMAL_ARTIFACT")
    return transformed
