"""Gate-A orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import constants as C
from .errors import TypedBlocker
from .materialization import _write_json_atomic
from .reporting import _blocked_payload, build_gate_a_preflight


def run_gate_a(
    *,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Run Gate A and atomically write its preflight and dry-run artifacts."""

    root = Path(output_root) if output_root is not None else C.FINAL_TEST_V2_ROOT
    preflight_path = root / C.GATE_A_PREFLIGHT_PATH.name
    dry_run_path = root / C.GATE_A_DRY_RUN_PATH.name
    try:
        payload = build_gate_a_preflight()
        _write_json_atomic(dry_run_path, payload["dry_run"])
        _write_json_atomic(preflight_path, payload)
        return payload
    except TypedBlocker as error:
        payload = _blocked_payload(error.code, error.detail)
        _write_json_atomic(preflight_path, payload)
        return payload


__all__ = ["run_gate_a"]
