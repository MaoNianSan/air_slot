"""Validate the active artifact index and output reference graph.

This is a read-only contract check. It verifies that every indexed active
artifact exists with the recorded bytes, that the active implementation
fingerprint agrees with the pointer, and that the materialized reference graph
contains no dangling active artifact-file references.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
INDEX_PATH = ROOT / "registries" / "ACTIVE_MODEL_ARTIFACTS_V1.json"
POINTER_PATH = ROOT / "registries" / "ACTIVE_MODEL_IMPLEMENTATION.json"
GRAPH_PATH = ROOT / "reports" / "output_refactor" / "OUTPUT_REFERENCE_GRAPH_V1.json"
ALLOWED_CATEGORIES = {"ACTIVE_AUTHORITY", "ACTIVE_FIXTURE"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate() -> dict[str, Any]:
    errors: list[str] = []
    index = _load(INDEX_PATH)
    pointer = _load(POINTER_PATH)
    graph = _load(GRAPH_PATH)
    entries = index.get("entries", [])
    paths = [str(entry.get("path", "")).replace("\\", "/") for entry in entries]
    if index.get("schema_version") != "ACTIVE_MODEL_ARTIFACTS_V1":
        errors.append("ACTIVE_INDEX_SCHEMA_MISMATCH")
    if len(paths) != len(set(paths)):
        errors.append("DUPLICATE_ACTIVE_PATH")
    for entry, path_text in zip(entries, paths):
        if entry.get("category") not in ALLOWED_CATEGORIES:
            errors.append(f"INVALID_CATEGORY:{path_text}")
        path = ROOT / path_text
        if not path.is_file():
            errors.append(f"MISSING_ACTIVE_ARTIFACT:{path_text}")
            continue
        if int(entry.get("size_bytes", -1)) != path.stat().st_size:
            errors.append(f"SIZE_MISMATCH:{path_text}")
        if entry.get("sha256") != _sha256(path):
            errors.append(f"HASH_MISMATCH:{path_text}")
    if index.get("implementation_fingerprint") != pointer.get("implementation_fingerprint"):
        errors.append("IMPLEMENTATION_FINGERPRINT_POINTER_MISMATCH")
    index_payload = dict(index)
    recorded_index_hash = index_payload.pop("artifact_index_hash", None)
    if recorded_index_hash != content_id(index_payload):
        errors.append("ACTIVE_INDEX_HASH_MISMATCH")
    if index.get("scientific_baseline") != "MODEL_BASELINE_SEAL_V1":
        errors.append("SCIENTIFIC_BASELINE_POINTER_MISMATCH")
    broken_count = int(graph.get("broken_reference_count", -1))
    if broken_count != len(graph.get("broken_references", [])):
        errors.append("REFERENCE_GRAPH_COUNT_MISMATCH")
    if broken_count != 0:
        errors.append("BROKEN_ARTIFACT_REFERENCES_NONZERO")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "active_entries": len(entries),
        "active_categories": sorted({entry.get("category") for entry in entries}),
        "implementation_fingerprint": index.get("implementation_fingerprint"),
        "artifact_index_hash": index.get("artifact_index_hash"),
        "broken_artifact_references": broken_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    result = validate()
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else f"{result['status']}: {result['errors'] or 'active index and reference graph are consistent'}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
