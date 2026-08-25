import json

import pytest

from exp.exp2.execution.artifact_loader import (
    ARTIFACT_SCHEMA_VERSION,
    Exp2ArtifactLoader,
    Exp2ExecutionBlocked,
)
from exp.exp2.execution.execution_manifest import (
    ArtifactKind,
    ArtifactReference,
    ExecutionReadinessStatus,
)
from model.common.identity import content_id


def test_loader_checks_all_artifact_hashes_and_contracts(execution_fixture):
    loader = Exp2ArtifactLoader(artifact_root=execution_fixture["root"])
    artifacts = loader.load_all(execution_fixture["manifest"])

    assert artifacts.status is ExecutionReadinessStatus.READY
    assert artifacts.m1.scenario_hash.startswith("sha256:")
    assert artifacts.m2.cu_lineage.registry_id == "M2_CU_FIXTURE"
    assert artifacts.m3.action_ids == ("A00",)
    assert artifacts.m4.monetary_mapping_hash == "sha256:" + "5" * 64


def test_missing_or_hash_mismatched_artifact_is_explicitly_blocked(execution_fixture):
    loader = Exp2ArtifactLoader(artifact_root=execution_fixture["root"])
    missing = execution_fixture["references"]["m1"].model_copy(
        update={"path": "does-not-exist.json"}
    )
    with pytest.raises(Exp2ExecutionBlocked) as captured:
        loader.load_m1(missing)
    assert captured.value.status is ExecutionReadinessStatus.BLOCKED_MISSING_ARTIFACT

    path = execution_fixture["root"] / "m1.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["payload"]["scenarios"][0]["D_OB"] = 99.0
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(Exp2ExecutionBlocked) as captured:
        loader.load_m1(execution_fixture["references"]["m1"])
    assert captured.value.status is ExecutionReadinessStatus.BLOCKED_MISSING_ARTIFACT
    assert "ARTIFACT_UNAVAILABLE_OR_INVALID" in captured.value.reason


def test_unfrozen_m4_mapping_or_policy_has_no_fallback(execution_fixture):
    root = execution_fixture["root"]
    payload = {
        **execution_fixture["payloads"]["m4"],
        "monetary_mapping_status": "NOT_FROZEN",
    }
    artifact_hash = content_id(payload)
    path = root / "m4_unfrozen.json"
    path.write_text(json.dumps({
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_kind": "M4",
        "artifact_version": "M4_UNFROZEN_V1",
        "artifact_hash": artifact_hash,
        "payload": payload,
    }), encoding="utf-8")
    reference = ArtifactReference(
        artifact_kind=ArtifactKind.M4,
        path=path.name,
        artifact_version="M4_UNFROZEN_V1",
        artifact_hash=artifact_hash,
    )

    with pytest.raises(Exp2ExecutionBlocked) as captured:
        Exp2ArtifactLoader(artifact_root=root).load_m4(reference)
    assert captured.value.status is ExecutionReadinessStatus.BLOCKED_UNSUPPORTED_MAPPING
    assert "NOT_FROZEN" in captured.value.reason
