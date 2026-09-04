"""Reproducibility gates for a dirty-worktree model baseline seal."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from model.common.identity import content_id


ROOT = Path(__file__).resolve().parents[2]
CODE_MANIFEST_PATH = ROOT / "registries" / "MODEL_RUNTIME_CODE_MANIFEST_V1.json"
V1R1_MANIFEST_PATH = ROOT / "registries" / "MODEL_RUNTIME_CODE_MANIFEST_V1R1.json"
ACTIVE_POINTER_PATH = ROOT / "registries" / "ACTIVE_MODEL_IMPLEMENTATION.json"
SNAPSHOT_MANIFEST_PATH = (
    ROOT
    / "artifacts"
    / "provenance"
    / "model_baseline_v1_source"
    / "MODEL_RUNTIME_SOURCE_SNAPSHOT_V1_MANIFEST.json"
)
V1_STATUS_PATH = ROOT / "registries" / "MODEL_RUNTIME_CODE_MANIFEST_V1_PROVENANCE.json"
SEAL_PATH = ROOT / "registries" / "MODEL_BASELINE_SEAL_V1.json"
OLD_FINGERPRINT = (
    "sha256:b556f0ad692692f0ddda5b7666c3932c1541e748f3f9724b0b05a112d93400d1"
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def test_historical_runtime_manifest_is_immutable_provenance():
    manifest = _read(CODE_MANIFEST_PATH)
    entries = manifest["entries"]
    paths = [entry["relative_path"] for entry in entries]

    assert manifest["schema_version"] == "MODEL_RUNTIME_CODE_MANIFEST_V1"
    assert manifest["entry_count"] == len(entries)
    assert paths == sorted(paths)
    assert len(paths) == len(set(paths))
    assert all(not path.startswith(("tests/", "validation/", "reports/", "artifacts/")) for path in paths)
    assert {
        "model/PRE/foundation.py",
        "model/M1/contracts.py",
        "model/M1/scenarios.py",
        "model/M2/scientific_registry.py",
        "model/M3/readiness.py",
        "model/M4/residual_risk.py",
        "configs/scientific/foundation.yaml",
        "configs/engineering/m1_data2_development_fast.yaml",
    }.issubset(paths)

    snapshot = _read(SNAPSHOT_MANIFEST_PATH)
    assert snapshot["status"] == "HISTORICAL_IMMUTABLE_PROVENANCE"
    assert snapshot["importable"] is False
    assert snapshot["entry_count"] == len(entries)
    assert snapshot["source_manifest_hash"] == manifest["manifest_hash"]
    assert [item["relative_path"] for item in snapshot["entries"]] == paths
    for entry in snapshot["entries"]:
        path = SNAPSHOT_MANIFEST_PATH.parent / entry["relative_path"]
        assert path.is_file()
        assert _sha256(path) == entry["sha256"]
        assert entry["size"] == path.stat().st_size
        assert entry["role"]

    hash_basis = {
        "schema_version": manifest["schema_version"],
        "entries": entries,
    }
    assert content_id(hash_basis) == manifest["manifest_hash"]


def test_active_pointer_uses_v1r1_manifest_and_live_hashes():
    pointer = _read(ACTIVE_POINTER_PATH)
    implementation = _read(ROOT / pointer["implementation_registry_path"])
    manifest = _read(V1R1_MANIFEST_PATH)
    assert pointer["status"] == "ACTIVE"
    assert pointer["active_implementation"] == "MODEL_BASELINE_IMPLEMENTATION_V1R1"
    assert pointer["runtime_manifest_hash"] == manifest["manifest_hash"]
    assert pointer["implementation_fingerprint"] == implementation["implementation_fingerprint"]
    assert manifest["schema_version"] == "MODEL_RUNTIME_CODE_MANIFEST_V1R1"
    for entry in manifest["entries"]:
        path = ROOT / entry["relative_path"]
        assert path.is_file()
        assert _sha256(path) == entry["sha256"]


def test_baseline_fingerprint_includes_code_and_all_model_authorities():
    code_manifest = _read(CODE_MANIFEST_PATH)
    provenance = _read(V1_STATUS_PATH)
    seal = _read(SEAL_PATH)
    payload = seal["fingerprint_payload"]

    assert payload["schema_version"] == "MODEL_BASELINE_FINGERPRINT_V1"
    assert payload["runtime_code_manifest_hash"] == code_manifest["manifest_hash"]
    assert seal["runtime_code_manifest"]["file_sha256"] == _sha256(
        CODE_MANIFEST_PATH
    )
    assert content_id(payload) == seal["baseline_fingerprint"]
    assert seal["baseline_fingerprint"] != OLD_FINGERPRINT

    assert payload["pre_contract"]["scientific_config_hash"]
    for key in (
        "checkpoint_hash",
        "checkpoint_file_sha256",
        "calibration_hash",
        "positive_tail_closure_hash",
        "positive_tail_continuation_hash",
        "engineering_config_hash",
        "scientific_config_hash",
    ):
        assert payload["m1"][key]
    for key in (
        "passenger_design_file_sha256",
        "cu_registry_hash",
        "passenger_reference_manifest_hash",
        "passenger_reference_artifact_hashes",
        "reference_artifact_file_sha256s",
        "seven_scale_artifact_hash",
        "scale_artifact_file_sha256s",
    ):
        assert payload["m2"][key]
    for key in (
        "action_registry_hash",
        "response_registry_hash",
        "readiness_artifact_hash",
    ):
        assert payload["m3"][key]
    for key in ("rmb_registry_hash", "risk_policy_hash"):
        assert payload["m4"][key]

    assert provenance["status"] == "HISTORICAL_IMMUTABLE_PROVENANCE"
    assert provenance["manifest_hash"] == code_manifest["manifest_hash"]
    reproducibility = seal["dirty_worktree_reproducibility"]
    assert reproducibility["initial_status"] == "FAIL"
    assert reproducibility["status"] == "PASS"
    assert reproducibility["runtime_code_manifest_hash"] == code_manifest["manifest_hash"]

    checkpoint_path = ROOT / seal["M1"]["checkpoint_path"]
    assert _sha256(checkpoint_path) == payload["m1"]["checkpoint_file_sha256"]
    for relative_path, expected in payload["m2"]["scale_artifact_file_sha256s"].items():
        assert _sha256(ROOT / relative_path) == expected
    for name, expected in payload["m2"]["reference_artifact_file_sha256s"].items():
        reference_path = seal["M2"]["reference_artifacts"][name]["path"]
        assert _sha256(ROOT / reference_path) == expected
