"""Materialized Phase 5 artifact contracts (Development evidence only)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "diagnostics" / "v2_phase5_development"
FREEZE_PATH = ROOT / "registries" / "v2_scientific_freeze_draft.json"
RUN_SUMMARY_PATH = PHASE_DIR / "PHASE5_RUN_SUMMARY.json"


def _read(path: Path):
    if not path.is_file():
        pytest.skip(f"Phase 5 artifact not materialized: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def test_family_a_reports_development_metrics_without_directional_claims():
    payload = _read(PHASE_DIR / "FAMILY_A_STATE_FAMILIES.json")
    assert payload["status"] == "PASS"
    assert payload["artifact_scope"] == "DEVELOPMENT_ONLY"
    assert payload["directional_claims"] == "NONE"
    assert payload["ranking_performed"] is False
    assert payload["selection_use"] == "NOT_USED_FOR_HISTORY_PRIMARY_SELECTION"
    assert payload["loss_metrics_used"] == {
        "L_att": False,
        "L_rec": False,
        "L_total": False,
    }
    assert payload["final_test_access_count"] == 0
    assert set(payload["models"]) == {
        "HISTORY_H16_PRIMARY",
        "CURRENT_H16_COMPARATOR",
        "HISTORY_H8_SENSITIVITY",
    }


def test_family_b_uses_representation_specific_variogram_rows():
    payload = _read(PHASE_DIR / "FAMILY_B_REPRESENTATION_FAMILIES.json")
    assert payload["status"] == "PASS"
    assert payload["directional_claims"] == "NONE"
    assert payload["ranking_performed"] is False
    assert payload["loss_metrics_used"] == {
        "L_att": False,
        "L_rec": False,
        "L_total": False,
    }
    rows_contract = payload["variogram_rows_artifact"]
    assert rows_contract["cross_representation_sharing"] is False
    assert rows_contract["note"] == "VARIogram_ROWS_ARE_REPRESENTATION_SPECIFIC"
    rows_path = PHASE_DIR / "FAMILY_B_VARIogram_ROWS.npz"
    if not rows_path.is_file():
        pytest.skip(f"Phase 5 artifact not materialized: {rows_path}")
    with np.load(rows_path) as arrays:
        for key in (
            "joint_variogram_rows",
            "point_variogram_rows",
            "marginal_variogram_rows",
        ):
            assert key in arrays.files
        assert not np.shares_memory(
            arrays["joint_variogram_rows"], arrays["point_variogram_rows"]
        )
        assert not np.shares_memory(
            arrays["joint_variogram_rows"], arrays["marginal_variogram_rows"]
        )
        assert not np.shares_memory(
            arrays["point_variogram_rows"], arrays["marginal_variogram_rows"]
        )


def test_freeze_draft_remains_pending_and_has_no_manuscript_sensitivity_grid():
    payload = _read(FREEZE_PATH)
    assert payload["status"] == "DRAFT_NOT_ACTIVATED"
    assert payload["freeze_commit"] == "PENDING"
    assert payload["not_a_formal_freeze"] is True
    assert payload["activation_owner"] == "PHASE_6_SCIENTIFIC_FREEZE"
    assert payload["final_test_access_count"] == 1
    assert payload["new_final_test_execution"] is False
    sensitivity = payload["predefined_sensitivity"]["m_cs"]
    assert sensitivity["nominal"] == pytest.approx(0.90)
    assert sensitivity["grid"] == []
    assert sensitivity["status"] == "NO_MANUSCRIPT_PREDEFINED_SENSITIVITY_VALUES"
    assert payload["m4_evaluation"]["L_total_constructed"] is False
    assert payload["stage2_solver"]["formal_path"] == (
        "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID"
    )
    assert payload["stage2_solver"]["parity_backend"] == "PYOMO_HIGHS"


def test_phase5_run_summary_preserves_final_test_boundary():
    payload = _read(RUN_SUMMARY_PATH)
    assert payload["status"] == "PASS"
    assert payload["artifact_scope"] == "DEVELOPMENT_ONLY"
    assert payload["final_test_access_count"] == 1
    assert payload["new_final_test_execution"] is False
    assert payload["no_final_test_path_read"] is True
    assert payload["push_performed"] is False
