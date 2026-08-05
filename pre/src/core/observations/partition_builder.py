from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd

from ...input import sha256_file
from .partition_manifest import atomic_write_parquet, parquet_metadata
from .retention import retain_source_global_rows


def build_partition(
    path: Path,
    requests: pd.DataFrame,
    builder: Callable[[pd.DataFrame], pd.DataFrame],
) -> tuple[pd.DataFrame, list[str], int, str, str]:
    frame = builder(requests)
    if frame.empty:
        return frame, [], 0, "", ""
    frame = retain_source_global_rows(frame)
    atomic_write_parquet(frame, path)
    columns, _, rows, fingerprint = parquet_metadata(path)
    return frame, columns, rows, fingerprint, sha256_file(path)
