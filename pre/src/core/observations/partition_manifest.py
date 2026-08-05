from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ...input import object_hash
from ..contracts import OBSERVATION_CONTRACT_ID


PARTITION_COMPLETE_STATUSES = {"PASS", "PASS_EMPTY"}
EMPTY_REASONS = {
    "NO_SOURCE_RECORDS",
    "NO_ADMISSIBLE_SOURCE_RECORDS",
    "NO_MATCHING_IDENTITY",
    "NO_REQUEST_OVERLAP",
}
VALIDATION_COLUMNS = [
    "observation_id",
    "source",
    "observation_date",
    "observation_time",
    "event_time",
    "availability_time",
    "source_record_id",
    "source_file",
    "source_hash",
    "airport_id",
    "aircraft_id",
    "flight_id",
]


@dataclass(frozen=True)
class ObservationDatasetResult:
    row_counts: dict[str, int]
    partition_counts: dict[str, int]
    pass_empty_counts: dict[str, int]
    content_hash: str
    validation: dict[str, object]
    evidence_rows: list[dict[str, object]]
    partition_manifest: dict[str, object]
    source_columns: dict[str, list[str]]


def schema_fingerprint(columns: list[str], dtypes: list[str]) -> str:
    return object_hash(list(zip(columns, dtypes)))


def expected_empty_schema_fingerprint(source: str) -> str:
    return object_hash(
        {
            "contract": OBSERVATION_CONTRACT_ID,
            "source": source,
            "required_columns": VALIDATION_COLUMNS,
        }
    )


def parquet_metadata(path: Path) -> tuple[list[str], list[str], int, str]:
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    columns = list(schema.names)
    dtypes = [str(schema.field(name).type) for name in columns]
    return columns, dtypes, int(parquet.metadata.num_rows), schema_fingerprint(columns, dtypes)


def atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)
