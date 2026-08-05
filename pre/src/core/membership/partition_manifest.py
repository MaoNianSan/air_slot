from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ...input import object_hash
from ..contracts import CONTRACT_ID, RESEARCH_CODE_REVISION
from ..observations import schema_fingerprint
from .interval_join import MEMBERSHIP_COLUMNS


MEMBERSHIP_PARTITION_MANIFEST_NAME = "observation_membership_partition_manifest.json"
PARTITION_COMPLETE_STATUSES = {"PASS", "PASS_EMPTY"}


@dataclass(frozen=True)
class MembershipDatasetResult:
    row_count: int
    partition_count: int
    pass_empty_count: int
    dataset_hash: str
    partition_manifest_hash: str
    validation: dict[str, Any]
    partition_manifest: dict[str, Any]


def expected_empty_schema_fingerprint(source: str) -> str:
    return object_hash(
        {
            "contract": CONTRACT_ID,
            "research_code_revision": RESEARCH_CODE_REVISION,
            "dataset": "observation_membership",
            "source": source,
            "required_columns": MEMBERSHIP_COLUMNS,
        }
    )


def atomic_write_json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)


def parquet_metadata(path: Path) -> tuple[list[str], list[str], int, str]:
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    columns = list(schema.names)
    dtypes = [str(schema.field(name).type) for name in columns]
    return columns, dtypes, int(parquet.metadata.num_rows), schema_fingerprint(columns, dtypes)
