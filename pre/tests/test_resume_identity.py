from __future__ import annotations

from dataclasses import replace

from src.core.contracts import RESEARCH_CODE_REVISION
from src.core.resume_contract import compare_resume_contract
from test_staging_resume_contract import _contract


def test_resume_hard_identity_and_provenance_are_separate() -> None:
    expected = _contract()
    provenance_changed = replace(
        expected,
        git_commit="2" * 40,
        git_dirty=not expected.git_dirty,
        implementation_hash="4" * 64,
    )
    provenance = compare_resume_contract(expected, provenance_changed)
    assert provenance["compatible"] is True
    assert len(provenance["warnings"]) == 3

    revision_changed = replace(
        expected,
        research_code_revision=RESEARCH_CODE_REVISION + "_CHANGED",
    )
    hard = compare_resume_contract(expected, revision_changed)
    assert hard["compatible"] is False
    assert "research_code_revision" in hard["differences"]
