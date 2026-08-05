from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..input import object_hash, sha256_file, write_parquet
from ..progress import stage_message
from ..state import StateStore
from .observation_builder import _align
from .observation_flow import build_flow_observations
from .observation_state import build_state_observations
from .observation_validation import validate_observations
from .observation_weather import build_weather_observations


@dataclass(frozen=True)
class ObservationDatasetResult:
    row_counts: dict[str, int]
    partition_counts: dict[str, int]
    content_hash: str
    validation: dict[str, object]
    evidence_rows: list[dict[str, object]]


def _clip_requests(
    requests: pd.DataFrame, source: str, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    subset = requests[
        requests["source"].eq(source)
        & requests["request_start"].lt(end)
        & requests["request_end"].ge(start)
    ].copy()
    if subset.empty:
        return subset
    subset["request_start"] = subset["request_start"].clip(lower=start)
    subset["request_end"] = subset["request_end"].clip(upper=end - pd.Timedelta(nanoseconds=1))
    return subset


VALIDATION_COLUMNS = [
    "observation_id",
    "source",
    "observation_time",
    "event_time",
    "availability_time",
    "request_start",
    "request_end",
    "source_file",
    "source_hash",
]


def _read_validation_projection(path: Path) -> tuple[pd.DataFrame, list[str]]:
    import pyarrow.parquet as pq

    columns = pq.ParquetFile(path).schema_arrow.names
    missing = sorted(set(VALIDATION_COLUMNS) - set(columns))
    if missing:
        raise ValueError("CORE_OBSERVATION_PARTITION_COLUMNS_MISSING:" + ",".join(missing))
    return pd.read_parquet(path, columns=VALIDATION_COLUMNS), columns


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
        "transformation": "NATIVE_RECORDS_WITH_EXPLICIT_COLUMN_REGISTRY",
        "support_level": "SUPPORTED_PROXY",
        "fallback_level": "NONE",
        "missing_reason": "",
        "future_information_used": False,
    }


def write_observation_dataset(
    root: Path,
    requests: pd.DataFrame,
    store: StateStore,
    metar: pd.DataFrame,
    inventory: pd.DataFrame,
    progress_level: str = "normal",
) -> ObservationDatasetResult:
    root.mkdir(parents=True, exist_ok=True)
    if requests.empty:
        empty_validation = {"status": "FAIL", "observation_rows": 0}
        return ObservationDatasetResult({}, {}, object_hash([]), empty_validation, [])
    start = requests["request_start"].min().normalize()
    end = requests["request_end"].max().normalize()
    row_counts = {"state": 0, "weather": 0, "flow": 0}
    partition_counts = {"state": 0, "weather": 0, "flow": 0}
    partition_hashes: dict[str, str] = {}
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
            clipped = _clip_requests(requests, source, day_start, day_end)
            if clipped.empty:
                continue
            path = root / f"source={source}" / f"observation_date={date_text}" / "part-00000.parquet"
            reused = path.exists()
            if reused:
                frame, partition_columns = _read_validation_projection(path)
            else:
                frame = builder(clipped)
                partition_columns = list(frame.columns)
            if frame.empty:
                continue
            frame = _align(frame).sort_values("observation_id", kind="mergesort")
            for column in [
                "observation_time",
                "event_time",
                "availability_time",
                "request_start",
                "request_end",
            ]:
                frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
            validation = validate_observations(frame)
            for key, value in validation.items():
                if (
                    isinstance(value, int)
                    and not isinstance(value, bool)
                    and key not in {"observation_rows"}
                ):
                    issues[key] = issues.get(key, 0) + value
            if not reused:
                write_parquet(frame, path)
            digest = sha256_file(path)
            key = f"source={source}/observation_date={date_text}"
            partition_hashes[key] = digest
            row_counts[source] += len(frame)
            partition_counts[source] += 1
            evidence_rows.append(
                _evidence_row(frame, source, date_text, digest, partition_columns)
            )
            stage_message(
                f"Core observations: source={source}; date={date_text}; rows={len(frame):,}; "
                f"cache={'HIT' if reused else 'MISS'}",
                level=progress_level,
            )
    total = sum(row_counts.values())
    status = "PASS" if total > 0 and not any(issues.values()) else "FAIL"
    validation = {
        "status": status,
        "observation_rows": total,
        "rows_by_source": row_counts,
        "partition_counts": partition_counts,
        **issues,
        "ratio_dependency_columns": [],
        "native_resolution_preserved": True,
        "on_demand_evidence_supported": status == "PASS",
    }
    return ObservationDatasetResult(
        row_counts=row_counts,
        partition_counts=partition_counts,
        content_hash=object_hash(partition_hashes),
        validation=validation,
        evidence_rows=evidence_rows,
    )
