"""Phase 6 activation-contract tests."""

from __future__ import annotations

from validation.v2_phase6.freeze_activation import (
    ACTIVE_STATUS,
    BASELINE_COMMIT,
    BASELINE_TREE,
    F_CONTINUITY_ARTIFACT_HASH,
    M2_REFERENCE_ID,
    M3_Q20,
    build_active_registry,
    check_activation,
)


def test_active_registry_distinguishes_baseline_from_activation_commit():
    payload = build_active_registry()
    assert payload["status"] == ACTIVE_STATUS
    assert payload["not_a_formal_freeze"] is False
    assert payload["freeze_commit"] == BASELINE_COMMIT
    assert (
        payload["freeze_commit_semantics"]
        == "PRE_FREEZE_SCIENTIFIC_BASELINE_NOT_ACTIVATION_COMMIT"
    )
    assert payload["pre_freeze_baseline_commit"] == BASELINE_COMMIT
    assert payload["pre_freeze_baseline_tree"] == BASELINE_TREE
    assert payload["complete_frozen_repository_state"] == "ANNOTATED_TAG_RESOLUTION"
    assert payload["activation_tag"] == "v2-scientific-freeze"
    assert payload["activation_tag_target"] == "RESOLVED_AFTER_COMMIT"


def test_active_registry_separates_m2_m3_and_f_continuity_objects():
    payload = build_active_registry()
    m2 = payload["m2_typical_turnaround_reference"]
    m3 = payload["m3_stage2_turnaround_lower_bound"]
    scale = payload["f_continuity_cu_scale"]

    assert m2["reference_id"] == M2_REFERENCE_ID
    assert m2["scope"] == "M2_NODE_REFERENCE_BUNDLE_FOR_F_CONTINUITY"
    assert m2["statistic_id"] == "MEDIAN"
    assert m2["global_value_minutes"] == 57.0
    assert m3["scope"] == "M3_STAGE2_FEASIBILITY_ONLY"
    assert m3["value_minutes"] == M3_Q20
    assert m3["sensitivity_minutes"] == {"q10": 34.0, "q30": 47.0}
    assert scale["declared_artifact_hash"] == F_CONTINUITY_ARTIFACT_HASH
    assert scale["median"] == 44.0
    assert scale["positive_n"] == 186742
    assert scale["population_rows"] == 2668531
    assert payload["merge_forbidden"] is True
    assert payload["41_is_not_the_m2_node_reference"] is True
    assert payload["57_is_not_the_stage2_lower_bound"] is True


def test_active_registry_final_test_accounting_is_frozen():
    payload = build_active_registry()
    assert payload["final_test_access_count"] == 1
    assert payload["current_freeze_run_increment"] == 0
    assert payload["new_final_test_execution"] is False
    assert payload["phase_7_entered"] is False
    assert payload["final_test_path_touched"] is False
    assert payload["final_test_accounting"] == {
        "historical_access_total": 1,
        "current_freeze_run_increment": 0,
        "new_final_test_execution": False,
        "phase_7_entered": False,
        "final_test_path_touched": False,
        "final_test_path": "artifacts/experiment/final_test",
        "sealed": True,
    }


def test_active_registry_has_no_total_loss_and_keeps_common_basis():
    payload = build_active_registry()
    assert payload["m4_evaluation"]["L_total_constructed"] is False
    assert payload["m4_evaluation"]["common_basis_only"] is True
    assert payload["m4_evaluation"]["monetary_branch"] == "SECONDARY_INTERPRETATION_ONLY"


def test_freeze_activation_check_passes():
    result = check_activation()
    assert result["status"] == "PASS"
    assert result["freeze_commit"] == BASELINE_COMMIT
    assert result["final_test_access_count"] == 1
    assert result["current_freeze_run_increment"] == 0
