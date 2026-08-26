"""Current Final Test RMB orchestrator contract tests."""

from __future__ import annotations

import json

from exp.reporting.final_test_run import (
    CHAIN_MANIFEST,
    EXP2,
    EXP3,
    EXP4,
    M3M4,
    ROOT,
    SCOPE,
    SCHEMA_VERSION,
    _exp3_contract_valid,
    _status,
)
from exp.common.official_execution import file_sha256


def test_scope_and_schema_contract():
    assert SCOPE == "FINAL_TEST_OUT_OF_TIME_2019_10_12"
    assert SCHEMA_VERSION == "AIR_SLOT_FINAL_TEST_RMB_CHAIN_MANIFEST_V2"


def test_completed_run_status_is_terminal_and_typed():
    status = _status(ROOT)
    assert status["q4_inputs"] == "PASS"
    assert status["preflight"] == "PASS"
    assert status["exp2b"] == "PASS"
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


def test_final_test_repair_artifacts_are_typed_and_component_specific():
    variogram = json.loads((ROOT / EXP2 / "EXP2A_FINAL_TEST_VARIOGRAM_SUMMARY.json").read_text(encoding="utf-8"))
    contrasts = json.loads((ROOT / EXP2 / "EXP2A_FINAL_TEST_VARIOGRAM_CONTRASTS.json").read_text(encoding="utf-8"))
    distortion = json.loads((ROOT / EXP2 / "downstream_distortion" / "EXP2B_FINAL_TEST_DOWNSTREAM_DISTORTION_MANIFEST.json").read_text(encoding="utf-8"))
    assert variogram["representation_specific_inputs"] is True
    assert [row["representation"] for row in variogram["summary_rows"]] == ["Point", "Marginal", "Joint"]
    assert {row["contrast"] for row in contrasts["contrast_rows"]} == {
        "Point minus Joint", "Marginal minus Joint",
    }
    assert len(distortion["summary_rows"]) == 14
    assert all(
        row["support_status"] in {"SUPPORTED_COMMON_FINITE_SUPPORT", "ABSTAIN_NO_COMMON_SUPPORT"}
        for row in distortion["summary_rows"]
    )
    assert any(row["component"] == "P_itinerary" for row in distortion["summary_rows"])
    assert distortion["monetary_aggregation"] == "NOT_PERFORMED_COMPONENT_LEVEL_CU_ONLY"


def test_final_test_exp4_predecessor_support_and_h32_typed_crps_na():
    metrics = json.loads((ROOT / EXP4 / "EXP4_FINAL_TEST_METRICS.json").read_text(encoding="utf-8"))["aggregate"]
    for method in ("HISTORICAL", "LIGHTGBM", "RANDOM_FOREST", "STATE_AWARE_H32"):
        target = metrics[f"{method}:T_IB_A00"]
        assert target["mae_node_count"] > 0
        assert target["mae_episode_count"] > 0
    for target in ("D_OB", "D_TX"):
        h32 = metrics[f"STATE_AWARE_H32:{target}"]
        assert h32["crps_minutes"] is None
        assert h32["crps_status"] == "NA_NOT_SAVED_BY_M1"


def test_exp3_and_m3m4_frozen_artifacts_are_unchanged_by_repairs():
    expected = {
        ROOT / EXP3 / "EXP3_FINAL_TEST_RMB_ACTION_RISK.parquet": "sha256:a1a13d1d8f3163488cd7fe126aaacb56e25173e7f1ea8cb945fdcd729437ddcc",
        ROOT / EXP3 / "EXP3_FINAL_TEST_RMB_METRICS.json": "sha256:63b8d5d1b236231535f756445b6ae0fc13dc14363d0c01fede92b53e83e0509e",
        ROOT / EXP3 / "EXP3_FINAL_TEST_RMB_EXECUTION_MANIFEST.json": "sha256:230f16b23974517cf61276664452821871fd579394316208ca8ee1a0e51ad696",
        ROOT / M3M4 / "M3M4_FINAL_TEST_RMB_MANIFEST.json": "sha256:7ffccdd05c4814438ecb8f56e03a7a33ef63f7529d5555c41ddaab0aa6da1f83",
        ROOT / M3M4 / "A00_FINAL_TEST_RMB_GATE_SUMMARY.json": "sha256:2e2eb2534be9fda99813ecfb6b4790cf051da4a3888593b6831e3008a38ab99c",
    }
    assert {path: file_sha256(path) for path in expected} == expected
