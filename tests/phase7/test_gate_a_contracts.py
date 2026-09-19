"""Freeze R2, cohort, and Gate-A dry-run contract tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from formal import v2_phase7_final_test_run as runner


def test_r2_authority_and_instruction_copies_are_frozen() -> None:
    authority = runner.validate_r2_authority()
    assert authority["status"] == "PASS"
    assert authority["tag"] == "v2-scientific-freeze-r2"
    assert authority["tag_object"] == runner.R2_TAG_OBJECT
    assert authority["tag_target_commit"] == runner.R2_TAG_TARGET_COMMIT
    assert authority["formal_solver"] == "PYOMO_HIGHS"
    assert authority["parity_oracle"] == (
        "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID"
    )
    assert authority["objective_perturbation"] == "NONE"
    assert authority["long_term_deviation"] is False
    assert authority["numerical_tolerance"] == {
        "name": "M3_NUMERICAL_COMPARISON_TOLERANCE",
        "value": 1e-6,
        "scientific_parameter": False,
    }
    assert authority["reconciliation"]["counts"]["action_disagreements"] == 0
    assert authority["reconciliation"]["counts"]["actionable_cases"] == 720
    assert authority["final_test_accounting"] == {
        "historical_access_total": 1,
        "current_freeze_run_increment": 0,
        "current_total": 1,
        "new_final_test_execution": False,
        "phase_7_entered": False,
    }

    instruction = runner.validate_instruction_copies()
    assert instruction["status"] == "PASS"
    assert instruction["byte_identical"] is True
    assert instruction["sha256"].startswith("sha256:")


def test_active_stage2_authority_is_enumeration_primary() -> None:
    active = runner.validate_stage2_production_authority()
    assert active["status"] == "PASS"
    contract = active["active_contract"]
    assert contract["stage2_primary_solver"] == (
        "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID"
    )
    assert contract["final_test_primary_solver"] == (
        "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID"
    )
    assert contract["highs_role"] == "PARITY_BACKEND_ONLY"
    assert contract["highs_required_for_production_rows"] is False
    assert contract["deterministic_tie_break"] == "SMALLEST_U"
    assert contract["solver_status_semantics"] == (
        "STAGE2_SOLVER_BACKEND_IDENTITY_NOT_TERMINATION_STATE"
    )
    assert active["historical_registry_labels"]["formal_solver"] == (
        "PYOMO_HIGHS"
    )
    assert active["historical_registry_labels"]["semantics"] == (
        "HISTORICAL_PROVENANCE_ONLY_SUPERSEDED_BY_ACTIVE_CONTRACT"
    )
    assert runner.validate_phase7_authority()[
        "stage2_production_authority"
    ] == active


def test_r2_text_artifact_hashes_bind_canonical_lf_bytes() -> None:
    authority = runner.validate_r2_authority()
    compatibility = authority["text_artifact_hash_compatibility"]
    f_continuity = compatibility["f_continuity_cu_scale"]
    train_support = compatibility["train_support_summary"]

    assert f_continuity["canonical_lf_sha256"] == (
        "sha256:b335b19564c1eaf827ed0d343405dc9e9871fd0284e546be28ab987884e507c0"
    )
    assert f_continuity["declared_worktree_sha256"] == (
        "sha256:688560356d5c7fa292b59e5a7b45cf249619c35bf6620446b1166034a5a2e061"
    )
    assert train_support["canonical_lf_sha256"] == (
        "sha256:27df8b4ea406b48ca7b494e48759edfeaf490a501ce2b6293638bbd7a2cce4c2"
    )
    assert train_support["declared_worktree_sha256"] == (
        "sha256:35e570a5b9f718d44f9b60d2c0525d53c756529a590865f511a7aef1be5436bc"
    )
    assert f_continuity["semantics"] == train_support["semantics"]
    assert "NUMERIC_PAYLOAD_UNCHANGED" in f_continuity["semantics"]


def test_cohort_reference_is_reused_not_reselected() -> None:
    cohort = runner.validate_cohort_reference()
    assert cohort["status"] == "PASS"
    assert cohort["selected_episode_count"] == 128
    assert cohort["selected_episode_hash"] == runner.SELECTED_EPISODE_HASH
    assert cohort["final_test_cohort_reused"] is True
    assert cohort["final_test_cohort_reselected"] is False
    assert cohort["raw_q4_read"] is False
    assert cohort["historical_access_total"] == 1


def test_gate_a_dry_run_preserves_typed_states_and_reference_invariants() -> None:
    result = runner.run_dry_run()
    assert result["status"] == "PASS"
    assert result["final_test_data_scientific_read_during_dry_run"] is False
    assert result["q4_raw_read"] is False
    assert (
        result[
            "legacy_final_test_result_tree_scientific_read_during_dry_run"
        ]
        is False
    )
    assert result[
        "legacy_final_test_result_tree_incidental_repository_audit_reads"
    ] == 1
    assert result[
        "legacy_final_test_result_tree_reads_used_for_scientific_computation"
    ] is False
    assert result[
        "legacy_final_test_result_tree_reads_used_for_selection"
    ] is False
    assert result["phase7_scientific_access_increment"] == 0
    assert result["parity"]["status"] == "PASS"
    assert result["parity"]["formal_solver"] == "PYOMO_HIGHS"
    assert result["parity"]["parity_oracle"] == (
        "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID"
    )
    assert result["stage2"]["formal_solver"] == "PYOMO_HIGHS"
    assert result["stage2"]["parity_oracle"] == "EXACT_ENUMERATION"
    assert result["stage2"]["stage2_primary_solver"] == (
        runner.STAGE2_PRIMARY_SOLVER
    )
    assert result["stage2"]["final_test_primary_solver"] == (
        runner.FINAL_TEST_PRIMARY_SOLVER
    )
    assert result["stage2"]["highs_role"] == runner.HIGHS_ROLE
    assert result["stage2"]["highs_required_for_production_rows"] is False
    assert result["stage2"]["deterministic_tie_break"] == (
        runner.DETERMINISTIC_TIE_BREAK
    )
    assert result["stage2"]["solver_status_semantics"] == (
        runner.SOLVER_STATUS_SEMANTICS
    )
    assert result["stage2"]["u_star_formal"] == result["stage2"]["u_star_oracle"]
    assert result["stage2"]["objective_absolute_error"] <= 1e-6
    assert result["stage2"]["recoverable_value_absolute_error"] <= 1e-6
    assert result["stage2"]["recoverable_value_formal"] >= -1e-6
    assert result["stage2"]["typed_states"] == {
        "NOT_ACTIONABLE": True,
        "UNDEFINED_ZERO_RECOVERABLE_VALUE": True,
        "N/A_NOT_DEFINED": True,
    }
    assert result["stage2"]["reference_invariants"] == {
        "L_att": 0.0,
        "L_rec": 0.0,
        "A0": 1.0,
        "A5": 1.0,
    }
    grids = result["stage2"]["action_grid_by_specification"]
    assert grids["Q80"][-1] == 25.0
    assert grids["nominal"][-1] == 45.0
    assert grids["Q95"][-1] == 75.0


def test_run_gate_a_writes_ready_preflight_without_access(tmp_path: Path) -> None:
    result = runner.run_gate_a(output_root=tmp_path)
    assert result["status"] == "READY_FOR_GATE_B"
    assert result["gate_b_authorized"] is False
    assert result["gate_a_commit"] == "RESOLVED_AFTER_GATE_A_COMMIT" or re.fullmatch(
        r"[0-9a-f]{40}", result["gate_a_commit"]
    )
    assert result["access_boundary"] == {
        "q4_raw_reads": 0,
        "repository_level_rg_incidental_audit_reads": 1,
        "legacy_final_test_result_tree_incidental_audit_reads": 1,
        "legacy_final_test_result_tree_scientific_reads": 0,
        "legacy_final_test_result_tree_reads_used_for_scientific_computation": 0,
        "legacy_final_test_result_tree_reads_used_for_selection": 0,
        "phase7_scientific_access_increment": 0,
        "final_test_data_reads": 0,
        "legacy_final_test_writes": 0,
        "allow_final_test_true_occurrences": 0,
        "gate_b_release_present": False,
        "phase7_access_epoch_opened": False,
    }
    assert result["final_test_accounting"]["current_total"] == 1
    assert result["final_test_accounting"]["current_freeze_run_increment"] == 0

    preflight_path = tmp_path / runner.GATE_A_PREFLIGHT_PATH.name
    dry_run_path = tmp_path / runner.GATE_A_DRY_RUN_PATH.name
    assert json.loads(preflight_path.read_text(encoding="utf-8")) == result
    assert json.loads(dry_run_path.read_text(encoding="utf-8")) == result["dry_run"]


def test_legacy_final_test_tree_is_guard_blocked() -> None:
    with pytest.raises(runner.TypedBlocker) as error:
        runner._read_json(runner.LEGACY_FINAL_TEST_ROOT / "forbidden.json")
    assert error.value.code == "LEGACY_FINAL_TEST_TREE_ACCESS_FORBIDDEN"
