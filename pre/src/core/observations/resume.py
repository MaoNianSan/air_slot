from __future__ import annotations

from pathlib import Path

import pandas as pd

from ...input import sha256_file
from .partition_manifest import (
    EMPTY_REASONS,
    VALIDATION_COLUMNS,
    expected_empty_schema_fingerprint,
    parquet_metadata,
)


def _read_validation_projection(
    path: Path,
) -> tuple[pd.DataFrame, list[str], str, int]:
    columns, _, rows, fingerprint = parquet_metadata(path)
    missing = sorted(set(VALIDATION_COLUMNS) - set(columns))
    if missing:
        raise ValueError(
            "CORE_OBSERVATION_PARTITION_COLUMNS_MISSING:" + ",".join(missing)
        )
    return (
        pd.read_parquet(path, columns=VALIDATION_COLUMNS),
        columns,
        fingerprint,
        rows,
    )


def validate_resumable_partition(
    path: Path,
    partition_key: str,
    expected_partitions: set[str],
    partition_manifest: dict[str, object],
) -> tuple[bool, str, pd.DataFrame | None, list[str], str, int]:
    if partition_key not in expected_partitions:
        return False, "PARTITION_NOT_EXPECTED", None, [], "", 0
    record = partition_manifest.get("partitions", {}).get(partition_key)
    if not isinstance(record, dict):
        return False, "PARTITION_MANIFEST_MISSING", None, [], "", 0
    status = str(record.get("status", ""))
    source = partition_key.split("/", 1)[0].split("=", 1)[1]
    date_text = partition_key.rsplit("=", 1)[1]
    if status == "PASS_EMPTY":
        if record.get("relative_path") or any(path.parent.glob("*.parquet")):
            return False, "PASS_EMPTY_FILE_CONFLICT", None, [], "", 0
        if record.get("empty_reason") not in EMPTY_REASONS:
            return False, "PASS_EMPTY_REASON_INVALID", None, [], "", 0
        fingerprint = expected_empty_schema_fingerprint(source)
        if record.get("schema_fingerprint") != fingerprint:
            return False, "PASS_EMPTY_SCHEMA_FINGERPRINT_MISMATCH", None, [], "", 0
        if int(record.get("row_count", -1)) != 0 or record.get("file_hash"):
            return False, "PASS_EMPTY_RECORD_INVALID", None, [], "", 0
        return (
            True,
            "PASS_EMPTY",
            pd.DataFrame(columns=VALIDATION_COLUMNS),
            VALIDATION_COLUMNS,
            fingerprint,
            0,
        )
    if status != "PASS":
        return False, f"PARTITION_STATUS_{status or 'MISSING'}", None, [], "", 0
    if not path.exists():
        return False, "PARTITION_FILE_MISSING", None, [], "", 0
    if record.get("relative_path") != f"{partition_key}/{path.name}":
        return False, "PARTITION_RELATIVE_PATH_MISMATCH", None, [], "", 0
    try:
        frame, columns, fingerprint, rows = _read_validation_projection(path)
    except Exception as exc:
        return False, f"PARTITION_UNREADABLE:{type(exc).__name__}", None, [], "", 0
    if sha256_file(path) != record.get("file_hash"):
        return False, "PARTITION_FILE_HASH_MISMATCH", None, columns, fingerprint, rows
    if fingerprint != record.get("schema_fingerprint"):
        return False, "PARTITION_SCHEMA_FINGERPRINT_MISMATCH", None, columns, fingerprint, rows
    if not frame["source"].astype("string").eq(source).all():
        return False, "PARTITION_SOURCE_IDENTITY_MISMATCH", None, columns, fingerprint, rows
    if not frame["observation_date"].astype("string").eq(date_text).all():
        return False, "PARTITION_DATE_IDENTITY_MISMATCH", None, columns, fingerprint, rows
    if rows != int(record.get("row_count", -1)):
        return False, "PARTITION_ROW_COUNT_MISMATCH", None, columns, fingerprint, rows
    return True, "PASS", frame, columns, fingerprint, rows
