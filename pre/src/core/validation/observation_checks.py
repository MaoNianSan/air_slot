from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ...input import object_hash, sha256_file
from ..contracts import stable_id
from ..observations import (
    EMPTY_REASONS,
    VALIDATION_COLUMNS,
    expected_empty_schema_fingerprint,
    validate_observations,
)
from ..observations.partition_manifest import parquet_metadata
from .table_checks import dataset_file_audit


def check_observations(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    dataset_root = root / "observations"
    manifest_path = dataset_root / "observation_partition_manifest.json"
    try:
        partition_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "status": "FAIL",
            "reason": "OBSERVATION_PARTITION_MANIFEST_MISSING",
            "extra_unregistered_files": [],
            "missing_registered_files": [],
            "duplicate_partition_files": [],
            "pass_empty_file_conflicts": [],
        }
    file_audit = dataset_file_audit(dataset_root, partition_manifest)
    failures: list[dict[str, Any]] = []
    rows = pass_empty = duplicate_ids = stable_id_errors = 0
    logical: dict[str, str] = {}
    for key, record in sorted(partition_manifest.get("partitions", {}).items()):
        status = str(record.get("status", ""))
        source = key.split("/", 1)[0].split("=", 1)[-1]
        observation_date = key.rsplit("=", 1)[-1]
        if status == "PASS_EMPTY":
            pass_empty += 1
            if record.get("empty_reason") not in EMPTY_REASONS:
                failures.append({"partition": key, "reason": "PASS_EMPTY_REASON_INVALID"})
            if record.get("schema_fingerprint") != expected_empty_schema_fingerprint(source):
                failures.append({"partition": key, "reason": "PASS_EMPTY_SCHEMA_MISMATCH"})
            if int(record.get("row_count", -1)) != 0 or record.get("relative_path"):
                failures.append({"partition": key, "reason": "PASS_EMPTY_RECORD_INVALID"})
            logical[key] = object_hash(record)
            continue
        if status != "PASS":
            failures.append({"partition": key, "reason": f"PARTITION_STATUS_{status or 'MISSING'}"})
            continue
        path = dataset_root / str(record.get("relative_path") or "")
        if not record.get("relative_path") or not path.exists():
            failures.append({"partition": key, "reason": "FILE_MISSING"})
            continue
        try:
            columns, _, metadata_rows, fingerprint = parquet_metadata(path)
            missing = sorted(set(VALIDATION_COLUMNS) - set(columns))
            if missing:
                failures.append({"partition": key, "reason": "COLUMNS_MISSING", "columns": missing})
                continue
            frame = pd.read_parquet(path, columns=VALIDATION_COLUMNS)
        except Exception as exc:
            failures.append({"partition": key, "reason": f"READ_FAIL:{type(exc).__name__}"})
            continue
        rows += metadata_rows
        logical[key] = sha256_file(path)
        duplicate_ids += int(frame["observation_id"].duplicated().sum())
        expected_ids = [stable_id(source, value) for value in frame["source_record_id"]]
        stable_id_errors += int(
            frame["observation_id"].astype("string").ne(
                pd.Series(expected_ids, index=frame.index, dtype="string")
            ).sum()
        )
        checks = [
            (logical[key] != record.get("file_hash"), "FILE_HASH_MISMATCH"),
            (fingerprint != record.get("schema_fingerprint"), "SCHEMA_FINGERPRINT_MISMATCH"),
            (metadata_rows != int(record.get("row_count", -1)), "ROW_COUNT_MISMATCH"),
            (not frame["source"].astype("string").eq(source).all(), "SOURCE_IDENTITY_MISMATCH"),
            (not frame["observation_date"].astype("string").eq(observation_date).all(), "DATE_IDENTITY_MISMATCH"),
        ]
        failures.extend({"partition": key, "reason": reason} for failed, reason in checks if failed)
        event_dates = pd.to_datetime(frame["event_time"], utc=True, errors="coerce").dt.strftime("%Y-%m-%d")
        if not event_dates.eq(observation_date).all():
            failures.append({"partition": key, "reason": "EVENT_DATE_IDENTITY_MISMATCH"})
        validation = validate_observations(frame)
        if validation["status"] != "PASS":
            failures.append({"partition": key, "reason": "PARTITION_VALIDATION_FAIL", "detail": validation})
    if duplicate_ids or stable_id_errors:
        failures.append({"reason": "OBSERVATION_KEY_VALIDATION_FAILED", "duplicate_observation_ids": duplicate_ids, "stable_id_errors": stable_id_errors})
    expected_rows = int(manifest.get("row_counts", {}).get("observations", rows))
    if rows != expected_rows:
        failures.append({"reason": "ROW_COUNT_MISMATCH", "expected": expected_rows, "actual": rows})
    if any(file_audit.values()):
        failures.append({"reason": "DATASET_FILE_AUDIT_FAILED"})
    partitions = len(partition_manifest.get("partitions", {}))
    return {
        "status": "PASS" if not failures else "FAIL",
        "partitions": partitions,
        "partition_count": partitions,
        "pass_empty_count": pass_empty,
        "observation_rows": rows,
        "rows": rows,
        "duplicate_observation_ids": duplicate_ids,
        "stable_id_errors": stable_id_errors,
        "failures": failures,
        "dataset_hash": object_hash(logical),
        "partition_manifest_hash": sha256_file(manifest_path),
        **file_audit,
    }
