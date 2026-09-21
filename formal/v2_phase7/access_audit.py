"""Atomic Phase-7 access-audit ledger transitions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from . import constants as C
from .checkpoint_resume import _access_epoch_id, _release_fingerprint
from .errors import _require
from .materialization import (
    _assert_not_legacy_final_test,
    _read_json,
    _write_json_atomic,
)
from .release import validate_release_schema


def open_access_epoch(
    audit_path: Path,
    release: Mapping[str, Any],
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Open the one Phase-7 access epoch or return the existing same epoch."""

    validate_release_schema(release)
    target = Path(audit_path)
    _assert_not_legacy_final_test(target)
    release_hash = _release_fingerprint(release)
    if target.exists():
        payload = _read_json(target)
        _require(
            payload.get("access_epoch_id") == _access_epoch_id(release),
            "PHASE7_ACCESS_EPOCH_ID_MISMATCH",
            payload.get("access_epoch_id"),
        )
        _require(
            payload.get("release_binding_sha256") == release_hash,
            "PHASE7_ACCESS_RELEASE_BINDING_MISMATCH",
        )
        _require(
            payload.get("phase7_increment") == C.PHASE7_ACCESS_INCREMENT
            and payload.get("current_total") == C.PHASE7_CURRENT_TOTAL,
            "PHASE7_ACCESS_INCREMENT_INVALID",
            payload,
        )
        updated = dict(payload)
        updated["retry_within_same_epoch"] = True
        updated["retry_count"] = int(payload.get("retry_count", 0)) + 1
        _write_json_atomic(target, updated)
        return updated

    opened = timestamp or datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "AIR_SLOT_V2_PHASE7_ACCESS_AUDIT_V1",
        "status": "PHASE7_ACCESS_EPOCH_OPEN",
        "access_epoch_id": _access_epoch_id(release),
        "access_epoch_opened": opened,
        "raw_read_started": False,
        "raw_read_completed": False,
        "retry_within_same_epoch": False,
        "retry_count": 0,
        "historical_access_total": C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
        "phase7_increment": C.PHASE7_ACCESS_INCREMENT,
        "current_total": C.PHASE7_CURRENT_TOTAL,
        "new_final_test_execution": True,
        "release_binding_sha256": release_hash,
        "release": dict(release),
        "same_epoch_retry_policy": "BINDING_AND_IO_FIXES_ONLY",
        "scientific_definition_change_closes_epoch": True,
        "cohort_change_closes_epoch": True,
        "parameter_selection_change_closes_epoch": True,
        "reporting_choice_change_closes_epoch": True,
    }
    _write_json_atomic(target, payload)
    return payload


def mark_access_read_started(
    audit_path: Path,
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    payload = _read_json(Path(audit_path))
    _require(
        payload.get("status") == "PHASE7_ACCESS_EPOCH_OPEN",
        "PHASE7_ACCESS_EPOCH_NOT_OPEN",
    )
    payload["raw_read_started"] = True
    payload["raw_read_started_at"] = timestamp or datetime.now(timezone.utc).isoformat()
    _write_json_atomic(Path(audit_path), payload)
    return payload


def mark_access_read_completed(
    audit_path: Path,
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    payload = _read_json(Path(audit_path))
    _require(
        payload.get("raw_read_started") is True,
        "PHASE7_RAW_READ_NOT_STARTED",
    )
    payload["raw_read_completed"] = True
    payload["raw_read_completed_at"] = (
        timestamp or datetime.now(timezone.utc).isoformat()
    )
    payload["status"] = "PHASE7_ACCESS_EPOCH_COMPLETE"
    _write_json_atomic(Path(audit_path), payload)
    return payload


__all__ = [
    "mark_access_read_completed",
    "mark_access_read_started",
    "open_access_epoch",
]
