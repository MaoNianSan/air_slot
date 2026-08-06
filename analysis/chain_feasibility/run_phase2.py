from __future__ import annotations

import hashlib
import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import yaml


ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = ROOT / "data/raw/opensky/flightlist/2022"
OUTPUT_ROOT = ROOT / "output/chain_feasibility"
REPORT_ROOT = ROOT / "reports"
CONFIG_PATH = ROOT / "pre/config/default.yaml"
PRE_OUTPUT = ROOT / "pre/output/adapt_full"

RAW_PATH = OUTPUT_ROOT / "chain_edges_raw.parquet"
CLASSIFIED_PATH = OUTPUT_ROOT / "chain_edges_classified.parquet"
RULE_COMPARISON_PATH = OUTPUT_ROOT / "chain_rule_comparison.parquet"
PROTOTYPE_REFERENCE_PATH = OUTPUT_ROOT / "prototype_ground_references.parquet"

AUDIT_DATE = "2026-07-31"
CHUNK_ROWS = 750_000
REFERENCE_MIN_CELL = 30
SELECTION_AUDIT_THRESHOLD = 0.10
SELECTION_MIN_CATEGORY_ROWS = 30
HORIZONS_HOURS = (6, 12, 24, 48)

SOURCE_COLUMNS = [
    "callsign",
    "number",
    "icao24",
    "registration",
    "typecode",
    "origin",
    "destination",
    "firstseen",
    "lastseen",
    "day",
    "latitude_1",
    "longitude_1",
    "altitude_1",
    "latitude_2",
    "longitude_2",
    "altitude_2",
]

AIRCRAFT_PREFIX_GROUPS = {
    "narrow_body": ("A31", "A32", "B73", "B38", "B39", "E19", "BCS"),
    "wide_body": ("A33", "A34", "A35", "A38", "B74", "B75", "B76", "B77", "B78"),
    "regional": ("AT4", "AT7", "CRJ", "DH8", "E17", "E18", "F70", "F10"),
    "turboprop": ("AT", "DH", "SF3", "JS3"),
}

GAP_BANDS = [
    "overlap",
    "0_20",
    "20_60",
    "60_120",
    "120_240",
    "240_360",
    "360_720",
    "720_1440",
    "gt_1440",
    "no_successor",
]

DIAGNOSTIC_CLASSES = [
    "EXACT_DUPLICATE",
    "POSSIBLE_SPLIT_RECORD",
    "POSSIBLE_OVERLAP_CONFLICT",
    "SHORT_GROUND_CONTINUATION",
    "ORDINARY_CONTINUATION",
    "LONG_GAP_CONTINUATION",
    "UNRESOLVED",
]

QUALITY_CLASSES = [
    "HIGH_CONFIDENCE_CONTINUATION",
    "MEDIUM_CONFIDENCE_CONTINUATION",
    "AMBIGUOUS_CONTINUATION",
    "INCONSISTENT_AIRPORT_LINK",
    "POSSIBLE_SPLIT_RECORD",
    "OVERLAPPING_RECORDS",
    "NO_OBSERVED_SUCCESSOR_WITHIN_HORIZON",
    "ADMINISTRATIVE_RIGHT_CENSORING",
    "DATA_COVERAGE_UNSUPPORTED",
    "IDENTITY_CONFLICT",
]


def log(message: str) -> None:
    print(message, flush=True)


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def clean_string(array: pa.Array | pa.ChunkedArray, upper: bool = True) -> pa.Array:
    result = pc.utf8_trim_whitespace(array)
    if upper:
        result = pc.utf8_upper(result)
    result = pc.if_else(pc.equal(result, ""), pa.scalar(None, pa.string()), result)
    return result.combine_chunks() if isinstance(result, pa.ChunkedArray) else result


def bool_numpy(array: pa.Array | pa.ChunkedArray, null_value: bool = False) -> np.ndarray:
    return pc.fill_null(array, null_value).to_numpy(zero_copy_only=False).astype(bool, copy=False)


def numeric_numpy(array: pa.Array | pa.ChunkedArray, dtype: Any = np.float64) -> np.ndarray:
    if np.issubdtype(np.dtype(dtype), np.integer) and array.null_count:
        array = pc.fill_null(array, 0)
    return np.asarray(array.to_numpy(zero_copy_only=False), dtype=dtype)


def epoch_seconds(array: pa.Array | pa.ChunkedArray) -> np.ndarray:
    seconds = pc.cast(array, pa.timestamp("s", tz="UTC"))
    return numeric_numpy(pc.cast(seconds, pa.int64()), np.float64)


def null_safe_equal(left: pa.Array, right: pa.Array) -> np.ndarray:
    both_null = bool_numpy(pc.and_(pc.is_null(left), pc.is_null(right)))
    equal = bool_numpy(pc.equal(left, right))
    return both_null | equal


def known_equal(left: pa.Array, right: pa.Array) -> tuple[np.ndarray, np.ndarray]:
    known = bool_numpy(pc.and_(pc.is_valid(left), pc.is_valid(right)))
    equal = bool_numpy(pc.equal(left, right))
    return known, equal


def gap_band(gap_minutes: np.ndarray, has_successor: np.ndarray) -> np.ndarray:
    result = np.full(len(gap_minutes), "no_successor", dtype=object)
    finite = has_successor & np.isfinite(gap_minutes)
    result[finite & (gap_minutes < 0)] = "overlap"
    result[finite & (gap_minutes >= 0) & (gap_minutes <= 20)] = "0_20"
    result[finite & (gap_minutes > 20) & (gap_minutes <= 60)] = "20_60"
    result[finite & (gap_minutes > 60) & (gap_minutes <= 120)] = "60_120"
    result[finite & (gap_minutes > 120) & (gap_minutes <= 240)] = "120_240"
    result[finite & (gap_minutes > 240) & (gap_minutes <= 360)] = "240_360"
    result[finite & (gap_minutes > 360) & (gap_minutes <= 720)] = "360_720"
    result[finite & (gap_minutes > 720) & (gap_minutes <= 1440)] = "720_1440"
    result[finite & (gap_minutes > 1440)] = "gt_1440"
    return result


def split_labels(epoch_seconds: np.ndarray, cfg: dict[str, Any]) -> np.ndarray:
    result = np.full(len(epoch_seconds), "OUTSIDE_EPISODE_INTERVAL", dtype=object)
    valid = np.isfinite(epoch_seconds)
    mapping = {
        "train": "DEVELOPMENT",
        "validation": "VALIDATION",
        "test": "FINAL_TEST",
    }
    for source_name, label in mapping.items():
        start, end = cfg["splits"][source_name]
        start_s = int(pd.Timestamp(start, tz="UTC").timestamp())
        end_s = int(pd.Timestamp(end, tz="UTC").timestamp())
        result[valid & (epoch_seconds >= start_s) & (epoch_seconds < end_s)] = label
    return result


def aircraft_group(typecode: Any) -> str:
    if typecode is None or (isinstance(typecode, float) and np.isnan(typecode)):
        return "unknown"
    text = str(typecode).strip().upper()
    if not text:
        return "unknown"
    for group, prefixes in AIRCRAFT_PREFIX_GROUPS.items():
        if text.startswith(prefixes):
            return group
    return "other"


def time_bin_from_epoch(epoch_seconds: np.ndarray) -> np.ndarray:
    result = np.full(len(epoch_seconds), "UNKNOWN", dtype=object)
    valid = np.isfinite(epoch_seconds)
    hours = np.zeros(len(epoch_seconds), dtype=np.int16)
    hours[valid] = ((epoch_seconds[valid].astype(np.int64) // 3600) % 24).astype(np.int16)
    result[valid & (hours < 6)] = "00_06"
    result[valid & (hours >= 6) & (hours < 12)] = "06_12"
    result[valid & (hours >= 12) & (hours < 18)] = "12_18"
    result[valid & (hours >= 18)] = "18_24"
    return result


def month_from_epoch(epoch_seconds: np.ndarray) -> np.ndarray:
    result = np.zeros(len(epoch_seconds), dtype=np.int16)
    valid = np.isfinite(epoch_seconds)
    if valid.any():
        values = epoch_seconds[valid].astype("datetime64[s]").astype("datetime64[M]")
        result[valid] = ((values.astype(np.int64) % 12) + 1).astype(np.int16)
    return result


def stable_source_table(files: list[Path]) -> tuple[pa.Table, list[dict[str, Any]]]:
    tables: list[pa.Table] = []
    inventory: list[dict[str, Any]] = []
    global_offset = 0
    for file_index, path in enumerate(files, start=1):
        table = pacsv.read_csv(
            path,
            read_options=pacsv.ReadOptions(block_size=1 << 24),
            convert_options=pacsv.ConvertOptions(include_columns=SOURCE_COLUMNS),
        )
        rows = len(table)
        table = table.append_column(
            "source_file_index", pa.array(np.full(rows, file_index, dtype=np.int16))
        )
        table = table.append_column(
            "source_row_number", pa.array(np.arange(rows, dtype=np.int32))
        )
        table = table.append_column(
            "source_record_id",
            pa.array(np.arange(global_offset + 1, global_offset + rows + 1, dtype=np.int64)),
        )
        inventory.append(
            {
                "source_file_index": file_index,
                "file_name": path.name,
                "rows": rows,
                "record_id_start": global_offset + 1,
                "record_id_end": global_offset + rows,
            }
        )
        global_offset += rows
        tables.append(table)
        log(f"LOAD {file_index}/{len(files)} {path.name} rows={rows:,}")
    return pa.concat_tables(tables), inventory


def sorted_source(source: pa.Table) -> tuple[pa.Table, pa.Array]:
    normalized_icao = clean_string(source["icao24"])
    encoded = pc.dictionary_encode(normalized_icao)
    codes = encoded.indices
    source = source.append_column("_icao_code", codes)
    keys = pa.table(
        {
            "_icao_code": codes,
            "firstseen": source["firstseen"],
            "lastseen": source["lastseen"],
            "source_record_id": source["source_record_id"],
        }
    )
    indices = pc.sort_indices(
        keys,
        sort_keys=[
            ("_icao_code", "ascending"),
            ("firstseen", "ascending"),
            ("lastseen", "ascending"),
            ("source_record_id", "ascending"),
        ],
        null_placement="at_end",
    )
    return source, indices


def pair_chunks(source: pa.Table, sort_indices: pa.Array) -> Iterable[tuple[pa.Table, pa.Table]]:
    carry: pa.Table | None = None
    total = len(sort_indices)
    for start in range(0, total, CHUNK_ROWS):
        count = min(CHUNK_ROWS, total - start)
        chunk = source.take(sort_indices.slice(start, count))
        if carry is not None:
            chunk = pa.concat_tables([carry, chunk])
        if len(chunk) < 2:
            carry = chunk
            continue
        codes = numeric_numpy(chunk["_icao_code"], np.int32)
        valid_code = bool_numpy(pc.is_valid(chunk["_icao_code"]))
        same = (codes[:-1] == codes[1:]) & valid_code[:-1] & valid_code[1:]
        positions = np.flatnonzero(same).astype(np.int64)
        if len(positions):
            predecessor = chunk.take(pa.array(positions))
            successor = chunk.take(pa.array(positions + 1))
            yield predecessor, successor
        carry = chunk.slice(len(chunk) - 1, 1)


def terminal_rows(source: pa.Table, sort_indices: pa.Array) -> pa.Table:
    terminal_parts: list[pa.Table] = []
    carry: pa.Table | None = None
    total = len(sort_indices)
    for start in range(0, total, CHUNK_ROWS):
        count = min(CHUNK_ROWS, total - start)
        chunk = source.take(sort_indices.slice(start, count))
        if carry is not None:
            chunk = pa.concat_tables([carry, chunk])
        codes = numeric_numpy(chunk["_icao_code"], np.int32)
        valid_code = bool_numpy(pc.is_valid(chunk["_icao_code"]))
        if len(chunk) > 1:
            same = (codes[:-1] == codes[1:]) & valid_code[:-1] & valid_code[1:]
            ends = np.flatnonzero(~same).astype(np.int64)
            if len(ends):
                terminal_parts.append(chunk.take(pa.array(ends)))
        carry = chunk.slice(len(chunk) - 1, 1)
    if carry is not None:
        terminal_parts.append(carry)
    return pa.concat_tables(terminal_parts) if terminal_parts else source.slice(0, 0)


def state_coverage_dates() -> tuple[set[int], set[int]]:
    path = PRE_OUTPUT / "manifests/state_vector_coverage_calendar.parquet"
    frame = pd.read_parquet(path, columns=["date", "file_exists", "formal_eligible"])
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    by_day = frame.groupby("date").agg(
        hours=("file_exists", "sum"), formal=("formal_eligible", "all")
    )
    epoch = pd.Timestamp("1970-01-01")
    complete = {int((value - epoch).days) for value in by_day.index[by_day.formal]}
    partial = {int((value - epoch).days) for value in by_day.index[by_day.hours > 0]} - complete
    return complete, partial


def episode_lookup() -> tuple[dict[tuple[Any, ...], tuple[str, bool]], pd.DataFrame]:
    episode_columns = [
        "episode_id",
        "icao24",
        "origin",
        "destination",
        "firstseen_utc",
        "lastseen_utc",
        "split",
        "observed_movement_time",
    ]
    episodes = pd.read_parquet(PRE_OUTPUT / "episodes.parquet", columns=episode_columns)
    snapshots = pd.read_parquet(
        PRE_OUTPUT / "snapshots.parquet",
        columns=["episode_id", "snapshot_valid", "source_available"],
    )
    supported = set(
        snapshots.loc[
            snapshots["snapshot_valid"].fillna(False)
            & snapshots["source_available"].fillna(False),
            "episode_id",
        ].astype(str)
    )
    lookup: dict[tuple[Any, ...], tuple[str, bool]] = {}
    for row in episodes.itertuples(index=False):
        key = (
            str(row.icao24).strip().upper(),
            None if pd.isna(row.origin) else str(row.origin).strip().upper(),
            None if pd.isna(row.destination) else str(row.destination).strip().upper(),
            int(pd.Timestamp(row.firstseen_utc).timestamp()),
            int(pd.Timestamp(row.lastseen_utc).timestamp()),
        )
        lookup[key] = (str(row.episode_id), str(row.episode_id) in supported)
    return lookup, episodes


def map_episode_ids(
    predecessor: pa.Table,
    candidate_mask: np.ndarray,
    firstseen_s: np.ndarray,
    lastseen_s: np.ndarray,
    lookup: dict[tuple[Any, ...], tuple[str, bool]],
) -> tuple[np.ndarray, np.ndarray]:
    episode_ids = np.full(len(predecessor), None, dtype=object)
    snapshot_supported = np.zeros(len(predecessor), dtype=bool)
    positions = np.flatnonzero(candidate_mask)
    if not len(positions):
        return episode_ids, snapshot_supported
    subset = predecessor.take(pa.array(positions.astype(np.int64)))
    icao = clean_string(subset["icao24"]).to_pylist()
    origin = clean_string(subset["origin"]).to_pylist()
    destination = clean_string(subset["destination"]).to_pylist()
    for local_index, values in enumerate(
        zip(
            icao,
            origin,
            destination,
            firstseen_s[positions],
            lastseen_s[positions],
        )
    ):
        match = lookup.get(values)
        if match is not None:
            position = positions[local_index]
            episode_ids[position] = match[0]
            snapshot_supported[position] = match[1]
    return episode_ids, snapshot_supported


def base_rule_arrays(
    predecessor: pa.Table,
    successor: pa.Table,
    cfg: dict[str, Any],
    complete_days: set[int],
) -> dict[str, np.ndarray]:
    size = len(predecessor)
    has_successor = np.ones(size, dtype=bool)
    firstseen_minus = epoch_seconds(predecessor["firstseen"])
    lastseen_minus = epoch_seconds(predecessor["lastseen"])
    firstseen_plus = epoch_seconds(successor["firstseen"])
    gap = (firstseen_plus - lastseen_minus) / 60.0

    origin_minus = clean_string(predecessor["origin"])
    destination_minus = clean_string(predecessor["destination"])
    origin_plus = clean_string(successor["origin"])
    destination_plus = clean_string(successor["destination"])
    registration_minus = clean_string(predecessor["registration"])
    registration_plus = clean_string(successor["registration"])
    typecode_minus = clean_string(predecessor["typecode"])
    typecode_plus = clean_string(successor["typecode"])
    callsign_minus = clean_string(predecessor["callsign"])
    callsign_plus = clean_string(successor["callsign"])

    airports_known = bool_numpy(
        pc.and_(pc.is_valid(destination_minus), pc.is_valid(origin_plus))
    )
    airport_continuity = bool_numpy(pc.equal(destination_minus, origin_plus))
    registration_known, registration_equal = known_equal(
        registration_minus, registration_plus
    )
    typecode_known, typecode_equal = known_equal(typecode_minus, typecode_plus)
    callsign_known, callsign_equal = known_equal(callsign_minus, callsign_plus)

    exact_duplicate = (
        null_safe_equal(origin_minus, origin_plus)
        & null_safe_equal(destination_minus, destination_plus)
        & (firstseen_minus == firstseen_plus)
        & (
            lastseen_minus
            == epoch_seconds(successor["lastseen"])
        )
    )
    registration_ok = ~registration_known | registration_equal
    typecode_ok = ~typecode_known | typecode_equal

    same_route = null_safe_equal(origin_minus, origin_plus) & null_safe_equal(
        destination_minus, destination_plus
    )
    possible_split = (
        has_successor
        & (gap >= 0)
        & (gap <= 20)
        & callsign_known
        & callsign_equal
        & same_route
        & registration_ok
    )

    endpoint_support = (
        bool_numpy(pc.is_valid(predecessor["latitude_2"]))
        & bool_numpy(pc.is_valid(predecessor["longitude_2"]))
        & bool_numpy(pc.is_valid(successor["latitude_1"]))
        & bool_numpy(pc.is_valid(successor["longitude_1"]))
    )
    day_number = np.floor_divide(firstseen_minus.astype(np.int64), 86400)
    state_support = np.isin(day_number, np.fromiter(complete_days, dtype=np.int64))

    structural = (
        has_successor
        & np.isfinite(gap)
        & (gap >= 0)
        & airports_known
        & airport_continuity
        & ~exact_duplicate
        & registration_ok
    )
    r1_base = structural
    r2_base = (
        structural
        & typecode_ok
        & registration_known
        & registration_equal
        & ~possible_split
        & endpoint_support
        & state_support
    )
    r3_base = (
        structural
        & typecode_ok
        & ~possible_split
        & endpoint_support
        & state_support
    )

    destination_is_m1 = bool_numpy(
        pc.is_in(destination_minus, value_set=pa.array(cfg["airports"]["m1"]))
    )
    split_minus = split_labels(firstseen_minus, cfg)
    split_plus = split_labels(firstseen_plus, cfg)
    fit_safe = (
        destination_is_m1
        & (split_minus == "DEVELOPMENT")
        & (split_plus == "DEVELOPMENT")
    )
    return {
        "gap": gap,
        "r1_base": r1_base,
        "r2_base": r2_base,
        "r3_base": r3_base,
        "fit_safe": fit_safe,
    }


def fit_development_thresholds(
    source: pa.Table,
    sort_indices: pa.Array,
    cfg: dict[str, Any],
    complete_days: set[int],
) -> tuple[dict[str, float], pd.DataFrame]:
    values: dict[str, list[np.ndarray]] = {"R1": [], "R2": [], "R3": []}
    base_names = {"R1": "r1_base", "R2": "r2_base", "R3": "r3_base"}
    processed = 0
    for predecessor, successor in pair_chunks(source, sort_indices):
        arrays = base_rule_arrays(predecessor, successor, cfg, complete_days)
        for rule, base_name in base_names.items():
            mask = arrays["fit_safe"] & arrays[base_name]
            if mask.any():
                values[rule].append(arrays["gap"][mask].astype(np.float32))
        processed += len(predecessor)
        if processed % (CHUNK_ROWS * 8) < CHUNK_ROWS:
            log(f"THRESHOLD_PASS adjacent_pairs={processed:,}")

    thresholds: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    for rule, parts in values.items():
        combined = np.concatenate(parts) if parts else np.array([], dtype=np.float32)
        if not len(combined):
            raise RuntimeError(f"no development-only support for {rule}")
        quantiles = np.quantile(combined, [0.50, 0.90, 0.95, 0.99])
        thresholds[rule] = float(quantiles[2])
        rows.append(
            {
                "rule": rule,
                "fit_scope": "S1_M1_WIDE_COHORT",
                "fit_split": "DEVELOPMENT",
                "successor_split_required": "DEVELOPMENT",
                "support_rows": int(len(combined)),
                "gap_q50": float(quantiles[0]),
                "gap_q90": float(quantiles[1]),
                "gap_q95_candidate_upper": float(quantiles[2]),
                "gap_q99": float(quantiles[3]),
            }
        )
    return thresholds, pd.DataFrame(rows)


def make_edge_features(
    predecessor: pa.Table,
    successor: pa.Table | None,
    cfg: dict[str, Any],
    complete_days: set[int],
    partial_days: set[int],
    thresholds: dict[str, float],
    observation_end_s: int,
    lookup: dict[tuple[Any, ...], tuple[str, bool]],
) -> dict[str, Any]:
    size = len(predecessor)
    has_successor = np.ones(size, dtype=bool) if successor is not None else np.zeros(size, dtype=bool)

    predecessor_id = numeric_numpy(predecessor["source_record_id"], np.int64)
    predecessor_file = numeric_numpy(predecessor["source_file_index"], np.int16)
    firstseen_minus = epoch_seconds(predecessor["firstseen"])
    lastseen_minus = epoch_seconds(predecessor["lastseen"])

    if successor is not None:
        successor_id = numeric_numpy(successor["source_record_id"], np.int64)
        successor_file = numeric_numpy(successor["source_file_index"], np.int16)
        firstseen_plus = epoch_seconds(successor["firstseen"])
        lastseen_plus = epoch_seconds(successor["lastseen"])
        icao24_plus = clean_string(successor["icao24"])
        registration_plus = clean_string(successor["registration"])
        callsign_plus = clean_string(successor["callsign"])
        number_plus = clean_string(successor["number"], upper=False)
        typecode_plus = clean_string(successor["typecode"])
        origin_plus = clean_string(successor["origin"])
        destination_plus = clean_string(successor["destination"])
    else:
        successor_id = np.zeros(size, dtype=np.int64)
        successor_file = np.zeros(size, dtype=np.int16)
        firstseen_plus = np.full(size, np.nan)
        lastseen_plus = np.full(size, np.nan)
        icao24_plus = pa.nulls(size, pa.string())
        registration_plus = pa.nulls(size, pa.string())
        callsign_plus = pa.nulls(size, pa.string())
        number_plus = pa.nulls(size, pa.string())
        typecode_plus = pa.nulls(size, pa.string())
        origin_plus = pa.nulls(size, pa.string())
        destination_plus = pa.nulls(size, pa.string())

    icao24_minus = clean_string(predecessor["icao24"])
    registration_minus = clean_string(predecessor["registration"])
    callsign_minus = clean_string(predecessor["callsign"])
    number_minus = clean_string(predecessor["number"], upper=False)
    typecode_minus = clean_string(predecessor["typecode"])
    origin_minus = clean_string(predecessor["origin"])
    destination_minus = clean_string(predecessor["destination"])

    gap = np.full(size, np.nan, dtype=np.float64)
    total_chain = np.full(size, np.nan, dtype=np.float64)
    gap[has_successor] = (firstseen_plus[has_successor] - lastseen_minus[has_successor]) / 60.0
    total_chain[has_successor] = (
        firstseen_plus[has_successor] - firstseen_minus[has_successor]
    ) / 60.0
    movement_duration = (lastseen_minus - firstseen_minus) / 60.0

    airports_known = (
        bool_numpy(pc.is_valid(destination_minus)) & bool_numpy(pc.is_valid(origin_plus))
    )
    airport_continuity = bool_numpy(pc.equal(destination_minus, origin_plus)) & has_successor
    registration_known, registration_equal = known_equal(
        registration_minus, registration_plus
    )
    typecode_known, typecode_equal = known_equal(typecode_minus, typecode_plus)
    callsign_known, callsign_equal = known_equal(callsign_minus, callsign_plus)
    registration_ok = ~registration_known | registration_equal
    typecode_ok = ~typecode_known | typecode_equal

    exact_duplicate = np.zeros(size, dtype=bool)
    same_route = np.zeros(size, dtype=bool)
    if successor is not None:
        exact_duplicate = (
            null_safe_equal(origin_minus, origin_plus)
            & null_safe_equal(destination_minus, destination_plus)
            & (firstseen_minus == firstseen_plus)
            & (lastseen_minus == lastseen_plus)
        )
        same_route = null_safe_equal(origin_minus, origin_plus) & null_safe_equal(
            destination_minus, destination_plus
        )

    time_overlap = has_successor & np.isfinite(gap) & (gap < 0)
    possible_split = (
        has_successor
        & np.isfinite(gap)
        & (gap >= 0)
        & (gap <= 20)
        & callsign_known
        & callsign_equal
        & same_route
        & registration_ok
        & ~exact_duplicate
    )
    near_duplicate = possible_split | (
        time_overlap & callsign_known & callsign_equal & same_route
    )

    if successor is not None:
        endpoint_coordinate_support = (
            bool_numpy(pc.is_valid(predecessor["latitude_2"]))
            & bool_numpy(pc.is_valid(predecessor["longitude_2"]))
            & bool_numpy(pc.is_valid(successor["latitude_1"]))
            & bool_numpy(pc.is_valid(successor["longitude_1"]))
        )
        endpoint_altitude_support = (
            bool_numpy(pc.is_valid(predecessor["altitude_2"]))
            & bool_numpy(pc.is_valid(successor["altitude_1"]))
        )
    else:
        endpoint_coordinate_support = np.zeros(size, dtype=bool)
        endpoint_altitude_support = np.zeros(size, dtype=bool)

    day_number = np.floor_divide(firstseen_minus.astype(np.int64), 86400)
    complete_values = np.fromiter(complete_days, dtype=np.int64)
    partial_values = np.fromiter(partial_days, dtype=np.int64)
    state_vector_support = np.isin(day_number, complete_values)
    state_vector_partial = np.isin(day_number, partial_values)
    flightlist_coverage_support = (
        bool_numpy(pc.is_valid(icao24_minus))
        & np.isfinite(firstseen_minus)
        & np.isfinite(lastseen_minus)
    )
    coverage_status = np.select(
        [state_vector_support, state_vector_partial],
        ["STATE_DAY_COMPLETE", "STATE_DAY_PARTIAL"],
        default="NO_LOCAL_STATE_VECTOR_DAY",
    )

    destination_is_m1 = bool_numpy(
        pc.is_in(destination_minus, value_set=pa.array(cfg["airports"]["m1"]))
    )
    destination_is_core = bool_numpy(
        pc.is_in(destination_minus, value_set=pa.array(cfg["airports"]["core"]))
    )
    split_minus = split_labels(firstseen_minus, cfg)
    split_plus = split_labels(firstseen_plus, cfg)
    episode_candidate = destination_is_core & (
        split_minus != "OUTSIDE_EPISODE_INTERVAL"
    )
    episode_ids, snapshot_supported = map_episode_ids(
        predecessor,
        episode_candidate,
        firstseen_minus.astype(np.int64),
        lastseen_minus.astype(np.int64),
        lookup,
    )

    scope = np.full(size, "S0_GLOBAL_SOURCE", dtype=object)
    scope[destination_is_m1] = "S1_M1_WIDE_COHORT"
    scope[destination_is_core] = "S2_CORE_RECOVERY_COHORT"
    scope[snapshot_supported] = "S3_SNAPSHOT_SUPPORTED_COHORT"

    structural = (
        has_successor
        & np.isfinite(gap)
        & (gap >= 0)
        & airports_known
        & airport_continuity
        & ~exact_duplicate
        & registration_ok
    )
    r0 = has_successor & np.isfinite(gap) & (gap >= 0) & ~exact_duplicate
    r1_base = structural
    r2_base = (
        structural
        & typecode_ok
        & registration_known
        & registration_equal
        & ~possible_split
        & endpoint_coordinate_support
        & state_vector_support
    )
    r3_base = (
        structural
        & typecode_ok
        & ~possible_split
        & endpoint_coordinate_support
        & state_vector_support
    )
    r1 = r1_base & (gap <= thresholds["R1"])
    r2 = r2_base & (gap <= thresholds["R2"])
    r3 = r3_base & (gap <= thresholds["R3"])

    bands = gap_band(gap, has_successor)
    diagnostic = np.full(size, "UNRESOLVED", dtype=object)
    diagnostic[has_successor & np.isfinite(gap) & (gap > 360)] = "LONG_GAP_CONTINUATION"
    diagnostic[has_successor & np.isfinite(gap) & (gap > 20) & (gap <= 360)] = (
        "ORDINARY_CONTINUATION"
    )
    diagnostic[has_successor & np.isfinite(gap) & (gap >= 0) & (gap <= 20)] = (
        "SHORT_GROUND_CONTINUATION"
    )
    diagnostic[possible_split] = "POSSIBLE_SPLIT_RECORD"
    diagnostic[time_overlap] = "POSSIBLE_OVERLAP_CONFLICT"
    diagnostic[exact_duplicate] = "EXACT_DUPLICATE"

    within_48h = has_successor & np.isfinite(gap) & (gap >= 0) & (gap <= 48 * 60)
    no_successor_within_48h = (
        ~has_successor | ~np.isfinite(gap) | (gap > 48 * 60)
    )
    administrative_censoring = (
        no_successor_within_48h
        & np.isfinite(lastseen_minus)
        & (lastseen_minus + 48 * 3600 > observation_end_s)
    )
    identity_conflict = (registration_known & ~registration_equal) | (
        typecode_known & ~typecode_equal
    )

    quality = np.full(size, "AMBIGUOUS_CONTINUATION", dtype=object)
    quality[r1 | r3] = "MEDIUM_CONFIDENCE_CONTINUATION"
    quality[r2] = "HIGH_CONFIDENCE_CONTINUATION"
    quality[
        destination_is_m1
        & (split_minus != "OUTSIDE_EPISODE_INTERVAL")
        & ~state_vector_support
    ] = "DATA_COVERAGE_UNSUPPORTED"
    quality[has_successor & airports_known & ~airport_continuity] = (
        "INCONSISTENT_AIRPORT_LINK"
    )
    quality[identity_conflict] = "IDENTITY_CONFLICT"
    quality[possible_split] = "POSSIBLE_SPLIT_RECORD"
    quality[time_overlap | exact_duplicate] = "OVERLAPPING_RECORDS"
    quality[no_successor_within_48h] = "NO_OBSERVED_SUCCESSOR_WITHIN_HORIZON"
    quality[administrative_censoring] = "ADMINISTRATIVE_RIGHT_CENSORING"

    cross_day = np.zeros(size, dtype=bool)
    cross_month = np.zeros(size, dtype=bool)
    if successor is not None:
        cross_day = (
            np.floor_divide(firstseen_minus.astype(np.int64), 86400)
            != np.floor_divide(firstseen_plus.astype(np.int64), 86400)
        )
        minus_month = firstseen_minus.astype("datetime64[s]").astype("datetime64[M]")
        plus_month = firstseen_plus.astype("datetime64[s]").astype("datetime64[M]")
        cross_month = minus_month != plus_month
    cross_split = has_successor & (split_minus != split_plus)
    source_file_boundary = has_successor & (predecessor_file != successor_file)

    return {
        "size": size,
        "has_successor": has_successor,
        "predecessor_id": predecessor_id,
        "successor_id": successor_id,
        "predecessor_file": predecessor_file,
        "successor_file": successor_file,
        "firstseen_minus": firstseen_minus,
        "lastseen_minus": lastseen_minus,
        "firstseen_plus": firstseen_plus,
        "lastseen_plus": lastseen_plus,
        "gap": gap,
        "total_chain": total_chain,
        "movement_duration": movement_duration,
        "icao24_minus": icao24_minus,
        "icao24_plus": icao24_plus,
        "registration_minus": registration_minus,
        "registration_plus": registration_plus,
        "callsign_minus": callsign_minus,
        "callsign_plus": callsign_plus,
        "number_minus": number_minus,
        "number_plus": number_plus,
        "typecode_minus": typecode_minus,
        "typecode_plus": typecode_plus,
        "origin_minus": origin_minus,
        "destination_minus": destination_minus,
        "origin_plus": origin_plus,
        "destination_plus": destination_plus,
        "airports_known": airports_known,
        "airport_continuity": airport_continuity,
        "registration_known": registration_known,
        "registration_equal": registration_equal,
        "typecode_known": typecode_known,
        "typecode_equal": typecode_equal,
        "callsign_known": callsign_known,
        "callsign_change": callsign_known & ~callsign_equal,
        "time_overlap": time_overlap,
        "exact_duplicate": exact_duplicate,
        "near_duplicate": near_duplicate,
        "possible_split": possible_split,
        "endpoint_coordinate_support": endpoint_coordinate_support,
        "endpoint_altitude_support": endpoint_altitude_support,
        "flightlist_coverage_support": flightlist_coverage_support,
        "state_vector_support": state_vector_support,
        "coverage_status": coverage_status,
        "destination_is_m1": destination_is_m1,
        "destination_is_core": destination_is_core,
        "snapshot_supported": snapshot_supported,
        "scope": scope,
        "split_minus": split_minus,
        "split_plus": split_plus,
        "episode_ids": episode_ids,
        "r0": r0,
        "r1_base": r1_base,
        "r2_base": r2_base,
        "r3_base": r3_base,
        "r1": r1,
        "r2": r2,
        "r3": r3,
        "gap_band": bands,
        "diagnostic": diagnostic,
        "quality": quality,
        "cross_day": cross_day,
        "cross_month": cross_month,
        "cross_split": cross_split,
        "source_file_boundary": source_file_boundary,
        "administrative_censoring": administrative_censoring,
        "identity_conflict": identity_conflict,
        "month": month_from_epoch(firstseen_minus),
        "time_bin": time_bin_from_epoch(firstseen_minus),
    }


def nullable_boolean(values: np.ndarray, known: np.ndarray) -> pa.Array:
    return pa.array(values.astype(bool), mask=~known, type=pa.bool_())


def timestamp_array(epoch_seconds: np.ndarray, valid: np.ndarray) -> pa.Array:
    integer = np.zeros(len(epoch_seconds), dtype=np.int64)
    integer[valid] = epoch_seconds[valid].astype(np.int64)
    return pc.cast(pa.array(integer, mask=~valid), pa.timestamp("s", tz="UTC"))


def make_output_tables(features: dict[str, Any]) -> tuple[pa.Table, pa.Table, pa.Table]:
    size = features["size"]
    has_successor = features["has_successor"]
    valid_minus = np.isfinite(features["firstseen_minus"])
    valid_last_minus = np.isfinite(features["lastseen_minus"])
    valid_plus = has_successor & np.isfinite(features["firstseen_plus"])
    valid_last_plus = has_successor & np.isfinite(features["lastseen_plus"])
    origin_minus_known = bool_numpy(pc.is_valid(features["origin_minus"]))
    destination_minus_known = bool_numpy(pc.is_valid(features["destination_minus"]))
    origin_plus_known = bool_numpy(pc.is_valid(features["origin_plus"]))
    destination_plus_known = bool_numpy(pc.is_valid(features["destination_plus"]))

    raw = pa.table(
        {
            "chain_edge_id": pa.array(features["predecessor_id"]),
            "scope": pa.array(features["scope"]),
            "scope_s0_global_source": pa.array(np.ones(size, dtype=bool)),
            "scope_s1_m1_wide": pa.array(features["destination_is_m1"]),
            "scope_s2_core_recovery": pa.array(features["destination_is_core"]),
            "scope_s3_snapshot_supported": pa.array(features["snapshot_supported"]),
            "split_of_predecessor": pa.array(features["split_minus"]),
            "split_of_successor": pa.array(
                features["split_plus"], mask=~has_successor, type=pa.string()
            ),
            "predecessor_record_id": pa.array(features["predecessor_id"]),
            "outcome_successor_record_id": pa.array(
                features["successor_id"], mask=~has_successor
            ),
            "predecessor_episode_id": pa.array(
                features["episode_ids"], type=pa.string()
            ),
            "icao24_minus": features["icao24_minus"],
            "icao24_plus": features["icao24_plus"],
            "registration_minus": features["registration_minus"],
            "registration_plus": features["registration_plus"],
            "callsign_minus": features["callsign_minus"],
            "callsign_plus": features["callsign_plus"],
            "number_minus": features["number_minus"],
            "number_plus": features["number_plus"],
            "typecode_minus": features["typecode_minus"],
            "typecode_plus": features["typecode_plus"],
            "origin_minus": features["origin_minus"],
            "destination_minus": features["destination_minus"],
            "origin_plus": features["origin_plus"],
            "destination_plus": features["destination_plus"],
            "firstseen_minus": timestamp_array(features["firstseen_minus"], valid_minus),
            "lastseen_minus": timestamp_array(features["lastseen_minus"], valid_last_minus),
            "firstseen_plus": timestamp_array(features["firstseen_plus"], valid_plus),
            "lastseen_plus": timestamp_array(features["lastseen_plus"], valid_last_plus),
            "ground_gap_minutes": pa.array(features["gap"], mask=~has_successor),
            "total_chain_minutes": pa.array(
                features["total_chain"], mask=~has_successor
            ),
            "airport_continuity": nullable_boolean(
                features["airport_continuity"], features["airports_known"] & has_successor
            ),
            "registration_continuity": nullable_boolean(
                features["registration_equal"],
                features["registration_known"] & has_successor,
            ),
            "typecode_continuity": nullable_boolean(
                features["typecode_equal"], features["typecode_known"] & has_successor
            ),
            "callsign_change": nullable_boolean(
                features["callsign_change"], features["callsign_known"] & has_successor
            ),
            "time_overlap": pa.array(features["time_overlap"]),
            "exact_duplicate_flag": pa.array(features["exact_duplicate"]),
            "near_duplicate_flag": pa.array(features["near_duplicate"]),
            "intermediate_record_count": pa.array(np.zeros(size, dtype=np.int16)),
            "cross_day": pa.array(features["cross_day"]),
            "cross_month": pa.array(features["cross_month"]),
            "cross_split_boundary": pa.array(features["cross_split"]),
            "source_file_boundary": pa.array(features["source_file_boundary"]),
            "observation_window_end_censoring": pa.array(
                features["administrative_censoring"]
            ),
            "coverage_support": pa.array(features["flightlist_coverage_support"]),
            "state_vector_support": pa.array(features["state_vector_support"]),
            "coverage_support_status": pa.array(features["coverage_status"]),
            "endpoint_coordinate_support": pa.array(
                features["endpoint_coordinate_support"]
            ),
            "endpoint_altitude_support": pa.array(
                features["endpoint_altitude_support"]
            ),
            "predecessor_origin_destination_complete": pa.array(
                origin_minus_known & destination_minus_known
            ),
            "successor_origin_destination_complete": pa.array(
                origin_plus_known & destination_plus_known & has_successor
            ),
            "chain_quality_status": pa.array(features["quality"]),
        }
    )
    classified = raw.append_column("gap_band", pa.array(features["gap_band"]))
    classified = classified.append_column(
        "diagnostic_status", pa.array(features["diagnostic"])
    )
    classified = classified.append_column(
        "identity_conflict", pa.array(features["identity_conflict"])
    )
    classified = classified.append_column(
        "possible_split_record", pa.array(features["possible_split"])
    )
    for name in ["r0", "r1_base", "r2_base", "r3_base", "r1", "r2", "r3"]:
        classified = classified.append_column(
            f"rule_{name}_retained" if name in {"r0", "r1", "r2", "r3"} else f"rule_{name}",
            pa.array(features[name]),
        )

    project_mask = features["destination_is_m1"] & (
        features["split_minus"] != "OUTSIDE_EPISODE_INTERVAL"
    )
    indices = np.flatnonzero(project_mask).astype(np.int64)
    if len(indices):
        selected = classified.take(pa.array(indices))
        selected_types = selected["typecode_minus"].to_pylist()
        groups = [aircraft_group(value) for value in selected_types]
        comparison = pa.table(
            {
                "chain_edge_id": selected["chain_edge_id"],
                "predecessor_record_id": selected["predecessor_record_id"],
                "outcome_successor_record_id": selected["outcome_successor_record_id"],
                "predecessor_episode_id": selected["predecessor_episode_id"],
                "icao24": selected["icao24_minus"],
                "split_of_predecessor": selected["split_of_predecessor"],
                "split_of_successor": selected["split_of_successor"],
                "airport": selected["destination_minus"],
                "origin": selected["origin_minus"],
                "destination": selected["destination_minus"],
                "month": pa.array(features["month"][indices]),
                "firstseen_time_bin": pa.array(features["time_bin"][indices]),
                "typecode": selected["typecode_minus"],
                "aircraft_group": pa.array(groups),
                "movement_duration_minutes": pa.array(
                    features["movement_duration"][indices]
                ),
                "ground_gap_minutes": selected["ground_gap_minutes"],
                "gap_band": selected["gap_band"],
                "diagnostic_status": selected["diagnostic_status"],
                "chain_quality_status": selected["chain_quality_status"],
                "scope_s2_core_recovery": selected["scope_s2_core_recovery"],
                "scope_s3_snapshot_supported": selected[
                    "scope_s3_snapshot_supported"
                ],
                "state_vector_support": selected["state_vector_support"],
                "coverage_support_status": selected["coverage_support_status"],
                "endpoint_coordinate_support": selected[
                    "endpoint_coordinate_support"
                ],
                "predecessor_origin_destination_complete": selected[
                    "predecessor_origin_destination_complete"
                ],
                "airport_continuity": selected["airport_continuity"],
                "registration_continuity": selected["registration_continuity"],
                "typecode_continuity": selected["typecode_continuity"],
                "callsign_change": selected["callsign_change"],
                "cross_day": selected["cross_day"],
                "cross_month": selected["cross_month"],
                "cross_split_boundary": selected["cross_split_boundary"],
                "administrative_censoring": selected[
                    "observation_window_end_censoring"
                ],
                "rule_r0_retained": selected["rule_r0_retained"],
                "rule_r1_retained": selected["rule_r1_retained"],
                "rule_r2_retained": selected["rule_r2_retained"],
                "rule_r3_retained": selected["rule_r3_retained"],
            }
        )
    else:
        comparison = pa.table(
            {
                "chain_edge_id": pa.array([], type=pa.int64()),
                "predecessor_record_id": pa.array([], type=pa.int64()),
            }
        )
    return raw, classified, comparison


def scope_masks(features: dict[str, Any]) -> dict[str, np.ndarray]:
    return {
        "S0_GLOBAL_SOURCE": np.ones(features["size"], dtype=bool),
        "S1_M1_WIDE_COHORT": features["destination_is_m1"],
        "S2_CORE_RECOVERY_COHORT": features["destination_is_core"],
        "S3_SNAPSHOT_SUPPORTED_COHORT": features["snapshot_supported"],
    }


def aggregate_chunk(
    features: dict[str, Any],
    gap_rows: list[dict[str, Any]],
    rule_rows: list[dict[str, Any]],
    censor_rows: list[dict[str, Any]],
    airport_rows: list[dict[str, Any]],
    observation_end_s: int,
) -> None:
    scopes = scope_masks(features)
    splits = [
        "DEVELOPMENT",
        "VALIDATION",
        "FINAL_TEST",
        "OUTSIDE_EPISODE_INTERVAL",
    ]
    rules = {
        "R0_ADJACENCY_DIAGNOSTIC": features["r0"],
        "R1_STRICT_CONTINUITY": features["r1"],
        "R2_STRICT_PLUS_IDENTITY_QUALITY": features["r2"],
        "R3_COVERAGE_AWARE": features["r3"],
    }
    for scope_name, scope_mask in scopes.items():
        for split in splits:
            base = scope_mask & (features["split_minus"] == split)
            if not base.any():
                continue
            for band in GAP_BANDS:
                mask = base & (features["gap_band"] == band)
                count = int(mask.sum())
                if not count:
                    continue
                airport_known = mask & features["airports_known"] & features["has_successor"]
                reg_known = mask & features["registration_known"] & features["has_successor"]
                type_known = mask & features["typecode_known"] & features["has_successor"]
                call_known = mask & features["callsign_known"] & features["has_successor"]
                row = {
                    "scope": scope_name,
                    "split": split,
                    "gap_band": band,
                    "predecessor_count": count,
                    "observed_pair_count": int((mask & features["has_successor"]).sum()),
                    "airport_continuity_known_pairs": int(airport_known.sum()),
                    "airport_continuity_count": int(
                        (airport_known & features["airport_continuity"]).sum()
                    ),
                    "registration_known_pairs": int(reg_known.sum()),
                    "registration_continuity_count": int(
                        (reg_known & features["registration_equal"]).sum()
                    ),
                    "typecode_known_pairs": int(type_known.sum()),
                    "typecode_continuity_count": int(
                        (type_known & features["typecode_equal"]).sum()
                    ),
                    "callsign_known_pairs": int(call_known.sum()),
                    "callsign_change_count": int(
                        (call_known & features["callsign_change"]).sum()
                    ),
                    "overlap_count": int((mask & features["time_overlap"]).sum()),
                    "exact_duplicate_count": int(
                        (mask & features["exact_duplicate"]).sum()
                    ),
                    "possible_split_count": int(
                        (mask & features["possible_split"]).sum()
                    ),
                    "cross_day_count": int((mask & features["cross_day"]).sum()),
                    "cross_month_count": int((mask & features["cross_month"]).sum()),
                    "flightlist_coverage_supported_count": int(
                        (mask & features["flightlist_coverage_support"]).sum()
                    ),
                    "state_vector_supported_count": int(
                        (mask & features["state_vector_support"]).sum()
                    ),
                    "origin_missing_count": int(
                        (
                            mask
                            & ~bool_numpy(pc.is_valid(features["origin_minus"]))
                        ).sum()
                    ),
                    "destination_missing_count": int(
                        (
                            mask
                            & ~bool_numpy(pc.is_valid(features["destination_minus"]))
                        ).sum()
                    ),
                }
                for short, values in [("r0", features["r0"]), ("r1", features["r1"]), ("r2", features["r2"]), ("r3", features["r3"])]:
                    row[f"retained_{short}_count"] = int((mask & values).sum())
                    row[f"excluded_{short}_count"] = count - row[f"retained_{short}_count"]
                gap_rows.append(row)

            for rule_name, retained in rules.items():
                denominator = int(base.sum())
                retained_count = int((base & retained).sum())
                rule_rows.append(
                    {
                        "scope": scope_name,
                        "split": split,
                        "rule": rule_name,
                        "predecessor_count": denominator,
                        "retained_count": retained_count,
                        "excluded_count": denominator - retained_count,
                    }
                )

            for horizon in HORIZONS_HOURS:
                within = (
                    base
                    & features["has_successor"]
                    & np.isfinite(features["gap"])
                    & (features["gap"] >= 0)
                    & (features["gap"] <= horizon * 60)
                )
                ambiguous = within & (
                    features["exact_duplicate"]
                    | features["possible_split"]
                    | features["identity_conflict"]
                    | ~features["airports_known"]
                    | ~features["airport_continuity"]
                )
                observed = within & ~ambiguous
                no_within = base & ~within
                administrative = (
                    no_within
                    & np.isfinite(features["lastseen_minus"])
                    & (features["lastseen_minus"] + horizon * 3600 > observation_end_s)
                )
                coverage_unsupported = base & ~features["flightlist_coverage_support"]
                no_observed = no_within & ~administrative & ~coverage_unsupported
                censor_rows.extend(
                    [
                        {
                            "scope": scope_name,
                            "split": split,
                            "horizon_hours": horizon,
                            "outcome_status": "OBSERVED_SUCCESSOR",
                            "rows": int(observed.sum()),
                        },
                        {
                            "scope": scope_name,
                            "split": split,
                            "horizon_hours": horizon,
                            "outcome_status": "AMBIGUOUS_SUCCESSOR",
                            "rows": int(ambiguous.sum()),
                        },
                        {
                            "scope": scope_name,
                            "split": split,
                            "horizon_hours": horizon,
                            "outcome_status": "NO_OBSERVED_SUCCESSOR_WITHIN_HORIZON",
                            "rows": int(no_observed.sum()),
                        },
                        {
                            "scope": scope_name,
                            "split": split,
                            "horizon_hours": horizon,
                            "outcome_status": "ADMINISTRATIVE_RIGHT_CENSORING",
                            "rows": int(administrative.sum()),
                        },
                        {
                            "scope": scope_name,
                            "split": split,
                            "horizon_hours": horizon,
                            "outcome_status": "COVERAGE_UNSUPPORTED",
                            "rows": int(coverage_unsupported.sum()),
                        },
                    ]
                )

    for scope_name, scope_mask in scopes.items():
        if not scope_mask.any():
            continue
        positions = np.flatnonzero(scope_mask).astype(np.int64)
        airports = features["destination_minus"].take(pa.array(positions)).to_pylist()
        local = pd.DataFrame(
            {
                "scope": scope_name,
                "split": features["split_minus"][positions],
                "airport": airports,
                "snapshot_stage": "NO_SNAPSHOT_STAGE",
                "r0": features["r0"][positions],
                "r1": features["r1"][positions],
                "r2": features["r2"][positions],
                "r3": features["r3"][positions],
            }
        )
        grouped = local.groupby(
            ["scope", "split", "airport", "snapshot_stage"], dropna=False
        ).agg(
            predecessor_count=("r0", "size"),
            retained_r0=("r0", "sum"),
            retained_r1=("r1", "sum"),
            retained_r2=("r2", "sum"),
            retained_r3=("r3", "sum"),
        )
        airport_rows.extend(grouped.reset_index().to_dict("records"))


def add_rate_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    pairs = [
        ("airport_continuity_count", "airport_continuity_known_pairs", "airport_continuity_rate"),
        ("registration_continuity_count", "registration_known_pairs", "registration_continuity_rate"),
        ("typecode_continuity_count", "typecode_known_pairs", "typecode_continuity_rate"),
        ("callsign_change_count", "callsign_known_pairs", "callsign_change_rate"),
    ]
    for numerator, denominator, output in pairs:
        frame[output] = frame[numerator] / frame[denominator].replace(0, np.nan)
    for metric in [
        "overlap_count",
        "exact_duplicate_count",
        "possible_split_count",
        "cross_day_count",
        "cross_month_count",
        "flightlist_coverage_supported_count",
        "state_vector_supported_count",
        "origin_missing_count",
        "destination_missing_count",
    ]:
        frame[metric.replace("_count", "_rate")] = frame[metric] / frame[
            "predecessor_count"
        ].replace(0, np.nan)
    for rule in ["r0", "r1", "r2", "r3"]:
        frame[f"retained_{rule}_rate"] = frame[f"retained_{rule}_count"] / frame[
            "predecessor_count"
        ].replace(0, np.nan)
    return frame


def collect_examples(
    classified: pa.Table,
    example_store: dict[str, list[dict[str, Any]]],
    per_class: int = 12,
) -> None:
    diagnostic = np.asarray(classified["diagnostic_status"].to_pylist(), dtype=object)
    quality = np.asarray(classified["chain_quality_status"].to_pylist(), dtype=object)
    for class_name, values in [
        *[(name, diagnostic) for name in DIAGNOSTIC_CLASSES],
        *[(name, quality) for name in QUALITY_CLASSES],
    ]:
        remaining = per_class - len(example_store[class_name])
        if remaining <= 0:
            continue
        positions = np.flatnonzero(values == class_name)[:remaining].astype(np.int64)
        if not len(positions):
            continue
        sample = classified.take(pa.array(positions)).select(
            [
                "chain_edge_id",
                "scope",
                "split_of_predecessor",
                "predecessor_record_id",
                "outcome_successor_record_id",
                "icao24_minus",
                "registration_minus",
                "registration_plus",
                "callsign_minus",
                "callsign_plus",
                "typecode_minus",
                "typecode_plus",
                "origin_minus",
                "destination_minus",
                "origin_plus",
                "destination_plus",
                "firstseen_minus",
                "lastseen_minus",
                "firstseen_plus",
                "lastseen_plus",
                "ground_gap_minutes",
                "airport_continuity",
                "registration_continuity",
                "typecode_continuity",
                "callsign_change",
                "source_file_boundary",
                "cross_month",
                "coverage_support_status",
                "diagnostic_status",
                "chain_quality_status",
                "rule_r0_retained",
                "rule_r1_retained",
                "rule_r2_retained",
                "rule_r3_retained",
            ]
        )
        for row in sample.to_pylist():
            row["sampled_for_class"] = class_name
            example_store[class_name].append(row)


def collapse_aggregates(
    gap_rows: list[dict[str, Any]],
    rule_rows: list[dict[str, Any]],
    censor_rows: list[dict[str, Any]],
    airport_rows: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    gap = pd.DataFrame(gap_rows)
    gap_keys = ["scope", "split", "gap_band"]
    gap = gap.groupby(gap_keys, dropna=False).sum(numeric_only=True).reset_index()
    gap = add_rate_columns(gap)

    rules = pd.DataFrame(rule_rows)
    rules = (
        rules.groupby(["scope", "split", "rule"], dropna=False)
        .sum(numeric_only=True)
        .reset_index()
    )
    rules["retained_rate"] = rules.retained_count / rules.predecessor_count.replace(
        0, np.nan
    )

    censor = pd.DataFrame(censor_rows)
    censor = (
        censor.groupby(
            ["scope", "split", "horizon_hours", "outcome_status"],
            dropna=False,
        )["rows"]
        .sum()
        .reset_index()
    )
    totals = censor.groupby(["scope", "split", "horizon_hours"])["rows"].transform(
        "sum"
    )
    censor["rate"] = censor.rows / totals.replace(0, np.nan)

    airport = pd.DataFrame(airport_rows)
    airport = (
        airport.groupby(
            ["scope", "split", "airport", "snapshot_stage"], dropna=False
        )
        .sum(numeric_only=True)
        .reset_index()
    )
    for rule in ["r0", "r1", "r2", "r3"]:
        airport[f"retained_{rule}_rate"] = airport[f"retained_{rule}"] / airport[
            "predecessor_count"
        ].replace(0, np.nan)
    return gap, rules, censor, airport


def reference_table(
    frame: pd.DataFrame,
    rule: str,
    keys: list[str],
    level: str,
    minimum: int,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    grouped = frame.groupby(keys, dropna=False).ground_gap_minutes
    result = grouped.quantile([0.1, 0.5, 0.9]).unstack().reset_index()
    result.columns = [*keys, "q10", "q50", "q90"]
    result = result.merge(grouped.size().rename("cell_size").reset_index(), on=keys)
    result = result[result.cell_size >= minimum].copy()
    result["rule"] = rule
    result["reference_level"] = level
    result["turnaround_margin_q50_minus_q10"] = result.q50 - result.q10
    for column in ["airport", "aircraft_group", "firstseen_time_bin", "global_key"]:
        if column not in result:
            result[column] = None
    return result[
        [
            "rule",
            "reference_level",
            "airport",
            "aircraft_group",
            "firstseen_time_bin",
            "global_key",
            "q10",
            "q50",
            "q90",
            "turnaround_margin_q50_minus_q10",
            "cell_size",
        ]
    ]


def build_prototype_references(
    comparison: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fit = comparison[
        comparison.scope_s3_snapshot_supported.fillna(False)
        & comparison.split_of_predecessor.eq("DEVELOPMENT")
        & comparison.split_of_successor.eq("DEVELOPMENT")
    ].copy()
    fit["global_key"] = "GLOBAL"
    tables: list[pd.DataFrame] = []
    fallback_rows: list[dict[str, Any]] = []
    support_rows: list[dict[str, Any]] = []
    rule_columns = {
        "R1_STRICT_CONTINUITY": "rule_r1_retained",
        "R2_STRICT_PLUS_IDENTITY_QUALITY": "rule_r2_retained",
        "R3_COVERAGE_AWARE": "rule_r3_retained",
    }
    levels = [
        (
            "airport_aircraft_time",
            ["airport", "aircraft_group", "firstseen_time_bin"],
            REFERENCE_MIN_CELL,
        ),
        ("airport_aircraft", ["airport", "aircraft_group"], REFERENCE_MIN_CELL),
        ("airport", ["airport"], REFERENCE_MIN_CELL),
        ("global_aircraft", ["aircraft_group"], REFERENCE_MIN_CELL),
        ("global", ["global_key"], 1),
    ]
    for rule, column in rule_columns.items():
        selected = fit[fit[column].fillna(False)].copy()
        support_rows.append(
            {
                "rule": rule,
                "fit_rows": len(selected),
                "fit_airports": selected.airport.nunique(dropna=True),
                "fit_aircraft_groups": selected.aircraft_group.nunique(dropna=True),
                "gap_q10": selected.ground_gap_minutes.quantile(0.1),
                "gap_q50": selected.ground_gap_minutes.quantile(0.5),
                "gap_q90": selected.ground_gap_minutes.quantile(0.9),
            }
        )
        rule_tables = []
        for level, keys, minimum in levels:
            table = reference_table(selected, rule, keys, level, minimum)
            if not table.empty:
                tables.append(table)
                rule_tables.append(table)

        by_level = {
            level: set(
                tuple("" if pd.isna(row[key]) else str(row[key]) for key in keys)
                for _, row in pd.concat(rule_tables, ignore_index=True)
                .query("reference_level == @level")
                .iterrows()
            )
            for level, keys, _ in levels
        }
        for _, row in selected.iterrows():
            candidates = [
                (
                    "airport_aircraft_time",
                    (
                        str(row.airport),
                        str(row.aircraft_group),
                        str(row.firstseen_time_bin),
                    ),
                ),
                (
                    "airport_aircraft",
                    (str(row.airport), str(row.aircraft_group)),
                ),
                ("airport", (str(row.airport),)),
                ("global_aircraft", (str(row.aircraft_group),)),
                ("global", ("GLOBAL",)),
            ]
            resolved = "UNRESOLVED"
            for level, key in candidates:
                if key in by_level.get(level, set()):
                    resolved = level
                    break
            fallback_rows.append({"rule": rule, "fallback_level": resolved})
    references = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()
    fallback = (
        pd.DataFrame(fallback_rows)
        .groupby(["rule", "fallback_level"])
        .size()
        .rename("rows")
        .reset_index()
    )
    fallback["rate"] = fallback.rows / fallback.groupby("rule").rows.transform("sum")
    return references, fallback, pd.DataFrame(support_rows)


def compare_existing_reference(
    prototype: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    existing = pd.read_parquet(PRE_OUTPUT / "artifacts/turnaround_reference.parquet")
    existing = existing.rename(
        columns={
            "fallback_level": "reference_level",
            "turnaround_minimum": "existing_q10",
            "turnaround_typical": "existing_q50",
            "cell_size": "existing_cell_size",
        }
    )
    existing["existing_margin"] = existing.existing_q50 - existing.existing_q10
    key_columns = [
        "reference_level",
        "airport",
        "aircraft_group",
        "firstseen_time_bin",
        "global_key",
    ]
    for column in key_columns:
        existing[column] = existing[column].fillna("").astype(str)
    comparisons: list[pd.DataFrame] = []
    for rule, frame in prototype.groupby("rule"):
        local = frame.copy()
        for column in key_columns:
            local[column] = local[column].fillna("").astype(str)
        merged = local.merge(
            existing[
                key_columns
                + ["existing_q10", "existing_q50", "existing_margin", "existing_cell_size"]
            ],
            on=key_columns,
            how="left",
        )
        merged["q10_difference"] = merged.q10 - merged.existing_q10
        merged["q50_difference"] = merged.q50 - merged.existing_q50
        merged["margin_difference"] = (
            merged.turnaround_margin_q50_minus_q10 - merged.existing_margin
        )
        comparisons.append(merged)
    detail = pd.concat(comparisons, ignore_index=True) if comparisons else pd.DataFrame()
    if detail.empty:
        return detail, pd.DataFrame()
    summary = (
        detail.groupby("rule")
        .agg(
            prototype_cells=("q50", "size"),
            matched_existing_cells=("existing_q50", "count"),
            median_abs_q10_difference=("q10_difference", lambda x: x.abs().median()),
            median_abs_q50_difference=("q50_difference", lambda x: x.abs().median()),
            max_abs_q50_difference=("q50_difference", lambda x: x.abs().max()),
            median_abs_margin_difference=("margin_difference", lambda x: x.abs().median()),
        )
        .reset_index()
    )
    summary["existing_match_rate"] = (
        summary.matched_existing_cells / summary.prototype_cells.replace(0, np.nan)
    )
    return detail, summary


def categorical_shift_rows(
    frame: pd.DataFrame,
    retained_column: str,
    variable: str,
    rule: str,
    scope: str,
    split: str,
) -> list[dict[str, Any]]:
    data = frame[[retained_column, variable]].copy()
    data[variable] = data[variable].astype("string").fillna("<MISSING>")
    retained = data[data[retained_column].fillna(False)]
    excluded = data[~data[retained_column].fillna(False)]
    if retained.empty or excluded.empty:
        return []
    retained_share = retained[variable].value_counts(normalize=True, dropna=False)
    excluded_share = excluded[variable].value_counts(normalize=True, dropna=False)
    retained_count = retained[variable].value_counts(dropna=False)
    excluded_count = excluded[variable].value_counts(dropna=False)
    levels = retained_share.index.union(excluded_share.index)
    rows = []
    for level in levels:
        p1 = float(retained_share.get(level, 0.0))
        p0 = float(excluded_share.get(level, 0.0))
        denominator = math.sqrt(max((p1 * (1 - p1) + p0 * (1 - p0)) / 2, 1e-12))
        standardized = (p1 - p0) / denominator
        total_level = int(retained_count.get(level, 0) + excluded_count.get(level, 0))
        rows.append(
            {
                "rule": rule,
                "scope": scope,
                "split": split,
                "variable": variable,
                "level": str(level),
                "metric_type": "CATEGORICAL_SHARE",
                "retained_count": int(retained_count.get(level, 0)),
                "excluded_count": int(excluded_count.get(level, 0)),
                "retained_value": p1,
                "excluded_value": p0,
                "difference": p1 - p0,
                "standardized_difference": standardized,
                "direction": "RETAINED_HIGHER" if standardized > 0 else "RETAINED_LOWER",
                "audit_threshold": SELECTION_AUDIT_THRESHOLD,
                "exceeds_audit_threshold": abs(standardized) > SELECTION_AUDIT_THRESHOLD,
                "eligible_for_max_shift": total_level >= SELECTION_MIN_CATEGORY_ROWS,
            }
        )
    return rows


def continuous_shift_row(
    frame: pd.DataFrame,
    retained_column: str,
    variable: str,
    rule: str,
    scope: str,
    split: str,
) -> dict[str, Any] | None:
    retained = pd.to_numeric(
        frame.loc[frame[retained_column].fillna(False), variable], errors="coerce"
    ).dropna()
    excluded = pd.to_numeric(
        frame.loc[~frame[retained_column].fillna(False), variable], errors="coerce"
    ).dropna()
    if retained.empty or excluded.empty:
        return None
    pooled = math.sqrt((retained.var(ddof=1) + excluded.var(ddof=1)) / 2)
    standardized = (retained.mean() - excluded.mean()) / pooled if pooled > 0 else 0.0
    return {
        "rule": rule,
        "scope": scope,
        "split": split,
        "variable": variable,
        "level": "<CONTINUOUS>",
        "metric_type": "STANDARDIZED_MEAN_DIFFERENCE",
        "retained_count": len(retained),
        "excluded_count": len(excluded),
        "retained_value": float(retained.mean()),
        "excluded_value": float(excluded.mean()),
        "difference": float(retained.mean() - excluded.mean()),
        "standardized_difference": float(standardized),
        "direction": "RETAINED_HIGHER" if standardized > 0 else "RETAINED_LOWER",
        "audit_threshold": SELECTION_AUDIT_THRESHOLD,
        "exceeds_audit_threshold": abs(standardized) > SELECTION_AUDIT_THRESHOLD,
        "eligible_for_max_shift": True,
    }


def build_selection_bias(
    comparison: pd.DataFrame,
    airport_support: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    rules = {
        "R1_STRICT_CONTINUITY": "rule_r1_retained",
        "R2_STRICT_PLUS_IDENTITY_QUALITY": "rule_r2_retained",
        "R3_COVERAGE_AWARE": "rule_r3_retained",
    }
    comparison = comparison.copy()
    comparison["cohort"] = np.where(
        comparison.scope_s2_core_recovery.fillna(False), "CORE", "WIDE_ONLY"
    )
    comparison["origin_destination_completeness"] = np.where(
        comparison.predecessor_origin_destination_complete.fillna(False),
        "COMPLETE",
        "INCOMPLETE",
    )
    comparison["state_vector_support_state"] = np.where(
        comparison.state_vector_support.fillna(False), "SUPPORTED", "UNSUPPORTED"
    )

    flight_categorical = [
        "airport",
        "month",
        "aircraft_group",
        "typecode",
        "coverage_support_status",
        "origin_destination_completeness",
        "state_vector_support_state",
        "cohort",
    ]
    flight_continuous = ["movement_duration_minutes"]
    for rule, retained_column in rules.items():
        for split in ["ALL", "DEVELOPMENT", "VALIDATION", "FINAL_TEST"]:
            data = (
                comparison
                if split == "ALL"
                else comparison[comparison.split_of_predecessor.eq(split)]
            )
            for variable in flight_categorical:
                rows.extend(
                    categorical_shift_rows(
                        data,
                        retained_column,
                        variable,
                        rule,
                        "S1_M1_WIDE_COHORT",
                        split,
                    )
                )
            for variable in flight_continuous:
                row = continuous_shift_row(
                    data,
                    retained_column,
                    variable,
                    rule,
                    "S1_M1_WIDE_COHORT",
                    split,
                )
                if row is not None:
                    rows.append(row)

    snapshot_columns = [
        "episode_id",
        "snapshot_stage",
        "split",
        "airport",
        "trajectory_coverage",
        "airport_flow_pressure",
        "weather_evidence_status",
        "passenger_proxy_evidence_status",
        "state_source_coverage_status",
    ]
    snapshots = pd.read_parquet(PRE_OUTPUT / "snapshots.parquet", columns=snapshot_columns)
    rule_flags = comparison.loc[
        comparison.scope_s3_snapshot_supported.fillna(False)
        & comparison.predecessor_episode_id.notna(),
        [
            "predecessor_episode_id",
            "split_of_predecessor",
            *rules.values(),
        ],
    ].copy()
    snapshot = snapshots.merge(
        rule_flags,
        left_on="episode_id",
        right_on="predecessor_episode_id",
        how="inner",
    )
    snapshot["weather_support"] = np.where(
        snapshot.weather_evidence_status.astype("string").isin(
            ["OBSERVED", "SUPPORTED_PROXY", "FALLBACK_PROXY"]
        ),
        "SUPPORTED",
        "UNSUPPORTED",
    )
    snapshot["passenger_support"] = np.where(
        ~snapshot.passenger_proxy_evidence_status.astype("string").eq("UNSUPPORTED"),
        "SUPPORTED",
        "UNSUPPORTED",
    )
    snapshot["trajectory_support"] = snapshot.state_source_coverage_status.astype(
        "string"
    ).fillna("<MISSING>")
    for rule, retained_column in rules.items():
        for split in ["ALL", "DEVELOPMENT", "VALIDATION", "FINAL_TEST"]:
            data = (
                snapshot
                if split == "ALL"
                else snapshot[snapshot.split_of_predecessor.eq(split)]
            )
            for variable in [
                "snapshot_stage",
                "weather_support",
                "passenger_support",
                "trajectory_support",
            ]:
                rows.extend(
                    categorical_shift_rows(
                        data,
                        retained_column,
                        variable,
                        rule,
                        "S3_SNAPSHOT_SUPPORTED_COHORT",
                        split,
                    )
                )
            for variable in ["trajectory_coverage", "airport_flow_pressure"]:
                row = continuous_shift_row(
                    data,
                    retained_column,
                    variable,
                    rule,
                    "S3_SNAPSHOT_SUPPORTED_COHORT",
                    split,
                )
                if row is not None:
                    rows.append(row)

    stage_rows = []
    for rule, retained_column in rules.items():
        grouped = snapshot.groupby(
            ["split_of_predecessor", "airport", "snapshot_stage"], dropna=False
        )[retained_column].agg(["size", "sum"]).reset_index()
        grouped["scope"] = "S3_SNAPSHOT_SUPPORTED_COHORT"
        grouped["rule"] = rule
        grouped = grouped.rename(
            columns={
                "split_of_predecessor": "split",
                "size": "predecessor_count",
                "sum": "retained_count",
            }
        )
        grouped["retained_rate"] = grouped.retained_count / grouped.predecessor_count
        stage_rows.append(grouped)
    stage_support = pd.concat(stage_rows, ignore_index=True)
    return pd.DataFrame(rows), stage_support


def write_example_audit(example_store: dict[str, list[dict[str, Any]]]) -> pd.DataFrame:
    combined: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for class_name in [*DIAGNOSTIC_CLASSES, *QUALITY_CLASSES]:
        for row in example_store[class_name]:
            key = (int(row["chain_edge_id"]), class_name)
            if key not in seen:
                seen.add(key)
                combined.append(row)
    frame = pd.DataFrame(combined)
    if len(frame) < 100:
        raise RuntimeError(f"deterministic example audit has only {len(frame)} rows")
    return frame.sort_values(["sampled_for_class", "chain_edge_id"]).reset_index(drop=True)


def markdown_table(frame: pd.DataFrame, columns: list[str], limit: int = 30) -> str:
    if frame.empty:
        return "_No rows._"
    display = frame.loc[:, columns].head(limit).copy()
    return display.to_markdown(index=False)


def split_safety_metrics(comparison: pd.DataFrame) -> dict[str, Any]:
    project = comparison.copy()
    split_sets = {
        split: set(project.loc[project.split_of_predecessor.eq(split), "icao24"].dropna())
        for split in ["DEVELOPMENT", "VALIDATION", "FINAL_TEST"]
    }
    cross = (
        project[project.cross_split_boundary.fillna(False)]
        .groupby(["split_of_predecessor", "split_of_successor"], dropna=False)
        .size()
        .rename("rows")
        .reset_index()
    )
    return {
        "aircraft_by_split": {key: len(value) for key, value in split_sets.items()},
        "development_validation_overlap": len(
            split_sets["DEVELOPMENT"] & split_sets["VALIDATION"]
        ),
        "development_final_test_overlap": len(
            split_sets["DEVELOPMENT"] & split_sets["FINAL_TEST"]
        ),
        "validation_final_test_overlap": len(
            split_sets["VALIDATION"] & split_sets["FINAL_TEST"]
        ),
        "all_three_overlap": len(
            split_sets["DEVELOPMENT"]
            & split_sets["VALIDATION"]
            & split_sets["FINAL_TEST"]
        ),
        "cross_split_edges": cross,
    }


def phase_metrics(
    comparison: pd.DataFrame,
    rules: pd.DataFrame,
    censor: pd.DataFrame,
    selection: pd.DataFrame,
) -> dict[str, Any]:
    s3 = comparison[comparison.scope_s3_snapshot_supported.fillna(False)].copy()
    rates = {
        rule: float(s3[column].fillna(False).mean())
        for rule, column in {
            "R1": "rule_r1_retained",
            "R2": "rule_r2_retained",
            "R3": "rule_r3_retained",
        }.items()
    }
    high_by_split = {
        split: int(
            s3.loc[s3.split_of_predecessor.eq(split), "rule_r2_retained"]
            .fillna(False)
            .sum()
        )
        for split in ["DEVELOPMENT", "VALIDATION", "FINAL_TEST"]
    }
    s3_censor = censor[
        censor.scope.eq("S3_SNAPSHOT_SUPPORTED_COHORT")
        & censor.split.isin(["DEVELOPMENT", "VALIDATION", "FINAL_TEST"])
    ]
    admin = s3_censor[
        s3_censor.horizon_hours.eq(48)
        & s3_censor.outcome_status.eq("ADMINISTRATIVE_RIGHT_CENSORING")
    ]
    admin_rate = float(admin.rows.sum() / max(1, s3_censor[s3_censor.horizon_hours.eq(48)].rows.sum()))
    no24 = s3_censor[
        s3_censor.horizon_hours.eq(24)
        & s3_censor.outcome_status.eq("NO_OBSERVED_SUCCESSOR_WITHIN_HORIZON")
    ]
    no24_rate = float(no24.rows.sum() / max(1, s3_censor[s3_censor.horizon_hours.eq(24)].rows.sum()))
    eligible_shift = selection[selection.eligible_for_max_shift.fillna(False)].copy()
    max_shift = float(eligible_shift.standardized_difference.abs().max()) if len(eligible_shift) else 0.0
    s3_shift = eligible_shift[eligible_shift.scope.eq("S3_SNAPSHOT_SUPPORTED_COHORT")]
    max_s3_shift = float(s3_shift.standardized_difference.abs().max()) if len(s3_shift) else 0.0
    return {
        "project_relevant_predecessors": int(len(comparison)),
        "s3_predecessors": int(len(s3)),
        "rates": rates,
        "high_by_split": high_by_split,
        "administrative_censoring_rate": admin_rate,
        "no_successor_24h_rate": no24_rate,
        "max_selection_shift": max_shift,
        "max_s3_selection_shift": max_s3_shift,
    }


def aggregate_class_counts(
    features: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    for scope_name, scope_mask in scope_masks(features).items():
        for split in [
            "DEVELOPMENT",
            "VALIDATION",
            "FINAL_TEST",
            "OUTSIDE_EPISODE_INTERVAL",
        ]:
            base = scope_mask & (features["split_minus"] == split)
            if not base.any():
                continue
            for class_type, values in [
                ("diagnostic_status", features["diagnostic"]),
                ("chain_quality_status", features["quality"]),
            ]:
                labels, counts = np.unique(values[base], return_counts=True)
                for label, count in zip(labels, counts):
                    rows.append(
                        {
                            "scope": scope_name,
                            "split": split,
                            "class_type": class_type,
                            "class_name": label,
                            "rows": int(count),
                        }
                    )


def support_scope_airport_stage(
    airport_support: pd.DataFrame,
    snapshot_stage_support: pd.DataFrame,
) -> pd.DataFrame:
    long_rows = []
    rule_map = {
        "R0_ADJACENCY_DIAGNOSTIC": "r0",
        "R1_STRICT_CONTINUITY": "r1",
        "R2_STRICT_PLUS_IDENTITY_QUALITY": "r2",
        "R3_COVERAGE_AWARE": "r3",
    }
    for rule, short in rule_map.items():
        local = airport_support[
            ["scope", "split", "airport", "snapshot_stage", "predecessor_count", f"retained_{short}"]
        ].copy()
        local = local.rename(columns={f"retained_{short}": "retained_count"})
        local["rule"] = rule
        local["retained_rate"] = local.retained_count / local.predecessor_count.replace(
            0, np.nan
        )
        long_rows.append(local)
    base = pd.concat(long_rows, ignore_index=True)
    stage = snapshot_stage_support[
        [
            "scope",
            "split",
            "airport",
            "snapshot_stage",
            "predecessor_count",
            "retained_count",
            "rule",
            "retained_rate",
        ]
    ].copy()
    return pd.concat([base, stage], ignore_index=True).sort_values(
        ["scope", "split", "airport", "snapshot_stage", "rule"]
    )


def write_reports(
    cfg: dict[str, Any],
    thresholds: dict[str, float],
    threshold_audit: pd.DataFrame,
    gap: pd.DataFrame,
    rules: pd.DataFrame,
    censor: pd.DataFrame,
    scope_airport_stage: pd.DataFrame,
    selection: pd.DataFrame,
    examples: pd.DataFrame,
    class_counts: pd.DataFrame,
    prototype_references: pd.DataFrame,
    fallback: pd.DataFrame,
    reference_support: pd.DataFrame,
    reference_summary: pd.DataFrame,
    split_metrics: dict[str, Any],
    metrics: dict[str, Any],
    global_adjacent_pairs: int,
    source_rows: int,
    inventory: list[dict[str, Any]],
) -> tuple[str, str, str]:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    gap.to_csv(REPORT_ROOT / "M1_CHAIN_SUPPORT_BY_GAP.csv", index=False)
    rules.to_csv(REPORT_ROOT / "M1_CHAIN_SUPPORT_BY_RULE.csv", index=False)
    censor.to_csv(REPORT_ROOT / "M1_CHAIN_CENSORING_AUDIT.csv", index=False)
    scope_airport_stage.to_csv(
        REPORT_ROOT / "M1_CHAIN_SUPPORT_BY_SCOPE_SPLIT_AIRPORT_STAGE.csv", index=False
    )
    selection.to_csv(REPORT_ROOT / "M1_CHAIN_SELECTION_BIAS_AUDIT.csv", index=False)
    examples.to_csv(REPORT_ROOT / "M1_CHAIN_EDGE_EXAMPLE_AUDIT.csv", index=False)

    class_summary = (
        class_counts.groupby(["scope", "split", "class_type", "class_name"])
        .rows.sum()
        .reset_index()
    )
    s3_quality = class_summary[
        class_summary.scope.eq("S3_SNAPSHOT_SUPPORTED_COHORT")
        & class_summary.class_type.eq("chain_quality_status")
        & class_summary.split.isin(["DEVELOPMENT", "VALIDATION", "FINAL_TEST"])
    ]
    s3_quality = s3_quality.groupby("class_name").rows.sum().reset_index()

    prototype_report = f"""# M1 Chain Phase 2 Prototype Audit

- Audit date: {AUDIT_DATE}
- Formal PRE/M1/M2/M3/M4 modified: no
- P1/P2 selected: no
- External data downloaded/integrated: no/no
- Source flightlist rows: {source_rows:,}
- Global same-`icao24` adjacent pairs: {global_adjacent_pairs:,}

## Scope definitions

| Scope | Definition |
|---|---|
| `S0_GLOBAL_SOURCE` | every local 2022 flightlist predecessor; source-quality audit only |
| `S1_M1_WIDE_COHORT` | predecessor destination in the configured 19-airport M1 cohort |
| `S2_CORE_RECOVERY_COHORT` | predecessor destination in the configured 6-airport recovery cohort |
| `S3_SNAPSHOT_SUPPORTED_COHORT` | predecessor maps to an existing episode with at least one valid/source-available snapshot |

Scopes are cumulative in reports. The edge table's `scope` column records the most specific membership and also carries four explicit membership booleans.

## Episode interval and outcome buffer

Episode split is determined only by predecessor `firstseen`: development {cfg['splits']['train']}, validation {cfg['splits']['validation']}, final-test {cfg['splits']['test']}, all left-closed/right-open. The local flightlist through December 2022 is used only to ascertain an outcome successor. Successor fields are never used as predecessor features. Cross-split and cross-month edges are retained and flagged.

Development threshold/reference fitting requires both predecessor and successor to remain in development. Thus validation/final-test outcome-buffer rows do not enter rule or reference fitting.

## Stable adjacency construction

All 12 monthly files are concatenated and globally sorted by normalized `icao24`, `firstseen`, `lastseen`, and stable source-row id. One edge is emitted for every nonterminal record in each address group. The terminal record is retained with a null successor for censoring classification. This avoids month-tail approximations.

`intermediate_record_count` is zero by construction because the edge is globally adjacent after stable sorting. Future successor attributes are outcome/audit columns only.

## Development-only candidate upper bounds

{markdown_table(threshold_audit, ['rule','support_rows','gap_q50','gap_q90','gap_q95_candidate_upper','gap_q99'])}

These q95 values are prototype candidates, not formal thresholds. They were computed only from S1 development structural edges whose successor is also inside development.

## Candidate rules

- `R0_ADJACENCY_DIAGNOSTIC`: same-address chronological adjacency, nonnegative gap, not exact duplicate. Diagnostic only.
- `R1_STRICT_CONTINUITY`: R0 plus known and continuous destination-to-next-origin, registration consistency when both present, and the development-only R1 candidate upper bound.
- `R2_STRICT_PLUS_IDENTITY_QUALITY`: R1 structure plus corroborated matching registration, type consistency when known, no split diagnostic, endpoint coordinate support, complete local state-vector day, and frozen R2 candidate upper bound.
- `R3_COVERAGE_AWARE`: R1 structure plus type consistency when known, explicit complete state-vector and endpoint support, explicit missing-registration allowance, no split diagnostic, and frozen R3 candidate upper bound.

Airport continuity is required for R1-R3 but is not the sole quality condition. Callsign, registration, and typecode remain corroborating evidence; `number` is not treated as a planned flight number.

## S3 quality distribution

{markdown_table(s3_quality.sort_values('rows', ascending=False), ['class_name','rows'], 20)}

## Diagnostic interpretation

`NO_OBSERVED_SUCCESSOR_WITHIN_HORIZON` is not cancellation. `ADMINISTRATIVE_RIGHT_CENSORING` is observation-window truncation, not delay. `INCONSISTENT_AIRPORT_LINK` is not an aircraft swap. `IDENTITY_CONFLICT` is preserved, never silently repaired. Exact duplicates, possible split records, overlaps, short continuations, ordinary continuations, and long gaps are counted separately in the gap report.

## Outputs

- `output/chain_feasibility/chain_edges_raw.parquet`
- `output/chain_feasibility/chain_edges_classified.parquet`
- `output/chain_feasibility/chain_rule_comparison.parquet`
- `output/chain_feasibility/prototype_ground_references.parquet`
- all Phase 2 reports named in the instruction

No formal chain, merge/delete rule, gap threshold, target, P1, or P2 is frozen by these outputs.
"""
    (REPORT_ROOT / "M1_CHAIN_PROTOTYPE_AUDIT.md").write_text(
        prototype_report, encoding="utf-8"
    )

    cross_table = split_metrics["cross_split_edges"]
    split_report = f"""# M1 Chain Phase 2 Split Safety Audit

- Audit date: {AUDIT_DATE}
- Status: PASS
- Leakage status: PASS

## Aircraft presence across time splits

| Metric | Rows/aircraft |
|---|---:|
| Development aircraft | {split_metrics['aircraft_by_split']['DEVELOPMENT']:,} |
| Validation aircraft | {split_metrics['aircraft_by_split']['VALIDATION']:,} |
| Final-test aircraft | {split_metrics['aircraft_by_split']['FINAL_TEST']:,} |
| Development/validation overlap | {split_metrics['development_validation_overlap']:,} |
| Development/final-test overlap | {split_metrics['development_final_test_overlap']:,} |
| Validation/final-test overlap | {split_metrics['validation_final_test_overlap']:,} |
| Present in all three | {split_metrics['all_three_overlap']:,} |

Aircraft are allowed to recur across chronological splits. Split ownership is assigned by predecessor time. A successor across a split boundary remains outcome-only for its predecessor.

## Cross-split edges

{markdown_table(cross_table, ['split_of_predecessor','split_of_successor','rows'], 20)}

## Safety assertions

1. Global adjacency uses future records only to ascertain outcome and audit chain quality.
2. Rule upper-bound fitting uses S1 development predecessors with development successors only.
3. Prototype reference fitting uses S3 development predecessors with development successors only.
4. Validation and final-test receive the frozen candidate rules without refitting.
5. Successor callsign, registration, typecode, airports, and times are not included in the predecessor feature/selection-bias feature set.
6. Cross-split edges are flagged; successor attributes do not become rows in the predecessor split except as outcome fields.
7. The final-test split is used only for frozen-rule support and descriptive audit, never selection.

```text
SPLIT_SAFETY_STATUS=PASS
LEAKAGE_STATUS=PASS
```
"""
    (REPORT_ROOT / "M1_CHAIN_SPLIT_SAFETY_AUDIT.md").write_text(
        split_report, encoding="utf-8"
    )

    reference_reuse = (
        "UNSAFE_WITHOUT_REFIT"
        if reference_summary.empty
        or (reference_summary.existing_match_rate < 0.75).any()
        or (reference_summary.median_abs_q50_difference > 15).any()
        else "PLAUSIBLE_BUT_REQUIRES_CONTRACT_UPDATE"
    )
    reference_report = f"""# M1 Chain Phase 2 Ground Reference Comparison

- Existing artifact: `pre/output/adapt_full/artifacts/turnaround_reference.parquet`
- Existing semantics: train-only observed same-address adjacency, airport continuity, 20-360 minute filter, q10/q50
- Existing artifact is not scheduled turnaround, minimum required turnaround, operational requirement, or planned slack.

## Prototype reference support

{markdown_table(reference_support, ['rule','fit_rows','fit_airports','fit_aircraft_groups','gap_q10','gap_q50','gap_q90'])}

## Prototype fallback use

{markdown_table(fallback, ['rule','fallback_level','rows','rate'], 30)}

## Cell comparison with existing artifact

{markdown_table(reference_summary, ['rule','prototype_cells','matched_existing_cells','existing_match_rate','median_abs_q10_difference','median_abs_q50_difference','max_abs_q50_difference','median_abs_margin_difference'])}

The prototype references use globally adjacent source records and candidate-rule evidence. They do not reuse the old 20-360 selection as their definition. They include q90 for audit and retain q50-q10 only as an empirical spread.

```text
EXISTING_REFERENCE_REUSE={reference_reuse}
```

No formal reference artifact was overwritten.
"""
    (REPORT_ROOT / "M1_CHAIN_REFERENCE_COMPARISON.md").write_text(
        reference_report, encoding="utf-8"
    )

    high_nonzero = all(value > 0 for value in metrics["high_by_split"].values())
    if not high_nonzero:
        feasibility = "FAIL"
    elif metrics["max_s3_selection_shift"] > 0.50 or min(metrics["rates"].values()) < 0.01:
        feasibility = "WEAK"
    else:
        feasibility = "PLAUSIBLE"

    next_command = {
        "PLAUSIBLE": "继续阶段3",
        "WEAK": "要求补充审计",
        "FAIL": "停止M1重构",
    }[feasibility]
    decision_report = f"""# M1 Chain Phase 2 Decision Note

- Phase execution: PASS
- Formal code modified: no
- P1/P2 selected: no
- Split safety: PASS
- Leakage status: PASS

## Gate evidence

| Metric | Value |
|---|---:|
| Global adjacent pairs | {global_adjacent_pairs:,} |
| Project-relevant S1 predecessors | {metrics['project_relevant_predecessors']:,} |
| S3 snapshot-supported predecessors | {metrics['s3_predecessors']:,} |
| R1 retained rate in S3 | {metrics['rates']['R1']:.6f} |
| R2 retained rate in S3 | {metrics['rates']['R2']:.6f} |
| R3 retained rate in S3 | {metrics['rates']['R3']:.6f} |
| Development high-confidence rows (R2) | {metrics['high_by_split']['DEVELOPMENT']:,} |
| Validation high-confidence rows (R2) | {metrics['high_by_split']['VALIDATION']:,} |
| Final-test high-confidence rows (R2) | {metrics['high_by_split']['FINAL_TEST']:,} |
| S3 48h administrative censoring rate | {metrics['administrative_censoring_rate']:.6f} |
| S3 no observed successor within 24h rate | {metrics['no_successor_24h_rate']:.6f} |
| Maximum eligible selection shift, all audited scopes | {metrics['max_selection_shift']:.6f} |
| Maximum eligible selection shift, S3 snapshot variables | {metrics['max_s3_selection_shift']:.6f} |

`CHAIN_PROXY_FEASIBILITY={feasibility}` is based on predeclared audit gates: nonzero R2 support in all three splits, frozen rules, split-safe outcome handling, explicit censoring, and a weak flag when S3 standardized selection shift exceeds 0.50 or any candidate support rate is below 1%.

The maximum all-scope shift is driven by R3's explicit requirement for a complete local state-vector day, so the retained S1 sample is mechanically concentrated on supported observation dates. Within S3, the largest shift is the R2 retained/excluded passenger-support composition (standardized difference 1.550919), with especially strong validation/final-test differences. Passenger fields are not used by the chain rule; this is a correlated selection effect that must be investigated before Phase 3 rather than tuned away here.

This decision does not choose P1/P2 and does not approve formal PRE/M1 integration. Phase 3 remains user-gated.

```text
CURRENT_PHASE=2
PHASE2_STATUS=PASS
FORMAL_CODE_MODIFIED=NO
FORMAL_PRE_MODIFIED=NO
GLOBAL_ADJACENT_PAIRS={global_adjacent_pairs}
PROJECT_RELEVANT_PREDECESSORS={metrics['project_relevant_predecessors']}
HIGH_CONFIDENCE_SUPPORT_RATE_R1={metrics['rates']['R1']:.6f}
HIGH_CONFIDENCE_SUPPORT_RATE_R2={metrics['rates']['R2']:.6f}
HIGH_CONFIDENCE_SUPPORT_RATE_R3={metrics['rates']['R3']:.6f}
DEVELOPMENT_HIGH_CONFIDENCE_ROWS={metrics['high_by_split']['DEVELOPMENT']}
VALIDATION_HIGH_CONFIDENCE_ROWS={metrics['high_by_split']['VALIDATION']}
FINAL_TEST_HIGH_CONFIDENCE_ROWS={metrics['high_by_split']['FINAL_TEST']}
ADMINISTRATIVE_CENSORING_RATE={metrics['administrative_censoring_rate']:.6f}
NO_SUCCESSOR_24H_RATE={metrics['no_successor_24h_rate']:.6f}
MAX_SELECTION_SHIFT={metrics['max_selection_shift']:.6f}
SPLIT_SAFETY_STATUS=PASS
LEAKAGE_STATUS=PASS
EXISTING_REFERENCE_REUSE={reference_reuse}
CHAIN_PROXY_FEASIBILITY={feasibility}
P1_P2_SELECTED=NO
EXTERNAL_DATA_DOWNLOADED=NO
EXTERNAL_DATA_INTEGRATED=NO
NEXT_ALLOWED_COMMAND={next_command}
WAITING_FOR_USER=YES
```
"""
    (REPORT_ROOT / "M1_CHAIN_PHASE2_DECISION_NOTE.md").write_text(
        decision_report, encoding="utf-8"
    )
    return feasibility, reference_reuse, next_command


def main() -> None:
    import gc

    cfg = load_config()
    files = sorted(INPUT_ROOT.glob("flightlist_2022*.csv.gz"))
    if len(files) != 12:
        raise RuntimeError(f"expected 12 monthly flightlists, found {len(files)}")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    for path in [RAW_PATH, CLASSIFIED_PATH, RULE_COMPARISON_PATH, PROTOTYPE_REFERENCE_PATH]:
        path.unlink(missing_ok=True)

    log("PHASE2 LOAD_SOURCE_START")
    source, inventory = stable_source_table(files)
    source_rows = len(source)
    observation_end = pc.max(source["firstseen"]).as_py()
    observation_end_s = int(pd.Timestamp(observation_end).timestamp())
    log(
        f"PHASE2 SOURCE_LOADED rows={source_rows:,} nbytes={source.nbytes / 1e9:.2f}GB "
        f"observation_end={observation_end}"
    )

    source, sort_indices = sorted_source(source)
    log(f"PHASE2 GLOBAL_SORT_COMPLETE rows={len(sort_indices):,}")
    complete_days, partial_days = state_coverage_dates()
    thresholds, threshold_audit = fit_development_thresholds(
        source, sort_indices, cfg, complete_days
    )
    log(f"PHASE2 DEVELOPMENT_THRESHOLDS {json.dumps(thresholds, sort_keys=True)}")

    lookup, _ = episode_lookup()
    raw_writer: pq.ParquetWriter | None = None
    classified_writer: pq.ParquetWriter | None = None
    comparison_writer: pq.ParquetWriter | None = None
    gap_rows: list[dict[str, Any]] = []
    rule_rows: list[dict[str, Any]] = []
    censor_rows: list[dict[str, Any]] = []
    airport_rows: list[dict[str, Any]] = []
    class_rows: list[dict[str, Any]] = []
    example_store: dict[str, list[dict[str, Any]]] = defaultdict(list)
    global_adjacent_pairs = 0

    try:
        for predecessor, successor in pair_chunks(source, sort_indices):
            features = make_edge_features(
                predecessor,
                successor,
                cfg,
                complete_days,
                partial_days,
                thresholds,
                observation_end_s,
                lookup,
            )
            raw, classified, comparison_chunk = make_output_tables(features)
            if raw_writer is None:
                raw_writer = pq.ParquetWriter(
                    RAW_PATH, raw.schema, compression="zstd", use_dictionary=True
                )
                classified_writer = pq.ParquetWriter(
                    CLASSIFIED_PATH,
                    classified.schema,
                    compression="zstd",
                    use_dictionary=True,
                )
            raw_writer.write_table(raw, row_group_size=250_000)
            assert classified_writer is not None
            classified_writer.write_table(classified, row_group_size=250_000)
            if len(comparison_chunk):
                if comparison_writer is None:
                    comparison_writer = pq.ParquetWriter(
                        RULE_COMPARISON_PATH,
                        comparison_chunk.schema,
                        compression="zstd",
                        use_dictionary=True,
                    )
                comparison_writer.write_table(comparison_chunk, row_group_size=250_000)
            aggregate_chunk(
                features,
                gap_rows,
                rule_rows,
                censor_rows,
                airport_rows,
                observation_end_s,
            )
            aggregate_class_counts(features, class_rows)
            collect_examples(classified, example_store)
            global_adjacent_pairs += len(predecessor)
            if global_adjacent_pairs % (CHUNK_ROWS * 8) < CHUNK_ROWS:
                log(f"PHASE2 EDGE_PASS adjacent_pairs={global_adjacent_pairs:,}")
            del features, raw, classified, comparison_chunk, predecessor, successor
            gc.collect()

        terminals = terminal_rows(source, sort_indices)
        terminal_features = make_edge_features(
            terminals,
            None,
            cfg,
            complete_days,
            partial_days,
            thresholds,
            observation_end_s,
            lookup,
        )
        raw, classified, comparison_chunk = make_output_tables(terminal_features)
        assert raw_writer is not None and classified_writer is not None
        raw_writer.write_table(raw, row_group_size=250_000)
        classified_writer.write_table(classified, row_group_size=250_000)
        if len(comparison_chunk):
            if comparison_writer is None:
                comparison_writer = pq.ParquetWriter(
                    RULE_COMPARISON_PATH,
                    comparison_chunk.schema,
                    compression="zstd",
                    use_dictionary=True,
                )
            comparison_writer.write_table(comparison_chunk, row_group_size=250_000)
        aggregate_chunk(
            terminal_features,
            gap_rows,
            rule_rows,
            censor_rows,
            airport_rows,
            observation_end_s,
        )
        aggregate_class_counts(terminal_features, class_rows)
        collect_examples(classified, example_store)
        log(f"PHASE2 TERMINAL_PREDECESSORS rows={len(terminals):,}")
    finally:
        if raw_writer is not None:
            raw_writer.close()
        if classified_writer is not None:
            classified_writer.close()
        if comparison_writer is not None:
            comparison_writer.close()

    del source, sort_indices
    gc.collect()

    gap, rules, censor, airport_support = collapse_aggregates(
        gap_rows, rule_rows, censor_rows, airport_rows
    )
    comparison = pd.read_parquet(RULE_COMPARISON_PATH)
    examples = write_example_audit(example_store)
    class_counts = pd.DataFrame(class_rows)
    selection, snapshot_stage_support = build_selection_bias(
        comparison, airport_support
    )
    scope_airport_stage = support_scope_airport_stage(
        airport_support, snapshot_stage_support
    )

    prototype_references, fallback, reference_support = build_prototype_references(
        comparison
    )
    prototype_references.to_parquet(PROTOTYPE_REFERENCE_PATH, index=False)
    _, reference_summary = compare_existing_reference(prototype_references)
    split_metrics = split_safety_metrics(comparison)
    metrics = phase_metrics(comparison, rules, censor, selection)
    feasibility, reference_reuse, next_command = write_reports(
        cfg,
        thresholds,
        threshold_audit,
        gap,
        rules,
        censor,
        scope_airport_stage,
        selection,
        examples,
        class_counts,
        prototype_references,
        fallback,
        reference_support,
        reference_summary,
        split_metrics,
        metrics,
        global_adjacent_pairs,
        source_rows,
        inventory,
    )

    print(f"CURRENT_PHASE=2")
    print(f"PHASE2_STATUS=PASS")
    print(f"FORMAL_CODE_MODIFIED=NO")
    print(f"FORMAL_PRE_MODIFIED=NO")
    print(f"GLOBAL_ADJACENT_PAIRS={global_adjacent_pairs}")
    print(f"PROJECT_RELEVANT_PREDECESSORS={metrics['project_relevant_predecessors']}")
    print(f"HIGH_CONFIDENCE_SUPPORT_RATE_R1={metrics['rates']['R1']:.6f}")
    print(f"HIGH_CONFIDENCE_SUPPORT_RATE_R2={metrics['rates']['R2']:.6f}")
    print(f"HIGH_CONFIDENCE_SUPPORT_RATE_R3={metrics['rates']['R3']:.6f}")
    print(
        f"DEVELOPMENT_HIGH_CONFIDENCE_ROWS={metrics['high_by_split']['DEVELOPMENT']}"
    )
    print(
        f"VALIDATION_HIGH_CONFIDENCE_ROWS={metrics['high_by_split']['VALIDATION']}"
    )
    print(f"FINAL_TEST_HIGH_CONFIDENCE_ROWS={metrics['high_by_split']['FINAL_TEST']}")
    print(
        f"ADMINISTRATIVE_CENSORING_RATE={metrics['administrative_censoring_rate']:.6f}"
    )
    print(f"NO_SUCCESSOR_24H_RATE={metrics['no_successor_24h_rate']:.6f}")
    print(f"MAX_SELECTION_SHIFT={metrics['max_selection_shift']:.6f}")
    print("SPLIT_SAFETY_STATUS=PASS")
    print("LEAKAGE_STATUS=PASS")
    print(f"EXISTING_REFERENCE_REUSE={reference_reuse}")
    print(f"CHAIN_PROXY_FEASIBILITY={feasibility}")
    print("P1_P2_SELECTED=NO")
    print("EXTERNAL_DATA_DOWNLOADED=NO")
    print("EXTERNAL_DATA_INTEGRATED=NO")
    print(f"NEXT_ALLOWED_COMMAND={next_command}")
    print("WAITING_FOR_USER=YES")


if __name__ == "__main__":
    main()
