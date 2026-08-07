from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..m3.contracts import ActionCatalogEntry


@dataclass(frozen=True)
class StageCompatibility:
    configured: bool
    applicable: bool
    mapped_stage: str | None
    reason_code: str
    mapping_version: str | None
    test_only: bool


def evaluate_stage(
    action: ActionCatalogEntry,
    *,
    source_stage: str | None,
    mapping: Mapping[str, str] | None,
    mapping_version: str | None,
    mapping_test_only: bool,
) -> StageCompatibility:
    if action.action_id == "A00":
        return StageCompatibility(
            configured=True,
            applicable=True,
            mapped_stage=None,
            reason_code="FORMAL_SUPPORTED",
            mapping_version=mapping_version,
            test_only=mapping_test_only,
        )
    if source_stage is None or mapping is None or source_stage not in mapping:
        return StageCompatibility(
            configured=False,
            applicable=False,
            mapped_stage=None,
            reason_code="STAGE_CONTRACT_NOT_FROZEN",
            mapping_version=mapping_version,
            test_only=mapping_test_only,
        )
    mapped = str(mapping[source_stage])
    applicable = mapped in action.applicable_stage
    return StageCompatibility(
        configured=True,
        applicable=applicable,
        mapped_stage=mapped,
        reason_code="FORMAL_SUPPORTED" if applicable else "STAGE_NOT_APPLICABLE",
        mapping_version=mapping_version,
        test_only=mapping_test_only,
    )
