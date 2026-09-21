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

    paths = (
        C.epoch_paths_for(Path(output_root))
        if output_root is not None
        else C.stage_matched_epoch_paths()
    )
    preflight_path = paths.gate_a_preflight_path
    dry_run_path = paths.gate_a_dry_run_path
    try:
        payload = build_gate_a_preflight(epoch_paths=paths)
        _write_json_atomic(dry_run_path, payload["dry_run"])
        _write_json_atomic(preflight_path, payload)
        return payload
    except TypedBlocker as error:
        payload = _blocked_payload(
            error.code,
            error.detail,
            epoch_paths=paths,
        )
        _write_json_atomic(preflight_path, payload)
        return payload


__all__ = ["run_gate_a"]
