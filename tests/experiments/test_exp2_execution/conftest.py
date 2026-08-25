import json

import pytest

from exp.exp2.execution.artifact_loader import ARTIFACT_SCHEMA_VERSION
from exp.exp2.execution.execution_manifest import (
    ArtifactKind,
    ArtifactReference,
    Exp2ExecutionManifest,
)
from model.common.identity import content_id


def _write_artifact(path, kind, version, payload):
    artifact_hash = content_id(payload)
    path.write_text(json.dumps({
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_kind": kind.value,
        "artifact_version": version,
        "artifact_hash": artifact_hash,
        "payload": payload,
    }, indent=2), encoding="utf-8")
    return ArtifactReference(
        artifact_kind=kind,
        path=path.name,
        artifact_version=version,
        artifact_hash=artifact_hash,
    )


@pytest.fixture
def execution_fixture(tmp_path):
    m1_payload = {
        "scenarios": [{
            "scenario_id": 0,
            "scenario_weight": 1.0,
            "D_OB": 3.0,
            "D_TX": 2.0,
            "D_TO": 5.0,
            "lineage": ["M1_FIXTURE_LINEAGE"],
        }],
        "cutoff_provenance": {
            "decision_node_id": "NODE_1",
            "decision_time_utc": "2026-08-20T08:00:00+00:00",
            "information_cutoff_utc": "2026-08-20T08:00:00+00:00",
            "availability_rule": "AVAILABILITY_TIME_LE_INFORMATION_CUTOFF",
            "source_manifest_hash": "sha256:" + "1" * 64,
        },
    }
    component_ids = (
        "F_continuity", "F_execution", "F_propagation", "P_time",
        "P_itinerary", "P_service", "R_operating",
    )
    channels = (
        "Flight", "Flight", "Flight", "Passenger",
        "Passenger", "Passenger", "Resource",
    )
    m2_payload = {
        "consequences": [{
            "scenario_id": 0,
            "scenario_weight": 1.0,
            "components": [
                {
                    "component_id": component_id,
                    "aspect": channel,
                    "constructed_value_cu": float(index),
                    "support_state": "SUPPORTED",
                    "reference_lineage": [f"M2:{component_id}"],
                }
                for index, (component_id, channel) in enumerate(
                    zip(component_ids, channels, strict=True), start=1
                )
            ],
        }],
        "cu_lineage": {
            "registry_id": "M2_CU_FIXTURE",
            "registry_hash": "sha256:" + "2" * 64,
            "freeze_id": "M2_CU_FIXTURE_FREEZE",
            "reference_period": "FIXTURE_ONLY",
        },
    }
    m3_payload = {
        "action_ids": ["A00"],
        "action_registry_hash": "sha256:" + "3" * 64,
        "response_registry_hash": "sha256:" + "4" * 64,
    }
    m4_payload = {
        "monetary_mapping_hash": "sha256:" + "5" * 64,
        "monetary_mapping_status": "FROZEN",
        "risk_policy_hash": "sha256:" + "6" * 64,
        "risk_policy_status": "FROZEN",
    }
    references = {
        "m1": _write_artifact(tmp_path / "m1.json", ArtifactKind.M1, "M1_FIXTURE_V1", m1_payload),
        "m2": _write_artifact(tmp_path / "m2.json", ArtifactKind.M2, "M2_FIXTURE_V1", m2_payload),
        "m3": _write_artifact(tmp_path / "m3.json", ArtifactKind.M3, "M3_FIXTURE_V1", m3_payload),
        "m4": _write_artifact(tmp_path / "m4.json", ArtifactKind.M4, "M4_FIXTURE_V1", m4_payload),
    }
    manifest = Exp2ExecutionManifest(
        dataset_id="DATA2_FIXTURE",
        split="DEVELOPMENT_FIXTURE",
        seed=17,
        m1_artifact=references["m1"],
        m2_artifact=references["m2"],
        m3_artifact=references["m3"],
        m4_artifact=references["m4"],
        variant_id="EXP2A_JOINT",
        config_hash="sha256:" + "7" * 64,
    )
    return {
        "root": tmp_path,
        "manifest": manifest,
        "references": references,
        "payloads": {"m1": m1_payload, "m2": m2_payload, "m3": m3_payload, "m4": m4_payload},
        "write_artifact": _write_artifact,
    }
