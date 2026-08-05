from __future__ import annotations

from src.core.contracts import implementation_hash


def test_empty_implementation_scope_is_warning(tmp_path) -> None:
    result = implementation_hash(tmp_path)
    assert result == {
        "status": "WARNING",
        "reason": "IMPLEMENTATION_HASH_SCOPE_EMPTY",
        "hash": None,
        "file_count": 0,
    }
