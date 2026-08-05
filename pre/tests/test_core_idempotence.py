from __future__ import annotations

import json

from src.core.writer import begin_staging, publish_staging


def test_identical_publication_is_idempotent(tmp_path) -> None:
    output = tmp_path / "AIR_CHAIN_CORE_V1"
    first = begin_staging(output)
    (first / "pre_manifest.json").write_text(json.dumps({"core_data_hash": "a" * 64}), encoding="utf-8")
    assert publish_staging(first, output, "a" * 64) == "PUBLISHED_NEW"
    second = begin_staging(output)
    (second / "pre_manifest.json").write_text(json.dumps({"core_data_hash": "a" * 64}), encoding="utf-8")
    assert publish_staging(second, output, "a" * 64) == "REUSED_IDENTICAL_EXISTING"
    assert not second.exists()
