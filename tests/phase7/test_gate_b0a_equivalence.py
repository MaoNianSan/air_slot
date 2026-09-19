"""Gate B.0a solver-authority equivalence regression."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from validation.v2_phase7.gate_b0a_equivalence import (
    DEFAULT_BASELINE_ROOT,
    DEFAULT_OUTPUT,
    validate_equivalence,
)


def test_gate_b0a_prechange_backup_exists() -> None:
    if not DEFAULT_BASELINE_ROOT.is_dir():
        pytest.skip("pre-change Gate B.0a baseline is not materialized")
    assert (DEFAULT_BASELINE_ROOT / "dag" / "RECOVERY_DECISIONS.json").is_file()


def test_solver_authority_reconciliation_is_scientifically_equivalent() -> None:
    if not DEFAULT_BASELINE_ROOT.is_dir():
        pytest.skip("pre-change Gate B.0a baseline is not materialized")
    report = validate_equivalence(baseline_root=DEFAULT_BASELINE_ROOT)
    assert report["status"] == "PASS"
    assert report["scientific_exact_equality"] is True
    assert report["failures"] == []
    assert report["historical_final_test_access_total"] == 1
    assert report["phase7_scientific_access_increment"] == 0
    assert report["final_test_paths_read"] == []


def test_committed_gate_b0a_reconciliation_report_is_pass() -> None:
    if not DEFAULT_OUTPUT.is_file():
        pytest.skip("Gate B.0a equivalence report has not been generated")
    report = json.loads(Path(DEFAULT_OUTPUT).read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["scientific_exact_equality"] is True
    assert report["phase7_scientific_access_increment"] == 0
