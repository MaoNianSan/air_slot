from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def source_tree_hash(root: Path) -> str:
    """Hash the executable Python implementation used by a run.

    Git metadata is not always available in the user's project directory, so
    artifact reuse cannot rely on a commit hash alone.
    """
    candidates = [root / "main.py"]
    candidates.extend(sorted((root / "src").rglob("*.py")))
    h = hashlib.sha256()
    for path in candidates:
        if not path.exists():
            continue
        h.update(path.relative_to(root).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def stable_hash(*parts: Any) -> str:
    payload = "\x1f".join(str(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_seed(*parts: Any) -> int:
    return int(stable_hash(*parts)[:16], 16) % (2**32 - 1)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_commit(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def run_id(mode: str, config_hash: str, root: Path) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{mode}_{config_hash[:8]}_{git_commit(root)[:7]}"


def environment_manifest() -> dict[str, Any]:
    versions: dict[str, str] = {"numpy": np.__version__}
    for module_name in ("pandas", "pyarrow", "sklearn", "lightgbm", "scipy", "joblib", "matplotlib", "yaml"):
        try:
            module = __import__(module_name)
            versions[module_name] = str(getattr(module, "__version__", "unknown"))
        except Exception:
            versions[module_name] = "unavailable"
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "packages": versions,
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def first_existing(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    s = set(columns)
    return next((c for c in candidates if c in s), None)
