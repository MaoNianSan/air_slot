from __future__ import annotations

from src.core.contracts import implementation_hash


def test_implementation_hash_covers_non_core_dependency(tmp_path) -> None:
    (tmp_path / "pre/src/core").mkdir(parents=True)
    (tmp_path / "pre/config/schema").mkdir(parents=True)
    (tmp_path / "pre/src/core/a.py").write_text("CORE = 1\n", encoding="utf-8")
    dependency = tmp_path / "pre/src/input.py"
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    first = implementation_hash(tmp_path)
    dependency.write_text("VALUE = 2\n", encoding="utf-8")
    assert implementation_hash(tmp_path) != first

