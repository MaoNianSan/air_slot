from __future__ import annotations

from dataclasses import replace

from src.core.resume_contract import compare_resume_contract
from test_staging_resume_contract import _contract


def test_git_and_implementation_changes_only_warn() -> None:
    expected = _contract()
    actual = replace(
        expected,
        git_commit="9" * 40,
        git_dirty=not expected.git_dirty,
        implementation_hash="8" * 64,
    )
    comparison = compare_resume_contract(expected, actual)
    assert comparison["compatible"]
    codes = {warning["code"] for warning in comparison["warnings"]}
    assert "GIT_COMMIT_CHANGED_WARNING" in codes
    assert "IMPLEMENTATION_HASH_CHANGED_WARNING" in codes
