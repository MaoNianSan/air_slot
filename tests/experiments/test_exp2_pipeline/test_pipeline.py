from pathlib import Path

import pytest
import yaml

from exp.common.result_schema import ExperimentResult
from exp.exp2.execution.artifact_loader import Exp2ExecutionBlocked
from exp.exp2.runner import Exp2Runner


def test_pipeline_config_freezes_shape_without_scientific_values():
    config_path = (
        Path(__file__).resolve().parents[3]
        / "configs" / "experiment" / "exp2.yaml"
    )
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert config["experiment_id"] == "EXP2"
    assert config["variants"]["exp2a"]["reference"] == "EXP2A_JOINT"
    assert config["variants"]["exp2b"]["reference"] == "EXP2B_7COMP"
    assert all(
        reference["path"] == "REQUIRED"
        for reference in config["artifact_references"].values()
    )
    assert config["execution_gate"]["paper_result"] is False


def test_full_artifact_to_result_pipeline(execution_fixture, recording_executors, model_versions):
    calls, m3_executor, m4_evaluator = recording_executors
    result = Exp2Runner().execute_manifest(
        execution_fixture["manifest"],
        artifact_root=execution_fixture["root"],
        m3_executor=m3_executor,
        m4_evaluator=m4_evaluator,
        model_versions=model_versions,
    )

    assert isinstance(result, ExperimentResult)
    assert result.variant_id == "EXP2A_JOINT"
    assert [item[:2] for item in calls] == [("M3", "EXP2A_JOINT"), ("M4", "EXP2A_JOINT")]
    assert result.config_hash == execution_fixture["manifest"].config_hash
    assert all("artifact_lineage" in metric.metadata for metric in result.metrics.values())
    assert all(
        metric.metadata["artifact_lineage"]["m3_artifact_hash"]
        == execution_fixture["manifest"].m3_artifact.artifact_hash
        for metric in result.metrics.values()
    )
    assert result.metrics["STATE_REPRESENTATION_LINEAGE_PRESERVED"].value is True


def test_variant_switching_uses_one_fixed_binding(execution_fixture, recording_executors, model_versions):
    calls, m3_executor, m4_evaluator = recording_executors
    anchor = execution_fixture["manifest"]
    manifests = (
        anchor.model_copy(update={"variant_id": "EXP2A_MARGINAL"}),
        anchor.model_copy(update={"variant_id": "EXP2B_SCALAR"}),
    )
    results = Exp2Runner().execute_manifests(
        manifests,
        artifact_root=execution_fixture["root"],
        m3_executor=m3_executor,
        m4_evaluator=m4_evaluator,
        model_versions=model_versions,
    )

    assert tuple(result.variant_id for result in results) == ("EXP2A_MARGINAL", "EXP2B_SCALAR")
    assert [(row[1], row[2], row[3]) for row in calls if row[0] == "M3"] == [
        ("EXP2A_JOINT", "EXP2A_JOINT", "EXP2B_7COMP"),
        ("EXP2A_MARGINAL", "EXP2A_MARGINAL", "EXP2B_7COMP"),
        ("EXP2B_7COMP", "EXP2A_JOINT", "EXP2B_7COMP"),
        ("EXP2B_SCALAR", "EXP2A_JOINT", "EXP2B_SCALAR"),
    ]


def test_missing_artifact_blocks_before_downstream(execution_fixture, recording_executors, model_versions):
    calls, m3_executor, m4_evaluator = recording_executors
    manifest = execution_fixture["manifest"]
    missing = manifest.m1_artifact.model_copy(update={"path": "missing-m1.json"})

    with pytest.raises(Exp2ExecutionBlocked, match="BLOCKED_MISSING_ARTIFACT"):
        Exp2Runner().execute_manifest(
            manifest.model_copy(update={"m1_artifact": missing}),
            artifact_root=execution_fixture["root"],
            m3_executor=m3_executor,
            m4_evaluator=m4_evaluator,
            model_versions=model_versions,
        )
    assert calls == []


def test_lineage_and_fixed_binding_reject_variant_specific_artifacts(
    execution_fixture, recording_executors, model_versions
):
    _, m3_executor, m4_evaluator = recording_executors
    anchor = execution_fixture["manifest"]
    changed = anchor.model_copy(update={
        "variant_id": "EXP2B_3CHANNEL",
        "config_hash": "sha256:" + "8" * 64,
    })

    with pytest.raises(ValueError, match="FIXED_BINDING_IDENTITY_MISMATCH"):
        Exp2Runner().execute_manifests(
            (anchor, changed),
            artifact_root=execution_fixture["root"],
            m3_executor=m3_executor,
            m4_evaluator=m4_evaluator,
            model_versions=model_versions,
        )
