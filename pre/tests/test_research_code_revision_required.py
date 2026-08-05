from __future__ import annotations

from dataclasses import replace

from src.core.resume_contract import compare_resume_contract
from test_staging_resume_contract import _contract


def test_research_code_revision_difference_rejects_resume() -> None:
    expected = _contract()
    actual = replace(expected, research_code_revision="AIR_CHAIN_CORE_V2_R1")
    comparison = compare_resume_contract(expected, actual)
    assert not comparison["compatible"]
    assert "research_code_revision" in comparison["differences"]
