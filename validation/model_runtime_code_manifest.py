"""Deterministic active runtime code manifest for model baseline seals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from model.common.identity import content_id


RUNTIME_CODE_ROOTS = (
    ("model/common", "COMMON_RUNTIME_DEPENDENCY"),
    ("model/PRE", "PRE_AUTHORITATIVE_RUNTIME"),
    ("model/M1", "M1_RUNTIME"),
    ("model/M2", "M2_RUNTIME"),
    ("model/M3", "M3_RUNTIME"),
    ("model/M4", "M4_RUNTIME"),
)
RUNTIME_CONFIGS = (
    ("configs/scientific/foundation.yaml", "SCIENTIFIC_CONFIG"),
    ("configs/engineering/m1_data2_development_fast.yaml", "M1_ENGINEERING_CONFIG"),
)


def json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def json_sha256(payload: Any) -> str:
    return f"sha256:{hashlib.sha256(json_bytes(payload)).hexdigest()}"


def build_runtime_code_manifest(root: Path) -> dict[str, Any]:
    resolved_root = root.resolve()
    entries = []
    for relative_root, role in RUNTIME_CODE_ROOTS:
        for path in sorted((root / relative_root).rglob("*.py")):
            entries.append(
                {
                    "relative_path": path.resolve().relative_to(resolved_root).as_posix(),
                    "sha256": f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}",
                    "role": role,
                }
            )
    for relative_path, role in RUNTIME_CONFIGS:
        path = root / relative_path
        entries.append(
            {
                "relative_path": path.resolve().relative_to(resolved_root).as_posix(),
                "sha256": f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}",
                "role": role,
            }
        )
    entries.sort(key=lambda item: item["relative_path"])
    hash_basis = {"schema_version": "MODEL_RUNTIME_CODE_MANIFEST_V1", "entries": entries}
    return {
        **hash_basis,
        "entry_count": len(entries),
        "manifest_hash": content_id(hash_basis),
    }
