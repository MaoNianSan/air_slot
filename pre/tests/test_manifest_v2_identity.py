from __future__ import annotations

import json

from core_v2_bundle_fixture import build_synthetic_bundle
from src.core.contracts import CONTRACT_ID, RESEARCH_CODE_REVISION, SCHEMA_VERSION


def test_manifest_uses_current_v2_identity(tmp_path) -> None:
    build_synthetic_bundle(tmp_path)
    manifest = json.loads((tmp_path / "pre_manifest.json").read_text(encoding="utf-8"))
    assert manifest["contract_id"] == CONTRACT_ID
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["research_code_revision"] == RESEARCH_CODE_REVISION
    assert manifest["membership_partition_count"] == 1
    assert manifest["file_hashes"]
