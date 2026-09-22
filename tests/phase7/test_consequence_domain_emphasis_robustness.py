"""Consequence-domain emphasis robustness regressions.

Two layers:

* contract tests that need no sealed epoch: the profile registry, the exact
  expected row counts, the prohibited-column guard, and every branch of the
  staged transactional materialization including the rule-R2 repository-authority
  classification and the rule-R3 write-target guard;
* sealed-epoch projection tests that run the real entrypoint against the
  canonical-v2 epoch and assert the replay gates, the frozen anchors, the exact
  summary row counts and the primary invariance. These skip when the sealed epoch
  is absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from formal.v2_phase7 import constants as C
from formal.v2_phase7 import consequence_domain_emphasis_robustness as module

EPOCH_ROOT = C.STAGE_MATCHED_FINAL_TEST_ROOT
CONSEQUENCE_VARIANTS_PATH = EPOCH_ROOT / "checkpoints" / "CONSEQUENCE_VARIANTS.json"

SEALED_STAGE1_HEADLINE = {
    "PRE_IB": {
        "n_g": 29,
        "k_g": 3,
        "a_consequence": 3.2615917421940086,
        "a_delay": 3.2615917421940086,
        "L_att": 0.0,
        "changed_position_count": 0,
    },
    "POST_IB_PRE_OB": {
        "n_g": 127,
        "k_g": 13,
        "a_consequence": 13.501981165915817,
        "a_delay": 12.524028798352472,
        "L_att": 0.07243028675170074,
        "changed_position_count": 5,
    },
}
SEALED_OVERALL_L_ATT = 0.058337943404071974
SEALED_RECOVERY_L_REC = {
    "CURRENT_JOINT": 0.9070157057407199,
    "HISTORY_POINT": 0.9536416660613012,
    "HISTORY_MARGINAL": 0.016464660023900957,
}
SEALED_REFERENCE_RECOVERABLE_VALUE = 0.4140619139058148


# ----------------------------------------------------------------------
# contract tests (no sealed epoch required)
# ----------------------------------------------------------------------
def test_profiles_are_the_three_symmetric_emphasis_scenarios() -> None:
    assert module.ALL_PROFILE_IDS == (
        "BALANCED",
        "FLIGHT_EMPHASIS",
        "PASSENGER_EMPHASIS",
        "RESOURCE_EMPHASIS",
    )
    assert module.EMPHASIS_PROFILE_IDS == (
        "FLIGHT_EMPHASIS",
        "PASSENGER_EMPHASIS",
        "RESOURCE_EMPHASIS",
    )
    for profile in module.PROFILES:
        weights = profile.domain_weights
        assert all(weight >= 0.0 for weight in weights)
        assert sum(weights) == pytest.approx(1.0, abs=1e-12)
    assert module.BALANCED_PROFILE.is_primary_reference is True
    assert module.BALANCED_PROFILE.domain_weights == (1 / 3, 1 / 3, 1 / 3)
    for profile in module.PROFILES[1:]:
        assert profile.is_primary_reference is False
        assert profile.role == "SYMMETRIC_POST_HOC_STRESS_SCENARIO"


def test_balanced_maps_onto_the_canonical_primary_view() -> None:
    from model.M2.comparison_support import PRIMARY_AGGREGATION_VIEW

    assert module.BALANCED_PROFILE.aggregation_view == PRIMARY_AGGREGATION_VIEW
    assert module.BALANCED_PROFILE.aggregation_view == "PRIMARY_DOMAIN_BALANCED"
    emphasis_views = {
        profile.aggregation_view for profile in module.PROFILES[1:]
    }
    assert emphasis_views == {
        "DOMAIN_EMPHASIS_FLIGHT",
        "DOMAIN_EMPHASIS_PASSENGER",
        "DOMAIN_EMPHASIS_RESOURCE",
    }
    assert PRIMARY_AGGREGATION_VIEW not in emphasis_views


def test_profile_scope_always_keeps_the_primary_reference() -> None:
    scope = module.resolve_profile_scope(["RESOURCE_EMPHASIS"])
    assert [profile.profile_id for profile in scope] == [
        "BALANCED",
        "RESOURCE_EMPHASIS",
    ]
    assert len(module.resolve_profile_scope(None)) == 4
    with pytest.raises(module.CheckFailure) as error:
        module.resolve_profile_scope(["NOT_A_PROFILE"])
    assert "UNKNOWN_PROFILE" in str(error.value)


def test_expected_row_counts_match_the_instruction() -> None:
    full = module.expected_row_counts(profile_ids=module.ALL_PROFILE_IDS)
    assert full[module.STAGE1_PROFILE_SUMMARY_NAME] == 6
    assert full[module.STAGE1_DELAY_NAME] == 8
    assert full[module.STAGE1_INFORMATION_NAME] == 24
    assert full[module.STAGE2_HJ_ACTION_NAME] == 3
    assert full[module.STAGE2_INFORMATION_NAME] == 12
    reduced = module.expected_row_counts(profile_ids=["FLIGHT_EMPHASIS"])
    assert reduced[module.STAGE1_PROFILE_SUMMARY_NAME] == 2
    assert reduced[module.STAGE1_INFORMATION_NAME] == 12
    assert reduced[module.STAGE2_INFORMATION_NAME] == 6


def test_scope_declares_the_frozen_stage_and_cohort_settings() -> None:
    assert module.NOMINAL_Q == 0.10
    assert module.EXPECTED_STAGE1_N == {"PRE_IB": 29, "POST_IB_PRE_OB": 127}
    assert module.EXPECTED_STAGE1_K == {"PRE_IB": 3, "POST_IB_PRE_OB": 13}
    assert module.EXPECTED_STAGE2_N == 16
    assert module.EXPECTED_STAGE2_STAGE_COUNTS == {"PRE_IB": 3, "POST_IB_PRE_OB": 13}
    assert module.STAGES == ("PRE_IB", "POST_IB_PRE_OB")
    assert module.CONSEQUENCE_DOMAIN_EMPHASIS_COHORT_ID == (
        "FIXED_REFERENCE_STAGE_II_COHORT"
    )


def test_prohibited_column_guard_rejects_margin_and_inference_fields() -> None:
    module.assert_no_prohibited_columns(
        frames={"ok": pd.DataFrame({"profile_id": ["BALANCED"], "L_att": [0.0]})}
    )
    for column in (
        "cutoff_margin",
        "epsilon_inf",
        "perturbation_span",
        "certificate_status",
        "p_value",
        "ci_low",
        "bootstrap_share",
    ):
        with pytest.raises(module.CheckFailure) as error:
            module.assert_no_prohibited_columns(
                frames={"bad": pd.DataFrame({column: [1.0]})}
            )
        assert "PROHIBITED_COLUMN" in str(error.value)


def _tiny_frames() -> dict[str, pd.DataFrame]:
    return {
        name: pd.DataFrame({"profile_id": ["BALANCED"], "value": [1.0]})
        for name in module.PAYLOAD_ARTIFACTS
    }


def _tiny_manifest() -> dict:
    return {
        "analysis_name": module.ANALYSIS_NAME,
        "git_head": module._git_head(),
        "head_start": module._git_head(),
        "tracked_modifications_start": module._git_tracked_modifications(),
    }


def test_publish_fresh_run_renames_staging_into_place(tmp_path: Path) -> None:
    out_dir = tmp_path / "result"
    mode = module.publish(
        out_dir=out_dir,
        frames=_tiny_frames(),
        report="report\n",
        manifest=_tiny_manifest(),
    )
    assert mode == module.FRESH_ATOMIC_RENAME
    assert (out_dir / module.MANIFEST_NAME).is_file()
    assert (out_dir / module.REPORT_NAME).is_file()
    assert not module.staging_path(out_dir).exists()
    manifest = json.loads((out_dir / module.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["head_stable"] is True
    assert manifest["tracked_modifications_introduced_by_analysis_run"] == []
    assert set(manifest["output_artifact_hashes"]) == set(module.PAYLOAD_ARTIFACTS)
    tracking = manifest["output_artifact_tracking"]
    assert set(tracking["local_only_regenerable"]) == set(module.LOCAL_ONLY_ARTIFACTS)
    assert module.MANIFEST_NAME in tracking["committed_to_git"]


def test_publish_failure_leaves_no_official_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "result"

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "write_staging", _boom)
    with pytest.raises(RuntimeError):
        module.publish(
            out_dir=out_dir,
            frames=_tiny_frames(),
            report="report\n",
            manifest=_tiny_manifest(),
        )
    assert not out_dir.exists()
    assert not module.staging_path(out_dir).exists()


def test_publish_swap_failure_rolls_back_to_the_previous_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "result"
    module.publish(
        out_dir=out_dir,
        frames=_tiny_frames(),
        report="first\n",
        manifest=_tiny_manifest(),
    )
    first_report = (out_dir / module.REPORT_NAME).read_text(encoding="utf-8")
    real_rename = module._rename
    calls = {"count": 0}

    def _flaky(source: Path, target: Path) -> None:
        calls["count"] += 1
        if calls["count"] == 2 and Path(target) == out_dir:
            raise OSError("swap failed")
        real_rename(source, target)

    monkeypatch.setattr(module, "_rename", _flaky)
    with pytest.raises(module.CheckFailure) as error:
        module.publish(
            out_dir=out_dir,
            frames=_tiny_frames(),
            report="second\n",
            manifest=_tiny_manifest(),
        )
    assert "SUCCEEDED_PREVIOUS_RESULT_RESTORED" in str(error.value)
    assert (out_dir / module.REPORT_NAME).read_text(encoding="utf-8") == first_report
    assert not module.staging_path(out_dir).exists()
    assert not module.previous_path(out_dir).exists()


def test_publish_blocks_on_staging_residue(tmp_path: Path) -> None:
    out_dir = tmp_path / "result"
    module.staging_path(out_dir).mkdir(parents=True)
    with pytest.raises(module.CheckFailure) as error:
        module.publish(
            out_dir=out_dir,
            frames=_tiny_frames(),
            report="report\n",
            manifest=_tiny_manifest(),
        )
    assert "STAGING_RESIDUE" in str(error.value)


def test_publish_verifies_hashes_after_the_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A post-rename verification failure is reported, never swallowed."""

    out_dir = tmp_path / "result"
    monkeypatch.setattr(
        module,
        "_verify_materialized",
        lambda **kwargs: (_ for _ in ()).throw(
            module.CheckFailure("CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_VERIFY")
        ),
    )
    with pytest.raises(module.CheckFailure) as error:
        module.publish(
            out_dir=out_dir,
            frames=_tiny_frames(),
            report="report\n",
            manifest=_tiny_manifest(),
        )
    assert "BLOCKED_VERIFY" in str(error.value)
    assert not module.staging_path(out_dir).exists()


def test_write_target_guard_rejects_anything_outside_the_transaction(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "result"
    module._assert_write_target_allowed(target=out_dir, out_dir=out_dir)
    module._assert_write_target_allowed(
        target=module.staging_path(out_dir), out_dir=out_dir
    )
    module._assert_write_target_allowed(
        target=module.previous_path(out_dir), out_dir=out_dir
    )
    for outside in (tmp_path / "elsewhere", tmp_path / "other" / "result"):
        with pytest.raises(module.CheckFailure) as error:
            module._assert_write_target_allowed(target=outside, out_dir=out_dir)
        assert "WRITE_TARGET_OUTSIDE_TRANSACTION" in str(error.value)


def test_output_collision_blocks_a_different_run(tmp_path: Path) -> None:
    out_dir = tmp_path / "result"
    module.publish(
        out_dir=out_dir,
        frames=_tiny_frames(),
        report="report\n",
        manifest=_tiny_manifest(),
    )
    with pytest.raises(module.CheckFailure) as error:
        module.check_output_collision(
            out_dir=out_dir,
            head="0000000000000000000000000000000000000000",
            input_hashes={"a": "sha256:1"},
            analysis_source_sha256="sha256:2",
        )
    assert "OUTPUT_COLLISION" in str(error.value)
    manifest = json.loads((out_dir / module.MANIFEST_NAME).read_text(encoding="utf-8"))
    identical = module.check_output_collision(
        out_dir=out_dir,
        head=manifest["head_start"],
        input_hashes={},
        analysis_source_sha256=None,
    )
    assert identical["collision_check"] == "IDENTICAL_PRIOR_RUN"


def test_paper_results_snapshot_excludes_only_the_transaction_paths(
    tmp_path: Path,
) -> None:
    """The snapshot never covers a designated transaction path."""

    out_dir = tmp_path / "result"
    module._assert_write_target_allowed(target=out_dir, out_dir=out_dir)
    excluded = (
        out_dir,
        module.staging_path(out_dir),
        module.previous_path(out_dir),
    )
    snapshot = module.paper_results_snapshot(excluded=excluded)
    suffixes = (module.STAGING_SUFFIX, module.PREVIOUS_SUFFIX)
    for path in snapshot:
        assert not path.endswith(suffixes), path
    if out_dir.exists():  # pragma: no cover - the tmp path never exists here
        assert str(out_dir) not in snapshot
    assert isinstance(module._snapshot_digest(snapshot), str)
    assert len(module._snapshot_digest(snapshot)) == len("sha256:") + 64


# ----------------------------------------------------------------------
# sealed-epoch projection tests
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def analysis_run(tmp_path_factory) -> tuple[dict, Path]:
    if not CONSEQUENCE_VARIANTS_PATH.is_file():
        pytest.skip("sealed canonical-v2 epoch not present in this checkout")
    out_dir = tmp_path_factory.mktemp("domain_emphasis") / "out"
    module.main(["--epoch-root", str(EPOCH_ROOT), "--out-dir", str(out_dir)])
    manifest = json.loads((out_dir / module.MANIFEST_NAME).read_text(encoding="utf-8"))
    return manifest, out_dir


def test_manifest_declares_the_robustness_contract(analysis_run) -> None:
    manifest, _ = analysis_run
    assert manifest["analysis_name"] == "CONSEQUENCE_DOMAIN_EMPHASIS_ROBUSTNESS"
    assert manifest["analysis_type"] == "POST_HOC_ROBUSTNESS"
    assert manifest["primary_profile"] == "BALANCED"
    assert manifest["primary_weight_profile"] == "BALANCED"
    for key in (
        "primary_weight_profile_changed",
        "weights_reselected",
        "weights_learned",
        "weights_calibrated",
        "expert_elicitation_used",
        "model_retrained",
        "model_recalibrated",
        "parameter_reselected",
        "final_test_cohort_changed",
        "consequence_components_changed",
        "component_normalization_changed",
        "stage2_reference_cohort_changed",
        "stage1_stage_q_grid_rerun",
        "bootstrap_used",
        "significance_testing_used",
        "robustness_threshold_defined",
        "decision_margin_quantities_reported",
        "manuscript_claim_emitted",
    ):
        assert manifest[key] is False, key
    assert manifest["stage1_q"] == 0.10
    assert manifest["stage2_N"] == 16
    assert manifest["stage2_reference_cohort"] == "R_STAR"
    assert manifest["write_mode"] == "STAGED_TRANSACTIONAL_MATERIALIZATION"
    assert manifest["partial_output_exposed"] is False
    assert manifest["manifest_self_hash_included"] is False
    assert manifest["manifest_self_hash_reason"] == "SELF_REFERENTIAL_HASH_NOT_DEFINED"
    assert manifest["tracked_modifications_introduced_by_analysis_run"] == []
    assert manifest["preexisting_unexpected_tracked_modifications"] == []
    assert manifest["preexisting_implementation_modifications"] == [
        "model/M2/comparison_support.py"
    ]
    assert manifest["weight_profiles"] == list(module.ALL_PROFILE_IDS)
    assert manifest["all_gates_passed"] is True


def test_all_gates_pass(analysis_run) -> None:
    manifest, _ = analysis_run
    gates = manifest["gates"]
    assert gates["gate_b"]["status"] == "PASS"
    assert gates["gate_c"]["status"] == "PASS"
    assert gates["gate_d"]["status"] == "PASS"
    assert manifest["gate_statuses"] == {
        "gate_a_passed": True,
        "gate_b_passed": True,
        "gate_c_passed": True,
        "gate_d_passed": True,
    }


def test_gate_b_replays_the_sealed_stage1_authority(analysis_run) -> None:
    manifest, _ = analysis_run
    gate_b = manifest["gates"]["gate_b"]
    assert gate_b["consequence_priority_points_matched"] == 952
    assert gate_b["consequence_priority_points_expected"] == 952
    assert gate_b["max_abs_priority_deviation"] == 0.0
    for stage, sealed in SEALED_STAGE1_HEADLINE.items():
        replay = gate_b["headline_checks"][stage]
        for field, expected in sealed.items():
            assert replay[field] == pytest.approx(expected, abs=1e-12), (stage, field)
    assert gate_b["overall_headline_L_att"] == pytest.approx(
        SEALED_OVERALL_L_ATT, abs=1e-12
    )
    assert len(gate_b["information_comparators"]) == 6


def test_gate_c_replays_the_sealed_stage2_authority(analysis_run) -> None:
    manifest, _ = analysis_run
    gate_c = manifest["gates"]["gate_c"]
    assert gate_c["level1_points_matched"] == 160
    assert gate_c["level1_points_expected"] == 160
    assert gate_c["level1_max_abs_deviation"] <= 1e-12
    assert gate_c["level2_cases_matched"] == 64
    assert gate_c["level2_cases_expected"] == 64
    assert gate_c["level3_cases_matched"] == 64
    by_variant = {
        entry["comparator_variant"]: entry["L_rec"]
        for entry in gate_c["level4_comparators"]
    }
    assert set(by_variant) == set(SEALED_RECOVERY_L_REC)
    for variant, expected in SEALED_RECOVERY_L_REC.items():
        assert by_variant[variant] == pytest.approx(expected, abs=1e-12)


def test_gate_d_reasserts_primary_invariance(analysis_run) -> None:
    manifest, _ = analysis_run
    gate_d = manifest["gates"]["gate_d"]
    assert gate_d["primary_balanced_artifacts_unchanged"] is True
    assert gate_d["sealed_input_hashes_unchanged"] is True
    assert gate_d["frozen_science_source_hashes_unchanged"] is True
    assert gate_d["implementation_authority_unchanged_during_run"] is True
    assert gate_d["r_star_unchanged"] == {
        "total": 16,
        "by_stage": {"PRE_IB": 3, "POST_IB_PRE_OB": 13},
    }
    assert gate_d["nominal_q_unchanged"] == 0.10
    assert gate_d["paper_results_roots_unchanged"] is True


def test_summary_row_counts_are_exact(analysis_run) -> None:
    manifest, out_dir = analysis_run
    expected = module.expected_row_counts(profile_ids=module.ALL_PROFILE_IDS)
    for name, count in expected.items():
        if name.endswith(".parquet"):
            frame = pd.read_parquet(out_dir / name)
        else:
            frame = pd.read_csv(out_dir / name)
        assert len(frame) == count, name
    assert manifest["observed_row_counts"] == expected


def test_stage1_tables_are_stage_local_and_two_directional(analysis_run) -> None:
    _, out_dir = analysis_run
    profile_frame = pd.read_csv(out_dir / module.STAGE1_PROFILE_SUMMARY_NAME)
    assert set(profile_frame["stage"]) == set(module.STAGES)
    assert set(profile_frame["profile_id"]) == set(module.EMPHASIS_PROFILE_IDS)
    for _, row in profile_frame.iterrows():
        assert row["N"] == module.EXPECTED_STAGE1_N[row["stage"]]
        assert row["K"] == module.EXPECTED_STAGE1_K[row["stage"]]
        assert row["entered_count"] == row["displaced_count"]
        assert row["changed_positions"] == row["entered_count"]
        assert 0.0 <= row["shortlist_overlap_rate"] <= 1.0
    assert profile_frame["comparison_direction"].str.contains("BALANCED_BASIS").all()
    assert profile_frame["comparison_direction"].str.contains("PROFILE_BASIS").all()


def test_delay_summary_preserves_the_balanced_headline_and_marks_scope(
    analysis_run,
) -> None:
    _, out_dir = analysis_run
    frame = pd.read_csv(out_dir / module.STAGE1_DELAY_NAME)
    assert len(frame) == 8
    assert frame["interpretation_scope"].eq(
        "PROFILE_SPECIFIC_DELAY_VS_CONSEQUENCE_NOT_PRIMARY_HEADLINE"
    ).all()
    balanced = frame[frame["profile_id"] == "BALANCED"].set_index("stage")
    for stage, sealed in SEALED_STAGE1_HEADLINE.items():
        row = balanced.loc[stage]
        assert row["profile_reference_consequence_value"] == pytest.approx(
            sealed["a_consequence"], abs=1e-12
        )
        assert row["delay_shortlist_consequence_value"] == pytest.approx(
            sealed["a_delay"], abs=1e-12
        )
        assert row["attention_loss"] == pytest.approx(sealed["L_att"], abs=1e-12)


def test_information_tables_keep_the_common_basis_and_headline_structure(
    analysis_run,
) -> None:
    _, out_dir = analysis_run
    stage1 = pd.read_csv(out_dir / module.STAGE1_INFORMATION_NAME)
    assert len(stage1) == 24
    assert set(stage1["reference_variant"]) == {"HISTORY_JOINT"}
    assert set(stage1["comparator_variant"]) == {"CURRENT_JOINT", "HISTORY_POINT", "HISTORY_MARGINAL"}
    assert stage1["N_common"].eq(stage1["N_reference"]).all()
    assert stage1["N_common"].eq(stage1["N_comparator"]).all()
    balanced = stage1[stage1["profile_id"] == "BALANCED"].set_index(
        ["stage", "comparator_variant"]
    )
    assert balanced.loc[("PRE_IB", "CURRENT_JOINT"), "attention_loss"] == pytest.approx(
        0.0, abs=1e-12
    )
    assert balanced.loc[
        ("PRE_IB", "HISTORY_POINT"), "attention_loss"
    ] == pytest.approx(0.6457297347005055, abs=1e-12)
    assert balanced.loc[
        ("POST_IB_PRE_OB", "HISTORY_POINT"), "attention_loss"
    ] == pytest.approx(0.5361866769295646, abs=1e-12)

    stage2 = pd.read_csv(out_dir / module.STAGE2_INFORMATION_NAME)
    assert len(stage2) == 12
    assert stage2["N"].eq(16).all()
    balanced_stage2 = stage2[stage2["profile_id"] == "BALANCED"].set_index(
        "comparator_variant"
    )
    for variant, expected in SEALED_RECOVERY_L_REC.items():
        assert balanced_stage2.loc[variant, "L_rec"] == pytest.approx(
            expected, abs=1e-12
        )
    for _, row in stage2.iterrows():
        assert row["reference_recoverable_value"] == pytest.approx(
            SEALED_REFERENCE_RECOVERABLE_VALUE, abs=1e-12
        ) or row["profile_id"] != "BALANCED"
        if row["L_rec"] is not None and row["retained_value"] is not None:
            assert row["retained_value"] == pytest.approx(
                1.0 - row["L_rec"], abs=1e-12
            )


def test_stage2_hj_action_sensitivity_is_regret_first(analysis_run) -> None:
    _, out_dir = analysis_run
    frame = pd.read_csv(out_dir / module.STAGE2_HJ_ACTION_NAME)
    assert len(frame) == 3
    assert set(frame["profile_id"]) == set(module.EMPHASIS_PROFILE_IDS)
    for _, row in frame.iterrows():
        assert row["N"] == 16
        assert row["reference_profile_id"] == "BALANCED"
        assert row["primary_metric"] == (
            "ACTION_AGREEMENT_AND_BIDIRECTIONAL_OBJECTIVE_REGRET"
        )
        assert "NOT_COMPARABLE_ACROSS_PROFILES" in row["recoverable_value_interpretation"]
        assert row["balanced_total_recoverable_value"] == pytest.approx(
            SEALED_REFERENCE_RECOVERABLE_VALUE, abs=1e-12
        )
        assert row["exact_action_count"] + row["N_action_changed"] >= 16
        assert row["N_increased_recovery"] + row["N_decreased_recovery"] == row[
            "N_action_changed"
        ]
        assert row["median_abs_action_change"] <= row["max_abs_action_change"]


def test_chain_records_cover_every_scope_profile_and_variant(analysis_run) -> None:
    _, out_dir = analysis_run
    stage1 = pd.read_parquet(out_dir / module.STAGE1_RECORDS_NAME)
    assert len(stage1) == 4 * 4 * 156
    assert set(stage1["variant"]) == set(
        ("HISTORY_JOINT", "CURRENT_JOINT", "HISTORY_POINT", "HISTORY_MARGINAL")
    )
    per_group = stage1.groupby(["profile_id", "variant", "stage"]).size()
    assert set(per_group.values) == {29, 127}
    stage2 = pd.read_parquet(out_dir / module.STAGE2_RECORDS_NAME)
    assert set(stage2["record_kind"]) == {
        "PROFILE_ACTION",
        "COMPARATOR_ACTION",
        "HJ_PREFERENCE",
    }
    assert len(stage2[stage2["record_kind"] == "PROFILE_ACTION"]) == 4 * 4 * 16
    assert len(stage2[stage2["record_kind"] == "COMPARATOR_ACTION"]) == 4 * 3 * 16
    assert len(stage2[stage2["record_kind"] == "HJ_PREFERENCE"]) == 3 * 16


def test_report_states_the_declarations_and_reading_rules(analysis_run) -> None:
    _, out_dir = analysis_run
    report = (out_dir / module.REPORT_NAME).read_text(encoding="utf-8")
    for needle in (
        "## A. Do domain emphases materially change the consequence shortlist?",
        "## B. Does the Delay-vs-Consequence finding persist?",
        "## C. Does priority remain distinct from local recoverability?",
        "## D. Does the information-value ordering persist?",
        "## E. Exceptions",
        "RQ-R1",
        "RQ-R4",
        "## Reading rules",
        "## Interpretation boundary for the manuscript",
        "robustness checks rather than empirically elicited airline utility weights",
        "`bootstrap_used` = `False`",
        "`robustness_threshold_defined` = `False`",
    ):
        assert needle in report, needle
    assert "The results are robust" not in report
    assert "ROBUST = TRUE" not in report


def test_run_is_read_only_over_the_sealed_epoch(analysis_run) -> None:
    manifest, _ = analysis_run
    for name, path in manifest["input_artifact_paths"].items():
        assert Path(path).is_file(), name
        assert module._sha256_file(Path(path)) == manifest["input_artifact_hashes"][name]
    seal = module._load(EPOCH_ROOT / "EPOCH_SEAL.json")
    assert manifest["epoch_provenance"]["execution_result_sha256"] == seal[
        "execution_result_sha256"
    ]
    assert manifest["epoch_provenance"]["post_execution_audit_sha256"] == seal[
        "post_execution_audit_json_sha256"
    ]


def test_successive_runs_of_the_same_source_are_byte_identical(
    analysis_run, tmp_path: Path
) -> None:
    """A regeneration with identical inputs reproduces the same payload hashes."""

    manifest, out_dir = analysis_run
    out_dir_second = tmp_path / "second"
    module.main(["--epoch-root", str(EPOCH_ROOT), "--out-dir", str(out_dir_second)])
    second = json.loads(
        (out_dir_second / module.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert second["output_artifact_hashes"] == manifest["output_artifact_hashes"]
