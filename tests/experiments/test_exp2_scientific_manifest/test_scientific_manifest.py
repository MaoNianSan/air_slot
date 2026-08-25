from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from exp.exp2.artifacts.action_manifest import (
    ActionFreezeStatus,
    ActionManifestPreparer,
    ActionSupportRecord,
    ActionSupportStatus,
    ScientificActionManifest,
)
from exp.exp2.execution.scientific_manifest import (
    M4ScientificGate,
    M4ScientificGateStatus,
    ScientificManifestStatus,
    ScientificManifestValidator,
)
from model.M4.residual_risk import RiskPolicyStatus
from model.common.monetary_system import MonetaryMappingStatus


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPOSITORY_ROOT / "configs" / "experiment" / "exp2_scientific_manifest.yaml"


def _write_manifest_copy(tmp_path, mutate):
    payload = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    path = tmp_path / "exp2_scientific_manifest.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_manifest_binds_current_registries_but_remains_blocked_for_freeze():
    result = ScientificManifestValidator().validate_path(MANIFEST_PATH)

    assert result.status is ScientificManifestStatus.BLOCKED_MISSING_ARTIFACT
    assert result.dataset_binding_valid is True
    assert result.lineage_valid is True
    assert "M1_ARTIFACT_REQUIRED" in result.reason_codes
    assert result.m4_gate.status is M4ScientificGateStatus.BLOCKED_UNSUPPORTED_MAPPING
    assert "MAPPING_UNRESOLVED" in result.m4_gate.reason_codes


def test_registry_hash_inconsistency_is_fail_closed(tmp_path):
    path = _write_manifest_copy(
        tmp_path,
        lambda payload: payload["M3"]["action_manifest"].update(
            {"registry_hash": "sha256:" + "0" * 64}
        ),
    )

    result = ScientificManifestValidator().validate_path(path)

    assert result.status is ScientificManifestStatus.BLOCKED_LINEAGE_MISMATCH
    assert "M3_ACTION_REGISTRY_HASH_MISMATCH" in result.reason_codes


def test_required_checkpoint_is_reported_as_missing_artifact():
    result = ScientificManifestValidator().validate_path(MANIFEST_PATH)

    assert "M1_CHECKPOINT_REQUIRED" in result.reason_codes
    assert result.status is ScientificManifestStatus.BLOCKED_MISSING_ARTIFACT


def test_m4_gate_rejects_test_only_mapping_and_policy():
    manifest = ScientificManifestValidator().load(MANIFEST_PATH)
    binding = manifest.m4.model_copy(update={
        "risk_policy": "frozen-risk-policy.json",
        "artifact_id": "frozen-m4-artifact",
        "hash": "sha256:" + "a" * 64,
        "mapping_status": MonetaryMappingStatus.TEST_ONLY,
        "risk_policy_status": RiskPolicyStatus.TEST_ONLY,
        "support_status": "SUPPORTED",
        "mapping_resolved": True,
        "mapping_provenance": ("TEST_FIXTURE_MAPPING_PROVENANCE",),
        "risk_policy_provenance": ("TEST_FIXTURE_POLICY_PROVENANCE",),
    })

    result = M4ScientificGate().validate(binding)

    assert result.status is M4ScientificGateStatus.BLOCKED_UNSUPPORTED_MAPPING
    assert "TEST_ONLY_MAPPING_REJECTED" in result.reason_codes
    assert "TEST_ONLY_RISK_POLICY_REJECTED" in result.reason_codes


def test_action_manifest_requires_ordered_a00_and_supported_non_a00_action():
    manifest = ScientificActionManifest(
        action_ids=("A00", "A11"),
        action_registry_hash="sha256:" + "1" * 64,
        response_bundle_hash="sha256:" + "2" * 64,
        support_records=(
            ActionSupportRecord(action_id="A00", support_status=ActionSupportStatus.SUPPORTED),
            ActionSupportRecord(action_id="A11", support_status=ActionSupportStatus.SUPPORTED),
        ),
    )
    assert ActionManifestPreparer().prepare(manifest).status is ActionFreezeStatus.READY

    unsupported = manifest.model_copy(update={
        "support_records": (
            ActionSupportRecord(action_id="A00", support_status=ActionSupportStatus.SUPPORTED),
            ActionSupportRecord(action_id="A11", support_status=ActionSupportStatus.ABSTAIN),
        )
    })
    result = ActionManifestPreparer().prepare(unsupported)
    assert result.status is ActionFreezeStatus.BLOCKED
    assert "NO_SUPPORTED_NON_A00_ACTION" in result.reason_codes

    unordered = manifest.model_copy(update={
        "action_ids": ("A11", "A00"),
    })
    result = ActionManifestPreparer().prepare(unordered)
    assert result.status is ActionFreezeStatus.BLOCKED
    assert "A00_MUST_BE_FIRST" in result.reason_codes
