from __future__ import annotations

import hashlib

import pytest

from pre_contract_gate import DownstreamContractMismatch, require_m1_ready


def _manifest(pre_hash: str, m2_status: str = "PASS") -> dict:
    return {
        "pre_bundle_identity": {
            "contract_id": "AIR_CHAIN_CORE_V2",
            "schema_version": "air-chain-core-2.0",
            "research_code_revision": "AIR_CHAIN_CORE_V2_R2",
            "pre_manifest_hash": pre_hash,
        },
        "m1_contract_id": "M1_CHAIN_DYNAMIC_DISTRIBUTION_V1",
        "model_version": "model-1",
        "engineering_status": "PASS",
        "target_support_status": {
            "R_IB": "OFFICIAL_OPERATIONAL",
            "R_OB": "OFFICIAL_OPERATIONAL",
            "T_TX": "OFFICIAL_OPERATIONAL",
        },
        "training_status": "PASS",
        "calibration_status": "PASS",
        "evaluation_status": "PASS",
        "m2_interface_status": m2_status,
    }


def test_readiness_gate_binds_pre_hash(published_root) -> None:
    path = published_root / "pre_manifest.json"
    pre_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    result = require_m1_ready(path, _manifest(pre_hash), "m2")
    assert result["M1_ENGINEERING_STATUS"] == "PASS"


def test_readiness_gate_reports_m2_contract_mismatch(published_root) -> None:
    path = published_root / "pre_manifest.json"
    pre_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(DownstreamContractMismatch, match="M2_CONTRACT_MISMATCH"):
        require_m1_ready(path, _manifest(pre_hash, "M2_CONTRACT_MISMATCH"), "m2")
