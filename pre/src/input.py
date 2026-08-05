from __future__ import annotations

import gzip
import hashlib
import json
import tarfile
import time
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np
import pandas as pd

from .input_sources import (
    attach_provenance,
    discover_files,
    iter_csv_tar,
    mapped,
    normalize_airport,
    read_table,
    resolve_source_root,
    sha256_file,
)
from .progress import progress_iter, stage_message


AIRCRAFT_COLUMNS = [
    "icao24", "registration", "manufacturer", "manufacturer_icao", "model", "typecode",
    "serialnumber", "line_number", "icao_aircraft_type", "operator", "operator_callsign",
    "operator_icao", "operator_iata", "owner", "test_reg", "emitter_category",
]




def object_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_icao24(value: Any) -> str:
    text = "" if pd.isna(value) else str(value).strip().lower()
    return text.zfill(6) if text else ""




def normalize_text(value: Any, fallback: str = "UNKNOWN") -> str:
    text = "" if pd.isna(value) else str(value).strip()
    return text if text else fallback














def _parse_time(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    # pandas may raise before applying errors="coerce" when NumPy is configured
    # to raise on an infinite/out-of-nanosecond-range multiplication.  Mask such
    # source values first; the invalid record remains explicitly NaT and is later
    # excluded with INVALID_TIME rather than being silently repaired.
    valid_numeric = numeric.notna() & np.isfinite(numeric) & numeric.between(-9_223_372_036, 9_223_372_036)
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns, UTC]")
    if valid_numeric.any():
        result.loc[valid_numeric] = pd.to_datetime(numeric.loc[valid_numeric], unit="s", utc=True, errors="coerce")
    text_mask = numeric.isna() & series.notna()
    if text_mask.any():
        result.loc[text_mask] = pd.to_datetime(series.loc[text_mask], utc=True, errors="coerce")
    return result


def load_flightlist(cfg: dict[str, Any], formal_dates: set[pd.Timestamp] | None = None) -> pd.DataFrame:
    """Load only flight legs relevant to the formal observation dates and airport cohort."""
    spec = cfg["sources"]["flightlist"]
    files = discover_files(cfg["project_root"], cfg["data_root"], spec)
    if not files:
        raise FileNotFoundError("SOURCE_NOT_PROVIDED: flightlist")
    normalized_dates = {pd.Timestamp(value).normalize().tz_localize(None) if pd.Timestamp(value).tzinfo else pd.Timestamp(value).normalize() for value in (formal_dates or set())}
    lookback_days = int(
        cfg.get("predecessor_matching", {}).get("flightlist_lookback_days", 0)
    )
    source_dates = set(normalized_dates)
    for value in normalized_dates:
        source_dates.update(
            value - pd.Timedelta(days=offset)
            for offset in range(1, lookback_days + 1)
        )
    eligible_airports = set(cfg["airports"]["core"] if cfg["validation"].get("strict_core_support", True) else cfg["airports"]["m1"])
    chunk_rows = int(cfg.get("flightlist", {}).get("chunk_rows", 250_000))
    frames = []
    progress_level = cfg["runtime"]["progress_level"]
    started = time.monotonic()
    last_heartbeat = started
    usecols = list(dict.fromkeys(
        spec["columns"][name]
        for name in ("icao24", "origin", "destination", "firstseen", "lastseen")
        if name in spec["columns"]
    ))
    for path in progress_iter(files, total=len(files), description="Flightlists", unit="files", level=progress_level):
        suffixes = "".join(path.suffixes).lower()
        if suffixes.endswith(".parquet"):
            chunks = [pd.read_parquet(path)]
        else:
            chunks = pd.read_csv(path, usecols=usecols, low_memory=False, chunksize=chunk_rows)
        file_hash = sha256_file(path)
        offset = 0
        for raw in chunks:
            frame = mapped(raw, spec["columns"], ["icao24", "origin", "destination", "firstseen", "lastseen"])
            frame["icao24"] = frame["icao24"].map(normalize_icao24)
            frame["origin"] = frame["origin"].map(normalize_airport)
            frame["destination"] = frame["destination"].map(normalize_airport)
            frame["firstseen"] = _parse_time(frame["firstseen"])
            frame["lastseen"] = _parse_time(frame["lastseen"])
            keep = frame["destination"].isin(eligible_airports)
            if source_dates:
                dates = frame["firstseen"].dt.tz_convert("UTC").dt.normalize().dt.tz_localize(None)
                keep &= dates.isin(source_dates)
            frame = frame.loc[keep].copy()
            if not frame.empty:
                original_positions = frame.index.to_numpy()
                frame["raw_source_file"] = str(path)
                frame["raw_source_hash"] = file_hash
                frame["source_record_id"] = [f"{path.name}:{offset + int(position)}" for position in original_positions]
                frames.append(frame.reset_index(drop=True))
            offset += len(raw)
            now = time.monotonic()
            if now - last_heartbeat >= 120:
                stage_message(
                    f"Flightlist filter: {path.name}; rows scanned={offset:,}; retained={sum(len(x) for x in frames):,}; elapsed={(now-started)/60:.1f}m",
                    level=progress_level,
                )
                last_heartbeat = now
    if not frames:
        raise FileNotFoundError("flightlist contains no rows for formal dates and eligible airports")
    return pd.concat(frames, ignore_index=True)


def load_aircraft(cfg: dict[str, Any]) -> pd.DataFrame:
    spec = cfg["sources"]["aircraft"]
    files = discover_files(cfg["project_root"], cfg["data_root"], spec)
    frames = []
    for path in files:
        try:
            raw = read_table(path)
            if "icao24" not in raw.columns:
                raw = pd.read_csv(path, names=AIRCRAFT_COLUMNS, low_memory=False, encoding_errors="replace")
        except Exception:
            raw = pd.read_csv(path, names=AIRCRAFT_COLUMNS, low_memory=False, encoding_errors="replace")
        frame = mapped(raw, spec["columns"], ["icao24"])
        frames.append(attach_provenance(frame, path))
    if not frames:
        return pd.DataFrame(columns=["icao24", "typecode", "raw_source_file", "raw_source_hash", "source_record_id"])
    out = pd.concat(frames, ignore_index=True)
    out["icao24"] = out["icao24"].map(normalize_icao24)
    return out.drop_duplicates("icao24", keep="last")


def load_airports(cfg: dict[str, Any]) -> pd.DataFrame:
    spec = cfg["sources"]["ourairports"]
    root = resolve_source_root(cfg["project_root"], cfg["data_root"], spec["root"])
    airport_path = root / spec["airports_file"]
    runway_path = root / spec["runways_file"]
    if not airport_path.exists() or not runway_path.exists():
        raise FileNotFoundError(f"OurAirports files missing under {root}")
    airports = pd.read_csv(airport_path, low_memory=False)
    runways = pd.read_csv(runway_path, low_memory=False)
    am = spec["airport_columns"]
    rm = spec["runway_columns"]
    out = pd.DataFrame({
        "airport": airports[am["ident"]].map(normalize_airport),
        "airport_latitude": pd.to_numeric(airports[am["latitude"]], errors="coerce"),
        "airport_longitude": pd.to_numeric(airports[am["longitude"]], errors="coerce"),
        "airport_type": airports[am.get("type")].astype("string") if am.get("type") in airports.columns else "UNKNOWN",
    })
    runway_frame = pd.DataFrame({
        "airport": runways[rm["airport_ident"]].map(normalize_airport),
        "closed": pd.to_numeric(runways[rm["closed"]], errors="coerce").fillna(0).astype(int),
    })
    counts = runway_frame[runway_frame["closed"] == 0].groupby("airport").size().rename("runway_count")
    out = out.drop_duplicates("airport").merge(counts, on="airport", how="left")
    out["source_version"] = spec.get("version", "frozen")
    out["raw_source_hash"] = sha256_file(airport_path) + ":" + sha256_file(runway_path)
    return out


def load_metar(cfg: dict[str, Any]) -> pd.DataFrame:
    spec = cfg["sources"]["metar"]
    files = discover_files(cfg["project_root"], cfg["data_root"], spec)
    if not files:
        raise FileNotFoundError("SOURCE_NOT_PROVIDED: metar")
    frames = []
    progress_level = cfg["runtime"]["progress_level"]
    for path in progress_iter(files, total=len(files), description="METAR", unit="files", level=progress_level):
        raw = read_table(path)
        frame = mapped(raw, spec["columns"], ["airport", "observation_time"])
        for raw_column in raw.columns:
            if raw_column not in frame.columns:
                frame[str(raw_column)] = raw[raw_column]
        if "precipitation_flag" in raw.columns:
            frame["precipitation_flag"] = raw["precipitation_flag"]
        frames.append(attach_provenance(frame, path))
    out = pd.concat(frames, ignore_index=True)
    out["airport"] = out["airport"].map(normalize_airport)
    out["observation_time"] = pd.to_datetime(out["observation_time"], utc=True, errors="coerce")
    out["availability_time"] = out["observation_time"] + pd.to_timedelta(cfg["availability_lag_minutes"].get("metar", 0), unit="m")
    for col in ["wind_speed", "wind_gust", "visibility", "ceiling", "temperature", "dewpoint"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    weather_code = out.get(
        "weather_code",
        pd.Series(pd.NA, index=out.index, dtype="string"),
    )
    out["weather_code"] = (
        weather_code.astype("string")
        .str.strip()
        .fillna("UNKNOWN")
        .replace("", "UNKNOWN")
    )
    precipitation_pattern = r"(?:DZ|RA|SN|SG|IC|PL|GR|GS|UP)"
    derived_precipitation = out["weather_code"].str.upper().str.contains(
        precipitation_pattern, regex=True, na=False,
    ).astype(bool)
    source_flag = out.get("precipitation_flag")
    if source_flag is not None and source_flag.notna().any():
        normalized = source_flag.astype("string").str.strip().str.lower()
        true_values = {"1", "true", "t", "yes", "y"}
        false_values = {"0", "false", "f", "no", "n", ""}
        invalid = normalized.notna() & ~normalized.isin(true_values | false_values)
        if invalid.any():
            examples = normalized.loc[invalid].drop_duplicates().head(5).tolist()
            raise ValueError(f"Unsupported precipitation_flag values: {examples}")
        supplied = normalized.notna()
        derived_precipitation.loc[supplied] = normalized.loc[supplied].isin(true_values).astype(bool)
    out["precipitation_flag"] = derived_precipitation.astype(bool)
    out["temperature_dewpoint_spread"] = out["temperature"] - out["dewpoint"]
    return out.sort_values(["airport", "availability_time"]).reset_index(drop=True)



def load_eurostat(cfg: dict[str, Any], source_name: str) -> pd.DataFrame:
    from .input_eurostat import load_eurostat as load

    return load(cfg, source_name)












def require_parquet_engine() -> None:
    try:
        import pyarrow  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("pyarrow is required. Run: python -m pip install -r requirements.txt") from exc


def write_parquet(frame: pd.DataFrame, path: str | Path) -> None:
    require_parquet_engine()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, compression="zstd")


def write_json(value: Any, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
