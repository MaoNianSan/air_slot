from __future__ import annotations

from pathlib import Path
from typing import NoReturn

from .config import RunConfig
from .failures import M2ContractMismatch


def run_precision(
    cfg: RunConfig,
    progress_level: str = "normal",
    pre_output: Path | None = None,
) -> NoReturn:
    del cfg, progress_level, pre_output
    raise M2ContractMismatch(
        "M2_CONTRACT_MISMATCH: precision mode awaits the M1 joint-sample migration"
    )
