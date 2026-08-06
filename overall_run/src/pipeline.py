from __future__ import annotations

from pathlib import Path

from .config import RunConfig
from .failures import M3ContractMismatch
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
        cfg,
        mode,
        progress_level,
        pre_output,
        refit,
        override_fast_gate,
        output_name,
        resume_staging,
    )
    raise M3ContractMismatch(
        "M3_CONTRACT_MISMATCH: M1-to-M2 V2 is available but M3 has not migrated to M2 sample losses"
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
