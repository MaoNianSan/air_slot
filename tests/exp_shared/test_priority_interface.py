from __future__ import annotations

import ast
from pathlib import Path

import pytest

from exp.shared.contracts import (
    CURRENT_AGGREGATION_CANDIDATE,
    PriorityAggregationCandidate,
)
from exp.shared.priority import (
    current_aggregation_candidate,
    validate_development_scope,
)

ROOT = Path(__file__).resolve().parents[2]


def test_current_aggregation_is_explicitly_candidate_only():
    candidate = current_aggregation_candidate()
    assert candidate == CURRENT_AGGREGATION_CANDIDATE
    assert candidate.status == "DEVELOPMENT_CANDIDATE"
    assert candidate.formal_protocol_id is None
    assert candidate.final_test_authorized is False
    assert candidate.paper_result is False


def test_candidate_model_rejects_protocol_registration():
    with pytest.raises(ValueError, match="PRIORITY_AGGREGATION_PROTOCOL_NOT_REGISTERED"):
        PriorityAggregationCandidate(
            candidate_id="candidate",
            formal_protocol_id="RECOVERY_PRIORITY_PROTOCOL_V1",
        )


def test_shared_scope_forbids_final_test_access():
    validate_development_scope(final_test_access_count=0)
    with pytest.raises(
        RuntimeError, match="SHARED_PRIORITY_FINAL_TEST_ACCESS_FORBIDDEN"
    ):
        validate_development_scope(final_test_access_count=1)


def test_no_final_protocol_is_registered_in_interface_source():
    source = (ROOT / "exp" / "shared" / "priority.py").read_text(encoding="utf-8")
    assert "RECOVERY_PRIORITY_PROTOCOL_V1" not in source
    literals = {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not {"FINAL", "FROZEN", "FINAL_PROTOCOL", "FROZEN_PROTOCOL"} & literals
