from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ...input import sha256_file
from ..observations import EMPTY_REASONS
from .interval_join import MEMBERSHIP_COLUMNS
from .partition_manifest import expected_empty_schema_fingerprint, parquet_metadata
from .partition_plan import partition_path
from .validation import validate_observation_membership


def validate_resumable_membership_partition(
    root: Path,
    partition_key: str,
    expected_partitions: set[str],
    partition_manifest: dict[str, Any],
) -> tuple[bool, str, int, str]:
    if partition_key not in expected_partitions:
        return False, "PARTITION_NOT_EXPECTED", 0, ""
    record = partition_manifest.get("partitions", {}).get(partition_key)
    if not isinstance(record, dict):
        return False, "PARTITION_MANIFEST_MISSING", 0, ""
    path = partition_path(root, partition_key)
    status = str(record.get("status", ""))
    source = partition_key.split("/", 1)[0].split("=", 1)[1]
    if status == "PASS_EMPTY":
        if record.get("relative_path") or any(path.parent.glob("*.parquet")):
            return False, "PASS_EMPTY_FILE_CONFLICT", 0, ""
        if record.get("empty_reason") not in EMPTY_REASONS:
            return False, "PASS_EMPTY_REASON_INVALID", 0, ""
        fingerprint = str(record.get("schema_fingerprint", ""))
        if fingerprint != expected_empty_schema_fingerprint(source):
            return False, "PASS_EMPTY_SCHEMA_FINGERPRINT_MISMATCH", 0, fingerprint
        if int(record.get("row_count", -1)) != 0 or record.get("file_hash"):
            return False, "PASS_EMPTY_RECORD_INVALID", 0, fingerprint
        return True, "PASS_EMPTY", 0, fingerprint
    if status != "PASS":
        return False, f"PARTITION_STATUS_{status or 'MISSING'}", 0, ""
    if not path.exists():
        return False, "PARTITION_FILE_MISSING", 0, ""
    if record.get("relative_path") != f"{partition_key}/{path.name}":
        return False, "PARTITION_RELATIVE_PATH_MISMATCH", 0, ""
    try:
        columns, _, rows, fingerprint = parquet_metadata(path)
        missing = sorted(set(MEMBERSHIP_COLUMNS) - set(columns))
        if missing:
            return False, "PARTITION_COLUMNS_MISSING:" + ",".join(missing), rows, fingerprint
        frame = pd.read_parquet(path, columns=MEMBERSHIP_COLUMNS)
    except Exception as exc:
        return False, f"PARTITION_UNREADABLE:{type(exc).__name__}", 0, ""
    if sha256_file(path) != record.get("file_hash"):
        return False, "PARTITION_FILE_HASH_MISMATCH", rows, fingerprint
    if fingerprint != record.get("schema_fingerprint"):
        return False, "PARTITION_SCHEMA_FINGERPRINT_MISMATCH", rows, fingerprint
    if rows != int(record.get("row_count", -1)):
        return False, "PARTITION_ROW_COUNT_MISMATCH", rows, fingerprint
    if not frame["source"].astype("string").eq(source).all():
        return False, "PARTITION_SOURCE_IDENTITY_MISMATCH", rows, fingerprint
    if validate_observation_membership(frame)["status"] != "PASS":
        return False, "PARTITION_MEMBERSHIP_VALIDATION_FAILED", rows, fingerprint
    return True, "PASS", rows, fingerprint
