from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ...input import object_hash, write_json
from ...progress import stage_message
from ...state import StateStore
from ..contracts import ResumeContract
from ..observation_flow import build_flow_observations
from ..observation_state import build_state_observations
from ..observation_weather import build_weather_observations
from ..resume_contract import PARTITION_MANIFEST_NAME, expected_observation_partitions
from .partition_builder import build_partition
from .partition_manifest import (
    VALIDATION_COLUMNS,
    ObservationDatasetResult,
    expected_empty_schema_fingerprint,
)
from .partition_plan import clip_requests, requests_for_day
from .resume import validate_resumable_partition
from .validation import validate_observations


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
    return (
        "NO_SOURCE_RECORDS"
        if source == "weather" and metar.empty
        else "NO_ADMISSIBLE_SOURCE_RECORDS"
    )


def _empty_result() -> ObservationDatasetResult:
    return ObservationDatasetResult(
        {},
        {},
        {},
        object_hash([]),
        {"status": "FAIL", "observation_rows": 0},
        [],
        {"partitions": {}},
        {},
    )


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
        return _empty_result()
    start = requests["request_start"].min().normalize()
    end = requests["request_end"].max().normalize()
    expected = set(
        resume_contract.expected_partitions
        if resume_contract is not None
        else expected_observation_partitions(requests)
    )
    manifest_path = root / PARTITION_MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        manifest = {"partitions": {}}
    row_counts = {source: 0 for source in ("state", "weather", "flow")}
    partition_counts = row_counts.copy()
    pass_empty_counts = row_counts.copy()
    partition_hashes: dict[str, str] = {}
    source_columns = {source: set() for source in row_counts}
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
            if requests_for_day(requests, source, day_start, day_end).empty:
                continue
            clipped = clip_requests(requests, source, day_start, day_end)
            key = f"source={source}/observation_date={date_text}"
            path = root / key / "part-00000.parquet"
            reusable, reason, frame, columns, fingerprint, rows = (
                validate_resumable_partition(path, key, expected, manifest)
            )
            if not reusable:
                manifest.setdefault("partitions", {})[key] = {
                    "source": source,
                    "observation_date": date_text,
                    "status": "IN_PROGRESS",
                    "row_count": 0,
                    "relative_path": None,
                    "file_hash": None,
                    "schema_fingerprint": expected_empty_schema_fingerprint(source),
                    "validated_at": str(pd.Timestamp.now(tz="UTC")),
                }
                write_json(manifest, manifest_path)
                try:
                    frame, columns, rows, fingerprint, digest = build_partition(
                        path, clipped, builder
                    )
                except Exception as exc:
                    manifest["partitions"][key].update(
                        status="FAIL",
                        failure_reason=f"BUILD_READ_FAILURE:{type(exc).__name__}",
                        validated_at=str(pd.Timestamp.now(tz="UTC")),
                    )
                    write_json(manifest, manifest_path)
                    raise
                if frame.empty:
                    if any(path.parent.glob("*.parquet")):
                        raise ValueError(f"OBSERVATION_PASS_EMPTY_FILE_CONFLICT={key}")
                    manifest["partitions"][key] = {
                        "source": source,
                        "observation_date": date_text,
                        "status": "PASS_EMPTY",
                        "row_count": 0,
                        "relative_path": None,
                        "file_hash": None,
                        "schema_fingerprint": expected_empty_schema_fingerprint(source),
                        "empty_reason": _empty_reason(source, metar),
                        "validated_at": str(pd.Timestamp.now(tz="UTC")),
                        "resume_status": "REBUILT",
                        "resume_reason": reason,
                    }
                    write_json(manifest, manifest_path)
                    partition_hashes[key] = object_hash(manifest["partitions"][key])
                    source_columns[source].update(VALIDATION_COLUMNS)
                    partition_counts[source] += 1
                    pass_empty_counts[source] += 1
                    stage_message(
                        f"Core observations: source={source}; date={date_text}; rows=0; status=PASS_EMPTY",
                        level=progress_level,
                    )
                    continue
            assert frame is not None
            if reason == "PASS_EMPTY":
                partition_hashes[key] = object_hash(manifest["partitions"][key])
                source_columns[source].update(VALIDATION_COLUMNS)
                partition_counts[source] += 1
                pass_empty_counts[source] += 1
                continue
            validation = validate_observations(frame)
            for name, value in validation.items():
                if isinstance(value, int) and not isinstance(value, bool) and name != "observation_rows":
                    issues[name] = issues.get(name, 0) + value
            digest = digest if not reusable else str(manifest["partitions"][key]["file_hash"])
            partition_hashes[key] = digest
            source_columns[source].update(columns)
            row_counts[source] += int(rows)
            partition_counts[source] += 1
            manifest.setdefault("partitions", {})[key] = {
                "status": "PASS",
                "relative_path": path.relative_to(root).as_posix(),
                "file_hash": digest,
                "schema_fingerprint": fingerprint,
                "source": source,
                "observation_date": date_text,
                "row_count": int(rows),
                "validated_at": str(pd.Timestamp.now(tz="UTC")),
                "resume_status": "REUSED" if reusable else "REBUILT",
                "resume_reason": reason,
            }
            write_json(manifest, manifest_path)
            evidence_rows.append(_evidence_row(frame, source, date_text, digest, columns))
            stage_message(
                f"Core observations: source={source}; date={date_text}; rows={rows:,}; cache={'HIT' if reusable else 'MISS'}",
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
        row_counts,
        partition_counts,
        pass_empty_counts,
        object_hash(partition_hashes),
        validation,
        evidence_rows,
        manifest,
        {key: sorted(value) for key, value in source_columns.items()},
    )
