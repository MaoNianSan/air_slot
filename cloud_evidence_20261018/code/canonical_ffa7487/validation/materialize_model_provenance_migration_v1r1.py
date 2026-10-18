"""Materialize the V1 historical-manifest supersession metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
V1_MANIFEST = ROOT / "registries" / "MODEL_RUNTIME_CODE_MANIFEST_V1.json"
V1R1_IMPLEMENTATION = ROOT / "registries" / "MODEL_BASELINE_IMPLEMENTATION_V1R1.json"
V1R1_MANIFEST = ROOT / "registries" / "MODEL_RUNTIME_CODE_MANIFEST_V1R1.json"
SNAPSHOT_MANIFEST = (
    ROOT
    / "artifacts"
    / "provenance"
    / "model_baseline_v1_source"
    / "MODEL_RUNTIME_SOURCE_SNAPSHOT_V1_MANIFEST.json"
)
STATUS_PATH = ROOT / "registries" / "MODEL_RUNTIME_CODE_MANIFEST_V1_PROVENANCE.json"
SUPERSESSION_PATH = ROOT / "registries" / "MODEL_IMPLEMENTATION_SUPERSESSION_V1_TO_V1R1.json"
ACTIVE_POINTER_PATH = ROOT / "registries" / "ACTIVE_MODEL_IMPLEMENTATION.json"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def materialize() -> dict[str, Any]:
    v1 = _read(V1_MANIFEST)
    v1r1 = _read(V1R1_IMPLEMENTATION)
    manifest = _read(V1R1_MANIFEST)
    snapshot = _read(SNAPSHOT_MANIFEST)
    scientific_parent = v1r1["scientific_parent_fingerprint"]

    status_payload = {
        "schema_version": "MODEL_RUNTIME_CODE_MANIFEST_V1_PROVENANCE_V1",
        "manifest": "MODEL_RUNTIME_CODE_MANIFEST_V1",
        "manifest_hash": v1["manifest_hash"],
        "status": "HISTORICAL_IMMUTABLE_PROVENANCE",
        "live_filesystem_validation": "NOT_APPLICABLE_AFTER_V1R1",
        "scientific_parent_fingerprint": scientific_parent,
        "source_snapshot_manifest": str(SNAPSHOT_MANIFEST.relative_to(ROOT)),
        "source_snapshot_manifest_hash": snapshot["snapshot_manifest_hash"],
        "entry_count": v1["entry_count"],
    }
    status = {**status_payload, "artifact_hash": content_id(status_payload)}

    supersession_payload = {
        "schema_version": "MODEL_IMPLEMENTATION_SUPERSESSION_V1_TO_V1R1",
        "scientific_baseline": "MODEL_BASELINE_SEAL_V1",
        "scientific_fingerprint": scientific_parent,
        "predecessor_implementation": "MODEL_RUNTIME_CODE_MANIFEST_V1",
        "successor_implementation": "MODEL_BASELINE_IMPLEMENTATION_V1R1",
        "predecessor_runtime_status": "HISTORICAL_SUPERSEDED",
        "successor_runtime_status": "ACTIVE",
        "scientific_semantics_changed": False,
        "behavioral_equivalence": v1r1["behavioral_equivalence"],
        "predecessor_manifest_hash": v1["manifest_hash"],
        "predecessor_source_snapshot_manifest_hash": snapshot["snapshot_manifest_hash"],
        "successor_runtime_manifest_hash": v1r1["new_runtime_manifest_hash"],
        "successor_implementation_fingerprint": v1r1["implementation_fingerprint"],
    }
    supersession = {**supersession_payload, "record_hash": content_id(supersession_payload)}

    pointer_payload = {
        "schema_version": "ACTIVE_MODEL_IMPLEMENTATION_V1",
        "active_implementation": "MODEL_BASELINE_IMPLEMENTATION_V1R1",
        "implementation_registry_path": str(V1R1_IMPLEMENTATION.relative_to(ROOT)),
        "runtime_manifest_path": str(V1R1_MANIFEST.relative_to(ROOT)),
        "runtime_manifest_hash": manifest["manifest_hash"],
        "implementation_fingerprint": v1r1["implementation_fingerprint"],
        "scientific_baseline": "MODEL_BASELINE_SEAL_V1",
        "scientific_parent_fingerprint": scientific_parent,
        "status": "ACTIVE",
    }
    pointer = {**pointer_payload, "pointer_hash": content_id(pointer_payload)}

    for path, payload in (
        (STATUS_PATH, status),
        (SUPERSESSION_PATH, supersession),
        (ACTIVE_POINTER_PATH, pointer),
    ):
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "historical_manifest_status": str(STATUS_PATH.relative_to(ROOT)),
        "supersession_record": str(SUPERSESSION_PATH.relative_to(ROOT)),
        "active_pointer": str(ACTIVE_POINTER_PATH.relative_to(ROOT)),
        "snapshot_manifest_hash": snapshot["snapshot_manifest_hash"],
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    print(json.dumps(materialize(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
