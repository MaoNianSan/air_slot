"""Materialize an immutable, non-importable snapshot of the sealed V1 runtime.

The snapshot is sourced only from MODEL_RUNTIME_CODE_MANIFEST_V1.  It is a
provenance archive, not an importable Python package and never participates in
the active V1R1 runtime manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
SOURCE_MANIFEST = ROOT / "registries" / "MODEL_RUNTIME_CODE_MANIFEST_V1.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "provenance" / "model_baseline_v1_source"


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _read_manifest() -> dict[str, Any]:
    payload = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "MODEL_RUNTIME_CODE_MANIFEST_V1":
        raise RuntimeError("V1_SOURCE_MANIFEST_SCHEMA_INVALID")
    entries = payload.get("entries") or []
    if payload.get("entry_count") != len(entries):
        raise RuntimeError("V1_SOURCE_MANIFEST_ENTRY_COUNT_INVALID")
    return payload


def materialize(output: Path = DEFAULT_OUTPUT, *, overwrite: bool = False) -> dict[str, Any]:
    source = _read_manifest()
    if output.exists() and any(output.iterdir()) and not overwrite:
        raise FileExistsError("V1_SOURCE_SNAPSHOT_EXISTS")
    output.mkdir(parents=True, exist_ok=True)

    rows = []
    for entry in source["entries"]:
        relative = Path(entry["relative_path"])
        source_path = ROOT / relative
        if not source_path.is_file():
            raise RuntimeError(f"V1_SOURCE_FILE_MISSING:{entry['relative_path']}")
        actual_hash = _sha256(source_path)
        if actual_hash != entry["sha256"]:
            raise RuntimeError(
                f"V1_SOURCE_FILE_HASH_MISMATCH:{entry['relative_path']}:{actual_hash}:{entry['sha256']}"
            )
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
        rows.append(
            {
                "relative_path": relative.as_posix(),
                "sha256": actual_hash,
                "size": source_path.stat().st_size,
                "role": entry["role"],
            }
        )

    payload = {
        "schema_version": "MODEL_RUNTIME_SOURCE_SNAPSHOT_V1",
        "source_manifest_schema_version": source["schema_version"],
        "source_manifest_hash": source["manifest_hash"],
        "source_manifest_file_sha256": _sha256(SOURCE_MANIFEST),
        "status": "HISTORICAL_IMMUTABLE_PROVENANCE",
        "importable": False,
        "entries": sorted(rows, key=lambda item: item["relative_path"]),
        "entry_count": len(rows),
        "final_test_access_count": 0,
    }
    result = {**payload, "snapshot_manifest_hash": content_id(payload)}
    manifest_path = output / "MODEL_RUNTIME_SOURCE_SNAPSHOT_V1_MANIFEST.json"
    manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    matched = all(
        _sha256(output / item["relative_path"]) == item["sha256"]
        for item in rows
    )
    if not matched:
        raise RuntimeError("V1_SOURCE_SNAPSHOT_HASH_VALIDATION_FAILED")
    return {
        "snapshot_root": str(output.relative_to(ROOT)),
        "manifest": str(manifest_path.relative_to(ROOT)),
        "entry_count": len(rows),
        "all_hashes_matched": matched,
        "snapshot_manifest_hash": result["snapshot_manifest_hash"],
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    print(json.dumps(materialize(args.output, overwrite=args.overwrite), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
