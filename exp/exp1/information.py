"""Information-role transformations for Exp1A."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from model.common.errors import ContractError
from model.common.identity import content_id

from .variants import Exp1Variant, information_mask


def apply_direct_reuse_mask(artifact: dict[str, Any], variant: str) -> dict[str, Any]:
    """Apply only the declared Exp1A mask; preserve the full model chain."""
    if variant not in (Exp1Variant.EXP1A_FULL.value, Exp1Variant.EXP1A_NO_DIRECT_REUSE.value):
        raise ContractError("EXP1A_VARIANT_REQUIRED")
    source_hash = content_id(artifact)
    transformed = deepcopy(artifact)
    mask = information_mask(variant)
    if variant == Exp1Variant.EXP1A_NO_DIRECT_REUSE.value:
        transformed.pop("upstream_hidden_history", None)
        transformed.pop("raw_weather_context", None)
    transformed["direct_reuse_mask"] = mask
    transformed["full_chain_preserved"] = True
    transformed["model_chain"] = ("PRE", "M1", "M2", "M3", "M4")
    transformed["source_artifact_hash"] = source_hash
    return transformed


def assert_no_direct_reuse_leakage(artifact: dict[str, Any]) -> None:
    mask = artifact.get("direct_reuse_mask", {})
    for field in ("upstream_hidden_history", "raw_weather_context", "realized_outcomes", "future_information"):
        if mask.get(field) == "BLOCKED" and field in artifact:
            raise ContractError(f"EXP1A_BLOCKED_FIELD_PRESENT:{field}")
    if artifact.get("full_chain_preserved") is not True:
        raise ContractError("EXP1A_FULL_CHAIN_REQUIRED")


__all__ = ["apply_direct_reuse_mask", "assert_no_direct_reuse_leakage"]
