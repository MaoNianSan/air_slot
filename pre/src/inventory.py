from __future__ import annotations

import re
import tarfile
from pathlib import Path
from typing import Any

import pandas as pd

from .input import discover_files, resolve_source_root, sha256_file
from .progress import progress_iter


STATE_NAME = re.compile(r"states_(\d{4}-\d{2}-\d{2})-(\d{2})\.csv\.tar$")


def _inventory_record(source: str, path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    stat = path.stat()
    record: dict[str, Any] = {
        "source": source,
        "absolute_path": str(path.resolve()),
        "relative_path": str(path),
        "file_name": path.name,
        "format": "".join(path.suffixes).lower().lstrip("."),
        "size_bytes": int(stat.st_size),
        "modified_time": pd.Timestamp(stat.st_mtime, unit="s", tz="UTC"),
        "sha256": sha256_file(path),
        "readable": True,
        "read_error": "",
        "source_standard": spec.get("source_standard", ""),
        "source_version": spec.get("version", ""),
        "date": pd.NaT,
        "hour": pd.NA,
        "formal_eligible": pd.NA,
        "coverage_status": "NOT_APPLICABLE",
    }
    match = STATE_NAME.match(path.name)
    if source == "state_vectors" and match:
        record["date"] = pd.Timestamp(match.group(1))
        record["hour"] = int(match.group(2))
        try:
            with tarfile.open(path, mode="r:*") as archive:
                members = [m for m in archive.getmembers() if m.isfile() and m.name.lower().endswith((".csv", ".csv.gz"))]
                if not members:
                    raise ValueError("no CSV member")
        except Exception as exc:
            record["readable"] = False
            record["read_error"] = str(exc)
    return record


def inventory(cfg: dict[str, Any], *, allow_missing_required: bool = False) -> pd.DataFrame:
    discovered: list[tuple[str, Path, dict[str, Any]]] = []
    for source, spec in cfg["sources"].items():
        if source == "ourairports":
            root = resolve_source_root(cfg["project_root"], cfg["data_root"], spec["root"])
            expected = [root / spec["airports_file"], root / spec["runways_file"]]
            missing_expected = [p for p in expected if not p.exists()]
            if missing_expected and spec.get("required", False) and not allow_missing_required:
                raise FileNotFoundError(f"required OurAirports files missing: {missing_expected}")
            files = [p for p in expected if p.exists()]
        else:
            files = discover_files(cfg["project_root"], cfg["data_root"], spec)
        if not files and spec.get("required", False) and not allow_missing_required:
            raise FileNotFoundError(f"required source has no files: {source}")
        discovered.extend((source, path, spec) for path in files)
    rows = [
        _inventory_record(source, path, spec)
        for source, path, spec in progress_iter(
            discovered,
            total=len(discovered),
            description="Inventory",
            unit="files",
            level=cfg["runtime"]["progress_level"],
        )
    ]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    state = frame[frame["source"] == "state_vectors"].copy()
    if not state.empty:
        day_counts = state[state["readable"]].groupby("date")["hour"].nunique()
        required_hours = int(cfg["validation"]["complete_day_hours"])
        complete_dates = set(day_counts[day_counts >= required_hours].index)
        mask = frame["source"] == "state_vectors"
        frame.loc[mask, "formal_eligible"] = frame.loc[mask, "date"].isin(complete_dates)
        frame.loc[mask, "coverage_status"] = frame.loc[mask].apply(
            lambda row: "FORMAL_COMPLETE_DAY" if bool(row["formal_eligible"]) else (
                "UNREADABLE" if not bool(row["readable"]) else "RETAINED_LEGACY_PARTIAL"
            ), axis=1
        )
    return frame.sort_values(["source", "relative_path"]).reset_index(drop=True)


def state_coverage_calendar(inventory_frame: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    state = inventory_frame[inventory_frame["source"] == "state_vectors"].copy()
    if state.empty:
        return pd.DataFrame(columns=[
            "date", "hour", "file_exists", "archive_readable", "file_count", "row_count", "time_min", "time_max", "formal_eligible", "coverage_status"
        ])
    observed_dates = pd.to_datetime(state["date"], errors="coerce").dropna().dt.normalize().unique()
    if len(observed_dates) == 0:
        return pd.DataFrame()
    rows = []
    complete_hours = int(cfg["validation"]["complete_day_hours"])
    for date in sorted(pd.Timestamp(x) for x in observed_dates):
        subset = state[state["date"] == date]
        readable_hours = set(pd.to_numeric(subset.loc[subset["readable"], "hour"], errors="coerce").dropna().astype(int))
        complete = len(readable_hours) >= complete_hours
        for hour in range(24):
            cell = subset[pd.to_numeric(subset["hour"], errors="coerce") == hour]
            exists = not cell.empty
            readable = bool(cell["readable"].all()) if exists else False
            if complete and exists and readable:
                status = "FORMAL_COMPLETE_DAY"
            elif exists and readable:
                status = "RETAINED_LEGACY_PARTIAL"
            elif exists:
                status = "UNREADABLE"
            else:
                status = "SOURCE_COVERAGE_GAP"
            rows.append({
                "date": date,
                "hour": hour,
                "file_exists": exists,
                "archive_readable": readable,
                "file_count": len(cell),
                "row_count": pd.NA,
                "time_min": pd.NaT,
                "time_max": pd.NaT,
                "formal_eligible": complete and exists and readable,
                "coverage_status": status,
            })
    output = pd.DataFrame(rows)
    if not output.empty:
        output["date"] = pd.to_datetime(output["date"], errors="coerce").dt.normalize()
        output["hour"] = pd.to_numeric(output["hour"], errors="coerce").astype("Int64")
        output["row_count"] = pd.to_numeric(output["row_count"], errors="coerce").astype("Int64")
        output["time_min"] = pd.to_datetime(output["time_min"], utc=True, errors="coerce")
        output["time_max"] = pd.to_datetime(output["time_max"], utc=True, errors="coerce")
        output["formal_eligible"] = output["formal_eligible"].fillna(False).astype(bool)
    return output


def complete_state_dates(coverage: pd.DataFrame, cfg: dict[str, Any]) -> set[pd.Timestamp]:
    if coverage.empty:
        return set()
    complete_hours = int(cfg["validation"]["complete_day_hours"])
    grouped = coverage[coverage["archive_readable"]].groupby("date")["hour"].nunique()
    return {pd.Timestamp(date).normalize() for date, count in grouped.items() if int(count) >= complete_hours}
