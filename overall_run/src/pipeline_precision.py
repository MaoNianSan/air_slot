from __future__ import annotations

from pathlib import Path
from typing import NoReturn

from .config import RunConfig
from .failures import M3ContractMismatch


def run_precision(
    cfg: RunConfig,
    progress_level: str = "normal",
    pre_output: Path | None = None,
) -> NoReturn:
    del cfg, progress_level, pre_output
    raise M3ContractMismatch(
        "M3_CONTRACT_MISMATCH: precision mode awaits the M2 V2 to M3 migration"
    )
