"""Regression checks for the Section 5 contract ownership move."""

from model.common import section5_contracts as shared
from exp.jatm_section5 import contracts as compatibility


def test_section5_constants_keep_compatibility_identity() -> None:
    assert compatibility.REPRESENTATIONS is shared.REPRESENTATIONS
    assert compatibility.STAGE1_ACTIONABLE_STAGES is shared.STAGE1_ACTIONABLE_STAGES
    assert (
        compatibility.STAGE1_ACTIONABLE_STAGE_CLASSES
        is shared.STAGE1_ACTIONABLE_STAGE_CLASSES
    )
    assert compatibility.FLATTENED_UNION_SEMANTICS == shared.FLATTENED_UNION_SEMANTICS


def test_shared_contract_is_identifier_only() -> None:
    assert shared.__all__ == [
        "FLATTENED_UNION_SEMANTICS",
        "REPRESENTATIONS",
        "STAGE1_ACTIONABLE_STAGE_CLASSES",
        "STAGE1_ACTIONABLE_STAGES",
    ]
