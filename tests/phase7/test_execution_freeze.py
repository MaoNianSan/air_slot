"""Execution-freeze authority and Gate-B pre-open tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from formal import v2_phase7_final_test_run as runner
from formal.v2_phase7 import constants as C
from formal.v2_phase7 import execution_freeze as freeze


@pytest.fixture(scope="module")
def freeze_payload() -> dict[str, object]:
    return freeze.build_execution_freeze()


def test_freeze_is_content_addressed_not_head_addressed(
    freeze_payload: dict[str, object],
) -> None:
    assert freeze_payload["status"] == "FROZEN_PRE_OPEN_AUTHORITY"
    assert freeze_payload["development_selection_closed"] is True
    assert str(freeze_payload["artifact_hash"]).startswith("sha256:")
    assert (
        freeze_payload["dirty_change_classification"]["authority_scope"]
        == "CONTENT_ADDRESSED_RUNTIME_NOT_GIT_HEAD"
    )
    assert (
        freeze_payload["final_test_accounting"][
            "new_stage_matched_epoch_access_count_before_open"
        ]
        == 0
    )


def test_frozen_scientific_contract_is_stage_matched(
    freeze_payload: dict[str, object],
) -> None:
    contract = freeze_payload["scientific_contract"]
    assert contract["stage1_stages"] == ["PRE_IB", "POST_IB_PRE_OB"]
    assert contract["pooled_stage1_ranking"] is False
    assert contract["taxi_comp_stage1_participation"] is False
    assert (
        contract["stage1_overall_aggregation"]
        == "PRE_TURN_OBJECTIVE_THEN_NORMALIZE"
    )
    assert contract["transition_coordinate"] == "NODE_RELATIVE_SOBT"
    assert contract["section5_primary_model"] == "H16_FROZEN_PRIMARY"
    assert contract["formal_executor_reconciliation"] == (
        "SCIENTIFIC_OUTPUT_COMPLETENESS"
    )
    assert contract["paired_marginal_increment"] == (
        "FROZEN_AND_EXECUTABLE"
    )
    assert contract["section5_robustness"] == (
        "FROZEN_AND_EXECUTABLE"
    )
    assert (
        contract["stage2_reference_cohort_rule"]
        == "SUPPORT_QUALIFIED_UNION_OF_PRE_TURN_Q10_CONSEQUENCE_SHORTLISTS"
    )
    epoch = freeze_payload["stage_matched_final_test_epoch"]
    assert epoch["output_root"] == str(C.STAGE_MATCHED_FINAL_TEST_ROOT)
    assert epoch["human_release_required"] is True
    assert epoch["pre_open_gate_required"] is True


def test_governance_delta_is_epoch_scoped_access_only(
    freeze_payload: dict[str, object],
) -> None:
    delta = freeze_payload["governance_delta"]
    assert delta["classification"] == "FORMAL_EXECUTION_COMPLETENESS_ONLY"
    assert delta["scope"] == (
        "PAIRED_MARGINAL_INCREMENT_AND_SECTION5_ROBUSTNESS_EXECUTION_ONLY"
    )
    assert delta["previous_final_test_epoch"] == (
        "SEALED_AUDIT_FAILED_SCIENTIFIC_OUTPUT_INCOMPLETE"
    )
    assert delta["canonical_stage_node_contract"] == (
        "ONE_NODE_PER_EPISODE_STAGE_BEFORE_SUPPORT"
    )
    assert delta["formal_executor_reconciliation"] == (
        "SCIENTIFIC_OUTPUT_COMPLETENESS"
    )
    assert delta["m1_definition_changed"] is False
    assert delta["m2_definition_changed"] is False
    assert delta["m3_selector_definition_changed"] is False
    assert delta["m3_stage2_definition_changed"] is False
    assert delta["m4_loss_definition_changed"] is False
    assert delta["stage1_orchestration_changed"] is False
    assert delta["scientific_orchestration_changed"] is False
    assert delta["formal_execution_completeness_changed"] is True
    assert delta["scientific_definition_changed"] is False


def test_historical_epoch_provenance_is_disclosed_but_not_current(
    freeze_payload: dict[str, object],
) -> None:
    provenance = freeze_payload["historical_epoch_provenance"]
    assert provenance["root"] == str(C.FINAL_TEST_V2_ROOT)
    assert provenance["present"] is True
    assert provenance["release"]["exists"] is True
    assert provenance["release"]["is_read_only"] is True
    assert provenance["access_audit"]["exists"] is True
    assert provenance["access_audit"]["is_read_only"] is True
    assert provenance["used_for_scientific_computation"] is False
    assert provenance["used_for_selection"] is False
    consumed = freeze_payload["consumed_stage_matched_epoch_provenance"]
    assert consumed["root"] == str(
        C.CONSUMED_CANONICAL_V1_FINAL_TEST_ROOT
    )
    assert consumed["present"] is True
    assert consumed["epoch_seal_exists"] is True
    assert consumed["previous_final_test_epoch"] == (
        "SEALED_AUDIT_FAILED_SCIENTIFIC_OUTPUT_INCOMPLETE"
    )
    assert consumed["seal_status"] == (
        "SEALED_AUDIT_FAILED_SCIENTIFIC_OUTPUT_INCOMPLETE"
    )
    assert consumed["blocking_failure_codes"] == [
        "PAIRED_MARGINAL_INCREMENT_NOT_EXECUTED",
        "SECTION5_ROBUSTNESS_RESULTS_NOT_EXECUTED",
    ]
    assert consumed["post_execution_audit_status"] == "FAIL"
    assert consumed["canonicalization_before_support"] == "PASS"
    assert consumed["invalid_for_paper_results"] is True
    assert consumed["used_for_current_epoch"] is False
    assert consumed["used_for_scientific_computation"] is False
    assert consumed["used_for_selection"] is False
    previous = freeze_payload[
        "previous_noncanonical_epoch_provenance"
    ]
    assert previous["root"] == str(
        C.CONSUMED_STAGE_MATCHED_FINAL_TEST_ROOT
    )
    assert previous["seal_status"] == "SEALED_AUDIT_FAILED"
    assert previous["blocking_failure_codes"] == [
        "CANONICALIZATION_BEFORE_SUPPORT"
    ]
    assert previous["canonicalization_before_support"] == "FAIL"


def test_cross_worktree_contract_probe_matches(
    freeze_payload: dict[str, object],
) -> None:
    cross = freeze_payload["cross_worktree_contract"]
    assert cross["status"] == "PASS"
    assert cross["equal_on_shared_contract"] is True
    assert (
        cross["paper_primary"]["stages"]
        == cross["phase7"]["stages"]
        == ["PRE_IB", "POST_IB_PRE_OB"]
    )
    assert cross["paper_primary"]["classes"] == ["PRE", "TURN"]
    assert cross["paper_primary"]["q_grid"] == [0.05, 0.10, 0.20, 0.30]


def test_generated_governance_outputs_are_not_authority_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated = [
        "formal/JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V2.json",
        "formal/JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V2.md",
        "formal/JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V1.json",
        "formal/JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V1.md",
        "artifacts/diagnostics/v2_phase7/STAGE_MATCHED_PRE_OPEN_GATE.json",
        (
            "artifacts/experiment/final_test_v2_stage_matched/"
            "GATE_B_HUMAN_RELEASE.json"
        ),
        (
            "artifacts/experiment/final_test_v2_stage_matched_canonical_v1/"
            "GATE_B_HUMAN_RELEASE.json"
        ),
        (
            "artifacts/experiment/final_test_v2_stage_matched_canonical_v2/"
            "GATE_B_HUMAN_RELEASE.json"
        ),
        "formal/v2_phase7/execution_freeze.py",
    ]
    monkeypatch.setattr(
        freeze, "_status_paths", lambda root: list(generated)
    )
    report = freeze._dirty_classification()
    assert report["phase7_all_dirty_paths"] == [
        "formal/v2_phase7/execution_freeze.py"
    ]
    assert set(report["phase7_volatile_outputs_excluded"]) == set(
        generated[:-1]
    )


def test_git_identity_and_dirty_state_are_not_authority(
    freeze_payload: dict[str, object],
) -> None:
    projected = freeze._authority_projection(freeze_payload)
    assert "dirty_change_classification" not in projected
    for key in ("branch", "head", "dirty"):
        assert key not in projected["phase7"]
        assert key not in projected["paper_primary"]


def test_write_and_validate_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    json_path = tmp_path / "freeze.json"
    md_path = tmp_path / "freeze.md"
    report_path = tmp_path / "pre_open_gate.json"
    monkeypatch.setattr(freeze, "FREEZE_JSON_PATH", json_path)
    monkeypatch.setattr(freeze, "FREEZE_MD_PATH", md_path)
    monkeypatch.setattr(freeze, "PRE_OPEN_REPORT_PATH", report_path)
    payload = freeze.write_execution_freeze()
    assert json_path.is_file()
    assert md_path.is_file()
    report_path.write_text("{}\n", encoding="utf-8")
    result = freeze.validate_execution_freeze()
    assert result["status"] == "PASS"
    assert result["artifact_hash"] == payload["artifact_hash"]
    assert result["cross_worktree_contract"] == "PASS"


def test_freeze_never_reads_prior_or_legacy_final_test_trees(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forbidden = (
        C.FINAL_TEST_V2_ROOT.resolve(),
        C.LEGACY_FINAL_TEST_ROOT.resolve(),
    )

    def guarded(path: Path) -> object:
        resolved = Path(path).resolve()
        assert not any(
            resolved == root or root in resolved.parents for root in forbidden
        )
        return original(path)

    original = freeze._read_json
    monkeypatch.setattr(freeze, "_read_json", guarded)
    payload = freeze.build_execution_freeze()
    assert payload["final_test_accounting"][
        "prior_final_test_v2_tree_reused"
    ] is False
    assert payload["final_test_accounting"][
        "legacy_final_test_tree_read_for_freeze"
    ] is False


def _fake_freeze(root: Path) -> dict[str, object]:
    return {
        "artifact_hash": "sha256:" + "a" * 64,
        "freeze_id": freeze.FREEZE_ID,
        "stage_matched_final_test_epoch": {"output_root": str(root)},
    }


def _pre_open_report(path: Path, artifact_hash: str) -> None:
    path.write_text(
        json.dumps(
            {"status": "PASS", "freeze_artifact_hash": artifact_hash}
        )
        + "\n",
        encoding="utf-8",
    )


def test_gate_b_production_rejects_legacy_epoch_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_hash = "sha256:" + "a" * 64
    report_path = tmp_path / "pre_open.json"
    freeze_path = tmp_path / "freeze.json"
    _pre_open_report(report_path, artifact_hash)
    freeze_path.write_text(
        json.dumps(
            {
                "artifact_hash": artifact_hash,
                "stage_matched_final_test_epoch": {
                    "output_root": str(C.STAGE_MATCHED_FINAL_TEST_ROOT)
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(freeze, "FREEZE_JSON_PATH", freeze_path)
    monkeypatch.setattr(freeze, "PRE_OPEN_REPORT_PATH", report_path)
    monkeypatch.setattr(
        freeze,
        "validate_execution_freeze",
        lambda: _fake_freeze(C.STAGE_MATCHED_FINAL_TEST_ROOT),
    )
    release_path = tmp_path / "release.json"
    release_path.write_text(
        json.dumps(runner.make_release()) + "\n", encoding="utf-8"
    )
    with pytest.raises(runner.TypedBlocker) as error:
        runner.execute_gate_b(
            release_path=release_path,
            audit_path=tmp_path / "audit.json",
            final_test_root=C.FINAL_TEST_V2_ROOT,
            use_production_executor=True,
        )
    assert error.value.code == "GATE_B_FINAL_TEST_ROOT_NOT_FROZEN"


def test_gate_b_production_rejects_release_outside_frozen_epoch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_hash = "sha256:" + "a" * 64
    report_path = tmp_path / "pre_open.json"
    freeze_path = tmp_path / "freeze.json"
    _pre_open_report(report_path, artifact_hash)
    freeze_path.write_text(
        json.dumps(
            {
                "artifact_hash": artifact_hash,
                "stage_matched_final_test_epoch": {
                    "output_root": str(C.STAGE_MATCHED_FINAL_TEST_ROOT)
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(freeze, "FREEZE_JSON_PATH", freeze_path)
    monkeypatch.setattr(freeze, "PRE_OPEN_REPORT_PATH", report_path)
    monkeypatch.setattr(
        freeze,
        "validate_execution_freeze",
        lambda: _fake_freeze(C.STAGE_MATCHED_FINAL_TEST_ROOT),
    )
    release_path = tmp_path / "release.json"
    release_path.write_text(
        json.dumps(runner.make_release()) + "\n", encoding="utf-8"
    )
    with pytest.raises(runner.TypedBlocker) as error:
        runner.execute_gate_b(
            release_path=release_path,
            audit_path=tmp_path / "audit.json",
            final_test_root=C.STAGE_MATCHED_FINAL_TEST_ROOT,
            use_production_executor=True,
        )
    assert error.value.code == "GATE_B_RELEASE_OUTSIDE_FROZEN_EPOCH"


def test_gate_b_reads_persisted_freeze_manifest_for_epoch_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_hash = "sha256:" + "a" * 64
    freeze_path = tmp_path / "freeze.json"
    report_path = tmp_path / "pre_open.json"
    freeze_path.write_text(
        json.dumps(
            {
                "artifact_hash": artifact_hash,
                "stage_matched_final_test_epoch": {
                    "output_root": str(C.STAGE_MATCHED_FINAL_TEST_ROOT)
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _pre_open_report(report_path, artifact_hash)
    monkeypatch.setattr(freeze, "FREEZE_JSON_PATH", freeze_path)
    monkeypatch.setattr(freeze, "PRE_OPEN_REPORT_PATH", report_path)
    monkeypatch.setattr(
        freeze,
        "validate_execution_freeze",
        lambda: {
            "status": "PASS",
            "artifact_hash": artifact_hash,
            "freeze_id": freeze.FREEZE_ID,
        },
    )
    release_path = tmp_path / "release.json"
    release_path.write_text(
        json.dumps(runner.make_release()) + "\n", encoding="utf-8"
    )
    with pytest.raises(runner.TypedBlocker) as error:
        runner.execute_gate_b(
            release_path=release_path,
            use_production_executor=True,
        )
    assert error.value.code == "GATE_B_RELEASE_OUTSIDE_FROZEN_EPOCH"


def test_pre_open_gate_rejects_existing_epoch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "epoch"
    root.mkdir()
    monkeypatch.setattr(freeze, "validate_execution_freeze", lambda: {
        "freeze_id": freeze.FREEZE_ID,
        "artifact_hash": "sha256:" + "a" * 64,
        "cross_worktree_contract": {"status": "PASS"},
    })
    monkeypatch.setattr(C, "STAGE_MATCHED_FINAL_TEST_ROOT", root)
    monkeypatch.setattr(
        C, "STAGE_MATCHED_GATE_B_RELEASE_PATH", root / "release.json"
    )
    monkeypatch.setattr(
        C, "STAGE_MATCHED_ACCESS_AUDIT_PATH", root / "audit.json"
    )
    with pytest.raises(runner.TypedBlocker) as error:
        freeze.pre_open_gate(write_report=False)
    assert error.value.code == "FREEZE_STAGE_MATCHED_EPOCH_ROOT_PREEXISTING"


def test_failed_epoch_tree_hashes_are_frozen(
    freeze_payload: dict[str, object],
) -> None:
    for key in (
        "consumed_stage_matched_epoch_provenance",
        "previous_noncanonical_epoch_provenance",
    ):
        provenance = freeze_payload[key]
        tree = provenance["tree_content_hash"]
        assert tree["present"] is True
        assert tree["file_count"] == 15
        assert str(tree["sha256"]).startswith("sha256:")


def test_failed_epoch_hash_stability_passes_when_unchanged(
    freeze_payload: dict[str, object],
) -> None:
    result = freeze._historical_failed_epoch_hash_stability(freeze_payload)
    assert result["status"] == "PASS"
    assert all(item["tree_hash_match"] for item in result["epochs"])
