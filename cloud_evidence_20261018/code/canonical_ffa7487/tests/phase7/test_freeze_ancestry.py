"""R2-aware freeze ancestry contract tests."""

from __future__ import annotations

import copy

from validation.v2_phase7 import freeze_ancestry


def test_freeze_ancestry_resolves_phase6_and_r2_tags() -> None:
    report = freeze_ancestry.check_freeze_ancestry()

    assert report["status"] == "PASS"
    assert report["failures"] == []
    assert report["registry"]["phase6"] == {
        "tag": freeze_ancestry.PHASE6_TAG,
        "tag_object": freeze_ancestry.PHASE6_TAG_OBJECT,
        "tag_target_commit": freeze_ancestry.PHASE6_TAG_TARGET,
        "object_type": "tag",
        "snapshot": report["registry"]["phase6"]["snapshot"],
    }
    assert report["registry"]["r2"] == {
        "tag": freeze_ancestry.R2_TAG,
        "tag_object": freeze_ancestry.R2_TAG_OBJECT,
        "tag_target_commit": freeze_ancestry.R2_TAG_TARGET,
        "object_type": "tag",
        "snapshot": report["registry"]["r2"]["snapshot"],
    }
    assert report["registry"]["phase6"]["snapshot"]["status"] == "PASS"
    assert report["registry"]["r2"]["snapshot"]["status"] == "PASS"


def test_freeze_ancestry_binds_parent_linkage_and_immutability() -> None:
    report = freeze_ancestry.check_freeze_ancestry()

    assert report["ancestry"] == {
        "phase6_is_ancestor_of_r2": True,
        "r2_is_ancestor_of_head": True,
    }
    assert all(report["parent_linkage"].values())
    parent = report["registry_immutability"][freeze_ancestry.PARENT_REGISTRY]
    r2 = report["registry_immutability"][freeze_ancestry.R2_REGISTRY]
    assert parent["immutable"] is True
    assert r2["immutable"] is True
    assert r2["parent_bytes_sha256"] is None
    for path in freeze_ancestry.ADOPTED_REGISTRIES:
        assert report["registry_immutability"][path]["immutable"] is True


def test_freeze_ancestry_never_reads_legacy_final_test_tree() -> None:
    report = freeze_ancestry.check_freeze_ancestry()

    assert report["final_test_boundary"]["legacy_final_test_tree_read"] is False
    assert report["final_test_boundary"]["final_test_absolute_path"].endswith(
        "artifacts\\experiment\\final_test"
    ) or report["final_test_boundary"]["final_test_absolute_path"].endswith(
        "artifacts/experiment/final_test"
    )


def test_freeze_ancestry_report_allows_only_lagging_ancestor_head() -> None:
    report = freeze_ancestry.check_freeze_ancestry()
    observed = copy.deepcopy(report)
    observed["registry"]["current_head"] = freeze_ancestry._git_text(
        "rev-parse", "HEAD^"
    )

    assert freeze_ancestry._report_comparison_failures(observed, report) == []


def test_freeze_ancestry_report_rejects_non_ancestor_head() -> None:
    report = freeze_ancestry.check_freeze_ancestry()
    observed = copy.deepcopy(report)
    observed["registry"]["current_head"] = "0" * 40

    assert freeze_ancestry._report_comparison_failures(observed, report) == [
        "PHASE7_FREEZE_ANCESTRY_REPORT_HEAD_NOT_ANCESTOR"
    ]


def test_freeze_ancestry_report_rejects_non_head_mutations() -> None:
    report = freeze_ancestry.check_freeze_ancestry()
    observed = copy.deepcopy(report)
    observed["schema_version"] = "MUTATED"

    assert freeze_ancestry._report_comparison_failures(observed, report) == [
        "PHASE7_FREEZE_ANCESTRY_REPORT_MISMATCH"
    ]
