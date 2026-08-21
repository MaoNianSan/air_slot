from __future__ import annotations

import pytest

from exp.common.result_schema import ExperimentResult
from exp.exp2.execution.artifact_loader import Exp2ExecutionBlocked
from exp.exp2.execution.execution_manifest import (
    ArtifactKind,
    ExecutionReadinessStatus,
)
from exp.exp2.runner import Exp2Runner
from exp.exp2.variants import EXP2_VARIANT_IDS
from model.common.identity import content_id

from .conftest import build_production_manifest_copy


def test_fixture_package_is_explicitly_test_only_and_content_linked(smoke_package):
    assert all(
        envelope["artifact_scope"] == "TEST_ONLY_SMOKE"
        for envelope in smoke_package["envelopes"].values()
    )
    assert smoke_package["responses"]["artifact_scope"] == "TEST_ONLY_SMOKE"
    assert smoke_package["risk_policy"]["artifact_scope"] == "TEST_ONLY_SMOKE"
    assert all(
        envelope["artifact_hash"] == content_id(envelope["payload"])
        for envelope in smoke_package["envelopes"].values()
    )
    assert (
        smoke_package["envelopes"][ArtifactKind.M3]["payload"]
        ["response_registry_hash"]
        == content_id(smoke_package["responses"]["responses"])
    )
    assert (
        smoke_package["envelopes"][ArtifactKind.M4]["payload"]
        ["risk_policy_hash"]
        == content_id(smoke_package["risk_policy"])
    )


def test_all_six_variants_execute_through_one_smoke_binding(
    smoke_package, smoke_downstream, smoke_model_versions
):
    calls, m3_executor, m4_evaluator = smoke_downstream
    anchor = smoke_package["manifest"]
    manifests = tuple(
        anchor.model_copy(update={"variant_id": variant_id})
        for variant_id in EXP2_VARIANT_IDS
    )

    results = Exp2Runner().execute_smoke_manifests(
        manifests,
        artifact_root=smoke_package["root"],
        m3_executor=m3_executor,
        m4_evaluator=m4_evaluator,
        model_versions=smoke_model_versions,
    )

    assert tuple(result.variant_id for result in results) == EXP2_VARIANT_IDS
    assert all(isinstance(result, ExperimentResult) for result in results)
    assert all(result.provenance["paper_result"] is False for result in results)
    assert all(
        result.metrics["STATE_REPRESENTATION_LINEAGE_PRESERVED"].value is True
        for result in results
    )
    assert all(
        metric.metadata["artifact_lineage"]["execution_scope"]
        == "TEST_ONLY_SMOKE"
        for result in results
        for metric in result.metrics.values()
    )

    m3_calls = [item for item in calls if item["stage"] == "M3"]
    m4_calls = [item for item in calls if item["stage"] == "M4"]
    assert len(m3_calls) == len(m4_calls)
    expected_representations = {
        "EXP2A_JOINT": ("EXP2A_JOINT", "EXP2B_7COMP"),
        "EXP2A_MARGINAL": ("EXP2A_MARGINAL", "EXP2B_7COMP"),
        "EXP2A_POINT": ("EXP2A_POINT", "EXP2B_7COMP"),
        "EXP2B_7COMP": ("EXP2A_JOINT", "EXP2B_7COMP"),
        "EXP2B_3CHANNEL": ("EXP2A_JOINT", "EXP2B_3CHANNEL"),
        "EXP2B_SCALAR": ("EXP2A_JOINT", "EXP2B_SCALAR"),
    }
    for variant_id, expected in expected_representations.items():
        assert any(
            item["variant_id"] == variant_id
            and (item["scenario_variant"], item["consequence_variant"]) == expected
            for item in m3_calls
        )
        assert any(item["variant_id"] == variant_id for item in m4_calls)

    comparison_hashes = {
        result.variant_id: result.metrics[
            "STATE_REPRESENTATION_LINEAGE_PRESERVED"
        ].metadata["artifact_lineage"]["comparison_representation_hash"]
        for result in results
    }
    assert len({comparison_hashes[item] for item in EXP2_VARIANT_IDS[:3]}) == 3
    assert len({comparison_hashes[item] for item in EXP2_VARIANT_IDS[3:]}) == 3


@pytest.mark.parametrize(
    ("copy_options", "expected_status", "expected_reason"),
    (
        (
            {"keep_test_only_m4": True},
            ExecutionReadinessStatus.BLOCKED_UNSUPPORTED_MAPPING,
            "TEST_ONLY_SMOKE_ARTIFACT_REJECTED_BY_PRODUCTION",
        ),
        (
            {"drop_m3_response": True},
            ExecutionReadinessStatus.BLOCKED_MISSING_ARTIFACT,
            "M3_CONTRACT_INVALID",
        ),
        (
            {"drop_m4_risk_policy": True},
            ExecutionReadinessStatus.BLOCKED_MISSING_ARTIFACT,
            "M4_CONTRACT_INVALID",
        ),
    ),
)
def test_production_gate_rejects_smoke_or_incomplete_support(
    tmp_path,
    smoke_package,
    smoke_downstream,
    smoke_model_versions,
    copy_options,
    expected_status,
    expected_reason,
):
    calls, m3_executor, m4_evaluator = smoke_downstream
    manifest = build_production_manifest_copy(
        tmp_path, smoke_package, **copy_options
    )

    with pytest.raises(Exp2ExecutionBlocked) as exc_info:
        Exp2Runner().execute_manifest(
            manifest,
            artifact_root=tmp_path,
            m3_executor=m3_executor,
            m4_evaluator=m4_evaluator,
            model_versions=smoke_model_versions,
        )

    assert exc_info.value.status is expected_status
    assert expected_reason in exc_info.value.reason
    assert calls == []
