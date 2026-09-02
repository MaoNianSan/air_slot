"""Passenger-reference artifact materialization for the independent refactor."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from model.PRE.reference.data2_m2_train_fit import fit_passenger_consequence_references
from model.PRE.references.connection_share_reference import ConnectionShareReference
from model.PRE.references.passenger_load_reference import ExpectedPassengersReference


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def reference_payload(reference: Any) -> dict[str, Any]:
    if isinstance(reference, ExpectedPassengersReference):
        return {
            "schema_version": "PASSENGER_EXPECTED_PAX_REFERENCE_V1",
            "reference_id": reference.reference_id,
            "reference_unit": reference.reference_unit,
            "grain": reference.grain,
            "fallback_hierarchy": list(reference.fallback_hierarchy),
            "fit_partition": reference.fit_partition,
            "source": reference.source,
            "support_state": reference.support_state.value,
            "evidence_class": reference.evidence_class.value,
            "lineage_hash": reference.lineage_hash,
            "excluded_rows": reference.excluded_rows,
            "cells": [
                {
                    **cell.__dict__,
                    "support_state": cell.support_state.value,
                }
                for cell in reference.cells
            ],
        }
    if isinstance(reference, ConnectionShareReference):
        return {
            "schema_version": "PASSENGER_CONNECTION_SHARE_REFERENCE_V1",
            "reference_id": reference.reference_id,
            "connection_share": reference.connection_share,
            "total_passenger_weight": reference.total_passenger_weight,
            "connecting_passenger_weight": reference.connecting_passenger_weight,
            "grain": reference.grain,
            "fallback_hierarchy": list(reference.fallback_hierarchy),
            "fit_partition": reference.fit_partition,
            "source": reference.source,
            "support_state": reference.support_state.value,
            "evidence_class": reference.evidence_class.value,
            "lineage_hash": reference.lineage_hash,
            "excluded_rows": reference.excluded_rows,
            "cells": [
                {
                    **cell.__dict__,
                    "support_state": cell.support_state.value,
                }
                for cell in reference.cells
            ],
        }
    raise TypeError(type(reference).__name__)


def write_passenger_reference_freeze(*, root: Path, artifact_dir: Path, scales: dict[str, dict[str, Any]]) -> dict[str, Path]:
    fitted = fit_passenger_consequence_references(root=root)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for key, filename in (("expected_pax", "T100_EXPECTED_PAX_PER_FLIGHT_REFERENCE.json"), ("connection_share", "DB1B_CONNECTION_SHARE_REFERENCE.json")):
        path = artifact_dir / filename
        payload = reference_payload(fitted[key])
        payload["artifact_hash"] = "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        paths[key] = path
    scale_payload = {"schema_version": "PASSENGER_CONSEQUENCE_TRAIN_SCALES_V1", "fit_partition": "TRAIN", "scale_rule": "POSITIVE_TRAIN_PERIOD_MEDIAN", "components": scales, "final_test_access_count": 0, "paper_full_run": False}
    scale_payload["artifact_hash"] = "sha256:" + hashlib.sha256(json.dumps(scale_payload, sort_keys=True).encode()).hexdigest()
    scale_path = artifact_dir / "PASSENGER_CONSEQUENCE_TRAIN_SCALES.json"
    scale_path.write_text(json.dumps(scale_payload, indent=2, sort_keys=True), encoding="utf-8")
    paths["scales"] = scale_path
    manifest = {
        "schema_version": "PASSENGER_REFERENCE_MANIFEST_V1",
        "fit_partition": "TRAIN",
        "sources": {str(path.relative_to(root)): _sha256_file(path) for path in fitted["source_paths"]},
        "fallback_hierarchy": list(fitted["expected_pax"].fallback_hierarchy),
        "connection_share_fallback_hierarchy": list(fitted["connection_share"].fallback_hierarchy),
        "reference_ids": {key: fitted[key].reference_id for key in ("expected_pax", "connection_share")},
        "artifact_hashes": {key: payload_hash for key, payload_hash in (("expected_pax", json.loads(paths["expected_pax"].read_text())["artifact_hash"]), ("connection_share", json.loads(paths["connection_share"].read_text())["artifact_hash"]), ("scales", scale_payload["artifact_hash"]))},
        "data1_modified": False,
        "data2_modified": False,
        "final_test_access_count": 0,
        "experiment_created": False,
    }
    manifest_path = artifact_dir / "PASSENGER_REFERENCE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    paths["manifest"] = manifest_path
    return paths


__all__ = ["reference_payload", "write_passenger_reference_freeze"]
