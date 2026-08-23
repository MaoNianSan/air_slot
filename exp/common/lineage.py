"""Formal experiment lineage helpers."""

from __future__ import annotations

from typing import Mapping

from model.common.errors import ContractError


REQUIRED_HASH_KEYS = (
    "model_hash", "schema_hash", "cohort_hash", "scenario_hash",
    "support_hash", "m2_hash", "mapping_hash", "risk_policy_hash",
)


def validate_formal_lineage(lineage: Mapping[str, str]) -> dict[str, str]:
    missing = [key for key in REQUIRED_HASH_KEYS if not str(lineage.get(key, "")).startswith("sha256:")]
    if missing:
        raise ContractError("FORMAL_LINEAGE_HASH_MISSING:" + ",".join(missing))
    return {key: str(lineage[key]) for key in REQUIRED_HASH_KEYS}


def build_formal_lineage(*, experiment: str, variant: str, hashes: Mapping[str, str]) -> dict[str, str]:
    bound = validate_formal_lineage(hashes)
    return {"experiment": experiment, "variant": variant, **bound}


__all__ = ["REQUIRED_HASH_KEYS", "build_formal_lineage", "validate_formal_lineage"]
