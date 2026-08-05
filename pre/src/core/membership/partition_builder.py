from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ...input import sha256_file
from .interval_join import IDENTITY_COLUMNS, interval_join_partition
from .partition_manifest import (
    atomic_write_parquet,
    expected_empty_schema_fingerprint,
    parquet_metadata,
)
from .partition_plan import empty_reason
from .validation import validate_observation_membership


def build_partition(
    observation_path: str,
    membership_path: str,
    source: str,
    observation_date: str,
    requests: pd.DataFrame,
) -> dict[str, Any]:
    observation_identity, _ = IDENTITY_COLUMNS[source]
    import pyarrow.parquet as pq

    available = set(
        pq.ParquetFile(Path(observation_path)).schema_arrow.names
    )
    selected = [
        column
        for column in (
            "observation_id",
            "source",
            "observation_date",
            "event_time",
            "availability_time",
            observation_identity,
            "flight_id",
        )
        if column in available
    ]
    observations = pd.read_parquet(Path(observation_path), columns=selected)
    membership = interval_join_partition(
        observations,
        requests,
        source=source,
        observation_date=observation_date,
    )
    path = Path(membership_path)
    if membership.empty:
        if any(path.parent.glob("*.parquet")):
            raise ValueError("MEMBERSHIP_PASS_EMPTY_FILE_CONFLICT")
        return {
            "status": "PASS_EMPTY",
            "row_count": 0,
            "relative_path": None,
            "file_hash": None,
            "schema_fingerprint": expected_empty_schema_fingerprint(source),
            "empty_reason": empty_reason(observations, requests, source),
        }
    validation = validate_observation_membership(membership)
    if validation["status"] != "PASS":
        raise ValueError(
            "MEMBERSHIP_PARTITION_VALIDATION_FAILED=" + json.dumps(validation)
        )
    atomic_write_parquet(membership, path)
    _, _, rows, fingerprint = parquet_metadata(path)
    if rows != len(membership):
        raise ValueError("MEMBERSHIP_PARTITION_WRITE_ROW_COUNT_MISMATCH")
    return {
        "status": "PASS",
        "row_count": rows,
        "relative_path": f"source={source}/observation_date={observation_date}/{path.name}",
        "file_hash": sha256_file(path),
        "schema_fingerprint": fingerprint,
    }
