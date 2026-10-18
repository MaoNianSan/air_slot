"""Decision-margin mechanism diagnostic regressions.

Two layers:

* contract tests of the certificate primitives and the staged transactional
  materialization on synthetic inputs - no sealed epoch required. They pin the
  four-valued status rules, the one-way nature of a stability certificate (a
  ``NOT_CERTIFIED`` row may legitimately be stable, or changed, and both are
  counted separately), the ``span <= 2 * eps`` relation, the schema guards and
  every branch of the swap transaction;
* sealed-epoch projection tests that run the real entrypoint against the
  canonical-v2 epoch and assert the two replay gates, the frozen anchors and the
  primary-result invariance. These skip when the sealed epoch is absent.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from formal.v2_phase7 import constants as C
from formal.v2_phase7 import decision_margin_diagnostic as module

EPOCH_ROOT = C.STAGE_MATCHED_FINAL_TEST_ROOT
ATTENTION_PATH = EPOCH_ROOT / "checkpoints" / "ATTENTION_DECISIONS.json"


def _ranked(scores: list[tuple[str, float]]) -> tuple[tuple[str, float], ...]:
    return tuple(sorted(scores, key=lambda item: (-item[1], item[0])))


# ----------------------------------------------------------------------
# Stage-I certificate primitives
# ----------------------------------------------------------------------
def test_stage1_status_rules_cover_the_four_statuses() -> None:
    ranking = _ranked([("a", 1.0), ("b", 0.90), ("c", 0.10)])
    margin = module.stage1_pair_margin(
        reference_ranking=ranking,
        alternative_scores={"a": 1.01, "b": 0.89, "c": 0.12},
        k=2,
    )
    assert margin["cutoff_margin"] == pytest.approx(0.80, abs=1e-15)
    assert margin["epsilon_inf"] == pytest.approx(0.02, abs=1e-15)
    assert margin["certificate_slack"] == pytest.approx(0.76, abs=1e-15)
    assert (
        module.stage1_certificate_status(
            has_common_cohort=True,
            margin=margin["cutoff_margin"],
            slack=margin["certificate_slack"],
        )
        == module.CERTIFIED_STABLE
    )

    # a zero cutoff margin cannot certify anything: the K-th and (K+1)-th
    # reference chains carry the same priority
    tied = module.stage1_pair_margin(
        reference_ranking=_ranked([("a", 1.0), ("b", 1.0), ("c", 1.0)]),
        alternative_scores={"a": 1.0, "b": 1.0, "c": 1.0},
        k=2,
    )
    assert tied["cutoff_margin"] == 0.0
    assert (
        module.stage1_certificate_status(
            has_common_cohort=True,
            margin=tied["cutoff_margin"],
            slack=tied["certificate_slack"],
        )
        == module.NO_STRICT_REFERENCE_MARGIN
    )

    # a perturbation close to the margin is inconclusive, not a prediction
    close = module.stage1_pair_margin(
        reference_ranking=ranking,
        alternative_scores={"a": 1.7, "b": 1.1, "c": 0.2},
        k=2,
    )
    assert close["certificate_slack"] < 0
    assert (
        module.stage1_certificate_status(
            has_common_cohort=True,
            margin=close["cutoff_margin"],
            slack=close["certificate_slack"],
        )
        == module.NOT_CERTIFIED
    )

    # no common support at all
    assert (
        module.stage1_certificate_status(
            has_common_cohort=False, margin=None, slack=None
        )
        == module.ABSTAIN_NO_COMMON_SUPPORT
    )
    # a cohort too small to expose a (K + 1)-th chain has no strict margin
    assert (
        module.stage1_certificate_status(
            has_common_cohort=True, margin=None, slack=None
        )
        == module.NO_STRICT_REFERENCE_MARGIN
    )


def test_stage1_decision_outcome_counts_entered_and_displaced() -> None:
    outcome = module.stage1_decision_outcome(
        reference_selected=["a", "b", "c"],
        alternative_selected=["a", "b", "d"],
    )
    assert outcome["shortlist_identical"] is False
    assert outcome["intersection_count"] == 2
    assert outcome["changed_positions"] == 1
    assert outcome["entered"] == ["d"]
    assert outcome["displaced"] == ["c"]

    identical = module.stage1_decision_outcome(
        reference_selected=["a", "b"], alternative_selected=["b", "a"]
    )
    assert identical["shortlist_identical"] is True
    assert identical["changed_positions"] == 0


def test_certified_stable_requires_a_stable_shortlist_but_not_the_converse() -> None:
    # a certified-stable row with an identical shortlist is accepted
    module.certified_stable_requires_unchanged(
        certificate_status=module.CERTIFIED_STABLE,
        reference_value=("a", "b"),
        alternative_value=("a", "b"),
        context={"scope": "TEST"},
    )
    # a certified-stable row with a moved shortlist is an implementation error
    with pytest.raises(module.CheckFailure) as error:
        module.certified_stable_requires_unchanged(
            certificate_status=module.CERTIFIED_STABLE,
            reference_value=("a", "b"),
            alternative_value=("a", "c"),
            context={"scope": "TEST"},
        )
    assert "DECISION_MARGIN_BLOCKED_CERTIFIED_STABLE_DECISION_CHANGED" in str(
        error.value
    )
    # NOT_CERTIFIED carries no implication about the decision, in either direction
    module.certified_stable_requires_unchanged(
        certificate_status=module.NOT_CERTIFIED,
        reference_value=("a", "b"),
        alternative_value=("a", "c"),
        context={"scope": "TEST"},
    )
    module.certified_stable_requires_unchanged(
        certificate_status=module.NOT_CERTIFIED,
        reference_value=("a", "b"),
        alternative_value=("a", "b"),
        context={"scope": "TEST"},
    )


def test_not_certified_but_stable_is_a_legal_observed_combination() -> None:
    """A positive fixture: inconclusive certificate, unchanged decision."""

    ranking = _ranked([("a", 1.0), ("b", 0.90), ("c", 0.10)])
    margin = module.stage1_pair_margin(
        reference_ranking=ranking,
        alternative_scores={"a": 1.70, "b": 1.60, "c": 0.20},
        k=2,
    )
    status = module.stage1_certificate_status(
        has_common_cohort=True,
        margin=margin["cutoff_margin"],
        slack=margin["certificate_slack"],
    )
    assert status == module.NOT_CERTIFIED
    # the alternative reorders nothing inside the top two
    outcome = module.stage1_decision_outcome(
        reference_selected=["a", "b"], alternative_selected=["a", "b"]
    )
    assert outcome["shortlist_identical"] is True
    counted = module.certificate_class_counts(
        [{"certificate_status": status, "decision_changed": False}],
        changed_key="decision_changed",
    )
    assert counted["N_not_certified_but_stable"] == 1
    assert counted["N_certified_stable"] == 0
    assert counted["N_not_certified_and_changed"] == 0


def test_certificate_class_counts_split_the_five_classes() -> None:
    rows = [
        {"certificate_status": module.CERTIFIED_STABLE, "changed": False},
        {"certificate_status": module.NOT_CERTIFIED, "changed": False},
        {"certificate_status": module.NOT_CERTIFIED, "changed": True},
        {"certificate_status": module.NO_STRICT_REFERENCE_MARGIN, "changed": False},
        {"certificate_status": module.ABSTAIN_NO_COMMON_SUPPORT, "changed": False},
        {"certificate_status": module.NOT_CERTIFIED, "changed": False},
    ]
    counts = module.certificate_class_counts(rows, changed_key="changed")
    assert counts == {
        "N_certified_stable": 1,
        "N_not_certified_but_stable": 2,
        "N_not_certified_and_changed": 1,
        "N_no_strict_reference_margin": 1,
        "N_abstain": 1,
    }


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(module.CheckFailure):
        module.certificate_class_counts(
            [{"certificate_status": "UNSTABLE_LIKE_LABEL", "changed": False}],
            changed_key="changed",
        )


# ----------------------------------------------------------------------
# perturbation quantities
# ----------------------------------------------------------------------
def test_span_is_never_larger_than_twice_epsilon_and_ignores_a_shift() -> None:
    for deltas in (
        [0.01, -0.02, 0.03],
        [5.0, 5.0, 5.0],
        [-1.0, 0.0, 1.0],
    ):
        epsilon = max(abs(value) for value in deltas)
        span = max(deltas) - min(deltas)
        assert span <= 2.0 * epsilon + 1e-15

    shifted = [value + 3.5 for value in (0.01, -0.02, 0.03)]
    assert max(shifted) - min(shifted) == pytest.approx(
        max([0.01, -0.02, 0.03]) - min([0.01, -0.02, 0.03]), abs=1e-15
    )
    assert max(abs(value) for value in shifted) > max(
        abs(value) for value in (0.01, -0.02, 0.03)
    )


def test_stage1_margin_reports_span_and_epsilon_together() -> None:
    ranking = _ranked([("a", 1.0), ("b", 0.5)])
    margin = module.stage1_pair_margin(
        reference_ranking=ranking,
        alternative_scores={"a": 1.5, "b": 1.1},
        k=1,
    )
    assert margin["epsilon_inf"] == pytest.approx(0.6, abs=1e-12)
    assert margin["perturbation_span"] == pytest.approx(0.1, abs=1e-12)
    assert margin["perturbation_span"] < 2.0 * margin["epsilon_inf"]


def test_alternative_boundary_separation_signs() -> None:
    reference = ["a", "b"]
    cohort = ["a", "b", "c", "d"]
    above = module.alternative_boundary_separation(
        reference_selected=reference,
        alternative_scores={"a": 5.0, "b": 4.0, "c": 1.0, "d": 0.5},
        cohort=cohort,
    )
    assert above["alternative_boundary_separation"] == pytest.approx(3.0, abs=1e-12)
    reversal = module.alternative_boundary_separation(
        reference_selected=reference,
        alternative_scores={"a": 5.0, "b": 1.0, "c": 4.0, "d": 0.5},
        cohort=cohort,
    )
    assert reversal["alternative_boundary_separation"] < 0.0
    tie = module.alternative_boundary_separation(
        reference_selected=reference,
        alternative_scores={"a": 1.0, "b": 1.0, "c": 1.0, "d": 0.5},
        cohort=cohort,
    )
    assert tie["alternative_boundary_separation"] == 0.0
    empty = module.alternative_boundary_separation(
        reference_selected=cohort,
        alternative_scores={"a": 1.0, "b": 1.0, "c": 1.0, "d": 0.5},
        cohort=cohort,
    )
    assert empty["alternative_boundary_separation"] is None


# ----------------------------------------------------------------------
# Stage-II certificate primitives
# ----------------------------------------------------------------------
def _table(values: dict[float, float]) -> tuple[tuple[float, float], ...]:
    return tuple((u, values[u]) for u in sorted(values))


def test_stage2_status_rules_cover_the_four_statuses() -> None:
    reference = _table({0.0: 0.5, 5.0: 0.9, 10.0: 1.0})
    alternative = _table({0.0: 0.51, 5.0: 0.9, 10.0: 1.0})
    margin = module.stage2_pair_margin(
        reference_table=reference, alternative_table=alternative
    )
    assert margin["reference_best_u"] == 0.0
    assert margin["reference_second_best_u"] == 5.0
    assert margin["action_gap"] == pytest.approx(0.4, abs=1e-12)
    assert margin["epsilon_inf"] == pytest.approx(0.01, abs=1e-12)
    assert (
        module.stage2_certificate_status(
            has_common_actions=True,
            action_gap=margin["action_gap"],
            slack=margin["certificate_slack"],
        )
        == module.CERTIFIED_STABLE
    )

    # an objective tie at the optimum leaves no strict margin, even though the
    # frozen tie-break still reports a unique u*
    tied = _table({0.0: 0.5, 5.0: 0.5, 10.0: 1.0})
    tied_margin = module.stage2_pair_margin(
        reference_table=tied, alternative_table=tied
    )
    assert tied_margin["reference_best_u"] == 0.0
    assert tied_margin["action_gap"] == 0.0
    assert (
        module.stage2_certificate_status(
            has_common_actions=True,
            action_gap=tied_margin["action_gap"],
            slack=tied_margin["certificate_slack"],
        )
        == module.NO_STRICT_REFERENCE_MARGIN
    )

    # a perturbation as large as the gap is inconclusive
    close = module.stage2_pair_margin(
        reference_table=reference,
        alternative_table=_table({0.0: 1.0, 5.0: 0.9, 10.0: 1.0}),
    )
    assert close["action_gap"] == pytest.approx(0.4, abs=1e-12)
    assert close["epsilon_inf"] == pytest.approx(0.5, abs=1e-12)
    assert (
        module.stage2_certificate_status(
            has_common_actions=True,
            action_gap=close["action_gap"],
            slack=close["certificate_slack"],
        )
        == module.NOT_CERTIFIED
    )

    # a single feasible action exposes no second-best action
    singleton = module.stage2_pair_margin(
        reference_table=_table({0.0: 1.0}), alternative_table=_table({0.0: 1.0})
    )
    assert singleton["reference_second_best_u"] is None
    assert (
        module.stage2_certificate_status(
            has_common_actions=True,
            action_gap=singleton["action_gap"],
            slack=singleton["certificate_slack"],
        )
        == module.NO_STRICT_REFERENCE_MARGIN
    )

    assert (
        module.stage2_certificate_status(
            has_common_actions=False, action_gap=None, slack=None
        )
        == module.ABSTAIN_NO_COMMON_SUPPORT
    )


def test_stage2_common_feasible_set_is_the_grid_intersection() -> None:
    margin = module.stage2_pair_margin(
        reference_table=_table({0.0: 1.0, 5.0: 0.9, 10.0: 0.8}),
        alternative_table=_table({5.0: 0.95, 10.0: 0.85, 15.0: 0.7}),
    )
    assert margin["common_feasible_set"] == (5.0, 10.0)
    assert set(margin["objective_delta"]) == {5.0, 10.0}
    assert (
        module.stage2_certificate_status(
            has_common_actions=True,
            action_gap=margin["action_gap"],
            slack=margin["certificate_slack"],
        )
        == module.NOT_CERTIFIED
        or margin["action_gap"] is not None
    )

    with pytest.raises(module.CheckFailure) as error:
        module.stage2_pair_margin(
            reference_table=_table({0.0: 1.0}),
            alternative_table=_table({5.0: 1.0}),
        )
    assert "DECISION_MARGIN_BLOCKED_OBJECTIVE_REPLAY_MISMATCH" in str(error.value)


def test_stage2_certificate_is_sufficient_for_action_stability() -> None:
    """A certified-stable pair must share its optimum; the converse need not."""

    reference = _table({0.0: 0.4, 5.0: 0.9, 10.0: 1.0})
    alternative = _table({0.0: 0.41, 5.0: 0.9, 10.0: 1.0})
    margin = module.stage2_pair_margin(
        reference_table=reference, alternative_table=alternative
    )
    status = module.stage2_certificate_status(
        has_common_actions=True,
        action_gap=margin["action_gap"],
        slack=margin["certificate_slack"],
    )
    assert status == module.CERTIFIED_STABLE
    assert margin["alternative_best_u"] == margin["reference_best_u"] == 0.0
    module.certified_stable_requires_unchanged(
        certificate_status=status,
        reference_value=margin["reference_best_u"],
        alternative_value=margin["alternative_best_u"],
        context={"scope": "TEST"},
    )


def test_recovery_event_flags_match_the_frozen_taxonomy() -> None:
    assert module.recovery_event_flags(10.0, 0.0)["missed_activation"] is True
    assert module.recovery_event_flags(0.0, 5.0)["false_activation"] is True
    assert module.recovery_event_flags(10.0, 5.0)["under_recovery"] is True
    assert module.recovery_event_flags(5.0, 10.0)["over_recovery"] is True
    quiet = module.recovery_event_flags(0.0, 0.0)
    assert quiet["ref_activation"] is False and quiet["alt_activation"] is False
    assert not any(
        quiet[key]
        for key in ("missed_activation", "false_activation", "under_recovery", "over_recovery")
    )


# ----------------------------------------------------------------------
# schema guards
# ----------------------------------------------------------------------
def test_schema_guards_reject_prohibited_columns_and_metric_keys() -> None:
    good = {
        "STAGE1": pd.DataFrame(
            [
                {
                    "comparison_id": "A",
                    "certificate_status": module.CERTIFIED_STABLE,
                    "epsilon_inf": 0.1,
                }
            ]
        )
    }
    module.assert_no_prohibited_columns(frames=good, manifest={"write_mode": "X"})

    with pytest.raises(module.CheckFailure):
        module.assert_no_prohibited_columns(
            frames={"STAGE1": pd.DataFrame({"delay_certificate": [1.0]})},
            manifest={},
        )
    with pytest.raises(module.CheckFailure):
        module.assert_no_prohibited_columns(
            frames={"STAGE1": pd.DataFrame({"delay_epsilon": [1.0]})}, manifest={}
        )
    with pytest.raises(module.CheckFailure):
        module.assert_no_prohibited_columns(
            frames={"STAGE1": pd.DataFrame({"L_att": [1.0]})}, manifest={}
        )
    with pytest.raises(module.CheckFailure):
        module.assert_no_prohibited_columns(
            frames={"STAGE1": pd.DataFrame({"accuracy": [1.0]})}, manifest={}
        )
    with pytest.raises(module.CheckFailure):
        module.assert_no_prohibited_columns(
            frames=good, manifest={"accuracy": 1.0}
        )
    with pytest.raises(module.CheckFailure):
        module.assert_no_prohibited_columns(
            frames=good, manifest={"certificate_counts": {"auc": 1.0}}
        )
    with pytest.raises(module.CheckFailure):
        module.assert_no_prohibited_columns(
            frames={
                "STAGE1": pd.DataFrame({"certificate_status": ["PREDICTED_CHANGE"]})
            },
            manifest={},
        )


def test_stage1_certificate_sweep_blocks_a_moved_certified_stable_row() -> None:
    summary = [
        {
            "comparison_id": "A",
            "stage": "PRE_IB",
            "certificate_status": module.CERTIFIED_STABLE,
        },
        {
            "comparison_id": "A",
            "stage": "POST_IB_PRE_OB",
            "certificate_status": module.NOT_CERTIFIED,
        },
    ]
    stable_records = [
        {
            "comparison_id": "A",
            "stage": "PRE_IB",
            "node_id": "n1",
            "selected_ref": True,
            "selected_alt": True,
        },
        # a NOT_CERTIFIED row is allowed to move a chain
        {
            "comparison_id": "A",
            "stage": "POST_IB_PRE_OB",
            "node_id": "n2",
            "selected_ref": True,
            "selected_alt": False,
        },
    ]
    module.assert_stage1_certificates_hold(records=stable_records, summary=summary)

    moved = list(stable_records)
    moved[0] = {**moved[0], "selected_alt": False}
    with pytest.raises(module.CheckFailure) as error:
        module.assert_stage1_certificates_hold(records=moved, summary=summary)
    assert "DECISION_MARGIN_BLOCKED_CERTIFIED_STABLE_DECISION_CHANGED" in str(
        error.value
    )


# ----------------------------------------------------------------------
# staging and transactional materialization
# ----------------------------------------------------------------------
def _tiny_frames() -> dict[str, pd.DataFrame]:
    return {
        module.STAGE1_RECORDS_NAME: pd.DataFrame({"a": [1, 2]}),
        module.STAGE1_SUMMARY_NAME: pd.DataFrame({"a": [1]}),
        module.STAGE2_CURVES_NAME: pd.DataFrame({"a": [1]}),
        module.STAGE2_CHAIN_NAME: pd.DataFrame({"a": [1]}),
        module.STAGE2_SUMMARY_NAME: pd.DataFrame({"a": [1]}),
        module.STAGE_Q_BOUNDARY_NAME: pd.DataFrame({"a": [1]}),
    }


def _tiny_manifest() -> dict:
    """A manifest stub whose worktree snapshot matches the real tree.

    The repository's own suite refreshes unrelated provenance files, so the
    tests must not assume a pristine worktree; they snapshot whatever is there.
    """

    authority = module.gate_repository_authority(
        out_dir=Path(C.ROOT) / "nonexistent_out"
    )
    return {
        "head_start": authority["head_start"],
        "write_mode": module.WRITE_MODE,
        "tracked_modifications_start": authority["tracked_modifications_start"],
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
    for name in module.PAYLOAD_ARTIFACTS:
        assert (out_dir / name).is_file()
    assert not module.staging_path(out_dir).exists()
    manifest = json.loads((out_dir / module.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["write_mode"] == module.WRITE_MODE
    assert manifest["materialization_mode"] == module.FRESH_ATOMIC_RENAME
    assert manifest["head_stable"] is True
    assert manifest["tracked_modifications_introduced_by_run"] == []
    assert manifest["tracked_modifications_end"] == manifest["tracked_modifications_start"]
    assert module.MANIFEST_NAME not in manifest["output_artifact_hashes"]
    assert set(manifest["output_artifact_hashes"]) == set(module.PAYLOAD_ARTIFACTS)
    assert set(manifest["output_artifact_tracking"]["local_only_regenerable"]) == set(
        module.LOCAL_ONLY_ARTIFACTS
    )


def test_publish_fresh_failure_leaves_no_official_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "result"

    def _boom(**kwargs) -> None:
        raise RuntimeError("injected manifest failure")

    monkeypatch.setattr(module, "write_manifest", _boom)
    with pytest.raises(RuntimeError):
        module.publish(
            out_dir=out_dir,
            frames=_tiny_frames(),
            report="report\n",
            manifest=_tiny_manifest(),
        )
    assert not out_dir.exists()
    assert not module.staging_path(out_dir).exists()


def test_publish_regeneration_failure_keeps_the_previous_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "result"
    module.publish(
        out_dir=out_dir,
        frames=_tiny_frames(),
        report="report\n",
        manifest=_tiny_manifest(),
    )
    before = {
        name: module._sha256_file(out_dir / name)
        for name in (*module.PAYLOAD_ARTIFACTS, module.MANIFEST_NAME)
    }

    def _boom(**kwargs) -> None:
        raise RuntimeError("injected manifest failure")

    monkeypatch.setattr(module, "write_manifest", _boom)
    with pytest.raises(RuntimeError):
        module.publish(
            out_dir=out_dir,
            frames=_tiny_frames(),
            report="report\n",
            manifest=_tiny_manifest(),
        )
    after = {
        name: module._sha256_file(out_dir / name)
        for name in (*module.PAYLOAD_ARTIFACTS, module.MANIFEST_NAME)
    }
    assert after == before
    assert not module.staging_path(out_dir).exists()
    assert not module.previous_path(out_dir).exists()


def test_publish_swap_failure_rolls_back_to_the_previous_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "result"
    module.publish(
        out_dir=out_dir,
        frames=_tiny_frames(),
        report="report\n",
        manifest=_tiny_manifest(),
    )
    before = {
        name: module._sha256_file(out_dir / name)
        for name in (*module.PAYLOAD_ARTIFACTS, module.MANIFEST_NAME)
    }

    real_rename = module._rename
    calls: list[int] = []

    def _flaky(source: Path, target: Path) -> None:
        calls.append(1)
        if len(calls) == 2:  # staging -> out_dir, after out_dir -> previous
            raise OSError("injected swap failure")
        real_rename(source, target)

    monkeypatch.setattr(module, "_rename", _flaky)
    with pytest.raises(module.CheckFailure) as error:
        module.publish(
            out_dir=out_dir,
            frames=_tiny_frames(),
            report="report\n",
            manifest=_tiny_manifest(),
        )
    assert "DECISION_MARGIN_BLOCKED_MATERIALIZATION" in str(error.value)
    assert "SUCCEEDED_PREVIOUS_RESULT_RESTORED" in str(error.value)
    after = {
        name: module._sha256_file(out_dir / name)
        for name in (*module.PAYLOAD_ARTIFACTS, module.MANIFEST_NAME)
    }
    assert after == before
    assert not module.previous_path(out_dir).exists()
    assert not module.staging_path(out_dir).exists()


def test_publish_failed_rollback_preserves_every_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "result"
    module.publish(
        out_dir=out_dir,
        frames=_tiny_frames(),
        report="report\n",
        manifest=_tiny_manifest(),
    )

    real_rename = module._rename
    calls: list[int] = []

    def _broken(source: Path, target: Path) -> None:
        calls.append(1)
        if len(calls) in (2, 3):  # the swap and the rollback both fail
            raise OSError("injected failure")
        real_rename(source, target)

    monkeypatch.setattr(module, "_rename", _broken)
    with pytest.raises(module.CheckFailure) as error:
        module.publish(
            out_dir=out_dir,
            frames=_tiny_frames(),
            report="report\n",
            manifest=_tiny_manifest(),
        )
    message = str(error.value)
    assert "DECISION_MARGIN_BLOCKED_MATERIALIZATION_ROLLBACK" in message
    assert "target_path" in message and "previous_path" in message
    assert "staging_path" in message
    # nothing was deleted: the previous result is intact beside the new attempt
    assert module.previous_path(out_dir).is_dir()
    assert module.staging_path(out_dir).is_dir()
    assert not out_dir.exists()
    shutil.rmtree(module.previous_path(out_dir), ignore_errors=True)
    shutil.rmtree(module.staging_path(out_dir), ignore_errors=True)


def test_staging_residue_blocks_a_run(tmp_path: Path) -> None:
    out_dir = tmp_path / "result"
    module.staging_path(out_dir).mkdir(parents=True)
    with pytest.raises(module.CheckFailure) as error:
        module.publish(
            out_dir=out_dir,
            frames=_tiny_frames(),
            report="report\n",
            manifest=_tiny_manifest(),
        )
    assert "DECISION_MARGIN_BLOCKED_STAGING_RESIDUE" in str(error.value)
    assert not out_dir.exists()


def test_materialize_verifies_hashes_after_the_swap(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / module.STAGE1_SUMMARY_NAME).write_text("a\n1\n", encoding="utf-8")
    hashes = {module.STAGE1_SUMMARY_NAME: module._sha256_file(staging / module.STAGE1_SUMMARY_NAME)}
    out_dir = tmp_path / "result"
    assert module.materialize(staging=staging, out_dir=out_dir, hashes=hashes) == (
        module.FRESH_ATOMIC_RENAME
    )

    second = tmp_path / "second"
    second.mkdir()
    (second / module.STAGE1_SUMMARY_NAME).write_text("b\n", encoding="utf-8")
    with pytest.raises(module.CheckFailure) as error:
        module.materialize(
            staging=second,
            out_dir=out_dir,
            hashes={module.STAGE1_SUMMARY_NAME: "sha256:" + "0" * 64},
        )
    assert "DECISION_MARGIN_BLOCKED_MATERIALIZATION_VERIFICATION" in str(error.value)


# ----------------------------------------------------------------------
# output collision
# ----------------------------------------------------------------------
def test_output_collision_gate(tmp_path: Path) -> None:
    out_dir = tmp_path / "result"
    inputs = {"checkpoints/X": "sha256:" + "a" * 64}
    source = "sha256:" + "b" * 64

    fresh = module.check_output_collision(
        out_dir=out_dir,
        head="HEAD1",
        input_hashes=inputs,
        diagnostic_source_sha256=source,
    )
    assert fresh["regeneration"] is False

    with pytest.raises(module.CheckFailure) as error:
        out_dir.mkdir()
        module.check_output_collision(
            out_dir=out_dir,
            head="HEAD1",
            input_hashes=inputs,
            diagnostic_source_sha256=source,
        )
    assert "DECISION_MARGIN_BLOCKED_OUTPUT_COLLISION" in str(error.value)
    assert "OUTPUT_DIRECTORY_WITHOUT_MANIFEST" in str(error.value)

    (out_dir / module.MANIFEST_NAME).write_text(
        json.dumps(
            {
                "git_head": "HEAD1",
                "input_artifact_hashes": inputs,
                "diagnostic_source_sha256": source,
                "run_timestamp": "t",
            }
        ),
        encoding="utf-8",
    )
    identical = module.check_output_collision(
        out_dir=out_dir,
        head="HEAD1",
        input_hashes=inputs,
        diagnostic_source_sha256=source,
    )
    assert identical["regeneration"] is True

    # a changed diagnostic source must never overwrite an earlier result
    with pytest.raises(module.CheckFailure) as error:
        module.check_output_collision(
            out_dir=out_dir,
            head="HEAD1",
            input_hashes=inputs,
            diagnostic_source_sha256="sha256:" + "c" * 64,
        )
    assert "diagnostic_source_sha256" in str(error.value)

    # so must a different head or different inputs
    with pytest.raises(module.CheckFailure) as error:
        module.check_output_collision(
            out_dir=out_dir,
            head="HEAD2",
            input_hashes=inputs,
            diagnostic_source_sha256=source,
        )
    assert "git_head" in str(error.value)
    with pytest.raises(module.CheckFailure) as error:
        module.check_output_collision(
            out_dir=out_dir,
            head="HEAD1",
            input_hashes={"checkpoints/X": "sha256:" + "d" * 64},
            diagnostic_source_sha256=source,
        )
    assert "input_artifact_hashes" in str(error.value)


def test_gate_repository_authority_reports_a_clean_tree() -> None:
    record = module.gate_repository_authority(out_dir=Path(C.ROOT) / "nonexistent_out")
    assert record["protected_tracked_modifications"] == []
    assert record["head_start"] == module._git_head()
    assert isinstance(record["preexisting_untracked"], list)
    assert isinstance(record["tracked_modifications_start"], list)
    # a pre-existing modification from other tooling is recorded, not fatal
    outside = Path(C.ROOT) / "nonexistent_out"
    assert not outside.exists()


def test_gate_repository_authority_blocks_a_dirty_protected_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "_git", lambda *args: " M formal/v2_phase7/sealed.py")
    with pytest.raises(module.CheckFailure) as error:
        module.gate_repository_authority(out_dir=tmp_path / "out")
    assert "PROTECTED_TRACKED_FILE_MODIFIED" in str(error.value)


def test_publish_blocks_a_tracked_modification_introduced_by_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "result"
    real_git = module._git

    def _git_with_new_dirt(*args: str) -> str:
        if args and args[0] == "status":  # the end-of-run worktree report
            return " M artifacts/diagnostics/unexpected.json"
        return real_git(*args)

    monkeypatch.setattr(module, "_git", _git_with_new_dirt)
    with pytest.raises(module.CheckFailure) as error:
        module.publish(
            out_dir=out_dir,
            frames=_tiny_frames(),
            report="report\n",
            manifest={
                "head_start": real_git("rev-parse", "HEAD"),
                "write_mode": module.WRITE_MODE,
                "tracked_modifications_start": [],
            },
        )
    assert "TRACKED_MODIFICATIONS_INTRODUCED_BY_RUN" in str(error.value)
    assert not out_dir.exists()
    assert not module.staging_path(out_dir).exists()


# ----------------------------------------------------------------------
# sealed canonical-v2 epoch projection
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def diagnostic_run(tmp_path_factory) -> tuple[dict, Path]:
    if not ATTENTION_PATH.is_file():
        pytest.skip("sealed canonical-v2 epoch not present in this checkout")
    out_dir = tmp_path_factory.mktemp("decision_margin") / "out"
    module.main(["--epoch-root", str(EPOCH_ROOT), "--out-dir", str(out_dir)])
    manifest = json.loads(
        (out_dir / module.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    return manifest, out_dir


def test_gates_and_frozen_anchors(diagnostic_run) -> None:
    manifest, _ = diagnostic_run
    gates = manifest["gates"]
    assert gates["gate_a_passed"] is True
    assert gates["gate_b_passed"] is True
    assert gates["gate_c_level1_passed"] is True
    assert gates["gate_c_level2_passed"] is True
    assert gates["gate_d_passed"] is True

    stage1 = gates["stage1"]
    assert stage1["expected_n_by_stage"] == {"PRE_IB": 29, "POST_IB_PRE_OB": 127}
    assert stage1["expected_k_by_stage"] == {"PRE_IB": 3, "POST_IB_PRE_OB": 13}
    assert stage1["abstaining_node_count"] == 0
    assert stage1["eligible_sets_identical_across_variants"] is True
    assert stage1["pairwise_common_support_equals_each_variant_eligible_set"] is True
    assert stage1["score_provenance"]["computational_authority"] is False
    assert stage1["score_provenance"]["conflicts"] == 0
    assert stage1["score_provenance"]["scores_compared"] > 0

    replay = gates["replay"]
    assert replay["level1_points_matched"] == replay["level1_points_expected"] == 160
    assert replay["level1_max_abs_deviation"] == pytest.approx(0.0, abs=1e-15)
    assert replay["level2_cases_matched"] == replay["level2_cases_expected"] == 64
    assert replay["level2_max_abs_deviation"] == pytest.approx(0.0, abs=1e-15)

    r_star = gates["r_star_counts"]
    assert r_star["total"] == 16
    assert r_star["by_stage"] == {"PRE_IB": 3, "POST_IB_PRE_OB": 13}
    assert r_star["r_star_unchanged"] is True
    assert manifest["stage2_N"] == 16
    assert manifest["stage2_reference_cohort_changed"] is False

    # the sealed M4 aggregates for the two HISTORY_JOINT-referenced pairs
    anchors = {anchor["comparison_id"]: anchor for anchor in gates["stage2_checks"]["anchors"]}
    assert set(anchors) == {
        "CURRENT_JOINT__TO__HISTORY_JOINT",
        "HISTORY_MARGINAL__TO__HISTORY_JOINT",
    }
    assert all(anchor["status"] == "MATCHED" for anchor in anchors.values())
    assert anchors["CURRENT_JOINT__TO__HISTORY_JOINT"]["sealed_recovery_loss"] == (
        pytest.approx(0.9070157057407199, abs=1e-12)
    )
    assert anchors["HISTORY_MARGINAL__TO__HISTORY_JOINT"]["sealed_recovery_loss"] == (
        pytest.approx(0.016464660023900957, abs=1e-12)
    )
    stage1_anchors = {anchor["comparison_id"] for anchor in gates["stage1_checks"]["anchors"]}
    assert stage1_anchors == {
        "CURRENT_JOINT__TO__HISTORY_JOINT",
        "HISTORY_MARGINAL__TO__HISTORY_JOINT",
    }


def test_manifest_declares_the_diagnostic_contract(diagnostic_run) -> None:
    manifest, _ = diagnostic_run
    assert manifest["analysis_name"] == "DECISION_MARGIN_MECHANISM_DIAGNOSTIC"
    assert manifest["analysis_type"] == "POST_HOC_MECHANISM_DIAGNOSTIC"
    assert manifest["split"] == "FINAL_TEST"
    assert manifest["model_retrained"] is False
    assert manifest["model_recalibrated"] is False
    assert manifest["parameter_reselected"] is False
    assert manifest["final_test_cohort_changed"] is False
    assert manifest["canonical_node_rule_changed"] is False
    assert manifest["support_rule_changed"] is False
    assert manifest["representation_redefined"] is False
    assert manifest["consequence_mapping_changed"] is False
    assert manifest["stage2_cohort_changed"] is False
    assert manifest["bootstrap_executed"] is False
    assert manifest["final_test_raw_data_read"] is False
    assert manifest["new_access_epoch_opened"] is False
    assert manifest["canonical_nominal_artifact_overwritten"] is False
    assert manifest["stage1_primary_q"] == 0.10
    assert manifest["certificate_is_sufficient_only"] is True
    assert manifest["certificate_failure_implies_change"] is False
    assert manifest["pairwise_attention_loss_is_primary"] is False
    assert manifest["delay_consequence_certificate_constructed"] is False
    assert manifest["stage_q_descriptor_scope"] == "BOUNDARY_LOCATION_ONLY"
    assert manifest["write_mode"] == "STAGED_TRANSACTIONAL_MATERIALIZATION"
    assert manifest["partial_output_exposed"] is False
    assert manifest["manifest_self_hash_included"] is False
    assert manifest["head_stable"] is True
    assert manifest["head_end"] == manifest["head_start"]
    assert manifest["tracked_modifications_introduced_by_run"] == []
    assert isinstance(manifest["tracked_modifications_start"], list)
    assert isinstance(manifest["tracked_modifications_end"], list)
    assert manifest["protected_tracked_modifications"] == []
    assert manifest["diagnostic_source_sha256"] is not None
    assert manifest["test_source_sha256"] is not None
    # the two tolerance roles share one frozen constant but stay distinct notions
    assert (
        manifest["numerical_tolerance"]["source"]
        == manifest["objective_replay_tolerance"]["source"]
        == "C.M3_NUMERICAL_COMPARISON_TOLERANCE"
    )
    assert manifest["numerical_tolerance"]["value"] == (
        manifest["objective_replay_tolerance"]["value"]
    )
    assert (
        manifest["numerical_tolerance"]["role"]
        != manifest["objective_replay_tolerance"]["role"]
    )
    assert manifest["manifest_self_hash_reason"] == (
        "SELF_REFERENTIAL_HASH_NOT_DEFINED"
    )
    assert set(manifest["output_artifact_hashes"]) == set(module.PAYLOAD_ARTIFACTS)
    assert module.MANIFEST_NAME in manifest["output_artifact_paths"]


def test_stage1_summary_reproduces_the_frozen_capacity(diagnostic_run) -> None:
    _manifest, out_dir = diagnostic_run
    summary = pd.read_csv(out_dir / module.STAGE1_SUMMARY_NAME)
    assert len(summary) == 6
    assert set(summary.comparison_id) == {
        "CURRENT_JOINT__TO__HISTORY_JOINT",
        "HISTORY_POINT__TO__HISTORY_MARGINAL",
        "HISTORY_MARGINAL__TO__HISTORY_JOINT",
    }
    for _index, row in summary.iterrows():
        expected_n = 29 if row["stage"] == "PRE_IB" else 127
        expected_k = 3 if row["stage"] == "PRE_IB" else 13
        assert int(row["N_common"]) == expected_n
        assert int(row["K"]) == expected_k
        assert row["K"] == -(-expected_k)  # frozen ceil(q * N) anchor
        assert int(row["intersection_count"]) + int(row["changed_positions"]) == int(
            row["K"]
        )
        assert int(row["entered_count"]) == int(row["displaced_count"])
        assert bool(row["shortlist_identical"]) == (int(row["changed_positions"]) == 0)
        assert row["perturbation_span"] <= 2.0 * row["epsilon_inf"] + 1e-12
        if row["certificate_status"] == module.CERTIFIED_STABLE:
            assert bool(row["shortlist_identical"]) is True
            assert row["certificate_slack"] > 0.0
        if row["certificate_status"] == module.NO_STRICT_REFERENCE_MARGIN:
            assert row["cutoff_margin"] <= 1e-6
    assert "L_att" not in summary.columns
    assert "pairwise_attention_loss" in summary.columns
    assert set(summary.certificate_status) <= set(module.ALLOWED_CERTIFICATE_STATUSES)


def test_stage1_records_cover_every_common_support_chain(diagnostic_run) -> None:
    _manifest, out_dir = diagnostic_run
    records = pd.read_parquet(out_dir / module.STAGE1_RECORDS_NAME)
    assert len(records) == 3 * (29 + 127)
    assert set(records.stage) == {"PRE_IB", "POST_IB_PRE_OB"}
    for _key, group in records.groupby(["comparison_id", "stage"]):
        assert len(group) == row_count_for(group)
        assert group["abs_priority_delta"].ge(0.0).all()
        assert group["boundary_crossed"].eq(
            group["selected_ref"] != group["selected_alt"]
        ).all()
        assert group["priority_ref"].ge(0.0).all()


def row_count_for(group: pd.DataFrame) -> int:
    return 29 if group["stage"].iloc[0] == "PRE_IB" else 127


def test_stage2_certificates_and_curves_are_consistent(diagnostic_run) -> None:
    manifest, out_dir = diagnostic_run
    chains = pd.read_csv(out_dir / module.STAGE2_CHAIN_NAME)
    curves = pd.read_parquet(out_dir / module.STAGE2_CURVES_NAME)
    assert len(chains) == 3 * 16
    assert len(curves) == 3 * 16 * 10
    assert set(curves.u_minutes) == set(module.EXPECTED_ACTION_GRID)

    certified = chains[chains.certificate_status == module.CERTIFIED_STABLE]
    assert (certified.u_ref == certified.u_alt).all()
    assert (certified.action_gap > 0.0).all()
    no_strict = chains[chains.certificate_status == module.NO_STRICT_REFERENCE_MARGIN]
    assert (no_strict.action_gap.abs() <= 1e-6).all()

    assert chains["perturbation_span"].le(2.0 * chains["epsilon_inf"] + 1e-12).all()
    assert chains["reference_regret_of_alt_action"].ge(-1e-6).all()
    assert chains["action_difference_minutes"].ge(0.0).all()
    for _key, group in chains.groupby("comparison_id"):
        changed = group[group.action_changed]
        assert (
            group.reference_regret_of_alt_action[group.action_changed].ge(-1e-6).all()
        )
        event_total = (
            group.missed_activation.astype(int)
            + group.false_activation.astype(int)
            + group.under_recovery.astype(int)
            + group.over_recovery.astype(int)
        )
        assert event_total.sum() <= len(group)
        del changed

    # curves agree with the chain summaries at the reported optima
    merged = curves.merge(
        chains[["comparison_id", "node_id", "u_ref", "u_alt", "reference_best_objective"]],
        on=["comparison_id", "node_id"],
        how="inner",
    )
    assert len(merged) == len(curves)
    ref_optimal = merged[merged.is_ref_optimal]
    assert (ref_optimal.u_minutes == ref_optimal.u_ref).all()
    assert (
        ref_optimal.J_ref - ref_optimal.reference_best_objective
    ).abs().le(1e-12).all()
    assert manifest["stage_q_cross_check"]["mismatches"] == []


def test_stage2_summary_counts_and_scopes(diagnostic_run) -> None:
    _manifest, out_dir = diagnostic_run
    summary = pd.read_csv(out_dir / module.STAGE2_SUMMARY_NAME)
    assert len(summary) == 3 * 3  # three comparisons x (ALL, PRE, TURN)
    assert set(summary.scope) == {"ALL", "PRE", "TURN"}
    for _index, row in summary.iterrows():
        assert row["N_certified_stable"] + row["N_not_certified_but_stable"] + (
            row["N_not_certified_and_changed"]
        ) + row["N_no_strict_reference_margin"] + row["N_abstain"] == (
            row["N_chain_total"]
        )
        assert row["N_action_changed"] + row["N_action_unchanged"] == (
            row["N_chain_total"]
        )
        assert row["N_action_unchanged"] == row["N_exact_agreement"]
        assert row["N_abstain"] == 0
    all_rows = summary[summary.scope == "ALL"]
    assert set(all_rows.N_chain_total) == {16}
    stage_rows = summary[summary.scope != "ALL"]
    assert set(stage_rows[stage_rows.scope == "PRE"].N_chain_total) == {3}
    assert set(stage_rows[stage_rows.scope == "TURN"].N_chain_total) == {13}


def test_headline_history_point_pair_is_not_redefined(diagnostic_run) -> None:
    """Pair B exists only here and never replaces HISTORY_POINT -> HISTORY_JOINT."""

    manifest, out_dir = diagnostic_run
    summary = pd.read_csv(out_dir / module.STAGE1_SUMMARY_NAME)
    point_to_marginal = summary[
        summary.comparison_id == "HISTORY_POINT__TO__HISTORY_MARGINAL"
    ]
    assert len(point_to_marginal) == 2
    assert set(point_to_marginal.reference_variant) == {"HISTORY_MARGINAL"}
    assert set(point_to_marginal.alternative_variant) == {"HISTORY_POINT"}
    # its loss is diagnostic-local and is never the primary HJ-referenced loss
    assert manifest["pairwise_attention_loss_is_primary"] is False

    published = json.loads(
        (EPOCH_ROOT / "PAPER_FACING_SECTION5_RESULTS.json").read_text(encoding="utf-8")
    )
    section = published["section_5_3_information_value"]
    assert section["reference"]["comparator_id"] == "HISTORY_JOINT"
    headline_point = next(
        item for item in section["comparators"] if item["comparator_id"] == "HISTORY_POINT"
    )
    headline_loss = float(headline_point["stage1_attention"]["L_att"])
    assert headline_loss == pytest.approx(0.557499838186944, abs=1e-15)
    # the pairwise marginal increment is a different quantity: the diagnostic
    # must not have overwritten, nor be confused with, the headline value
    assert not point_to_marginal.pairwise_attention_loss.apply(
        lambda value: abs(float(value) - headline_loss) <= 1e-15
    ).any()


def test_outputs_exclude_prohibited_fields(diagnostic_run) -> None:
    _manifest, out_dir = diagnostic_run
    frames = {
        module.STAGE1_SUMMARY_NAME: pd.read_csv(out_dir / module.STAGE1_SUMMARY_NAME),
        module.STAGE2_CHAIN_NAME: pd.read_csv(out_dir / module.STAGE2_CHAIN_NAME),
        module.STAGE2_SUMMARY_NAME: pd.read_csv(out_dir / module.STAGE2_SUMMARY_NAME),
        module.STAGE_Q_BOUNDARY_NAME: pd.read_csv(out_dir / module.STAGE_Q_BOUNDARY_NAME),
        module.STAGE1_RECORDS_NAME: pd.read_parquet(out_dir / module.STAGE1_RECORDS_NAME),
        module.STAGE2_CURVES_NAME: pd.read_parquet(out_dir / module.STAGE2_CURVES_NAME),
    }
    manifest = json.loads(
        (out_dir / module.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    module.assert_no_prohibited_columns(frames=frames, manifest=manifest)

    boundary = frames[module.STAGE_Q_BOUNDARY_NAME]
    assert len(boundary) == 8
    assert set(boundary.q) == {0.05, 0.10, 0.20, 0.30}
    assert set(boundary.N_supported) == {29, 127}
    assert boundary["consequence_cutoff_margin"].ge(0.0).all()
    assert boundary["delay_consequence_overlap_rate"].between(0.0, 1.0).all()
    assert manifest["stage_q_cross_check"]["cross_check_executed"] is True
    assert manifest["stage_q_cross_check"]["rows_compared"] == 8
    assert manifest["stage_q_cross_check"]["comparisons"] == 8 * 7
    assert manifest["stage_q_cross_check"]["mismatches"] == []


def test_report_states_the_reading_rules(diagnostic_run) -> None:
    _manifest, out_dir = diagnostic_run
    report = (out_dir / module.REPORT_NAME).read_text(encoding="utf-8")
    assert "sufficient" in report
    assert "never necessary" in report
    assert "not a classifier" in report
    assert "SELF_REFERENTIAL_HASH_NOT_DEFINED" in report
    for comparison in (
        "CURRENT_JOINT__TO__HISTORY_JOINT",
        "HISTORY_POINT__TO__HISTORY_MARGINAL",
        "HISTORY_MARGINAL__TO__HISTORY_JOINT",
    ):
        assert comparison in report


def test_run_is_read_only_over_the_sealed_epoch(diagnostic_run) -> None:
    manifest, _out_dir = diagnostic_run
    for name, path in manifest["input_artifact_paths"].items():
        assert module._sha256_file(Path(path)) == manifest["input_artifact_hashes"][name]
    seal = json.loads((EPOCH_ROOT / "EPOCH_SEAL.json").read_text(encoding="utf-8"))
    assert module._sha256_file(EPOCH_ROOT / "FINAL_TEST_EXECUTION_RESULT.json") == (
        seal["execution_result_sha256"]
    )
    assert module._sha256_file(EPOCH_ROOT / "POST_EXECUTION_AUDIT.json") == (
        seal["post_execution_audit_json_sha256"]
    )
