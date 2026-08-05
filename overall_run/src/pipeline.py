from __future__ import annotations

from pathlib import Path

from .config import RunConfig
from .failures import M2ContractMismatch
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
    raise M2ContractMismatch(
        "M2_CONTRACT_MISMATCH: overall_run awaits the M1 joint-sample input migration"
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
