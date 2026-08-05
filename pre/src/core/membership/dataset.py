from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ...input import object_hash, sha256_file
from ...progress import stage_message
from ..contracts import CONTRACT_ID, RESEARCH_CODE_REVISION, ResumeContract
from .parallel import Task, execute, worker_count
from .partition_manifest import (
    MEMBERSHIP_PARTITION_MANIFEST_NAME,
    PARTITION_COMPLETE_STATUSES,
    MembershipDatasetResult,
    atomic_write_json,
    expected_empty_schema_fingerprint,
)
from .partition_plan import partition_path, requests_for_partition
from .resume import validate_resumable_membership_partition


def _record_completion(
    manifest: dict[str, Any],
    manifest_path: Path,
    partition_key: str,
    result: dict[str, Any],
    *,
    reused: bool,
    resume_reason: str,
    progress_level: str,
) -> None:
    source = partition_key.split("/", 1)[0].split("=", 1)[1]
    observation_date = partition_key.rsplit("=", 1)[1]
    previous = manifest.setdefault("partitions", {}).get(partition_key, {})
    manifest["partitions"][partition_key] = {
        "source": source,
        "observation_date": observation_date,
        **result,
        "validated_at": previous.get(
            "validated_at", str(pd.Timestamp.now(tz="UTC"))
        ),
        "resume_status": "REUSED" if reused else "REBUILT",
        "resume_reason": resume_reason,
    }
    atomic_write_json(manifest, manifest_path)
    stage_message(
        f"Core membership: {partition_key}; rows={result['row_count']:,}; status={result['status']}",
        level=progress_level,
    )


def _summary(
    manifest: dict[str, Any],
    expected: set[str],
    manifest_path: Path,
    workers: int,
) -> MembershipDatasetResult:
    records = manifest.get("partitions", {})
    pass_count = sum(record.get("status") == "PASS" for record in records.values())
    pass_empty = sum(
        record.get("status") == "PASS_EMPTY" for record in records.values()
    )
    row_count = sum(int(record.get("row_count", 0)) for record in records.values())
    failures = [
        key
        for key in expected
        if records.get(key, {}).get("status") not in PARTITION_COMPLETE_STATUSES
    ]
    logical = {
        key: {
            field: record.get(field)
            for field in (
                "status",
                "row_count",
                "relative_path",
                "file_hash",
                "schema_fingerprint",
                "empty_reason",
                "source",
                "observation_date",
            )
        }
        for key, record in sorted(records.items())
        if key in expected
    }
    validation = {
        "status": "PASS"
        if not failures and len(records) == len(expected)
        else "FAIL",
        "membership_rows": row_count,
        "partition_count": pass_count + pass_empty,
        "pass_nonempty": pass_count,
        "pass_empty": pass_empty,
        "failed_or_missing_partitions": failures,
        "expected_partition_count": len(expected),
        "workers": workers,
    }
    return MembershipDatasetResult(
        row_count,
        pass_count + pass_empty,
        pass_empty,
        object_hash(logical),
        sha256_file(manifest_path),
        validation,
        manifest,
    )


def write_membership_dataset(
    root: Path,
    observations_root: Path,
    requests: pd.DataFrame,
    cfg: dict[str, Any],
    progress_level: str = "normal",
    *,
    resume_contract: ResumeContract | None = None,
) -> MembershipDatasetResult:
    root.mkdir(parents=True, exist_ok=True)
    observation_manifest = json.loads(
        (observations_root / "observation_partition_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    observation_partitions = observation_manifest.get("partitions", {})
    expected = set(observation_partitions)
    manifest_path = root / MEMBERSHIP_PARTITION_MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        manifest = {"partitions": {}}
    header = {
        "contract_id": CONTRACT_ID,
        "research_code_revision": RESEARCH_CODE_REVISION,
        "frozen_config_hash": resume_contract.frozen_config_hash
        if resume_contract
        else None,
    }
    if any(manifest.get(key) not in {None, value} for key, value in header.items()):
        manifest = {"partitions": {}}
    manifest.update(header)
    tasks: list[Task] = []
    for key in sorted(expected):
        observation_record = observation_partitions[key]
        source = key.split("/", 1)[0].split("=", 1)[1]
        observation_date = key.rsplit("=", 1)[1]
        path = partition_path(root, key)
        reusable, reason, _, _ = validate_resumable_membership_partition(
            root, key, expected, manifest
        )
        if reusable:
            _record_completion(
                manifest,
                manifest_path,
                key,
                manifest["partitions"][key],
                reused=True,
                resume_reason=reason,
                progress_level=progress_level,
            )
            continue
        manifest.setdefault("partitions", {})[key] = {
            "source": source,
            "observation_date": observation_date,
            "status": "IN_PROGRESS",
            "row_count": 0,
            "relative_path": None,
            "file_hash": None,
            "schema_fingerprint": expected_empty_schema_fingerprint(source),
            "validated_at": str(pd.Timestamp.now(tz="UTC")),
            "resume_reason": reason,
        }
        atomic_write_json(manifest, manifest_path)
        if observation_record.get("status") == "PASS_EMPTY":
            if any(path.parent.glob("*.parquet")):
                raise ValueError("MEMBERSHIP_PASS_EMPTY_FILE_CONFLICT")
            result = {
                "status": "PASS_EMPTY",
                "row_count": 0,
                "relative_path": None,
                "file_hash": None,
                "schema_fingerprint": expected_empty_schema_fingerprint(source),
                "empty_reason": str(
                    observation_record.get("empty_reason", "NO_SOURCE_RECORDS")
                ),
            }
            _record_completion(
                manifest,
                manifest_path,
                key,
                result,
                reused=False,
                resume_reason=reason,
                progress_level=progress_level,
            )
            continue
        if observation_record.get("status") != "PASS":
            raise ValueError(
                f"MEMBERSHIP_OBSERVATION_PARTITION_NOT_COMPLETE={key}:"
                f"{observation_record.get('status')}"
            )
        tasks.append(
            (
                key,
                observations_root / str(observation_record["relative_path"]),
                path,
                source,
                observation_date,
                requests_for_partition(requests, source, observation_date),
            )
        )
    workers = worker_count(cfg, [task[1] for task in tasks])
    try:
        results = execute(tasks, workers)
    except Exception as exc:
        for key, *_ in tasks:
            if manifest["partitions"][key].get("status") == "IN_PROGRESS":
                manifest["partitions"][key].update(
                    status="FAIL",
                    failure_reason=f"BUILD_READ_FAILURE:{type(exc).__name__}",
                    validated_at=str(pd.Timestamp.now(tz="UTC")),
                )
        atomic_write_json(manifest, manifest_path)
        raise
    for key, result in results:
        _record_completion(
            manifest,
            manifest_path,
            key,
            result,
            reused=False,
            resume_reason=str(
                manifest["partitions"][key].get("resume_reason", "REBUILT")
            ),
            progress_level=progress_level,
        )
    return _summary(manifest, expected, manifest_path, workers)
