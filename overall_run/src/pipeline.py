from __future__ import annotations

from pathlib import Path

from .config import RunConfig
from .failures import M3FormalLibraryNotReady, M3ParameterNotFrozen, M4ContractMismatch
from .pipeline_checkpoint import (
    FullBlockedByFastAcceptance,
    mark_running_staging_incomplete,
    prepare_empty_publish_target,
)
from .pipeline_modes import report_mode, validate_mode
from .pipeline_precision import run_precision


def run_experiment(
    cfg: RunConfig,
    mode: str,
    progress_level: str = "normal",
    pre_output: Path | None = None,
    refit: bool = True,
    *,
    override_fast_gate: bool = False,
    output_name: str | None = None,
    resume_staging: Path | None = None,
) -> Path:
    del (
        mode,
        progress_level,
        pre_output,
        refit,
        override_fast_gate,
        output_name,
        resume_staging,
    )
    m3_status = str(cfg.scientific["m3"].get("status", {}).get("parameter_freeze", ""))
    if m3_status != "DONE":
        raise M3ParameterNotFrozen(
            "M3_PARAMETER_NOT_FROZEN: atomic-subitem response parameters require development freeze"
        )
    library_status = str(cfg.scientific["m3"].get("status", {}).get("formal_library", ""))
    if library_status != "READY":
        raise M3FormalLibraryNotReady(
            "M3_FORMAL_LIBRARY_NOT_READY: the formal response library has not been generated"
        )
    raise M4ContractMismatch(
        "M4_CONTRACT_MISMATCH: M3 V4 atomic-subitem artifact is not yet supported"
    )


__all__ = [
    "FullBlockedByFastAcceptance",
    "mark_running_staging_incomplete",
    "prepare_empty_publish_target",
    "report_mode",
    "run_experiment",
    "run_precision",
    "validate_mode",
]
