from __future__ import annotations

import json
import math
import os
import re
import shutil
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from .fill import apply_fill
from .input import discover_files, iter_csv_tar, mapped, normalize_icao24, object_hash, require_parquet_engine, sha256_file
from .progress import progress_bar, stage_message


STATE_NAME = re.compile(r"states_(\d{4}-\d{2}-\d{2})-(\d{2})\.csv\.tar$")
STATE_COLUMNS = [
    "event_time", "availability_time", "icao24", "latitude", "longitude", "altitude",
    "velocity", "vertical_rate", "heading", "onground", "state_is_imputed",
    "state_imputation_method", "state_imputation_gap_minutes", "raw_source_file",
    "raw_source_hash", "source_record_id", "source_date", "source_hour",
    "source_coverage_status",
]
FLOW_COLUMNS = ["airport", "event_time", "availability_time", "icao24"]
CACHE_FORMAT_VERSION = "state-flow-v3"
# The previous hash differs only because cache invalidation policy was moved
# from destructive replacement to isolated variants; row extraction is byte-for-
#-byte unchanged.  Record the one-time compatibility migration explicitly.
COMPATIBLE_EXTRACTION_CODE_HASHES = {
    "017518cc95259b0e21a696c61e588d1f3294531d62bd92f6e83ad943dafac097",
    # Sequential implementation preceding bounded archive-level concurrency.
    # Partition contents and cache format are unchanged.
    "daaae65367f30e2bf81cb03f5cb0fb79f3e13183d0b78c9972670c5354f9a41f",
    # Dataset-object reuse changes only cache read orchestration.
    "b04c790cb0911cf1721491b1ea7936bade65c481a447f978f4f788ef6f3c1758",
}


@lru_cache(maxsize=2)
def _parquet_dataset(root: str):
    import pyarrow.dataset as ds

    return ds.dataset(root, format="parquet", partitioning="hive")


@dataclass(frozen=True)
class StateStore:
    candidate_root: Path
    flow_root: Path
    coverage: pd.DataFrame

    def load(
        self,
        kind: str,
        date: pd.Timestamp,
        *,
        hours: list[int] | None = None,
        airport: str | None = None,
        columns: list[str] | None = None,
    ) -> pd.DataFrame:
        """Read only requested hive partitions and columns from the reusable cache."""
        root = self.candidate_root if kind == "candidate" else self.flow_root
        if not root.exists():
            return pd.DataFrame(columns=columns or (STATE_COLUMNS if kind == "candidate" else FLOW_COLUMNS))
        require_parquet_engine()
        date_value = pd.Timestamp(date).strftime("%Y-%m-%d")
        import pyarrow.dataset as ds

        expr = ds.field("date") == date_value
        if hours:
            expr = expr & ds.field("hour").isin([int(x) for x in hours])
        if airport is not None and kind == "flow":
            expr = expr & (ds.field("airport") == str(airport))
        try:
            dataset = _parquet_dataset(str(root.resolve()))
            table = dataset.to_table(filter=expr, columns=columns)
            return table.to_pandas()
        except (FileNotFoundError, OSError):
            return pd.DataFrame(columns=columns or (STATE_COLUMNS if kind == "candidate" else FLOW_COLUMNS))


def _file_date_hour(path: Path) -> tuple[pd.Timestamp, int]:
    match = STATE_NAME.match(path.name)
    if not match:
        raise ValueError(f"unexpected state-vector filename: {path.name}")
    return pd.Timestamp(match.group(1)).normalize(), int(match.group(2))


def _standardize_chunk(raw: pd.DataFrame, spec: dict[str, Any], path: Path, file_hash: str, date: pd.Timestamp, hour: int, coverage_status: str, cfg: dict[str, Any], row_offset: int) -> pd.DataFrame:
    frame = mapped(raw, spec["columns"], ["time", "icao24", "latitude", "longitude"])
    frame["icao24"] = frame["icao24"].map(normalize_icao24)
    numeric_time = pd.to_numeric(frame["time"], errors="coerce")
    frame["event_time"] = pd.to_datetime(numeric_time, unit="s", utc=True, errors="coerce").where(numeric_time.notna(), pd.to_datetime(frame["time"], utc=True, errors="coerce"))
    frame["availability_time"] = frame["event_time"] + pd.to_timedelta(cfg["availability_lag_minutes"].get("state_vector", 0), unit="m")
    for column in ["latitude", "longitude", "altitude", "velocity", "vertical_rate", "heading"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["onground"] = frame["onground"].astype("boolean")
    units = spec.get("input_units", {})
    if units.get("altitude") == "feet": frame["altitude"] *= 0.3048
    if units.get("vertical_rate") == "feet_per_minute": frame["vertical_rate"] *= 0.3048 / 60.0
    frame["raw_source_file"] = str(path)
    frame["raw_source_hash"] = file_hash
    frame["source_record_id"] = [f"{path.name}:{row_offset + i}" for i in range(len(frame))]
    frame["source_date"], frame["source_hour"], frame["source_coverage_status"] = date, hour, coverage_status
    return apply_fill(frame, cfg)[STATE_COLUMNS]


def _haversine(lat: pd.Series, lon: pd.Series, lat0: float, lon0: float) -> np.ndarray:
    lat1, lon1 = np.radians(pd.to_numeric(lat, errors="coerce")), np.radians(pd.to_numeric(lon, errors="coerce"))
    dlat, dlon = lat1 - math.radians(lat0), lon1 - math.radians(lon0)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * math.cos(math.radians(lat0)) * np.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def _flow_rows(frame: pd.DataFrame, airports: pd.DataFrame, radius: float) -> pd.DataFrame:
    """Map each state once to each nearby core airport while streaming raw chunks."""
    pieces: list[pd.DataFrame] = []
    for ap in airports.itertuples(index=False):
        if pd.isna(ap.airport_latitude) or pd.isna(ap.airport_longitude):
            continue
        lat_delta = radius / 111.0
        lon_delta = radius / max(20.0, 111.0 * math.cos(math.radians(float(ap.airport_latitude))))
        bbox = frame[
            frame["latitude"].between(float(ap.airport_latitude) - lat_delta, float(ap.airport_latitude) + lat_delta)
            & frame["longitude"].between(float(ap.airport_longitude) - lon_delta, float(ap.airport_longitude) + lon_delta)
        ]
        if bbox.empty:
            continue
        near = bbox[_haversine(bbox["latitude"], bbox["longitude"], float(ap.airport_latitude), float(ap.airport_longitude)) <= radius]
        if not near.empty:
            piece = near[["event_time", "availability_time", "icao24"]].copy()
            piece.insert(0, "airport", str(ap.airport))
            pieces.append(piece)
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(columns=FLOW_COLUMNS)


def _requested_candidate(frame: pd.DataFrame, intervals: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]) -> pd.DataFrame:
    if frame.empty or not intervals:
        return frame.iloc[0:0].copy()
    pieces = []
    for code, group in frame[frame["icao24"].isin(intervals)].groupby("icao24", sort=False):
        mask = np.zeros(len(group), dtype=bool)
        times = group["event_time"]
        for start, end in intervals[str(code)]:
            mask |= (times >= start).to_numpy() & (times <= end).to_numpy()
        if mask.any(): pieces.append(group.loc[mask])
    return pd.concat(pieces, ignore_index=False) if pieces else frame.iloc[0:0].copy()


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    if path.exists(): return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temp, index=False, compression="zstd")
    os.replace(temp, path)


def _merge_intervals(requests: pd.DataFrame) -> dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]:
    intervals: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for code, group in requests.groupby("icao24", sort=False):
        merged: list[tuple[pd.Timestamp, pd.Timestamp]] = []
        for row in group.sort_values("request_start").itertuples(index=False):
            start, end = pd.Timestamp(row.request_start), pd.Timestamp(row.request_end)
            if merged and start <= merged[-1][1]: merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else: merged.append((start, end))
        intervals[str(code)] = merged
    return intervals


def _cache_key(cfg: dict[str, Any], requests: pd.DataFrame, airports: pd.DataFrame) -> str:
    raw = cfg.get("raw_hashes", {})
    payload = {
        "format": CACHE_FORMAT_VERSION, "raw_hashes": raw,
        "complete_dates": sorted({
            str(value.date()) for value in pd.concat([
                pd.to_datetime(requests["request_start"]).dt.normalize(),
                pd.to_datetime(requests["request_end"]).dt.normalize(),
            ]).dropna().unique()
        }),
        "core_airports": sorted(cfg["airports"]["core"]),
        "airport_coordinates": airports[["airport", "airport_latitude", "airport_longitude"]].fillna("").to_dict("records"),
        "snapshot_request_hash": object_hash(requests[["icao24", "request_start", "request_end"]].astype(str).to_dict("records")),
        "state_lookback": cfg["state_vectors"]["lookback_minutes"], "flow_lookback": cfg["flow"]["lookback_minutes"],
        "flow_radius": cfg["flow"]["airport_radius_km"], "dedup_key": cfg["flow"]["dedup_key"],
        "extraction_code_hash": sha256_file(Path(__file__)),
    }
    return object_hash(payload)


def extract_state_data(cfg: dict[str, Any], requests: pd.DataFrame, airports: pd.DataFrame, coverage: pd.DataFrame, cache_root: Path) -> tuple[StateStore, pd.DataFrame, dict[str, Any]]:
    """Build/reuse atomic date-hour state and airport-flow cache partitions.

    Candidate retention is constrained to snapshot lookback requests; flow records are
    spatially mapped once during streaming and never distance-filtered downstream.
    """
    spec, files = cfg["sources"]["state_vectors"], discover_files(cfg["project_root"], cfg["data_root"], cfg["sources"]["state_vectors"])
    requests = requests.copy()
    requests["date"] = pd.to_datetime(requests["date"]).dt.normalize()
    # Airport-flow pressure is only needed at snapshot dates.  Do not stream
    # otherwise complete archives merely because they happen to be discoverable.
    # Archive filenames identify UTC calendar dates without a timezone, while
    # snapshot requests are UTC-aware.  Normalize both sides to timezone-naive
    # UTC midnights before comparing them; otherwise no archive date can match
    # a requested date and every file is silently filtered out.
    requested_dates = set(pd.concat([
        pd.to_datetime(requests["request_start"], utc=True).dt.normalize().dt.tz_localize(None),
        pd.to_datetime(requests["request_end"], utc=True).dt.normalize().dt.tz_localize(None),
    ]).dropna())
    files = [path for path in files if _file_date_hour(path)[0] in requested_dates]
    key = _cache_key(cfg, requests, airports)
    manifest_path = cache_root / "cache_manifest.json"
    old = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    if old.get("cache_key") != key:
        # Never erase a valid multi-hour cache merely because a requested cohort
        # is a subset.  The cached candidate table is a safe superset and the
        # downstream lookup still filters by aircraft and decision-time window.
        previous_inputs = old.get("cache_inputs", {})
        compatible_subset = (
            old.get("format") == CACHE_FORMAT_VERSION
            and previous_inputs.get("extraction_code_hash") in (COMPATIBLE_EXTRACTION_CODE_HASHES | {sha256_file(Path(__file__))})
            and float(previous_inputs.get("state_lookback_minutes", -1)) == float(cfg["state_vectors"]["lookback_minutes"])
            and float(previous_inputs.get("flow_lookback_minutes", -1)) == float(cfg["flow"]["lookback_minutes"])
            and float(previous_inputs.get("flow_radius_km", -1)) == float(cfg["flow"]["airport_radius_km"])
            and previous_inputs.get("dedup_key") == cfg["flow"]["dedup_key"]
            and requested_dates.issubset({pd.Timestamp(x) for x in previous_inputs.get("request_dates", [])})
        )
        if not compatible_subset:
            # Isolate incompatible cache variants; preserve every prior cache.
            cache_root = cache_root.parent / f"{cache_root.name}-{key[:12]}"
            manifest_path = cache_root / "cache_manifest.json"
            old = {}
        cache_root.mkdir(parents=True, exist_ok=True)
        old = old or {
            "cache_key": key,
            "format": CACHE_FORMAT_VERSION,
            "partitions": {},
            "cache_inputs": {
                "request_dates": sorted(str(value.date()) for value in requested_dates),
                "state_lookback_minutes": cfg["state_vectors"]["lookback_minutes"],
                "flow_lookback_minutes": cfg["flow"]["lookback_minutes"],
                "flow_radius_km": cfg["flow"]["airport_radius_km"],
                "dedup_key": cfg["flow"]["dedup_key"],
                "extraction_code_hash": sha256_file(Path(__file__)),
            },
        }
        old["active_cache_key"] = key
        old["compatible_subset_reuse"] = bool(compatible_subset)
    candidate_root, flow_root = cache_root / "candidate_states", cache_root / "flow_states"
    intervals = _merge_intervals(requests)
    complete_dates = set(pd.to_datetime(coverage.loc[coverage["formal_eligible"], "date"]).dt.normalize())
    coverage_lookup = coverage.set_index(["date", "hour"])["coverage_status"].to_dict() if not coverage.empty else {}
    core = airports[airports["airport"].isin(cfg["airports"]["core"])].copy()
    # Worker threads only need the immutable cache state that existed at the
    # beginning of this invocation.  The main thread remains the sole writer
    # of the live manifest, avoiding concurrent reads from a mutating dict.
    frozen_partitions = dict(old.get("partitions", {}))
    rows: list[dict[str, Any]] = []
    bar = progress_bar(total=len(files), description="State/flow cache", unit="archives", level=cfg["runtime"]["progress_level"])
    started = time.monotonic()
    def process_archive(path: Path) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
        date, hour = _file_date_hour(path)
        part_key = f"{date:%Y-%m-%d}/{hour:02d}"
        candidate_path = candidate_root / f"date={date:%Y-%m-%d}" / f"hour={hour:02d}" / "part.parquet"
        flow_paths = [flow_root / f"date={date:%Y-%m-%d}" / f"airport={a}" / f"hour={hour:02d}" / "part.parquet" for a in core["airport"].astype(str)]
        cached_partition = frozen_partitions.get(part_key, {})
        can_reuse = cached_partition.get("status") == "COMPLETE" and candidate_path.exists() and all(p.exists() for p in flow_paths)
        if can_reuse:
            # A cache hit means zero rows were re-read in this invocation; it
            # does not mean the source archive was empty.  Preserve the
            # partition's recorded source/support counts so downstream
            # coverage reconciliation cannot turn valid cached hours into
            # SOURCE_COVERAGE_GAP records.
            return ({
                "date": date,
                "hour": hour,
                "raw_file": str(path),
                "raw_rows": int(cached_partition.get("raw_rows", 0)),
                "candidate_rows": int(cached_partition.get("candidate_rows", 0)),
                "flow_rows": int(cached_partition.get("flow_rows", 0)),
                "time_min": pd.NaT,
                "time_max": pd.NaT,
                "cache_status": "HIT",
            }, part_key, None)
        if date not in complete_dates:
            return ({"date": date, "hour": hour, "raw_file": str(path), "raw_rows": 0, "candidate_rows": 0, "flow_rows": 0, "time_min": pd.NaT, "time_max": pd.NaT, "cache_status": "SKIP_INCOMPLETE"}, part_key, None)
        total = candidate_n = flow_n = offset = 0
        candidates: list[pd.DataFrame] = []; flows: list[pd.DataFrame] = []
        status = coverage_lookup.get((date, hour), "SOURCE_COVERAGE_GAP")
        for raw in iter_csv_tar(path, chunksize=int(cfg["state_vectors"].get("chunk_rows", 250_000))):
            standardized = _standardize_chunk(raw, spec, path, cfg.get("raw_hashes", {}).get(str(path.resolve()), ""), date, hour, status, cfg, offset)
            offset += len(raw); total += len(standardized)
            candidate = _requested_candidate(standardized, intervals)
            flow = _flow_rows(standardized, core, float(cfg["flow"]["airport_radius_km"]))
            if not candidate.empty: candidates.append(candidate); candidate_n += len(candidate)
            if not flow.empty: flows.append(flow); flow_n += len(flow)
        candidate_frame = pd.concat(candidates, ignore_index=True).drop_duplicates(["icao24", "event_time"], keep="last") if candidates else pd.DataFrame(columns=STATE_COLUMNS)
        flow_frame = pd.concat(flows, ignore_index=True).drop_duplicates(["airport", "icao24", "event_time"], keep="last") if flows else pd.DataFrame(columns=FLOW_COLUMNS)
        _atomic_parquet(candidate_frame, candidate_path)
        for airport, group in flow_frame.groupby("airport", sort=False):
            _atomic_parquet(group[FLOW_COLUMNS], flow_root / f"date={date:%Y-%m-%d}" / f"airport={airport}" / f"hour={hour:02d}" / "part.parquet")
        # Empty airport partitions are represented by an empty file so resume checks are exact.
        for ap_path in flow_paths:
            _atomic_parquet(pd.DataFrame(columns=FLOW_COLUMNS), ap_path)
        metadata = {"status": "COMPLETE", "raw_rows": total, "candidate_rows": len(candidate_frame), "flow_rows": len(flow_frame)}
        return ({
            "date": date, "hour": hour, "raw_file": str(path), "raw_rows": total,
            "candidate_rows": len(candidate_frame), "flow_rows": len(flow_frame),
            "time_min": candidate_frame["event_time"].min() if not candidate_frame.empty else pd.NaT,
            "time_max": candidate_frame["event_time"].max() if not candidate_frame.empty else pd.NaT,
            "cache_status": "MISS",
        }, part_key, metadata)

    workers = max(1, int(cfg.get("runtime", {}).get("state_workers", 1)))
    # Do not send cache hits through loky: serializing the large request
    # interval index for hundreds of no-op tasks makes a near-complete resume
    # slower and more memory hungry than the actual remaining extraction.
    immediate_results: dict[Path, tuple[dict[str, Any], str, dict[str, Any] | None]] = {}
    work_files: list[Path] = []
    for path in files:
        date, hour = _file_date_hour(path)
        part_key = f"{date:%Y-%m-%d}/{hour:02d}"
        candidate_path = candidate_root / f"date={date:%Y-%m-%d}" / f"hour={hour:02d}" / "part.parquet"
        flow_paths = [flow_root / f"date={date:%Y-%m-%d}" / f"airport={a}" / f"hour={hour:02d}" / "part.parquet" for a in core["airport"].astype(str)]
        cached_partition = frozen_partitions.get(part_key, {})
        is_hit = cached_partition.get("status") == "COMPLETE" and candidate_path.exists() and all(p.exists() for p in flow_paths)
        if is_hit or date not in complete_dates:
            immediate_results[path] = process_archive(path)
        else:
            work_files.append(path)
    if workers > 1 and work_files:
        # Parsing and spatial filtering are CPU-heavy.  A bounded process pool
        # gives real parallelism; the parent remains the only manifest writer.
        parallel_iterator = Parallel(
            n_jobs=workers,
            backend="loky",
            batch_size=1,
            pre_dispatch=workers,
            return_as="generator",
        )(delayed(process_archive)(path) for path in work_files)
    else:
        parallel_iterator = iter(process_archive(path) for path in work_files)
    def ordered_results():
        for path in files:
            yield immediate_results[path] if path in immediate_results else next(parallel_iterator)
    result_iterator = ordered_results()
    manifest_changed = False
    for n, (row, part_key, metadata) in enumerate(result_iterator, start=1):
        rows.append(row)
        if metadata is not None:
            manifest_changed = True
            old.setdefault("partitions", {})[part_key] = metadata
            manifest_temp = manifest_path.with_suffix(".json.tmp")
            manifest_temp.write_text(json.dumps(old, indent=2, default=str), encoding="utf-8")
            os.replace(manifest_temp, manifest_path)
        candidate_n = int(row["candidate_rows"]); flow_n = int(row["flow_rows"])
        elapsed, remaining = time.monotonic() - started, max(len(files) - n, 0) * (time.monotonic() - started) / max(n, 1)
        if metadata is not None:
            stage_message(f"[2.5] State/flow cache {n}/{len(files)}; candidate={candidate_n:,}; flow={flow_n:,}; workers={workers}; elapsed={elapsed/60:.1f}m; ETA={remaining/60:.1f}m", level=cfg["runtime"]["progress_level"])
        bar.update(1)
    bar.close()
    if manifest_changed:
        old.update({"cache_key": key, "format": CACHE_FORMAT_VERSION, "completed_at": pd.Timestamp.now(tz="UTC")})
        manifest_path.write_text(json.dumps(old, indent=2, default=str), encoding="utf-8")
    return StateStore(candidate_root, flow_root, coverage), pd.DataFrame(rows), old
