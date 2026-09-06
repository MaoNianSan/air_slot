from __future__ import annotations

import ast
from pathlib import Path

import pytest

from exp.shared.contracts import (
    PRIORITY_CONTRACT_VERSION,
    SHARED_PRIORITY_AUTHORITY,
    SharedPriorityAuthority,
)
from exp.shared.priority import (
    current_scientific_authority,
    validate_development_scope,
)

ROOT = Path(__file__).resolve().parents[2]


def test_current_scientific_authority_is_human_approved_and_frozen():
    authority = current_scientific_authority()
    assert authority == SHARED_PRIORITY_AUTHORITY
    assert authority.version == "AIR_SLOT_SHARED_PRIORITY_CONTRACT_V1_20260906"
    assert authority.authority == "HUMAN_APPROVED"
    assert authority.status == "FROZEN_FOR_EXP2_EXP3_EXP4"
    assert authority.final_test_authorized is False
    assert authority.paper_result is False


def test_contract_hash_cannot_be_replaced():
    with pytest.raises(ValueError, match="PRIORITY_CONTRACT_HASH_MISMATCH"):
        SharedPriorityAuthority(contract_hash=f"sha256:{'0' * 64}")


def test_shared_scope_forbids_final_test_access():
    validate_development_scope(final_test_access_count=0)
    with pytest.raises(
        RuntimeError, match="SHARED_PRIORITY_FINAL_TEST_ACCESS_FORBIDDEN"
    ):
        validate_development_scope(final_test_access_count=1)


def test_candidate_label_is_not_a_scientific_authority():
    source = (ROOT / "exp" / "shared" / "contracts.py").read_text(
        encoding="utf-8"
    )
    literals = {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert PRIORITY_CONTRACT_VERSION in literals
    assert "DEVELOPMENT_CANDIDATE" not in literals
