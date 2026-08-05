from __future__ import annotations

import time
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

from ..episode import stable_flight_id
from ..input import _parse_time, normalize_icao24
from ..input_sources import discover_files, normalize_airport, sha256_file
from ..progress import progress_iter, stage_message


OPTIONAL_FLIGHT_COLUMNS = [
    "callsign",
    "number",
    "registration",
    "typecode",
    "latitude_1",
    "longitude_1",
    "altitude_1",
    "latitude_2",
    "longitude_2",
    "altitude_2",
]


FLIGHTLIST_MONTH = re.compile(r"flightlist_(\d{6})")


def _source_dates(
    formal_dates: set[pd.Timestamp], cfg: dict[str, Any]
) -> set[pd.Timestamp]:
    normalized: list[pd.Timestamp] = []
    for value in formal_dates:
        timestamp = pd.Timestamp(value).normalize()
        normalized.append(
            timestamp.tz_localize("UTC")
            if timestamp.tzinfo is None
            else timestamp.tz_convert("UTC")
        )
    normalized.sort()
    if not normalized:
        raise ValueError("CORE_FORMAL_DATES_EMPTY")
    ceiling = float(
        cfg["predecessor_matching"]["administrative_hard_ceiling_minutes"]
    )
    forward_days = int(math.ceil(ceiling / 1440.0))
    return {
        value + pd.Timedelta(days=offset)
        for value in normalized
        for offset in range(forward_days + 1)
    }


def _relevant_files(files: list[Path], dates: set[pd.Timestamp]) -> list[Path]:
    months = {value.strftime("%Y%m") for value in dates}
    selected = []
    for path in files:
        match = FLIGHTLIST_MONTH.search(path.name)
        if match is None or match.group(1) in months:
            selected.append(path)
    return selected


def _read_chunks(path: Path, wanted: set[str], chunk_rows: int):
    if "".join(path.suffixes).lower().endswith(".parquet"):
        yield pd.read_parquet(path, columns=list(wanted))
        return
    yield from pd.read_csv(
        path,
        usecols=lambda column: column in wanted,
        chunksize=chunk_rows,
        low_memory=False,
    )


def _normalize_chunk(
    raw: pd.DataFrame,
    path: Path,
    file_hash: str,
    offset: int,
    mapping: dict[str, str],
) -> pd.DataFrame:
    reverse = {source: target for target, source in mapping.items()}
    frame = raw.rename(columns=reverse).copy()
    required = {"icao24", "origin", "destination", "firstseen", "lastseen"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("CORE_FLIGHTLIST_COLUMNS_MISSING:" + ",".join(missing))
    frame["icao24"] = frame["icao24"].map(normalize_icao24)
    frame["origin"] = frame["origin"].map(normalize_airport)
    frame["destination"] = frame["destination"].map(normalize_airport)
    frame["firstseen_utc"] = _parse_time(frame.pop("firstseen"))
    frame["lastseen_utc"] = _parse_time(frame.pop("lastseen"))
    frame["raw_source_file"] = str(path)
    frame["raw_source_hash"] = file_hash
    frame["source_record_id"] = [
        f"{path.name}:{offset + int(position)}" for position in frame.index
    ]
    return frame.reset_index(drop=True)


def load_core_flights(
    cfg: dict[str, Any], formal_dates: set[pd.Timestamp]
) -> pd.DataFrame:
    """Load predecessor seeds and every possible immediate next observed leg."""
    spec = cfg["sources"]["flightlist"]
    files = discover_files(cfg["project_root"], cfg["data_root"], spec)
    if not files:
        raise FileNotFoundError("SOURCE_NOT_PROVIDED: flightlist")
    mapping = dict(spec["columns"])
    wanted = set(mapping.values()) | set(OPTIONAL_FLIGHT_COLUMNS)
    source_dates = _source_dates(formal_dates, cfg)
    files = _relevant_files(files, source_dates)
    chunk_rows = int(cfg.get("flightlist", {}).get("chunk_rows", 250_000))
    frames: list[pd.DataFrame] = []
    started = time.monotonic()
    for path in progress_iter(
        files,
        total=len(files),
        description="Core flightlists",
        unit="files",
        level=cfg["runtime"]["progress_level"],
    ):
        file_hash = cfg.get("raw_hashes", {}).get(str(path.resolve())) or sha256_file(path)
        offset = 0
        for raw in _read_chunks(path, wanted, chunk_rows):
            frame = _normalize_chunk(raw, path, file_hash, offset, mapping)
            dates = frame["firstseen_utc"].dt.normalize()
            in_window = dates.isin(source_dates)
            if in_window.any():
                frames.append(frame.loc[in_window].copy())
            offset += len(raw)
    if not frames:
        raise FileNotFoundError("CORE_FLIGHTLIST_NO_ROWS_IN_WINDOW")
    flights = pd.concat(frames, ignore_index=True)
    core_airports = set(cfg["airports"]["core"])
    formal = {pd.Timestamp(value).normalize().tz_localize(None) for value in formal_dates}
    start_dates = flights["firstseen_utc"].dt.normalize().dt.tz_localize(None)
    seed = flights["destination"].isin(core_airports) & start_dates.isin(formal)
    aircraft = set(flights.loc[seed, "icao24"])
    flights = flights[flights["icao24"].isin(aircraft)].copy()
    flights["is_predecessor_seed"] = seed.loc[flights.index].astype(bool)
    flights["flight_id"] = [
        stable_flight_id(code, origin, destination, firstseen, lastseen)
        if pd.notna(firstseen) and pd.notna(lastseen)
        else None
        for code, origin, destination, firstseen, lastseen in zip(
            flights["icao24"],
            flights["origin"],
            flights["destination"],
            flights["firstseen_utc"],
            flights["lastseen_utc"],
        )
    ]
    flights = flights.sort_values(
        ["icao24", "firstseen_utc", "lastseen_utc", "flight_id"],
        kind="mergesort",
    )
    flights = flights.drop_duplicates("flight_id", keep="first").reset_index(drop=True)
    stage_message(
        f"Core flightlist loaded: {len(flights):,} rows; "
        f"predecessor seeds={int(flights['is_predecessor_seed'].sum()):,}; "
        f"elapsed={(time.monotonic() - started):.1f}s",
        level=cfg["runtime"]["progress_level"],
    )
    return flights
