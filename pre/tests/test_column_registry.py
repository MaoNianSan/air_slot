from __future__ import annotations

import pandas as pd

from src.core.column_registry import build_column_registry, validate_column_registry
from core_fixtures import core_cfg


def test_column_registry_roles_and_alias_cycles() -> None:
    cfg = core_cfg()
    tables = {"episodes": pd.DataFrame({"chain_episode_id": ["c1"]})}
    registry = build_column_registry(tables, cfg)
    row = next(item for item in registry if item["column"] == "chain_episode_id")
    assert "IDENTITY" in row["roles"]
    assert validate_column_registry(registry, cfg)["status"] == "PASS"
    cfg["core_schema"]["column_aliases"] = {"a": "b", "b": "a"}
    assert validate_column_registry(registry, cfg)["status"] == "FAIL"
