"""Gate-B release validation and explicit executor boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import constants as C
from .access_audit import (
    mark_access_read_completed,
    mark_access_read_started,
    open_access_epoch,
)
from .errors import TypedBlocker
from .materialization import _read_json
from .release import validate_release_schema


def execute_gate_b(
    *,
    release_path: Path,
    audit_path: Path | None = None,
    pipeline: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate a human release and run an explicitly supplied executor.

    Gate A deliberately leaves ``pipeline`` unbound. This prevents an
    accidental Gate-B run from opening the access epoch without a human
    release and a separately reviewed scientific executor.
    """

    release = _read_json(Path(release_path))
    validated = validate_release_schema(release)
    target_audit = (
        Path(audit_path) if audit_path is not None else C.PHASE7_ACCESS_AUDIT_PATH
    )
    if pipeline is None:
        raise TypedBlocker(
            "GATE_B_SCIENTIFIC_EXECUTOR_NOT_BOUND",
            "human release validated, but no sealed Phase-7 executor was supplied",
        )
    epoch = open_access_epoch(target_audit, release)
    mark_access_read_started(target_audit)
    result = pipeline(
        {
            "release": release,
            "release_validation": validated,
            "access_epoch": epoch,
        }
    )
    mark_access_read_completed(target_audit)
    return {
        "status": "PASS",
        "release_validation": validated,
        "access_epoch": epoch,
        "result": result,
    }


__all__ = ["execute_gate_b"]
