import pytest
from pydantic import ValidationError

from exp.exp2.execution.execution_manifest import (
    Exp2ExecutionManifest,
    validate_variant_manifests,
)


def test_manifest_validates_all_required_identities(execution_fixture):
    manifest = execution_fixture["manifest"]
    restored = Exp2ExecutionManifest.model_validate_json(manifest.model_dump_json())

    assert restored == manifest
    assert manifest.manifest_hash.startswith("sha256:")
    assert manifest.dataset_id == "DATA2_FIXTURE"
    assert manifest.split == "DEVELOPMENT_FIXTURE"
    assert manifest.seed == 17


def test_manifest_rejects_wrong_artifact_slot_and_unknown_variant(execution_fixture):
    payload = execution_fixture["manifest"].model_dump(mode="python")
    payload["m1_artifact"] = payload["m2_artifact"]
    with pytest.raises(ValidationError, match="ARTIFACT_SLOT_MISMATCH"):
        Exp2ExecutionManifest.model_validate(payload)

    payload = execution_fixture["manifest"].model_dump(mode="python")
    payload["variant_id"] = "EXP2_UNKNOWN"
    with pytest.raises(ValidationError, match="VARIANT_UNKNOWN"):
        Exp2ExecutionManifest.model_validate(payload)


def test_variant_manifests_must_share_all_fixed_bindings(execution_fixture):
    manifest = execution_fixture["manifest"]
    marginal = manifest.model_copy(update={"variant_id": "EXP2A_MARGINAL"})
    validate_variant_manifests((manifest, marginal))

    changed = marginal.model_copy(update={"config_hash": "sha256:" + "8" * 64})
    with pytest.raises(ValueError, match="FIXED_BINDING_IDENTITY_MISMATCH"):
        validate_variant_manifests((manifest, changed))
