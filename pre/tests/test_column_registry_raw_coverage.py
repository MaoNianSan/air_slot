from __future__ import annotations

import pandas as pd

from core_fixtures import core_cfg
from src.core.column_registry import build_column_registry, validate_column_registry


def test_registry_covers_actual_raw_source_columns() -> None:
    cfg = core_cfg()
    registry = build_column_registry(
        {"episodes": pd.DataFrame({"chain_episode_id": ["c1"]})},
        cfg,
        source_columns={"state": ["observation_id", "geoaltitude", "callsign"]},
    )
    geo = next(
        row for row in registry
        if row["source"] == "state_vectors" and row["raw_column"] == "geoaltitude"
    )
    assert geo["retention_status"] == "RETAINED"
    assert validate_column_registry(registry, cfg)["status"] == "PASS"

