from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ...input import object_hash, sha256_file
from ..contracts import stable_id
from ..membership import (
    MEMBERSHIP_COLUMNS,
    MEMBERSHIP_PARTITION_MANIFEST_NAME,
    expected_empty_schema_fingerprint,
    validate_observation_membership,
)
from ..membership.partition_manifest import parquet_metadata
from ..observations import EMPTY_REASONS
from .table_checks import dataset_file_audit


def check_membership(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    dataset_root = root / "observation_membership"
    manifest_path = dataset_root / MEMBERSHIP_PARTITION_MANIFEST_NAME
    try:
        partition_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "status": "FAIL",
            "reason": "MEMBERSHIP_PARTITION_MANIFEST_MISSING",
            "membership_rows": 0,
            "partition_count": 0,
            "pass_empty": 0,
            "extra_unregistered_files": [],
            "missing_registered_files": [],
            "duplicate_partition_files": [],
            "pass_empty_file_conflicts": [],
        }
    file_audit = dataset_file_audit(dataset_root, partition_manifest)
    try:
        observation_manifest = json.loads(
            (root / "observations" / "observation_partition_manifest.json").read_text(encoding="utf-8")
        )
    except (FileNotFoundError, json.JSONDecodeError):
        observation_manifest = {"partitions": {}}
    failures: list[dict[str, Any]] = []
    rows = pass_empty = duplicate_ids = duplicate_relations = stable_id_errors = 0
    logical: dict[str, dict[str, Any]] = {}
    for key, record in sorted(partition_manifest.get("partitions", {}).items()):
        status = str(record.get("status", ""))
        source = key.split("/", 1)[0].split("=", 1)[-1]
        if status == "PASS_EMPTY":
            pass_empty += 1
            if record.get("empty_reason") not in EMPTY_REASONS:
                failures.append({"partition": key, "reason": "PASS_EMPTY_REASON_INVALID"})
            if record.get("schema_fingerprint") != expected_empty_schema_fingerprint(source):
                failures.append({"partition": key, "reason": "PASS_EMPTY_SCHEMA_MISMATCH"})
            if int(record.get("row_count", -1)) != 0 or record.get("relative_path"):
                failures.append({"partition": key, "reason": "PASS_EMPTY_RECORD_INVALID"})
        elif status == "PASS":
            path = dataset_root / str(record.get("relative_path") or "")
            if not record.get("relative_path") or not path.exists():
                failures.append({"partition": key, "reason": "FILE_MISSING"})
                continue
            try:
                columns, _, metadata_rows, fingerprint = parquet_metadata(path)
                missing = sorted(set(MEMBERSHIP_COLUMNS) - set(columns))
                if missing:
                    failures.append({"partition": key, "reason": "COLUMNS_MISSING", "columns": missing})
                    continue
                frame = pd.read_parquet(path, columns=MEMBERSHIP_COLUMNS)
            except Exception as exc:
                failures.append({"partition": key, "reason": f"READ_FAIL:{type(exc).__name__}"})
                continue
            rows += metadata_rows
            duplicate_ids += int(frame["membership_id"].duplicated().sum())
            duplicate_relations += int(frame.duplicated(["chain_episode_id", "observation_id", "interval_type"]).sum())
            expected_ids = [stable_id(chain, observation, interval) for chain, observation, interval in frame[["chain_episode_id", "observation_id", "interval_type"]].itertuples(index=False, name=None)]
            stable_id_errors += int(frame["membership_id"].astype("string").ne(pd.Series(expected_ids, index=frame.index)).sum())
            if validate_observation_membership(frame)["status"] != "PASS":
                failures.append({"partition": key, "reason": "PARTITION_VALIDATION_FAIL"})
            checks = [
                (sha256_file(path) != record.get("file_hash"), "FILE_HASH_MISMATCH"),
                (fingerprint != record.get("schema_fingerprint"), "SCHEMA_FINGERPRINT_MISMATCH"),
                (metadata_rows != int(record.get("row_count", -1)), "ROW_COUNT_MISMATCH"),
                (not frame["source"].astype("string").eq(source).all(), "SOURCE_IDENTITY_MISMATCH"),
            ]
            failures.extend({"partition": key, "reason": reason} for failed, reason in checks if failed)
            observation_record = observation_manifest.get("partitions", {}).get(key, {})
            observation_path = root / "observations" / str(observation_record.get("relative_path") or "")
            if observation_record.get("status") == "PASS" and observation_path.exists():
                observation_ids = set(pd.read_parquet(observation_path, columns=["observation_id"])["observation_id"].astype(str))
                missing_observations = int((~frame["observation_id"].astype(str).isin(observation_ids)).sum())
                if missing_observations:
                    failures.append({"partition": key, "reason": "OBSERVATION_PARTITION_IDENTITY_MISMATCH", "count": missing_observations})
            elif metadata_rows:
                failures.append({"partition": key, "reason": "OBSERVATION_PARTITION_FILE_MISSING"})
        else:
            failures.append({"partition": key, "reason": f"PARTITION_STATUS_{status or 'MISSING'}"})
        logical[key] = {field: record.get(field) for field in ("status", "row_count", "relative_path", "file_hash", "schema_fingerprint", "empty_reason", "source", "observation_date")}
    if duplicate_ids or duplicate_relations or stable_id_errors:
        failures.append({"reason": "MEMBERSHIP_KEY_VALIDATION_FAILED", "duplicate_membership_ids": duplicate_ids, "duplicate_relations": duplicate_relations, "stable_id_errors": stable_id_errors})
    if any(file_audit.values()):
        failures.append({"reason": "DATASET_FILE_AUDIT_FAILED"})
    if rows != int(manifest.get("membership_row_count", rows)):
        failures.append({"reason": "ROW_COUNT_MISMATCH"})
    if len(logical) != int(manifest.get("membership_partition_count", len(logical))):
        failures.append({"reason": "PARTITION_COUNT_MISMATCH"})
    dataset_hash = object_hash(logical)
    if manifest.get("membership_dataset_hash") != dataset_hash:
        failures.append({"reason": "MEMBERSHIP_DATASET_HASH_MISMATCH"})
    manifest_hash = sha256_file(manifest_path)
    if manifest.get("membership_partition_manifest_hash") != manifest_hash:
        failures.append({"reason": "MEMBERSHIP_PARTITION_MANIFEST_HASH_MISMATCH"})
    return {
        "status": "PASS" if not failures else "FAIL",
        "membership_rows": rows,
        "partition_count": len(logical),
        "pass_empty": pass_empty,
        "duplicate_membership_ids": duplicate_ids,
        "duplicate_relations": duplicate_relations,
        "stable_id_errors": stable_id_errors,
        "dataset_hash": dataset_hash,
        "partition_manifest_hash": manifest_hash,
        "failures": failures,
        **file_audit,
    }
