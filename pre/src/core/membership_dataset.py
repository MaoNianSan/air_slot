from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ..input import object_hash, sha256_file
from ..progress import stage_message
from .contracts import CONTRACT_ID, RESEARCH_CODE_REVISION, ResumeContract
from .membership_interval_join import IDENTITY_COLUMNS, MEMBERSHIP_COLUMNS, interval_join_partition
from .observation_dataset import EMPTY_REASONS, schema_fingerprint
from .observation_membership import validate_observation_membership


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


def _atomic_write_json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    os.replace(temporary, path)


def _atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)


def _parquet_metadata(path: Path) -> tuple[list[str], list[str], int, str]:
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    columns = list(schema.names)
    dtypes = [str(schema.field(name).type) for name in columns]
    return columns, dtypes, int(parquet.metadata.num_rows), schema_fingerprint(columns, dtypes)


def _partition_path(root: Path, partition_key: str) -> Path:
    return root / partition_key / "part-00000.parquet"


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
    path = _partition_path(root, partition_key)
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
        columns, _, rows, fingerprint = _parquet_metadata(path)
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
    validation = validate_observation_membership(frame)
    if validation["status"] != "PASS":
        return False, "PARTITION_MEMBERSHIP_VALIDATION_FAILED", rows, fingerprint
    return True, "PASS", rows, fingerprint


def _requests_for_partition(
    requests: pd.DataFrame, source: str, observation_date: str
) -> pd.DataFrame:
    day_start = pd.Timestamp(observation_date, tz="UTC")
    day_end = day_start + pd.Timedelta(days=1)
    return requests[
        requests["source"].eq(source)
        & pd.to_datetime(requests["request_start"], utc=True).lt(day_end)
        & pd.to_datetime(requests["request_end"], utc=True).ge(day_start)
    ].copy()


def _empty_reason(
    observations: pd.DataFrame, requests: pd.DataFrame, source: str
) -> str:
    if observations.empty:
        return "NO_SOURCE_RECORDS"
    if requests.empty:
        return "NO_REQUEST_OVERLAP"
    observation_identity, request_identity = IDENTITY_COLUMNS[source]
    observation_values = set(observations[observation_identity].dropna().astype(str))
    request_values = set(requests[request_identity].dropna().astype(str))
    return "NO_MATCHING_IDENTITY" if observation_values.isdisjoint(request_values) else "NO_REQUEST_OVERLAP"


def _build_partition(
    observation_path: str,
    membership_path: str,
    source: str,
    observation_date: str,
    requests: pd.DataFrame,
) -> dict[str, Any]:
    observation_identity, _ = IDENTITY_COLUMNS[source]
    import pyarrow.parquet as pq

    available = set(pq.ParquetFile(Path(observation_path)).schema_arrow.names)
    selected = [
        column
        for column in (
            "observation_id", "source", "observation_date", "event_time",
            "availability_time", observation_identity, "flight_id",
        )
        if column in available
    ]
    observations = pd.read_parquet(Path(observation_path), columns=selected)
    membership = interval_join_partition(
        observations, requests, source=source, observation_date=observation_date
    )
    if membership.empty:
        path = Path(membership_path)
        if any(path.parent.glob("*.parquet")):
            raise ValueError("MEMBERSHIP_PASS_EMPTY_FILE_CONFLICT")
        return {
            "status": "PASS_EMPTY",
            "row_count": 0,
            "relative_path": None,
            "file_hash": None,
            "schema_fingerprint": expected_empty_schema_fingerprint(source),
            "empty_reason": _empty_reason(observations, requests, source),
        }
    validation = validate_observation_membership(membership)
    if validation["status"] != "PASS":
        raise ValueError("MEMBERSHIP_PARTITION_VALIDATION_FAILED=" + json.dumps(validation))
    path = Path(membership_path)
    _atomic_write_parquet(membership, path)
    _, _, rows, fingerprint = _parquet_metadata(path)
    if rows != len(membership):
        raise ValueError("MEMBERSHIP_PARTITION_WRITE_ROW_COUNT_MISMATCH")
    return {
        "status": "PASS",
        "row_count": rows,
        "relative_path": (
            f"source={source}/observation_date={observation_date}/{path.name}"
        ),
        "file_hash": sha256_file(path),
        "schema_fingerprint": fingerprint,
    }


def _worker_count(cfg: dict[str, Any], paths: list[Path]) -> int:
    settings = cfg.get("core_membership", {})
    if settings.get("partition_unit", "source_date") != "source_date":
        raise ValueError("MEMBERSHIP_PARTITION_UNIT_MUST_BE_SOURCE_DATE")
    if bool(settings.get("nested_parallelism", False)):
        raise ValueError("MEMBERSHIP_NESTED_PARALLELISM_FORBIDDEN")
    requested = max(1, int(settings.get("workers", 4)))
    maximum = max(1, min(6, int(settings.get("max_workers", 6))))
    workers = min(requested, maximum, max(1, len(paths)))
    largest = max((path.stat().st_size for path in paths if path.exists()), default=0)
    if largest >= int(settings.get("single_worker_partition_bytes", 2_000_000_000)):
        return 1
    if largest >= int(settings.get("reduced_worker_partition_bytes", 1_000_000_000)):
        return min(workers, 2)
    return workers


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
    observation_manifest_path = observations_root / "observation_partition_manifest.json"
    observation_manifest = json.loads(observation_manifest_path.read_text(encoding="utf-8"))
    observation_partitions = observation_manifest.get("partitions", {})
    expected = set(observation_partitions)
    manifest_path = root / MEMBERSHIP_PARTITION_MANIFEST_NAME
    try:
        partition_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        partition_manifest = {"partitions": {}}
    expected_header = {
        "contract_id": CONTRACT_ID,
        "research_code_revision": RESEARCH_CODE_REVISION,
        "frozen_config_hash": resume_contract.frozen_config_hash if resume_contract else None,
    }
    if any(
        partition_manifest.get(key) not in {None, value}
        for key, value in expected_header.items()
    ):
        partition_manifest = {"partitions": {}}
    partition_manifest.update(expected_header)

    tasks: list[tuple[str, Path, Path, str, str, pd.DataFrame]] = []

    def record_completion(
        partition_key: str,
        result: dict[str, Any],
        *,
        reused: bool,
        resume_reason: str,
    ) -> None:
        source = partition_key.split("/", 1)[0].split("=", 1)[1]
        observation_date = partition_key.rsplit("=", 1)[1]
        previous = partition_manifest.setdefault("partitions", {}).get(partition_key, {})
        partition_manifest["partitions"][partition_key] = {
            "source": source,
            "observation_date": observation_date,
            **result,
            "validated_at": previous.get(
                "validated_at", str(pd.Timestamp.now(tz="UTC"))
            ),
            "resume_status": "REUSED" if reused else "REBUILT",
            "resume_reason": resume_reason,
        }
        _atomic_write_json(partition_manifest, manifest_path)
        stage_message(
            f"Core membership: {partition_key}; rows={result['row_count']:,}; "
            f"status={result['status']}",
            level=progress_level,
        )

    for partition_key in sorted(expected):
        observation_record = observation_partitions[partition_key]
        source = partition_key.split("/", 1)[0].split("=", 1)[1]
        observation_date = partition_key.rsplit("=", 1)[1]
        path = _partition_path(root, partition_key)
        reusable, reason, _, _ = validate_resumable_membership_partition(
            root, partition_key, expected, partition_manifest
        )
        if reusable:
            record_completion(
                partition_key,
                partition_manifest["partitions"][partition_key],
                reused=True,
                resume_reason=reason,
            )
            continue
        partition_manifest.setdefault("partitions", {})[partition_key] = {
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
        _atomic_write_json(partition_manifest, manifest_path)
        if observation_record.get("status") == "PASS_EMPTY":
            if any(path.parent.glob("*.parquet")):
                raise ValueError("MEMBERSHIP_PASS_EMPTY_FILE_CONFLICT")
            result = {
                "status": "PASS_EMPTY",
                "row_count": 0,
                "relative_path": None,
                "file_hash": None,
                "schema_fingerprint": expected_empty_schema_fingerprint(source),
                "empty_reason": str(observation_record.get("empty_reason", "NO_SOURCE_RECORDS")),
            }
            record_completion(
                partition_key, result, reused=False, resume_reason=reason
            )
            continue
        if observation_record.get("status") != "PASS":
            raise ValueError(
                f"MEMBERSHIP_OBSERVATION_PARTITION_NOT_COMPLETE={partition_key}:"
                f"{observation_record.get('status')}"
            )
        observation_path = observations_root / str(observation_record["relative_path"])
        tasks.append(
            (
                partition_key,
                observation_path,
                path,
                source,
                observation_date,
                _requests_for_partition(requests, source, observation_date),
            )
        )

    workers = _worker_count(cfg, [item[1] for item in tasks])
    if workers == 1:
        for key, observation_path, path, source, observation_date, subset in tasks:
            try:
                result = _build_partition(
                    str(observation_path), str(path), source, observation_date, subset
                )
                record_completion(
                    key,
                    result,
                    reused=False,
                    resume_reason=str(
                        partition_manifest["partitions"][key].get(
                            "resume_reason", "REBUILT"
                        )
                    ),
                )
            except Exception as exc:
                partition_manifest["partitions"][key].update(
                    status="FAIL",
                    failure_reason=f"BUILD_READ_FAILURE:{type(exc).__name__}",
                    validated_at=str(pd.Timestamp.now(tz="UTC")),
                )
                _atomic_write_json(partition_manifest, manifest_path)
                raise
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _build_partition,
                    str(observation_path),
                    str(path),
                    source,
                    observation_date,
                    subset,
                ): key
                for key, observation_path, path, source, observation_date, subset in tasks
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    result = future.result()
                    record_completion(
                        key,
                        result,
                        reused=False,
                        resume_reason=str(
                            partition_manifest["partitions"][key].get(
                                "resume_reason", "REBUILT"
                            )
                        ),
                    )
                except Exception as exc:
                    partition_manifest["partitions"][key].update(
                        status="FAIL",
                        failure_reason=f"BUILD_READ_FAILURE:{type(exc).__name__}",
                        validated_at=str(pd.Timestamp.now(tz="UTC")),
                    )
                    _atomic_write_json(partition_manifest, manifest_path)
                    raise

    records = partition_manifest.get("partitions", {})
    pass_count = sum(record.get("status") == "PASS" for record in records.values())
    pass_empty_count = sum(record.get("status") == "PASS_EMPTY" for record in records.values())
    row_count = sum(int(record.get("row_count", 0)) for record in records.values())
    failures = [
        key for key in expected
        if records.get(key, {}).get("status") not in PARTITION_COMPLETE_STATUSES
    ]
    logical = {
        key: {
            field: record.get(field)
            for field in (
                "status", "row_count", "relative_path", "file_hash",
                "schema_fingerprint", "empty_reason", "source", "observation_date",
            )
        }
        for key, record in sorted(records.items())
        if key in expected
    }
    validation = {
        "status": "PASS" if not failures and len(records) == len(expected) else "FAIL",
        "membership_rows": row_count,
        "partition_count": pass_count + pass_empty_count,
        "pass_nonempty": pass_count,
        "pass_empty": pass_empty_count,
        "failed_or_missing_partitions": failures,
        "expected_partition_count": len(expected),
        "workers": workers,
    }
    return MembershipDatasetResult(
        row_count=row_count,
        partition_count=pass_count + pass_empty_count,
        pass_empty_count=pass_empty_count,
        dataset_hash=object_hash(logical),
        partition_manifest_hash=sha256_file(manifest_path),
        validation=validation,
        partition_manifest=partition_manifest,
    )
