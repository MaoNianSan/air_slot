from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.pipeline_inputs import _load


def _override(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "override.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_part_adv_unknown_override_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="UNKNOWN_CONFIG_FIELD=unknown"):
        _load("fast", _override(tmp_path, {"unknown": 1}))


def test_part_adv_nested_type_mismatch_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="CONFIG_FIELD_TYPE_MISMATCH=m1"):
        _load("fast", _override(tmp_path, {"m1": 7}))


def test_part_adv_valid_override_accepted(tmp_path: Path) -> None:
    cfg = _load("fast", _override(tmp_path, {"predictive_samples_fast": 32}))
    assert cfg["samples"] == 32
