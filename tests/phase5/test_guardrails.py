"""Phase 5 release-boundary and draft-freeze guardrails."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from validation.v2_phase5.common import FINAL_TEST_ROOT, Phase5GuardError, assert_development_path
from validation.v2_phase5.freeze import (
    DRAFT_STATUS,
    FREEZE_COMMIT,
    REGISTRY_PATH,
)


PHASE5_ROOT = Path(__file__).resolve().parents[2] / "validation" / "v2_phase5"
READ_CALLS = {"read_text", "read_bytes", "read_parquet", "open"}


def test_phase5_guard_rejects_every_final_test_path():
    with pytest.raises(Phase5GuardError, match="PHASE5_FINAL_TEST_PATH_FORBIDDEN"):
        assert_development_path(FINAL_TEST_ROOT / "anything")
    with pytest.raises(Phase5GuardError, match="PHASE5_FINAL_TEST_PATH_FORBIDDEN"):
        assert_development_path(FINAL_TEST_ROOT / "nested" / "file.parquet")


def test_phase5_source_has_no_direct_final_test_read_call():
    violations = []
    for path in sorted(PHASE5_ROOT.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name not in READ_CALLS:
                continue
            source = ast.get_source_segment(text, node) or ""
            if "final_test" in source.lower():
                violations.append(f"{path.name}:{node.lineno}:{source}")
    assert violations == []


def test_freeze_draft_status_and_commit_are_never_activated():
    assert DRAFT_STATUS == "DRAFT_NOT_ACTIVATED"
    assert FREEZE_COMMIT == "PENDING"
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert payload["registry_id"] == "M2_DATA2_FORMAL_CU_V5"
    assert payload["final_test_access_count"] == 0


def _assert_no_constructed_total_loss(payload, path):
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"L_total", "L_total_constructed"}:
                assert value is False, (path, key, value)
            _assert_no_constructed_total_loss(value, path)
    elif isinstance(payload, list):
        for value in payload:
            _assert_no_constructed_total_loss(value, path)


def test_phase5_artifacts_never_construct_total_loss():
    phase_dir = (
        Path(__file__).resolve().parents[2]
        / "artifacts"
        / "diagnostics"
        / "v2_phase5_development"
    )
    for path in sorted(phase_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        _assert_no_constructed_total_loss(payload, path)
    freeze = (
        Path(__file__).resolve().parents[2]
        / "registries"
        / "v2_scientific_freeze_draft.json"
    )
    if freeze.is_file():
        payload = json.loads(freeze.read_text(encoding="utf-8"))
        assert payload["status"] == "DRAFT_NOT_ACTIVATED"
        assert payload["freeze_commit"] == "PENDING"
        assert payload["m4_evaluation"]["L_total_constructed"] is False
        _assert_no_constructed_total_loss(payload, freeze)
