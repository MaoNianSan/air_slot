"""Shared registry I/O without domain-specific schema ownership."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

import yaml

from .hashing import file_sha256


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("REGISTRY_ROOT_OBJECT_REQUIRED")
    return payload


def registry_source_identity(path: Path) -> dict[str, str]:
    return {"source_path": str(path), "source_sha256": file_sha256(path)}


def atomic_write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


__all__ = [
    "atomic_write_json",
    "read_json",
    "read_yaml",
    "registry_source_identity",
]
