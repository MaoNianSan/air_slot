from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.pipeline_config import load_config


def _override(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "override.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_pre_unknown_override_rejected(tmp_path: Path) -> None:
    path = _override(tmp_path, {"unknown_root": True})
    with pytest.raises(ValueError, match="UNKNOWN_CONFIG_FIELD=unknown_root"):
        load_config(path, mode="fast")


def test_pre_nested_unknown_override_rejected(tmp_path: Path) -> None:
    path = _override(
        tmp_path,
        {"predecessor_matching": {"foo": {"bar": 1}}},
    )
    with pytest.raises(
        ValueError,
        match=r"UNKNOWN_CONFIG_FIELD=predecessor_matching\.foo",
    ):
        load_config(path, mode="fast")


def test_pre_valid_override_accepted(tmp_path: Path) -> None:
    path = _override(tmp_path, {"runtime": {"progress_level": "quiet"}})
    cfg = load_config(path, mode="fast")
    assert cfg["runtime"]["progress_level"] == "quiet"
