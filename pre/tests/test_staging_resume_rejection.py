from __future__ import annotations

from dataclasses import replace

from src.core.resume_contract import select_compatible_staging, write_resume_manifest
from test_staging_resume_contract import _contract


def test_missing_and_mismatched_staging_are_rejected(tmp_path) -> None:
    output = tmp_path / "AIR_CHAIN_CORE_V2"
    missing = tmp_path / ".AIR_CHAIN_CORE_V2.staging-missing"
    missing.mkdir()
    mismatch = tmp_path / ".AIR_CHAIN_CORE_V2.staging-mismatch"
    mismatch.mkdir()
    write_resume_manifest(mismatch, replace(_contract(), frozen_config_hash="9" * 64))
    selected, audit = select_compatible_staging(output, _contract())
    assert selected is None
    reasons = {item["reason"] for item in audit["rejected"]}
    assert reasons == {"MISSING_RESUME_MANIFEST", "RESUME_CONTRACT_MISMATCH"}
