from datetime import date
from pathlib import Path

import pytest

from exp.m1_v2_development_inference_binding import (
    DEVELOPMENT_MONTHS,
    DEVELOPMENT_START,
    FINAL_TEST_START,
    _config_hash_for_root,
    _development_paths,
    _safety,
)


def test_inference_binding_scope_constants_are_development_only():
    assert DEVELOPMENT_MONTHS == (8, 9)
    assert DEVELOPMENT_START == date(2019, 8, 1)
    assert FINAL_TEST_START == date(2019, 10, 1)


def test_inference_binding_rejects_nonzero_final_test_safety():
    with pytest.raises(RuntimeError, match="FINAL_TEST_ACCESS_NONZERO"):
        _safety({"FINAL_TEST_ACCESS_COUNT": 1, "PAPER_FULL_RUN": False}, "TEST")


def test_inference_binding_rejects_paper_full_safety():
    with pytest.raises(RuntimeError, match="PAPER_FULL_TRUE"):
        _safety({"FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": True}, "TEST")


def test_inference_binding_source_scope_excludes_final_test(tmp_path: Path, monkeypatch):
    root = tmp_path
    for month in (8, 9):
        directory = root / "data2/raw/bts/ontime/2019" / f"month={month:02d}"
        directory.mkdir(parents=True)
        (directory / f"m{month}.csv").write_text("x", encoding="utf-8")
    paths = _development_paths(root)
    assert {item.parent.name for item in paths} == {"month=08", "month=09"}


def test_inference_binding_config_hash_uses_exact_three_file_contract(tmp_path: Path):
    for relative, value in (
        ("configs/scientific/foundation.yaml", "scientific: 1\n"),
        ("configs/reproducibility/smoke.yaml", "reproducibility: 1\n"),
        ("configs/engineering/local.example.yaml", "engineering: 1\n"),
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    assert _config_hash_for_root(tmp_path).startswith("sha256:")
