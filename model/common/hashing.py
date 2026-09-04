"""Canonical deterministic hashing helpers."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from .serialization import canonical_json_bytes


def content_id(value: Any) -> str:
    return f"sha256:{sha256(canonical_json_bytes(value)).hexdigest()}"


def file_sha256(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


__all__ = ["content_id", "file_sha256"]
