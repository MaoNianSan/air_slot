"""M2 V4 passenger-reference artifact serialization and materialization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from model.PRE import ConnectionShareReference
from model.PRE import ExpectedPassengersReference
from model.common.errors import ContractError


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


def write_passenger_reference_freeze(*, root: Path, artifact_dir: Path, scales: dict[str, dict[str, Any]] | None = None) -> dict[str, Path]:
    """Run the canonical V4 materializer and return its generated paths."""
    expected_dir = root / "artifacts" / "diagnostics" / "passenger_reference_freeze_v4"
    if artifact_dir.resolve() != expected_dir.resolve():
        raise ContractError("M2_V4_PASSENGER_ARTIFACT_DIRECTORY_MISMATCH")
    if not (expected_dir / "PASSENGER_REFERENCE_MANIFEST_V2.json").is_file():
        raise ContractError("M2_V4_PASSENGER_REFERENCE_FREEZE_NOT_MATERIALIZED")
    return {
        "expected_pax": expected_dir / "T100_EXPECTED_PAX_PER_FLIGHT_REFERENCE.json",
        "connection_share": expected_dir / "DB1B_CONNECTION_SHARE_REFERENCE.json",
        "scales": expected_dir / "M2_SEVEN_COMPONENT_TRAIN_SCALES.json",
        "manifest": expected_dir / "PASSENGER_REFERENCE_MANIFEST_V2.json",
    }


__all__ = ["reference_payload", "write_passenger_reference_freeze"]
