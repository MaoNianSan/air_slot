from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .input_sources import (
    attach_provenance,
    discover_files,
    mapped,
    normalize_airport,
    read_table,
)


def _decode_sdmx_json(path: Path) -> pd.DataFrame:
    data = json.loads(path.read_text(encoding="utf-8"))
    dimensions = data.get("dimension", {})
    sizes = data.get("size", [])
    ids = data.get("id", [])
    values = data.get("value", {})
    if not dimensions or not sizes or not ids or not values:
        return pd.DataFrame()
    position_to_code: dict[str, dict[int, str]] = {}
    for dim_name, dim_info in dimensions.items():
        index = dim_info.get("category", {}).get("index", {})
        position_to_code[dim_name] = {int(pos): str(code) for code, pos in index.items()}
    strides = [1]
    for size in reversed(sizes[1:]):
        strides.insert(0, strides[0] * size)
    rows = []
    for flat_index_text, value in values.items():
        flat_index = int(flat_index_text)
        remainder = flat_index
        row: dict[str, Any] = {}
        for i, dim_name in enumerate(ids):
            position = remainder // strides[i]
            remainder %= strides[i]
            row[dim_name] = position_to_code.get(dim_name, {}).get(position, str(position))
        row["value"] = value
        rows.append(row)
    return pd.DataFrame(rows)


def _month_number(value: Any) -> pd._libs.missing.NAType | int:
    if pd.isna(value):
        return pd.NA
    text = str(value)
    try:
        if "-" in text:
            return int(text[-2:])
        number = int(float(text))
        return number if 1 <= number <= 12 else pd.NA
    except ValueError:
        return pd.NA


def _period_text(value: Any, reference_year: int) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    try:
        if "-" in text:
            return str(pd.Period(text, freq="M"))
        month = int(float(text))
        if 1 <= month <= 12:
            return str(pd.Period(year=int(reference_year), month=month, freq="M"))
    except (TypeError, ValueError):
        return None
    return None


def _select_eurostat_measure(raw: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Select one non-overlapping monthly measure from the SDMX cube.

    The former loader discarded the SDMX dimensions and summed mutually
    overlapping totals/subtotals.  Passenger references require a single,
    traceable measure instead.
    """
    if source_name == "eurostat_passengers":
        selectors = {
            "freq": "M",
            "unit": "PAS",
            "tra_meas": "PAS_CRD",
            "schedule": "TOT",
            "tra_cov": "TOTAL",
        }
    else:
        selectors = {"freq": "M", "schedule": "TOTAL", "unit": "NR"}
    selected = raw
    for column, value in selectors.items():
        if column in selected.columns:
            selected = selected[selected[column].astype(str).eq(value)]
    return selected.copy()


def load_eurostat(cfg: dict[str, Any], source_name: str) -> pd.DataFrame:
    spec = cfg["sources"][source_name]
    files = discover_files(cfg["project_root"], cfg["data_root"], spec)
    value_name = "passengers" if source_name == "eurostat_passengers" else "commercial_flights"
    frames = []
    for path in files:
        if path.suffix.lower() == ".json":
            raw = _decode_sdmx_json(path)
            if raw.empty:
                continue
            raw = _select_eurostat_measure(raw, source_name)
            airport_col = next((c for c in ["rep_airp", "airport"] if c in raw.columns), None)
            time_col = next((c for c in ["time", "month"] if c in raw.columns), None)
            if airport_col is None or time_col is None:
                continue
            frame = pd.DataFrame({
                "airport": raw[airport_col],
                "raw_airport_code": raw[airport_col],
                "source_period": raw[time_col],
                "month": raw[time_col],
                value_name: raw["value"],
            })
        else:
            raw = read_table(path)
            frame = mapped(raw, spec["columns"], ["airport", "month", value_name])
            frame["raw_airport_code"] = frame["airport"]
            frame["source_period"] = frame["month"]
        frames.append(attach_provenance(frame, path))
    if not frames:
        return pd.DataFrame(columns=[
            "airport", "raw_airport_code", "airport_code_system",
            "source_period", "month", value_name,
        ])
    out = pd.concat(frames, ignore_index=True)
    out["airport"] = out["airport"].map(lambda x: normalize_airport(str(x).split("_")[-1]))
    out["airport_code_system"] = "EUROSTAT_REP_AIRP_ICAO_SUFFIX"
    out["source_period"] = out["source_period"].map(
        lambda value: _period_text(value, int(cfg["reference_year"]))
    )
    out["month"] = out["month"].map(_month_number).astype("Int64")
    out[value_name] = pd.to_numeric(out[value_name], errors="coerce")
    return out


