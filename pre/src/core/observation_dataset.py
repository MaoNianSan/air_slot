from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..input import object_hash, sha256_file, write_json
from ..progress import stage_message
from ..state import StateStore
from .contracts import OBSERVATION_CONTRACT_ID, ResumeContract
from .observation_builder import MEMBERSHIP_ONLY_COLUMNS, _align
from .observation_flow import build_flow_observations
from .observation_state import build_state_observations
from .observation_validation import validate_observations
from .observation_weather import build_weather_observations
from .resume_contract import PARTITION_MANIFEST_NAME, expected_observation_partitions


PARTITION_COMPLETE_STATUSES = {"PASS", "PASS_EMPTY"}
EMPTY_REASONS = {
    "NO_SOURCE_RECORDS", "NO_ADMISSIBLE_SOURCE_RECORDS",
    "NO_MATCHING_IDENTITY", "NO_REQUEST_OVERLAP",
}


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


VALIDATION_COLUMNS = [
    "observation_id", "source", "observation_date", "observation_time",
    "event_time", "availability_time", "source_record_id", "source_file",
    "source_hash", "airport_id", "aircraft_id", "flight_id",
]


def _requests_for_day(
    requests: pd.DataFrame, source: str, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    return requests[
        requests["source"].eq(source)
        & requests["request_start"].lt(end)
        & requests["request_end"].ge(start)
    ].copy()


def _clip_requests(
    requests: pd.DataFrame, source: str, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    subset = _requests_for_day(requests, source, start, end)
    if subset.empty:
        return subset
    subset["request_start"] = subset["request_start"].clip(lower=start)
    subset["request_end"] = subset["request_end"].clip(
        upper=end - pd.Timedelta(nanoseconds=1)
    )
    return subset


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


def _parquet_metadata(path: Path) -> tuple[list[str], list[str], int, str]:
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    columns = list(schema.names)
    dtypes = [str(schema.field(name).type) for name in columns]
    return columns, dtypes, int(parquet.metadata.num_rows), schema_fingerprint(columns, dtypes)


def _read_validation_projection(path: Path) -> tuple[pd.DataFrame, list[str], str, int]:
    columns, _, rows, fingerprint = _parquet_metadata(path)
    missing = sorted(set(VALIDATION_COLUMNS) - set(columns))
    if missing:
        raise ValueError("CORE_OBSERVATION_PARTITION_COLUMNS_MISSING:" + ",".join(missing))
    return pd.read_parquet(path, columns=VALIDATION_COLUMNS), columns, fingerprint, rows


def _atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)


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
        relative = record.get("relative_path")
        if relative or any(path.parent.glob("*.parquet")):
            return False, "PASS_EMPTY_FILE_CONFLICT", None, [], "", 0
        if record.get("empty_reason") not in EMPTY_REASONS:
            return False, "PASS_EMPTY_REASON_INVALID", None, [], "", 0
        if record.get("schema_fingerprint") != expected_empty_schema_fingerprint(source):
            return False, "PASS_EMPTY_SCHEMA_FINGERPRINT_MISMATCH", None, [], "", 0
        if int(record.get("row_count", -1)) != 0 or record.get("file_hash"):
            return False, "PASS_EMPTY_RECORD_INVALID", None, [], "", 0
        return True, "PASS_EMPTY", pd.DataFrame(columns=VALIDATION_COLUMNS), VALIDATION_COLUMNS, str(record["schema_fingerprint"]), 0
    if status != "PASS":
        return False, f"PARTITION_STATUS_{status or 'MISSING'}", None, [], "", 0
    if not path.exists():
        return False, "PARTITION_FILE_MISSING", None, [], "", 0
    expected_relative = f"{partition_key}/{path.name}"
    if record.get("relative_path") != expected_relative:
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


def _evidence_row(
    frame: pd.DataFrame,
    source: str,
    date_text: str,
    partition_hash: str,
    partition_columns: list[str],
) -> dict[str, object]:
    files = sorted(frame["source_file"].dropna().astype(str).unique())
    hashes = sorted(frame["source_hash"].dropna().astype(str).unique())
    return {
        "table": "observations",
        "entity_id": f"source={source}/observation_date={date_text}",
        "variable_name": f"native_{source}_record_columns",
        "raw_source": source,
        "raw_field": json.dumps(partition_columns, sort_keys=True),
        "source_record_id": f"PARTITION:{partition_hash}",
        "source_file": json.dumps(files, sort_keys=True),
        "source_hash": object_hash(hashes),
        "event_time": frame["event_time"].min(),
        "availability_time": frame["availability_time"].max(),
        "transformation": "SOURCE_GLOBAL_NATIVE_RECORDS_WITH_EXPLICIT_COLUMN_REGISTRY",
        "support_level": "SUPPORTED_PROXY",
        "fallback_level": "NONE",
        "missing_reason": "",
        "future_information_used": False,
    }


def _empty_reason(source: str, metar: pd.DataFrame) -> str:
    if source == "weather" and metar.empty:
        return "NO_SOURCE_RECORDS"
    return "NO_ADMISSIBLE_SOURCE_RECORDS"


def write_observation_dataset(
    root: Path,
    requests: pd.DataFrame,
    store: StateStore,
    metar: pd.DataFrame,
    inventory: pd.DataFrame,
    progress_level: str = "normal",
    *,
    resume_contract: ResumeContract | None = None,
) -> ObservationDatasetResult:
    root.mkdir(parents=True, exist_ok=True)
    if requests.empty:
        return ObservationDatasetResult(
            {}, {}, {}, object_hash([]), {"status": "FAIL", "observation_rows": 0},
            [], {"partitions": {}}, {},
        )
    start = requests["request_start"].min().normalize()
    end = requests["request_end"].max().normalize()
    expected = set(
        resume_contract.expected_partitions
        if resume_contract is not None
        else expected_observation_partitions(requests)
    )
    partition_manifest_path = root / PARTITION_MANIFEST_NAME
    try:
        partition_manifest = json.loads(partition_manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        partition_manifest = {"partitions": {}}
    row_counts = {"state": 0, "weather": 0, "flow": 0}
    partition_counts = {"state": 0, "weather": 0, "flow": 0}
    pass_empty_counts = {"state": 0, "weather": 0, "flow": 0}
    partition_hashes: dict[str, str] = {}
    source_columns: dict[str, set[str]] = {"state": set(), "weather": set(), "flow": set()}
    evidence_rows: list[dict[str, object]] = []
    issues: dict[str, int] = {}
    builders = {
        "state": lambda frame: build_state_observations(frame, store),
        "weather": lambda frame: build_weather_observations(frame, metar),
        "flow": lambda frame: build_flow_observations(frame, store, inventory),
    }
    for date in pd.date_range(start, end, freq="D"):
        day_start = pd.Timestamp(date)
        day_end = day_start + pd.Timedelta(days=1)
        date_text = day_start.strftime("%Y-%m-%d")
        for source, builder in builders.items():
            original_requests = _requests_for_day(requests, source, day_start, day_end)
            if original_requests.empty:
                continue
            clipped = _clip_requests(requests, source, day_start, day_end)
            partition_key = f"source={source}/observation_date={date_text}"
            path = root / partition_key / "part-00000.parquet"
            reusable, reuse_reason, frame, partition_columns, fingerprint, metadata_rows = validate_resumable_partition(
                path, partition_key, expected, partition_manifest
            )
            if not reusable:
                partition_manifest.setdefault("partitions", {})[partition_key] = {
                    "source": source, "observation_date": date_text,
                    "status": "IN_PROGRESS", "row_count": 0,
                    "relative_path": None, "file_hash": None,
                    "schema_fingerprint": expected_empty_schema_fingerprint(source),
                    "validated_at": str(pd.Timestamp.now(tz="UTC")),
                }
                write_json(partition_manifest, partition_manifest_path)
                try:
                    frame = builder(clipped)
                except Exception as exc:
                    partition_manifest["partitions"][partition_key].update(
                        status="FAIL",
                        failure_reason=f"BUILD_READ_FAILURE:{type(exc).__name__}",
                        validated_at=str(pd.Timestamp.now(tz="UTC")),
                    )
                    write_json(partition_manifest, partition_manifest_path)
                    raise
                if frame.empty:
                    existing_files = sorted(path.parent.glob("*.parquet"))
                    if existing_files:
                        partition_manifest["partitions"][partition_key].update(
                            status="FAIL",
                            failure_reason="PASS_EMPTY_FILE_CONFLICT",
                            validated_at=str(pd.Timestamp.now(tz="UTC")),
                        )
                        write_json(partition_manifest, partition_manifest_path)
                        raise ValueError(
                            f"OBSERVATION_PASS_EMPTY_FILE_CONFLICT={partition_key}"
                        )
                    empty_reason = _empty_reason(source, metar)
                    partition_manifest["partitions"][partition_key] = {
                        "source": source,
                        "observation_date": date_text,
                        "status": "PASS_EMPTY",
                        "row_count": 0,
                        "relative_path": None,
                        "file_hash": None,
                        "schema_fingerprint": expected_empty_schema_fingerprint(source),
                        "empty_reason": empty_reason,
                        "validated_at": str(pd.Timestamp.now(tz="UTC")),
                        "resume_status": "REBUILT",
                        "resume_reason": reuse_reason,
                    }
                    write_json(partition_manifest, partition_manifest_path)
                    partition_hashes[partition_key] = object_hash(partition_manifest["partitions"][partition_key])
                    source_columns[source].update(VALIDATION_COLUMNS)
                    partition_counts[source] += 1
                    pass_empty_counts[source] += 1
                    stage_message(
                        f"Core observations: source={source}; date={date_text}; rows=0; status=PASS_EMPTY",
                        level=progress_level,
                    )
                    continue
                frame = _align(frame)
                frame = frame.drop(
                    columns=[column for column in MEMBERSHIP_ONLY_COLUMNS if column in frame],
                    errors="ignore",
                ).sort_values("observation_id", kind="mergesort")
                for column in ["observation_time", "event_time", "availability_time"]:
                    frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
                frame = frame.drop_duplicates("observation_id", keep="last")
                _atomic_write_parquet(frame, path)
                partition_columns, _, metadata_rows, fingerprint = _parquet_metadata(path)
            assert frame is not None
            if reuse_reason == "PASS_EMPTY":
                partition_hashes[partition_key] = object_hash(partition_manifest["partitions"][partition_key])
                source_columns[source].update(VALIDATION_COLUMNS)
                partition_counts[source] += 1
                pass_empty_counts[source] += 1
                continue
            validation = validate_observations(frame)
            for key, value in validation.items():
                if isinstance(value, int) and not isinstance(value, bool) and key != "observation_rows":
                    issues[key] = issues.get(key, 0) + value
            digest = sha256_file(path)
            partition_hashes[partition_key] = digest
            source_columns[source].update(partition_columns)
            row_counts[source] += int(metadata_rows)
            partition_counts[source] += 1
            partition_manifest.setdefault("partitions", {})[partition_key] = {
                "status": "PASS",
                "relative_path": path.relative_to(root).as_posix(),
                "file_hash": digest,
                "schema_fingerprint": fingerprint,
                "source": source,
                "observation_date": date_text,
                "row_count": int(metadata_rows),
                "validated_at": str(pd.Timestamp.now(tz="UTC")),
                "resume_status": "REUSED" if reusable else "REBUILT",
                "resume_reason": reuse_reason,
            }
            write_json(partition_manifest, partition_manifest_path)
            evidence_rows.append(_evidence_row(frame, source, date_text, digest, partition_columns))
            stage_message(
                f"Core observations: source={source}; date={date_text}; rows={metadata_rows:,}; "
                f"cache={'HIT' if reusable else 'MISS'}",
                level=progress_level,
            )
    complete = sum(partition_counts.values())
    total = sum(row_counts.values())
    status = "PASS" if complete == len(expected) and not any(issues.values()) else "FAIL"
    validation = {
        "status": status,
        "observation_rows": total,
        "rows_by_source": row_counts,
        "partition_counts": partition_counts,
        "pass_empty_counts": pass_empty_counts,
        "pass_empty_count": sum(pass_empty_counts.values()),
        "expected_partition_count": len(expected),
        **issues,
        "ratio_dependency_columns": [],
        "native_resolution_preserved": True,
        "split_neutral": True,
        "on_demand_evidence_supported": status == "PASS" and total > 0,
    }
    return ObservationDatasetResult(
        row_counts=row_counts,
        partition_counts=partition_counts,
        pass_empty_counts=pass_empty_counts,
        content_hash=object_hash(partition_hashes),
        validation=validation,
        evidence_rows=evidence_rows,
        partition_manifest=partition_manifest,
        source_columns={key: sorted(value) for key, value in source_columns.items()},
    )
