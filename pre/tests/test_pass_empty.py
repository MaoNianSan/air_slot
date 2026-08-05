from __future__ import annotations

import json

from core_v2_bundle_fixture import build_synthetic_bundle
from src.core.validation import validate_existing_bundle


def test_pass_empty_is_fileless_and_independently_valid(tmp_path) -> None:
    bundle = build_synthetic_bundle(tmp_path, include_pass_empty=True)
    observation_manifest = json.loads(
        bundle["observation_manifest_path"].read_text(encoding="utf-8")
    )
    membership_manifest = json.loads(
        bundle["membership_manifest_path"].read_text(encoding="utf-8")
    )
    key = "source=weather/observation_date=2022-05-03"
    for manifest in (observation_manifest, membership_manifest):
        record = manifest["partitions"][key]
        assert record["status"] == "PASS_EMPTY"
        assert record["relative_path"] is None
        assert record["file_hash"] is None
    assert validate_existing_bundle(tmp_path, bundle["cfg"])["status"] == "PASS"
