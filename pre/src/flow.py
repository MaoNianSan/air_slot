from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .reference import AirportReference, FlowReference
from .state import StateStore


def _haversine_vector(lat: pd.Series, lon: pd.Series, lat0: float, lon0: float) -> pd.Series:
    lat1 = np.radians(pd.to_numeric(lat, errors="coerce"))
    lon1 = np.radians(pd.to_numeric(lon, errors="coerce"))
    lat2 = math.radians(lat0)
    lon2 = math.radians(lon0)
    dlat = lat1 - lat2
    dlon = lon1 - lon2
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * math.cos(lat2) * np.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def attach_flow(
    snapshots: pd.DataFrame,
    state_store: StateStore,
    airport_reference: AirportReference,
    cfg: dict[str, Any],
) -> pd.DataFrame:
    """Attach airport flow from pre-mapped airport/hour cache partitions.

    The extraction pass already applies the airport radius.  Here each airport
    is loaded once per needed day/hour, then sorted-window indexes are used;
    no snapshot re-scans a daily raw flow table or recomputes distances.
    """
    output = snapshots.copy()
    pieces = []
    for date, group in output.groupby(output["decision_time_utc"].dt.tz_convert("UTC").dt.normalize().dt.tz_localize(None), sort=True):
        records: dict[Any, tuple[Any, str, float, str]] = {}
        lookback = pd.to_timedelta(cfg["flow"]["lookback_minutes"], unit="m")
        for airport, subset_snapshots in group.groupby("airport", sort=False):
            try:
                airport_reference.resolve(str(airport))
            except KeyError:
                records.update({idx: (np.nan, "UNOBSERVED", 1.0, "SOURCE_NOT_PROVIDED") for idx in subset_snapshots.index})
                continue
            min_time = subset_snapshots["decision_time_utc"].min() - lookback
            snapshot_hours = subset_snapshots["decision_time_utc"].dt.hour.tolist()
            hours = sorted(set(snapshot_hours + [int((h - 1) % 24) for h in snapshot_hours] + [int(min_time.hour)]))
            dates = [pd.Timestamp(date)]
            if min_time.date() < pd.Timestamp(date).date(): dates.append(pd.Timestamp(date) - pd.Timedelta(days=1))
            flow = pd.concat([state_store.load("flow", d, hours=hours if d == pd.Timestamp(date) else [int(min_time.hour)], airport=str(airport), columns=["event_time", "availability_time", "icao24"]) for d in dates], ignore_index=True)
            # Read and sort each airport/day once.  Each state is admitted when
            # it becomes available, then evicted from a heap when it leaves the
            # lookback.  This preserves distinct-icao24 semantics without a
            # snapshot-times-flow-table rescan.
            flow = flow.sort_values(["availability_time", "event_time"], kind="mergesort").reset_index(drop=True) if not flow.empty else flow
            availability = flow["availability_time"].to_numpy(dtype="datetime64[ns]") if not flow.empty else np.array([], dtype="datetime64[ns]")
            events = flow["event_time"].to_numpy(dtype="datetime64[ns]") if not flow.empty else np.array([], dtype="datetime64[ns]")
            codes = flow["icao24"].astype(str).to_numpy() if not flow.empty else np.array([], dtype=object)
            import heapq
            active: dict[str, int] = {}
            expiry: list[tuple[np.datetime64, int, str]] = []
            next_available = 0
            for idx, row in subset_snapshots.sort_values("decision_time_utc", kind="mergesort").iterrows():
                decision = row["decision_time_utc"]
                status = _coverage_status(state_store.coverage, pd.Timestamp(date), decision.hour)
                if status == "SOURCE_COVERAGE_GAP":
                    records[idx] = (np.nan, "UNOBSERVED", 0.0, "SOURCE_COVERAGE_GAP"); continue
                decision64 = decision.tz_localize(None).to_datetime64()
                # availability is monotone here; state availability cannot
                # precede event time in the declared source contract.
                while next_available < len(flow) and availability[next_available] <= decision64:
                    event = events[next_available]
                    code = codes[next_available]
                    if event <= decision64 and event >= (decision - lookback).tz_localize(None).to_datetime64():
                        active[code] = active.get(code, 0) + 1
                        heapq.heappush(expiry, (event, next_available, code))
                    next_available += 1
                lower = (decision - lookback).tz_localize(None).to_datetime64()
                while expiry and expiry[0][0] < lower:
                    _, _, code = heapq.heappop(expiry)
                    active[code] -= 1
                    if active[code] <= 0:
                        del active[code]
                records[idx] = (float(len(active)), "DERIVED", 1.0, "")
        rows = pd.DataFrame.from_dict(
            records,
            orient="index",
            columns=["airport_flow_pressure", "flow_evidence_status", "flow_source_coverage", "flow_missing_reason"],
        ).reindex(group.index)
        piece = group.join(rows)
        pieces.append(piece)
    result = pd.concat(pieces).sort_index() if pieces else output
    if "airport_flow_pressure" in result:
        result["airport_flow_pressure"] = pd.to_numeric(result["airport_flow_pressure"], errors="coerce")
    if "flow_source_coverage" in result:
        result["flow_source_coverage"] = pd.to_numeric(result["flow_source_coverage"], errors="coerce")
    return result


def _coverage_status(coverage: pd.DataFrame, date: pd.Timestamp, hour: int) -> str:
    if coverage.empty:
        return "SOURCE_COVERAGE_GAP"
    subset = coverage[(coverage["date"] == pd.Timestamp(date).normalize()) & (coverage["hour"] == int(hour))]
    return str(subset.iloc[0]["coverage_status"]) if not subset.empty else "SOURCE_COVERAGE_GAP"


def attach_flow_margins(snapshots: pd.DataFrame, flow_reference: FlowReference, cfg: dict[str, Any]) -> pd.DataFrame:
    keys = snapshots[["airport", "time_bin"]].astype(str).drop_duplicates()
    reference_rows = []
    for airport, time_bin in keys.itertuples(index=False):
        try:
            threshold, level, _ = flow_reference.resolve(airport, time_bin, "flow_p90")
            p05, _, _ = flow_reference.resolve(airport, time_bin, "flow_p05")
            p95, _, _ = flow_reference.resolve(airport, time_bin, "flow_p95")
            reference_rows.append((airport, time_bin, threshold, p05, p95, level))
        except Exception:
            reference_rows.append((airport, time_bin, np.nan, np.nan, np.nan, "MISSING"))
    reference = pd.DataFrame(
        reference_rows,
        columns=["airport", "time_bin", "_capacity_threshold", "_capacity_p05", "_capacity_p95", "_capacity_fallback_level"],
    )
    result = snapshots.reset_index(drop=True).copy()
    result["_join_airport"] = result["airport"].astype(str)
    result["_join_time_bin"] = result["time_bin"].astype(str)
    result = result.merge(
        reference,
        left_on=["_join_airport", "_join_time_bin"],
        right_on=["airport", "time_bin"],
        how="left",
        validate="many_to_one",
        suffixes=("", "_reference"),
        sort=False,
    ).drop(columns=["_join_airport", "_join_time_bin", "airport_reference", "time_bin_reference"])
    flow = pd.to_numeric(result["airport_flow_pressure"], errors="coerce")
    reference_time = pd.to_numeric(result["reference_movement_time"], errors="coerce")
    elapsed = pd.to_numeric(result["elapsed_minutes"], errors="coerce")
    result["episode_capacity_margin"] = (
        result["_capacity_threshold"] - flow
    ) * float(cfg["rules"]["capacity_margin_scale_minutes"])
    result["episode_ops_margin"] = float(cfg["rules"]["operations_margin_minutes"])
    result["lead_time_margin"] = reference_time - elapsed
    components = result[["episode_capacity_margin", "episode_ops_margin", "lead_time_margin"]]
    complete = components.notna().all(axis=1)
    result["execution_window_margin"] = components.min(axis=1).where(complete)
    result["window_margin_complete"] = complete
    missing_capacity = result["_capacity_threshold"].isna()
    missing_flow = flow.isna() & ~missing_capacity
    missing_reference = reference_time.isna()
    reason = pd.Series("", index=result.index, dtype="string")
    reason = reason.mask(missing_flow, "airport_flow_pressure")
    reason = reason.mask(missing_capacity, "capacity_threshold")
    reason = reason.mask(missing_reference & reason.eq(""), "reference_movement_time")
    reason = reason.mask(missing_reference & reason.ne(""), reason + ",reference_movement_time")
    result["window_margin_missing_components"] = reason
    return result
