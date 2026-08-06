from __future__ import annotations

from pathlib import Path
from typing import NoReturn

from .config import RunConfig
from .failures import M3ParameterNotFrozen


def run_precision(
    cfg: RunConfig,
    progress_level: str = "normal",
    pre_output: Path | None = None,
) -> NoReturn:
    del cfg, progress_level, pre_output
    raise M3ParameterNotFrozen(
        "M3_PARAMETER_NOT_FROZEN: precision mode is unavailable before M3 parameter freeze"
    )
