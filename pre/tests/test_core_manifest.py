from __future__ import annotations

import pandas as pd

from src.core.pipeline import _manifest
from core_fixtures import core_cfg


def test_core_manifest_contains_frozen_contract_hashes() -> None:
    cfg = core_cfg()
    inventory = pd.DataFrame(
        [{"source": "flightlist", "relative_path": "raw.csv", "sha256": "a" * 64, "size_bytes": 1}]
    )
    manifest = _manifest(
        cfg,
        inventory,
        "b" * 64,
        {"episodes": "c" * 64},
        "d" * 64,
        {"episodes": 1, "observations": 1},
        {"observations": {"state": 1}},
    )
    required = set(cfg["core_schema"]["manifest_required"])
    assert not required - set(manifest)
    assert manifest["contract_id"] == "AIR_CHAIN_CORE_V1"
    assert len(manifest["core_data_hash"]) == 64
