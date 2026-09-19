"""Freeze R2 authority, corpus and registry contracts."""

from __future__ import annotations

from pathlib import Path

from validation.v2_phase6_r2.corpus import (
    FIXTURES,
    U_MAX_GRID,
    actionable_cases,
    corpus_manifest,
    typed_non_actionable_cases,
)
from validation.v2_phase6_r2.freeze import (
    BASE_REGISTRY_ARTIFACT_HASH,
    BASE_REGISTRY_FILE_SHA256,
    BASE_TAG_OBJECT,
    BASE_TAG_TARGET_COMMIT,
    FREEZE_COMMIT,
    FREEZE_COMMIT_SEMANTICS,
    R2_COMMIT_MESSAGE,
    SCHEMA_VERSION,
    STATUS_ACTIVE,
    TAG_TARGET,
    build_registry_payload,
    check_all,
)
from validation.v2_phase6_r2.common import (
    BASE_REGISTRY_PATH,
    R2_REGISTRY_PATH,
    RECONCILIATION_PATH,
    file_hash,
    payload_hash,
    read_json,
)


def test_base_freeze_registry_and_tag_are_immutable() -> None:
    base = read_json(BASE_REGISTRY_PATH)
    assert file_hash(BASE_REGISTRY_PATH) == BASE_REGISTRY_FILE_SHA256
    assert base["artifact_hash"] == BASE_REGISTRY_ARTIFACT_HASH
    assert payload_hash(base) == BASE_REGISTRY_ARTIFACT_HASH
    assert BASE_TAG_OBJECT == "35d5fe1896dd9e17be92bec601f87ec33adb4d56"
    assert (
        BASE_TAG_TARGET_COMMIT
        == "d29fc769e74d6b46f86d3fdf7db18b3f9936f8b1"
    )


def test_r2_registry_declares_highs_as_formal_authority() -> None:
    payload = build_registry_payload()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["status"] == STATUS_ACTIVE
    assert payload["freeze_commit"] == FREEZE_COMMIT
    assert payload["freeze_commit_semantics"] == FREEZE_COMMIT_SEMANTICS
    assert payload["activation_tag"] == "v2-scientific-freeze-r2"
    assert payload["activation_tag_target"] == TAG_TARGET
    assert payload["formal_solver"] == "PYOMO_HIGHS"
    assert payload["parity_oracle"] == "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID"
    assert payload["objective_perturbation"] == "NONE"
    assert payload["long_term_deviation"] is False
    assert payload["stage2_solver"]["formal_path"] == "PYOMO_HIGHS"
    assert payload["stage2_solver"]["parity_backend"] == (
        "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID"
    )
    assert payload["stage2_solver"]["parity_scope"] == (
        "ALL_AVAILABLE_NON_TEST_STAGE2_VALIDATION_CORPUS"
    )
    assert payload["stage2_solver"]["tie_rule"] == (
        "u*=min{u in U_i(theta): J_i(u)=min J_i}"
    )
    assert payload["phase6_r2_activation"]["commit_message"] == R2_COMMIT_MESSAGE
    assert payload["phase6_r2_activation"]["action_disagreements_allowed"] is False


def test_r2_registry_preserves_original_bytes_and_final_test_boundary() -> None:
    payload = build_registry_payload()
    assert payload["parent_freeze"]["registry_file_sha256"] == (
        BASE_REGISTRY_FILE_SHA256
    )
    assert payload["parent_freeze"]["immutable"] is True
    assert payload["r2_final_test_accounting"] == {
        "historical_access_total": 1,
        "current_freeze_run_increment": 0,
        "current_total": 1,
        "new_final_test_execution": False,
        "phase_7_entered": False,
        "final_test_path_touched": False,
    }
    assert file_hash(R2_REGISTRY_PATH) == (
        "sha256:15c1e8bf5ec5fbb5ee783595a124b1255b550d7d7bc96e34b2cd3df0a4e88e6f"
    )


def test_r2_corpus_is_complete_and_contains_tie_cases() -> None:
    actionable = actionable_cases()
    typed = typed_non_actionable_cases()
    manifest = corpus_manifest()
    assert len(actionable) == 720
    assert len(typed) == 2
    assert manifest["actionable_case_count"] == 720
    assert manifest["total_case_count"] == 722
    assert tuple(manifest["dimensions"]["fixtures"]) == tuple(
        fixture.fixture_id for fixture in FIXTURES
    )
    assert list(U_MAX_GRID) == [0.0, 5.0, 10.0, 25.0, 45.0, 75.0]
    tie = [
        case
        for case in actionable
        if case.fixture_id == "DEFAULT_TURN"
        and case.headroom_summary.u_max == 10.0
        and case.policy.lambda_policy == 0.25
        and abs(case.service.registry.scale("F_continuity") - 8.88888888888889)
        <= 1e-12
    ]
    assert len(tie) == 2


def test_r2_reconciliation_passes_without_action_disagreements(
    reconciliation_report,
) -> None:
    report = reconciliation_report
    assert report["status"] == "PASS"
    assert report["counts"]["actionable_cases"] == 720
    assert report["counts"]["typed_non_actionable_cases"] == 2
    assert report["counts"]["action_disagreements"] == 0
    assert report["counts"]["tie_break_cases"] >= 2
    assert report["counts"]["near_tie_candidate_count_max"] >= 2
    assert report["error_summary"]["objective_absolute_error_max"] <= 1e-6
    assert (
        report["error_summary"]["recoverable_value_absolute_error_max"] <= 1e-6
    )
    assert report["failures"] == []
    assert report["final_test_access_count"] == 1
    assert report["current_freeze_run_increment"] == 0
    assert report["new_final_test_execution"] is False
    assert report["phase_7_entered"] is False
    assert report["no_final_test_path_read"] is True


def test_r2_written_registry_and_report_are_byte_consistent() -> None:
    result = check_all()
    assert result["status"] == "PASS"
    assert result["failures"] == []
    assert result["registry_file_sha256"] == file_hash(R2_REGISTRY_PATH)
    assert file_hash(RECONCILIATION_PATH).startswith("sha256:")
