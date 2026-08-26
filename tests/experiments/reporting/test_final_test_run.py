"""Current Final Test RMB orchestrator contract tests."""

from __future__ import annotations

import json

from exp.reporting.final_test_run import (
    CHAIN_MANIFEST,
    EXP3,
    ROOT,
    SCOPE,
    SCHEMA_VERSION,
    _exp3_contract_valid,
    _status,
)


def test_scope_and_schema_contract():
    assert SCOPE == "FINAL_TEST_OUT_OF_TIME_2019_10_12"
    assert SCHEMA_VERSION == "AIR_SLOT_FINAL_TEST_RMB_CHAIN_MANIFEST_V2"


def test_completed_run_status_is_terminal_and_typed():
    status = _status(ROOT)
    assert status["q4_inputs"] == "PASS"
    assert status["preflight"] == "PASS"
    assert status["exp2b"] == "ABSTAIN_MONETARY_COMPONENT_NOT_IN_SCOPE"
    assert status["exp3"] == "PASS"
    assert status["support_gate"] == "PASS"
    assert status["exp4"] == "PASS"
    assert status["reporting"] == "PASS"


def test_exp3_v2_publication_contract():
    assert _exp3_contract_valid(ROOT)
    manifest = json.loads((ROOT / EXP3 / "EXP3_FINAL_TEST_RMB_EXECUTION_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "EXP3_FINAL_TEST_RMB_EXECUTION_MANIFEST_V2"
    assert manifest["safety"]["MODEL_RETRAINED"] is False
    assert manifest["safety"]["PARAMETER_RESELECTED"] is False


def test_chain_manifest_outputs_are_published():
    payload = json.loads((ROOT / CHAIN_MANIFEST).read_text(encoding="utf-8"))
    assert payload["status"] == "COMPLETE"
    assert payload["scope"] == SCOPE
    assert payload["evaluation_overlap"]["evaluation_row_overlap"] == 0
    assert payload["outputs"]["section5_results"].endswith(
        "artifacts/paper_results_v2_final_test_rmb/SECTION5_FINAL_RESULTS.json"
    )
