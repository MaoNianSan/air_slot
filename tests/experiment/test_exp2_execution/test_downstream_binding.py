import pytest

from exp.exp2.execution.artifact_loader import Exp2ArtifactLoader
from exp.exp2.execution.downstream_binding import Exp2DownstreamExecutor
from exp.exp2.execution.execution_manifest import ExecutionReadinessStatus


def _must_not_execute(**kwargs):
    raise AssertionError("SCIENTIFIC_EXECUTION_NOT_AUTHORIZED")


def test_one_binding_locks_same_m3_and_m4_for_all_variants(execution_fixture):
    manifest = execution_fixture["manifest"]
    artifacts = Exp2ArtifactLoader(
        artifact_root=execution_fixture["root"]
    ).load_all(manifest)
    binding = Exp2DownstreamExecutor(
        manifest=manifest,
        artifacts=artifacts,
        m3_executor=_must_not_execute,
        m4_evaluator=_must_not_execute,
    )
    marginal = manifest.model_copy(update={"variant_id": "EXP2A_MARGINAL"})
    component = manifest.model_copy(update={"variant_id": "EXP2B_COMPONENT"})

    binding.assert_variant_manifests((manifest, marginal, component))
    assert binding.status is ExecutionReadinessStatus.READY
    assert binding.binding_hash.startswith("sha256:")
    assert binding.m3_executor_identity.endswith(":_must_not_execute")
    assert binding.m4_evaluator_identity.endswith(":_must_not_execute")


def test_binding_rejects_variant_specific_m4_identity(execution_fixture):
    manifest = execution_fixture["manifest"]
    artifacts = Exp2ArtifactLoader(
        artifact_root=execution_fixture["root"]
    ).load_all(manifest)
    binding = Exp2DownstreamExecutor(
        manifest=manifest,
        artifacts=artifacts,
        m3_executor=_must_not_execute,
        m4_evaluator=_must_not_execute,
    )
    changed_m4 = manifest.m4_artifact.model_copy(
        update={"artifact_hash": "sha256:" + "9" * 64}
    )
    changed = manifest.model_copy(update={
        "variant_id": "EXP2A_MARGINAL",
        "m4_artifact": changed_m4,
    })

    with pytest.raises(ValueError, match="FIXED_BINDING_IDENTITY_MISMATCH"):
        binding.assert_variant_manifests((manifest, changed))
