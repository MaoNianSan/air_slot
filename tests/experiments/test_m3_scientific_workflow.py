"""Focused invariants for the fail-closed M3 scientific workflow."""

from __future__ import annotations

import json
from pathlib import Path

from model.M3.registry import PRINCIPAL_IDS


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "artifacts/diagnostics/m3_scientific_workflow_v11/M3_SCIENTIFIC_WORKFLOW_REPORT.json"


def test_workflow_report_preserves_action_identity_and_safety():
    assert REPORT.is_file()
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    checks = report["scientific_checks"]
    assert checks["action_count"] == 23
    assert checks["action_identity_preserved"] is True
    assert tuple(checks["executable_action_ids"]) == PRINCIPAL_IDS
    assert checks["non_a00_executable_count"] == 22
    assert report["safety"] == {
        "M1_TRAINING_RUNS": 0,
        "TUNING_RUNS": 0,
        "EXP2_RUNS": 0,
        "EXP3_RUNS": 0,
        "EXP4_RUNS": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "FULL": False,
        "PAPER_FULL_RUN": False,
    }


def test_workflow_stage_outputs_are_hash_bound_and_complete():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert set(report["stages"]) == {
        "consequence_mapping",
        "action_library",
        "m2_rmb_interface",
        "cu_rmb_readiness_audit",
        "conditional_action_support",
        "conditional_support_binding",
        "formal_support_audit",
        "exp3_preparation",
        "exp4_preparation",
        "scientific_reconciliation",
    }
    for stage in report["stages"].values():
        assert stage["status"] == "COMPLETED"
        for output in stage["outputs"].values():
            path = Path(output["path"])
            assert path.is_file()
            import hashlib

            assert output["sha256"] == f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
