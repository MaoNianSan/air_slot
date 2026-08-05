from __future__ import annotations

import json
import shutil

import pytest

from overall_run.src.m1.adapter import PreBundleValidationError, load_published_bundle


def test_published_bundle_identity_and_partition_hashes(published_root) -> None:
    bundle = load_published_bundle(published_root)
    assert bundle.identity.contract_id == "AIR_CHAIN_CORE_V2"
    assert bundle.identity.research_code_revision == "AIR_CHAIN_CORE_V2_R2"
    partition = next((published_root / "observations").rglob("*.parquet"))
    partition.write_bytes(partition.read_bytes() + b"corrupt")
    with pytest.raises(PreBundleValidationError, match="PRE_MANIFEST_HASH_MISMATCH"):
        load_published_bundle(published_root)


def test_partition_manifest_hash_is_bound_by_pre_manifest(published_root) -> None:
    path = published_root / "observations" / "observation_partition_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PreBundleValidationError, match="PRE_MANIFEST_HASH_MISMATCH"):
        load_published_bundle(published_root)


@pytest.mark.parametrize("forbidden", ["raw", "cache", "staging"])
def test_unpublished_roots_are_rejected(published_root, tmp_path, forbidden) -> None:
    target = tmp_path / forbidden / "output_core" / "fast" / "AIR_CHAIN_CORE_V2"
    shutil.copytree(published_root, target)
    with pytest.raises(PreBundleValidationError, match="PRE_UNPUBLISHED_BUNDLE"):
        load_published_bundle(target)
