from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..input import object_hash
from ..passenger_fit import fit_passenger_reference
from ..shared.flight_identity import aircraft_group, split_for, time_bin
from .contracts import stable_id


def _fit_bounds(cfg: dict[str, Any]) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = cfg["splits"]["train"]
    return pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")


def _reference_row(
    reference_type: str,
    group_key: str,
    statistic: str,
    value: float,
    cell_size: int,
    fallback_level: str,
    source_hash: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    start, end = _fit_bounds(cfg)
    return {
        "reference_id": stable_id(reference_type, group_key, statistic),
        "reference_type": reference_type,
        "group_key": group_key,
        "statistic": statistic,
        "reference_value": value,
        "cell_size": int(cell_size),
        "fallback_level": fallback_level,
        "fit_start_time": start,
        "fit_end_time": end,
        "fit_split": "train",
        "source_hash": source_hash,
    }


def _turnaround_rows(episodes: pd.DataFrame, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    train = episodes[
        episodes["engineering_eligible"].fillna(False).astype(bool)
        & episodes["split"].eq("train")
        & episodes["observed_ground_gap_minutes"].notna()
    ].copy()
    rows: list[dict[str, Any]] = []
    keys = ["turnaround_airport", "aircraft_group", "episode_start_time_bin"]
    for values, group in train.groupby(keys, dropna=False):
        group_key = json.dumps(dict(zip(keys, map(str, values))), sort_keys=True)
        hashes = sorted(
            set(group["predecessor_source_hash"].dropna().astype(str))
            | set(group["successor_source_hash"].dropna().astype(str))
        )
        source_hash = object_hash(hashes)
        gaps = pd.to_numeric(group["observed_ground_gap_minutes"], errors="coerce").dropna()
        rows.append(_reference_row("minimum_turnaround", group_key, "q10", float(gaps.quantile(0.1)), len(gaps), "EXACT_CELL", source_hash, cfg))
        rows.append(_reference_row("typical_turnaround", group_key, "median", float(gaps.median()), len(gaps), "EXACT_CELL", source_hash, cfg))
    return rows


def _observation_rows(
    root: Path,
    source: str,
    cfg: dict[str, Any],
    membership_path: Path | None = None,
) -> list[dict[str, Any]]:
    files = sorted((root / f"source={source}").rglob("*.parquet"))
    if not files:
        return []
    pieces = []
    columns = (
        ["observation_id", "airport_id", "event_time", "flow_count", "source_hash"]
        if source == "flow"
        else ["observation_id", "airport_id", "event_time", "wind_speed", "visibility", "temperature", "source_hash"]
    )
    candidate_membership = membership_path or (root.parent / "observation_membership")
    if candidate_membership.exists() and not candidate_membership.is_dir():
        raise ValueError("REFERENCE_MEMBERSHIP_DATASET_DIRECTORY_REQUIRED")
    for path in files:
        import pyarrow.parquet as pq

        available = set(pq.ParquetFile(path).schema_arrow.names)
        selected_columns = [column for column in columns if column in available]
        frame = pd.read_parquet(path, columns=selected_columns)
        membership = None
        if candidate_membership.is_dir():
            date_directory = path.parent.name
            membership_files = sorted(
                (
                    candidate_membership
                    / f"source={source}"
                    / date_directory
                ).glob("*.parquet")
            )
            if membership_files:
                membership = pd.concat(
                    [
                        pd.read_parquet(
                            membership_file,
                            columns=["observation_id", "source", "split"],
                        )
                        for membership_file in membership_files
                    ],
                    ignore_index=True,
                )
        if membership is not None:
            train_ids = membership[
                membership["source"].eq(source) & membership["split"].eq("train")
            ][["observation_id"]].drop_duplicates()
            frame = frame.merge(train_ids, on="observation_id", how="inner")
        elif "split" in frame:
            frame = frame[frame["split"].eq("train")]
        else:
            frame = frame.iloc[0:0]
        pieces.append(frame)
    nonempty = [piece for piece in pieces if not piece.empty]
    if not nonempty:
        return []
    data = pd.concat(nonempty, ignore_index=True).drop_duplicates("observation_id", keep="last")
    data = data.drop_duplicates(["airport_id", "event_time"], keep="last")
    rows: list[dict[str, Any]] = []
    fields = ["flow_count"] if source == "flow" else ["wind_speed", "visibility", "temperature"]
    for airport, group in data.groupby("airport_id", dropna=False):
        group_key = json.dumps({"airport": str(airport)}, sort_keys=True)
        source_hash = object_hash(sorted(group["source_hash"].dropna().astype(str).unique()))
        for field in fields:
            values = pd.to_numeric(group[field], errors="coerce").dropna()
            if values.empty:
                continue
            statistic = "q90" if field == "flow_count" else "median"
            value = float(values.quantile(0.9)) if field == "flow_count" else float(values.median())
            rows.append(_reference_row(f"{source}_{field}", group_key, statistic, value, len(values), "AIRPORT_TRAIN", source_hash, cfg))
    return rows


def _passenger_rows(
    flights: pd.DataFrame,
    passengers: pd.DataFrame,
    commercial: pd.DataFrame,
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    if passengers.empty or commercial.empty:
        return []
    legs = flights.copy()
    legs["split"] = legs["firstseen_utc"].map(lambda value: split_for(value, cfg["splits"]))
    legs["candidate_episode"] = legs["is_predecessor_seed"] & legs["split"].notna()
    legs["aircraft_group"] = legs.get("typecode", pd.Series(pd.NA, index=legs.index)).map(aircraft_group)
    legs["firstseen_time_bin"] = legs["firstseen_utc"].map(time_bin)
    legs["episode_id"] = legs["flight_id"]
    reference = fit_passenger_reference(passengers, commercial, legs, cfg)
    rows: list[dict[str, Any]] = []
    for record in reference.artifact_frame().itertuples(index=False):
        key = json.dumps({"destination": str(record.destination), "source_period": str(record.source_period)}, sort_keys=True)
        source_hash = object_hash(json.loads(str(record.raw_hashes)))
        rows.append(_reference_row("passenger_load_factor", key, "load_factor", float(record.load_factor) if pd.notna(record.load_factor) else np.nan, int(record.support_size), str(record.evidence_status), source_hash, cfg))
        rows.append(_reference_row("passenger_per_flight", key, "ratio", float(record.passenger_per_flight) if pd.notna(record.passenger_per_flight) else np.nan, int(record.support_size), str(record.evidence_status), source_hash, cfg))
    return rows


def build_references(
    episodes: pd.DataFrame,
    flights: pd.DataFrame,
    observation_root: Path,
    passengers: pd.DataFrame,
    commercial: pd.DataFrame,
    cfg: dict[str, Any],
    membership_path: Path | None = None,
) -> pd.DataFrame:
    rows = _turnaround_rows(episodes, cfg)
    rows.extend(_observation_rows(observation_root, "flow", cfg, membership_path))
    rows.extend(_observation_rows(observation_root, "weather", cfg, membership_path))
    rows.extend(_passenger_rows(flights, passengers, commercial, cfg))
    rows.append(_reference_row("taxi_out", "GLOBAL", "UNSUPPORTED", np.nan, 0, "UNSUPPORTED", object_hash("NO_AOBT_SOURCE"), cfg))
    frame = pd.DataFrame(rows).sort_values(["reference_type", "group_key", "statistic"], kind="mergesort")
    for column in ["fit_start_time", "fit_end_time"]:
        frame[column] = pd.to_datetime(frame[column], utc=True)
    return frame.reset_index(drop=True)
