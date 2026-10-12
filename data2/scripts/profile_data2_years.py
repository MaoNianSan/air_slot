# -*- coding: utf-8 -*-
"""Per-year profiling for the data2_2017_2022 instance (M1/M2, PROFILING_ONLY).

    python data2/scripts/profile_data2_years.py                 # all six years
    python data2/scripts/profile_data2_years.py --years 2019    # single year
    python data2/scripts/profile_data2_years.py --force --years 2017

Scope guards (hard constraints for this round):
- reads data2/raw READ-ONLY; writes only under data2/reports/multiyear_profiling/;
- no PRE pipeline, no training, no reference fitting, no episode
  materialization, no train/test split, no sampling, no COVID reweighting;
- per-year statistics only (never pooled totals);
- the instance contract is PROFILING_ONLY (model/PRE/instances/contract.py):
  PRE_ENABLED=false, EXPERIMENT_ENABLED=false, temporal split undefined.

Reuse chain (audited at runtime by static_reuse_audit - the audit is also
asserted by tests/contract/test_data2_multiyear_instance_contract.py):
every PRE function reused below is verified free of the legacy temporal-split
machinery (cohort.split_for_date / DATA2_TEMPORAL_SPLIT / FINAL_TEST_* /
"2019-" month keys / year==2019 guards). The split-dependent functions in
model/PRE/episode/containment.py are NOT reused except the pure-arithmetic
episode_node_count; chain eligibility here is structural (aircraft continuity,
airport continuity, bounded gate gap, orderable schedule window) with the
frozen SAME_AIRCRAFT_AIRPORT_GAP@1.0.0 parameters (max_gap_minutes=360).

Path layout (per year, never overwriting across years):
    data2/reports/multiyear_profiling/{year}/<table>.csv
    data2/reports/multiyear_profiling/data2_multiyear_profiling_audit.{json,md}
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from model.common.errors import ContractError
from model.PRE.canonical.data2_timestamps import (
    resolve_bts_actual_timestamp,
    resolve_bts_event_clock,
)
from model.PRE.canonical.normalization_common import (
    deterministic_id,
    missing,
    number,
)
from model.PRE.canonical.timezone import infer_rollover, local_hhmm_to_utc
from model.PRE.episode.builder import build_data2_episode_chain
from model.PRE.episode.containment import episode_node_count

REPO = Path(__file__).resolve().parents[2]
DATA2 = REPO / "data2"
RAW = DATA2 / "raw"
OUT_ROOT = DATA2 / "reports" / "multiyear_profiling"
YEARS = (2017, 2018, 2019, 2020, 2021, 2022)
QUANTILES = (0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99)
MAX_GAP_MINUTES = 360          # frozen D2-CHAIN-GATE-GAP parameter
INSTANCE_ID = "data2_2017_2022"

PROJECTED_ONTIME_COLUMNS = (
    "FlightDate", "Reporting_Airline", "Tail_Number",
    "Flight_Number_Reporting_Airline", "Origin", "Dest",
    "CRSDepTime", "CRSArrTime", "DepTime", "ArrTime",
    "WheelsOff", "WheelsOn", "TaxiOut", "TaxiIn",
    "DepDelay", "ArrDelay", "DepDelayMinutes", "ArrDelayMinutes",
    "Cancelled", "Diverted",
)

REUSE_ALLOWLIST = {
    "resolve_bts_actual_timestamp": "model.PRE.canonical.data2_timestamps",
    "resolve_bts_event_clock": "model.PRE.canonical.data2_timestamps",
    "local_hhmm_to_utc": "model.PRE.canonical.timezone",
    "infer_rollover": "model.PRE.canonical.timezone",
    "deterministic_id": "model.PRE.canonical.normalization_common",
    "missing": "model.PRE.canonical.normalization_common",
    "number": "model.PRE.canonical.normalization_common",
    "build_data2_episode_chain": "model.PRE.episode.builder",
    "episode_node_count": "model.PRE.episode.containment",
}

STATIC_FORBIDDEN_TOKENS = (
    "split_for_date",
    "DATA2_TEMPORAL_SPLIT",
    "FINAL_TEST_START",
    "FINAL_TEST",
    'startswith("2019-',
    "month_key",
    "== 2019",
    "!= 2019",
    "date(2019",
)


def static_reuse_audit() -> dict:
    """Verify no reused PRE function depends on legacy split machinery."""
    clean, violations = [], []
    for function_name, module_name in sorted(REUSE_ALLOWLIST.items()):
        module = __import__(module_name, fromlist=[function_name])
        function = getattr(module, function_name)
        source = inspect.getsource(function)
        hits = [token for token in STATIC_FORBIDDEN_TOKENS if token in source]
        if hits:
            violations.append({"function": f"{module_name}.{function_name}",
                               "tokens": hits})
        else:
            clean.append(f"{module_name}.{function_name}")
    return {"status": "PASS" if not violations else "FAIL",
            "clean_functions": clean, "violations": violations}


# --------------------------------------------------------------- helpers --

def _git(*args: str) -> str:
    out = subprocess.run(["git", "-C", str(REPO), *args],
                         capture_output=True, text=True)
    return (out.stdout + out.stderr).strip()


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_zones() -> dict[str, str]:
    path = DATA2 / "refs" / "us_airport_timezones.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {row["iata"]: row["timezone"] for row in csv.DictReader(stream)}


def load_station_map() -> dict[str, str]:
    """Frozen airport -> NOAA station mapping (only the 48 airports whose
    station files exist in the frozen 2019 raw universe are mapped)."""
    mapping = {}
    path = DATA2 / "refs" / "weather_station_map.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            station = row["station"].strip()
            if len(station) == 10:  # zero-pad the WBAN segment
                station = station[:6] + "0" + station[6:]
            if (RAW / "weather" / "noaa" / "2019" / f"{station}.csv").is_file():
                mapping[row["airport"].strip()] = station
    return mapping


def quantile_rows(name: str, values: np.ndarray) -> list[dict]:
    finite = values[np.isfinite(values)]
    rows = []
    for q in QUANTILES:
        value = float(np.quantile(finite, q)) if finite.size else None
        rows.append({"metric": name, "quantile": f"p{int(q * 100):02d}",
                     "value": value})
    rows.append({"metric": name, "quantile": "mean",
                 "value": round(float(finite.mean()), 4) if finite.size else None})
    rows.append({"metric": name, "quantile": "n_finite",
                 "value": int(finite.size)})
    return rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames,
                                lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


# --------------------------------------------------------- on-time pass --

def ontime_month_files(year: int) -> list[Path | None]:
    base = RAW / "bts" / "ontime" / str(year)
    files = []
    for month in range(1, 13):
        matches = sorted((base / f"month={month:02d}").glob("*.csv"))
        files.append(matches[0] if matches else None)
    return files


def build_episode_rows(frame: "pd.DataFrame",
                       zones: dict[str, str]) -> tuple[list[dict], Counter]:
    """Mirror the production lightweight projection (skips counted by reason),
    then dedupe ordering keys exactly as the chain rule requires."""
    skipped: Counter = Counter()
    rows: list[dict] = []
    columns = {name: frame[name].tolist() for name in PROJECTED_ONTIME_COLUMNS}
    date_cache: dict[str, date] = {}
    order_keys_seen: set[tuple] = set()
    duplicates = 0
    for index in range(len(frame)):
        origin = columns["Origin"][index]
        destination = columns["Dest"][index]
        zone_origin = zones.get(origin)
        zone_dest = zones.get(destination)
        tail = columns["Tail_Number"][index].strip()
        flight_date = columns["FlightDate"][index]
        if (zone_origin is None or zone_dest is None or missing(tail)
                or missing(flight_date)):
            skipped["zone_or_identity_missing"] += 1
            continue
        if (number(columns["Cancelled"][index]) or 0.0) > 0:
            skipped["cancelled"] += 1
            continue
        if (number(columns["Diverted"][index]) or 0.0) > 0:
            skipped["diverted"] += 1
            continue
        day = date_cache.get(flight_date)
        if day is None:
            try:
                day = date.fromisoformat(flight_date[:10])
            except ValueError:
                skipped["bad_flight_date"] += 1
                continue
            date_cache[flight_date] = day
        try:
            scheduled_departure = local_hhmm_to_utc(
                day, columns["CRSDepTime"][index], zone_origin)
            scheduled_arrival = local_hhmm_to_utc(
                day, columns["CRSArrTime"][index], zone_dest)
            if scheduled_departure is None or scheduled_arrival is None:
                skipped["schedule_missing"] += 1
                continue
            scheduled_arrival = infer_rollover(scheduled_departure,
                                               scheduled_arrival)
            departure = resolve_bts_actual_timestamp(
                service_day=day,
                schedule_utc=scheduled_departure,
                direct_hhmm=columns["DepTime"][index],
                timezone_name=zone_origin,
                signed_delay_value=columns["DepDelay"][index],
                reporting_delay_minutes_value=columns["DepDelayMinutes"][index],
                label="DEPARTURE")
            arrival = resolve_bts_actual_timestamp(
                service_day=day,
                schedule_utc=scheduled_arrival,
                direct_hhmm=columns["ArrTime"][index],
                timezone_name=zone_dest,
                signed_delay_value=columns["ArrDelay"][index],
                reporting_delay_minutes_value=columns["ArrDelayMinutes"][index],
                label="ARRIVAL")
            actual_departure = departure.canonical_utc
            actual_arrival = arrival.canonical_utc
            if actual_departure is None or actual_arrival is None:
                skipped["actual_unresolvable"] += 1
                continue
        except Exception:
            skipped["timestamp_resolution_failed"] += 1
            continue
        row = {
            "flight_id": deterministic_id("flight", {
                "FlightDate": flight_date,
                "Reporting_Airline": columns["Reporting_Airline"][index],
                "Flight_Number_Reporting_Airline":
                    columns["Flight_Number_Reporting_Airline"][index],
                "Origin": origin,
                "Dest": destination,
            }),
            "aircraft_id": tail,
            "aircraft_id_namespace": "REGISTRATION",
            "origin_airport_id": origin,
            "destination_airport_id": destination,
            "event_start_time": scheduled_departure,
            "event_end_time": scheduled_arrival,
            "actual_arrival_utc": actual_arrival,
            "actual_departure_utc": actual_departure,
            "dataset_instance_id": INSTANCE_ID,
            "service_date": day.isoformat(),
            "airline": columns["Reporting_Airline"][index],
        }
        order_key = (
            row["dataset_instance_id"], row["aircraft_id_namespace"],
            row["aircraft_id"], row["actual_departure_utc"],
            row["actual_arrival_utc"], row["flight_id"])
        if order_key in order_keys_seen:
            duplicates += 1
            continue
        order_keys_seen.add(order_key)
        rows.append(row)
    return rows, skipped


def pairwise_episodes(rows: list[dict]) -> tuple[list[tuple], Counter,
                                                 list[float]]:
    """Chain adjacency with rejection reasons. Reuses
    build_data2_episode_chain (audited clean); the ordering mirrors the
    frozen CHAIN_ORDERING_RULE. The split-dependent containment functions
    are intentionally NOT used."""
    ordered = sorted(rows, key=lambda row: (
        row["dataset_instance_id"], row["aircraft_id_namespace"],
        row["aircraft_id"], row["actual_departure_utc"],
        row["actual_arrival_utc"], row["flight_id"]))
    episodes: list[tuple] = []
    rejected: Counter = Counter()
    gaps: list[float] = []
    for predecessor, successor in zip(ordered, ordered[1:]):
        try:
            episode = build_data2_episode_chain(
                predecessor, successor, max_gap_minutes=MAX_GAP_MINUTES)
        except ContractError as error:
            rejected[str(error).split(":")[0]] += 1
            continue
        except ValueError:
            rejected["INVERTED_SCHEDULE_WINDOW"] += 1
            continue
        gaps.append((successor["actual_departure_utc"]
                     - predecessor["actual_arrival_utc"]).total_seconds() / 60.0)
        episodes.append((episode, successor))
    return episodes, rejected, gaps


def ontime_year_pass(year: int, zones: dict[str, str],
                     station_map: dict[str, str]) -> dict:
    """Full per-year pass: raw stats + chains + episodes + node arithmetic."""
    failures: list[dict] = []
    yearly_rows = yearly_cancelled = yearly_diverted = 0
    tails: set[str] = set()
    airports: set[str] = set()
    routes: Counter = Counter()
    airlines_flights: Counter = Counter()
    dep_parts: list[np.ndarray] = []
    arr_parts: list[np.ndarray] = []
    taxi_parts: list[np.ndarray] = []
    month_table: list[dict] = []
    labels_table: list[dict] = []
    year_episodes = year_nodes = year_candidate = year_rejected = 0
    station_episodes = station_nodes = 0
    gap_parts: list[np.ndarray] = []
    episode_airport_nodes: Counter = Counter()
    episode_airport_episodes: Counter = Counter()
    episode_airline_episodes: Counter = Counter()

    for month, path in enumerate(ontime_month_files(year), start=1):
        month_key = f"{year}-{month:02d}"
        if path is None:
            month_table.append({"year": year, "month": month, "status":
                                "MISSING_FILE"})
            failures.append({"source": "bts_ontime", "path": f"month={month:02d}",
                             "issue": "MISSING_FILE", "detail": ""})
            continue
        started = time.perf_counter()
        frame = pd.read_csv(path, usecols=list(PROJECTED_ONTIME_COLUMNS),
                            dtype=str, keep_default_na=False,
                            encoding="utf-8-sig")
        rows_total = len(frame)
        cancelled = int(sum((number(v) or 0.0) > 0
                            for v in frame["Cancelled"].tolist()))
        diverted = int(sum((number(v) or 0.0) > 0
                           for v in frame["Diverted"].tolist()))
        yearly_rows += rows_total
        yearly_cancelled += cancelled
        yearly_diverted += diverted
        tails.update(frame["Tail_Number"].str.strip().unique())
        airports.update(frame["Origin"].unique())
        airports.update(frame["Dest"].unique())
        routes.update((frame["Origin"] + ">" + frame["Dest"]).tolist())
        airlines_flights.update(frame["Reporting_Airline"].tolist())
        dep_parts.append(pd.to_numeric(frame["DepDelay"],
                                       errors="coerce").to_numpy(np.float32))
        arr_parts.append(pd.to_numeric(frame["ArrDelay"],
                                       errors="coerce").to_numpy(np.float32))
        taxi_parts.append(pd.to_numeric(frame["TaxiOut"],
                                        errors="coerce").to_numpy(np.float32))

        rows, skipped = build_episode_rows(frame, zones)
        episodes, rejected, gaps = pairwise_episodes(rows)
        month_episodes = len(episodes)
        month_nodes = 0
        month_station_episodes = 0
        month_station_nodes = 0
        for episode, successor in episodes:
            nodes = episode_node_count(
                episode_start_time=episode.episode_start_time,
                episode_end_time=episode.episode_end_time)
            month_nodes += nodes
            airport = successor["destination_airport_id"]
            episode_airline_episodes[successor["airline"]] += 1
            if airport in station_map:
                month_station_episodes += 1
                month_station_nodes += nodes
            episode_airport_episodes[airport] += 1
            episode_airport_nodes[airport] += nodes
        year_episodes += month_episodes
        year_nodes += month_nodes
        year_candidate += month_episodes + sum(rejected.values())
        year_rejected += sum(rejected.values())
        station_episodes += month_station_episodes
        station_nodes += month_station_nodes
        gap_parts.append(np.asarray(gaps, dtype=np.float64))
        month_table.append({
            "year": year, "month": month, "status": "OK",
            "rows": rows_total,
            "rows_used": len(rows),
            "cancelled": cancelled, "diverted": diverted,
            "skipped_zone_or_identity": skipped.get("zone_or_identity_missing", 0),
            "skipped_bad_date": skipped.get("bad_flight_date", 0),
            "skipped_schedule_missing": skipped.get("schedule_missing", 0),
            "skipped_actual_unresolvable": skipped.get("actual_unresolvable", 0),
            "skipped_timestamp_failed": skipped.get("timestamp_resolution_failed", 0),
            "duplicate_ordering_keys": skipped.get("duplicates", 0),
            "candidate_chains": month_episodes + sum(rejected.values()),
            "eligible_chains": month_episodes,
            "rejected_chains": sum(rejected.values()),
            "episodes": month_episodes,
            "decision_nodes": month_nodes,
            "episodes_with_station": month_station_episodes,
            "nodes_with_station": month_station_nodes,
            "seconds": round(time.perf_counter() - started, 1),
        })
        labels_table.append({
            "year": year, "month": month,
            "rows_input": rows_total,
            "rows_used": len(rows),
            "rows_skipped_cancelled": cancelled,
            "rows_skipped_diverted": diverted,
            "rows_skipped_other": (rows_total - len(rows) - cancelled
                                   - diverted),
            "R_IB_support": month_episodes,
            "R_IB_deficit_rows": rows_total - len(rows),
            "D_OB_support": month_episodes,
            "D_TX_support": month_episodes,
        })
        if rejected:
            failures.append({"source": "bts_ontime", "path": path.name,
                             "issue": "CHAIN_REJECTIONS",
                             "detail": json.dumps(dict(rejected))})
        print(f"  {month_key} rows={rows_total} used={len(rows)} "
              f"episodes={month_episodes} nodes={month_nodes} "
              f"({month_table[-1]['seconds']}s)", flush=True)
        del frame, rows, episodes

    dep_delay = np.concatenate(dep_parts) if dep_parts else np.empty(0, np.float32)
    arr_delay = np.concatenate(arr_parts) if arr_parts else np.empty(0, np.float32)
    taxi_out = np.concatenate(taxi_parts) if taxi_parts else np.empty(0, np.float32)
    gaps = np.concatenate(gap_parts) if gap_parts else np.empty(0, np.float64)
    return {
        "year": year,
        "summary": {
            "rows": yearly_rows,
            "unique_tail": len(tails),
            "unique_airports": len(airports),
            "unique_routes": len(routes),
            "cancelled": yearly_cancelled,
            "cancelled_rate": round(yearly_cancelled / yearly_rows, 6)
            if yearly_rows else None,
            "diverted": yearly_diverted,
            "diverted_rate": round(yearly_diverted / yearly_rows, 6)
            if yearly_rows else None,
            "months_present": sum(1 for m in month_table
                                  if m.get("status") == "OK"),
            "episodes": year_episodes,
            "decision_nodes": year_nodes,
            "candidate_chains": year_candidate,
            "rejected_chains": year_rejected,
            "episodes_with_station": station_episodes,
            "nodes_with_station": station_nodes,
        },
        "month_table": month_table,
        "labels_table": labels_table,
        "distributions": quantile_rows("dep_delay", dep_delay)
        + quantile_rows("arr_delay", arr_delay)
        + quantile_rows("taxi_out", taxi_out)
        + quantile_rows("gate_gap_minutes", gaps),
        "by_airport": [
            {"year": year, "airport": airport,
             "episodes": count,
             "nodes": episode_airport_nodes.get(airport, 0),
             "station_mapped": airport in station_map,
             "share": round(count / year_episodes, 6) if year_episodes else None}
            for airport, count in episode_airport_episodes.most_common()],
        "by_airline": [
            {"year": year, "airline": airline, "episodes": count,
             "share": round(count / year_episodes, 6) if year_episodes else None}
            for airline, count in episode_airline_episodes.most_common()],
        "airline_flights": dict(airlines_flights),
        "failures": failures,
    }


# ---------------------------------------------------- weather / db1b / t100 --

def weather_year_pass(year: int) -> tuple[list[dict], list[dict]]:
    rows_out, failures = [], []
    base = RAW / "weather" / "noaa" / str(year)
    station_files = sorted(base.glob("*.csv"))
    for path in station_files:
        try:
            frame = pd.read_csv(path, usecols=["STATION", "DATE"],
                                dtype=str, keep_default_na=False,
                                encoding="utf-8-sig")
            stamps = pd.to_datetime(frame["DATE"], errors="coerce")
            valid = stamps.dropna()
            gaps_minutes = valid.sort_values().diff().dt.total_seconds() / 60.0
            days = int(valid.dt.date.nunique())
            rows_out.append({
                "year": year, "station": path.stem, "rows": len(frame),
                "first": str(valid.min()), "last": str(valid.max()),
                "days_covered": days,
                "coverage_rate": round(days / 365.0, 4),
                "max_gap_minutes": round(float(gaps_minutes.max()), 1)
                if len(gaps_minutes.dropna()) else None,
                "stale_share_over_90m": round(
                    float((gaps_minutes > 90).mean()), 6)
                if len(gaps_minutes.dropna()) else None,
            })
        except Exception as error:
            failures.append({"source": "noaa_isd", "path": path.name,
                             "issue": "READ_FAILED",
                             "detail": f"{type(error).__name__}: {error}"})
    expected = sorted(p.stem for p in
                      (RAW / "weather" / "noaa" / "2019").glob("*.csv"))
    missing_stations = sorted(set(expected) - {p.stem for p in station_files})
    for station in missing_stations:
        failures.append({"source": "noaa_isd", "path": f"{station}.csv",
                         "issue": "MISSING_FILE", "detail": ""})
    return rows_out, failures


def _db1b_file_stats(path: Path, columns: list[str]) -> dict | None:
    if not path.is_file():
        return None
    rows = pax = 0
    routes: set[str] = set()
    carriers: set[str] = set()
    years_seen: set[str] = set()
    for chunk in pd.read_csv(path, usecols=columns, dtype=str,
                             keep_default_na=False, chunksize=3_000_000,
                             encoding="utf-8-sig"):
        rows += len(chunk)
        pax += int(pd.to_numeric(chunk["Passengers"],
                                 errors="coerce").fillna(0).sum())
        routes.update((chunk["Origin"] + ">" + chunk["Dest"]).tolist())
        years_seen.update(chunk["Year"].unique())
        if "TkCarrier" in chunk.columns:
            carriers.update(chunk["TkCarrier"].unique())
            carriers.update(chunk["OpCarrier"].unique())
    return {"rows": rows, "passengers": pax, "unique_routes": len(routes),
            "unique_carriers": len(carriers), "years_seen": sorted(years_seen)}


def db1b_year_pass(year: int) -> tuple[list[dict], list[dict]]:
    table, failures = [], []
    coupon_dir = RAW / "bts" / "db1b" / str(year) / "coupon"
    for quarter in (1, 2, 3, 4):
        path = coupon_dir / (f"Origin_and_Destination_Survey_DB1BCoupon_"
                             f"{year}_{quarter}.csv")
        stats = _db1b_file_stats(path, ["Origin", "Dest", "Passengers",
                                        "TkCarrier", "OpCarrier", "Year"])
        if stats is None:
            failures.append({"source": "bts_db1b_coupon", "path": path.name,
                             "issue": "MISSING_FILE", "detail": ""})
            continue
        if any(y != str(year) for y in stats["years_seen"]):
            failures.append({"source": "bts_db1b_coupon", "path": path.name,
                             "issue": "YEAR_COLUMN_MISMATCH",
                             "detail": json.dumps(stats["years_seen"])})
        table.append({"year": year, "product": "DB1B Coupon",
                      "partition": f"Q{quarter}", "rows": stats["rows"],
                      "quantity": stats["passengers"],
                      "coverage_routes": stats["unique_routes"],
                      "coverage_carriers": stats["unique_carriers"]})
        print(f"  db1b coupon Q{quarter}: rows={stats['rows']} "
              f"pax={stats['passengers']}", flush=True)
    market_path = (RAW / "bts" / "db1b" / str(year) / "market" /
                   f"Origin_and_Destination_Survey_DB1BMarket_{year}_1.csv")
    stats = _db1b_file_stats(market_path, ["Origin", "Dest", "Passengers",
                                           "Year"])
    if stats is None:
        failures.append({"source": "bts_db1b_market", "path": market_path.name,
                         "issue": "MISSING_FILE", "detail": ""})
    else:
        table.append({"year": year, "product": "DB1B Market (within-year Q1 "
                      "scope, cross-year consistent)", "partition": "Q1",
                      "rows": stats["rows"], "quantity": stats["passengers"],
                      "coverage_routes": stats["unique_routes"],
                      "coverage_carriers": stats["unique_carriers"]})
    return table, failures


def t100_year_pass(year: int) -> tuple[list[dict], list[dict]]:
    table, failures = [], []
    path = RAW / "bts" / "t100" / str(year) / "T_T100_SEGMENT_ALL_CARRIER.csv"
    if not path.is_file():
        failures.append({"source": "bts_t100", "path": path.name,
                         "issue": "MISSING_FILE", "detail": ""})
        return table, failures
    rows = pax = seats = 0
    routes: set[str] = set()
    carriers: set[str] = set()
    years_seen: set[str] = set()
    months_seen: set[str] = set()
    for chunk in pd.read_csv(
            path, usecols=["PASSENGERS", "SEATS", "ORIGIN", "DEST", "YEAR",
                           "MONTH", "UNIQUE_CARRIER"],
            dtype=str, keep_default_na=False, chunksize=3_000_000,
            encoding="utf-8-sig"):
        rows += len(chunk)
        pax += int(pd.to_numeric(chunk["PASSENGERS"],
                                 errors="coerce").fillna(0).sum())
        seats += int(pd.to_numeric(chunk["SEATS"],
                                   errors="coerce").fillna(0).sum())
        routes.update((chunk["ORIGIN"] + ">" + chunk["DEST"]).tolist())
        carriers.update(chunk["UNIQUE_CARRIER"].unique())
        years_seen.update(chunk["YEAR"].unique())
        months_seen.update(chunk["MONTH"].unique())
    if years_seen - {str(year)}:
        failures.append({"source": "bts_t100", "path": path.name,
                         "issue": "YEAR_COLUMN_MISMATCH",
                         "detail": json.dumps(sorted(years_seen))})
    table.append({"year": year, "product": "T-100 Segment (All Carriers)",
                  "partition": "FULL_YEAR", "rows": rows, "quantity": pax,
                  "coverage_routes": len(routes),
                  "coverage_carriers": len(carriers)})
    return table, failures


# ------------------------------------------------------- split candidates --

def split_candidates(year_summaries: dict[int, dict]) -> list[dict]:
    """Generate at most three temporal-split candidate LOGICS from the actual
    per-year support numbers. Selection is deliberately UNDECIDED; year bands
    are derived from observed support only (no event naming), structural-break
    years are kept whole inside single segments, and every segment stays
    strict out-of-time. A candidate that cannot fill all four segments with
    whole years at the observed break location is reported as such instead of
    being silently bent into feasibility."""
    years = sorted(year_summaries)
    episodes = {y: year_summaries[y]["summary"]["episodes"] for y in years}
    nodes = {y: year_summaries[y]["summary"]["decision_nodes"] for y in years}

    def support(band: list[int]) -> dict:
        return {"years": band, "episodes": sum(episodes[y] for y in band),
                "decision_nodes": sum(nodes[y] for y in band)}

    break_year = None
    drops = {}
    for previous, current in zip(years, years[1:]):
        if episodes[previous]:
            drops[current] = episodes[current] / episodes[previous]
    if drops:
        steepest = min(drops, key=drops.get)
        if drops[steepest] < 0.7:
            break_year = steepest

    candidates = []
    if break_year is not None:
        pre = [y for y in years if y < break_year]
        post = [y for y in years if y >= break_year]
        long_train = [y for y in years if y < years[-2]]
        long_candidate = {
            "logic": "long_history",
            "segments": {"train": long_train,
                         "calibration": years[-2:-1],
                         "development": [],
                         "final_test": years[-1:]},
            "episode_support": {
                "train": support(long_train),
                "calibration": support(years[-2:-1]),
                "development": support([]),
                "final_test": support(years[-1:])},
            "considerations": [
                "maximum training history; with six years and four strictly "
                "ordered whole-year segments this logic cannot populate a "
                "development segment distinct from calibration",
                f"the structural-break year {break_year} would sit inside "
                "the training segment",
            ],
            "selection": "UNDECIDED",
        }
        candidates.append(long_candidate)
        candidates.append({
            "logic": "regime_transition",
            "segments": {"train": pre,
                         "calibration": [break_year],
                         "development": years[-2:-1],
                         "final_test": years[-1:]},
            "episode_support": {"train": support(pre),
                                "calibration": support([break_year]),
                                "development": support(years[-2:-1]),
                                "final_test": support(years[-1:])},
            "considerations": [
                f"boundary placed at the steepest observed year-over-year "
                f"episode-volume drop ({break_year}: "
                f"{drops[break_year]:.3f} of the prior year); the break year "
                "anchors calibration as a whole",
                "the only candidate that fills all four segments with whole "
                "years at the observed break location",
            ],
            "selection": "UNDECIDED",
        })
        recent_train = [y for y in post if y < years[-2]]
        candidates.append({
            "logic": "recent_regime",
            "segments": {"train": recent_train,
                         "calibration": [],
                         "development": [],
                         "final_test": years[-1:]},
            "episode_support": {"train": support(recent_train),
                                "calibration": support([]),
                                "development": support([]),
                                "final_test": support(years[-1:])},
            "considerations": [
                f"only {len(post)} years follow the structural break; four "
                "strictly ordered whole-year segments cannot be populated",
                "reported as infeasible at whole-year granularity rather "
                "than forced; a within-year segmentation decision would be "
                "required and is out of scope for this round",
            ],
            "selection": "UNDECIDED",
        })
    else:
        candidates.append({
            "logic": "long_history",
            "segments": {"train": years[:-3], "calibration": years[-3:-2],
                         "development": years[-2:-1],
                         "final_test": years[-1:]},
            "episode_support": {"train": support(years[:-3]),
                                "calibration": support(years[-3:-2]),
                                "development": support(years[-2:-1]),
                                "final_test": support(years[-1:])},
            "considerations": ["no structural break year detected at the 0.7 "
                               "year-over-year volume-drop threshold"],
            "selection": "UNDECIDED",
        })
    return candidates


# ---------------------------------------------------------------- report --

def integrity_2019() -> dict:
    baseline = DATA2 / "reports" / "data2_raw_2019_baseline_sha256.csv"
    if not baseline.is_file():
        return {"ok": None, "note": "baseline missing"}
    changed = missing = checked = 0
    with baseline.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            checked += 1
            path = REPO / row["Path"]
            if not path.is_file():
                missing += 1
            elif hashlib.sha256(path.read_bytes()).hexdigest().upper() \
                    != row["SHA256"]:
                changed += 1
    return {"ok": changed == 0 and missing == 0, "files_checked": checked,
            "changed": changed, "missing": missing}


def write_year_tables(year: int, data: dict, weather_rows: list[dict],
                      references: list[dict], failures: list[dict]) -> None:
    out = OUT_ROOT / str(year)
    summary = data["summary"]
    write_csv(out / "on_time_summary.csv",
              ["year", "rows", "unique_tail", "unique_airports",
               "unique_routes", "cancelled", "cancelled_rate", "diverted",
               "diverted_rate", "months_present", "episodes", "decision_nodes",
               "episodes_with_station", "nodes_with_station"],
              [summary])
    write_csv(out / "episodes_nodes.csv",
              ["year", "month", "status", "rows", "rows_used", "cancelled",
               "diverted", "skipped_zone_or_identity", "skipped_bad_date",
               "skipped_schedule_missing", "skipped_actual_unresolvable",
               "skipped_timestamp_failed", "duplicate_ordering_keys",
               "candidate_chains", "eligible_chains", "rejected_chains",
               "episodes", "decision_nodes", "episodes_with_station",
               "nodes_with_station", "seconds"],
              data["month_table"])
    write_csv(out / "labels.csv",
              ["year", "month", "rows_input", "rows_used",
               "rows_skipped_cancelled", "rows_skipped_diverted",
               "rows_skipped_other", "R_IB_support", "R_IB_deficit_rows",
               "D_OB_support", "D_TX_support"],
              data["labels_table"])
    write_csv(out / "distributions.csv",
              ["year", "metric", "quantile", "value"],
              [{"year": year, **row} for row in data["distributions"]])
    write_csv(out / "by_airport.csv",
              ["year", "airport", "episodes", "nodes", "station_mapped",
               "share"], data["by_airport"])
    write_csv(out / "by_airline.csv",
              ["year", "airline", "episodes", "share"], data["by_airline"])
    write_csv(out / "weather_support.csv",
              ["year", "station", "rows", "first", "last", "days_covered",
               "coverage_rate", "max_gap_minutes", "stale_share_over_90m"],
              weather_rows)
    write_csv(out / "references.csv",
              ["year", "product", "partition", "rows", "quantity",
               "coverage_routes", "coverage_carriers"], references)
    write_csv(out / "source_failures.csv",
              ["year", "source", "path", "issue", "detail"],
              [{"year": year, **row} for row in failures])
    (out / "_COMPLETE").write_text(now() + "\n", encoding="utf-8")


def build_audit(payload: dict) -> tuple[dict, str]:
    started = payload["START_TIME"]
    summaries = payload["YEAR_SUMMARIES"]
    overall = "PASS"
    for year, data in summaries.items():
        if data["summary"]["months_present"] != 12:
            overall = "PARTIAL_WITH_BLOCKERS"
    if payload["2019_INTEGRITY"]["ok"] is False:
        overall = "FAIL"
    failures = payload["SOURCE_FAILURES"]
    hard = [f for f in failures
            if f["issue"] in ("MISSING_FILE", "YEAR_COLUMN_MISMATCH",
                              "READ_FAILED")]
    if hard and overall == "PASS":
        overall = "PARTIAL_WITH_BLOCKERS"
    report = {
        "EXECUTION_REPOSITORY": str(REPO),
        "BRANCH": _git("branch", "--show-current"),
        "START_TIME": started,
        "END_TIME": now(),
        "INSTANCE_CONTRACT": {
            "instance_id": "data2_2017_2022",
            "status": "PROFILING_ONLY",
            "PRE_ENABLED": False,
            "EXPERIMENT_ENABLED": False,
            "temporal_split": "UNDEFINED_PENDING_HUMAN_DECISION",
        },
        "STATIC_REUSE_AUDIT": payload["STATIC_REUSE_AUDIT"],
        "YEARS": payload["YEARS"],
        "YEAR_SUMMARIES": summaries,
        "MONTH_TABLES": payload["MONTH_TABLES"],
        "WEATHER": payload["WEATHER"],
        "REFERENCES": payload["REFERENCES"],
        "SOURCE_FAILURES": failures,
        "SPLIT_CANDIDATES": split_candidates(summaries),
        "2019_INTEGRITY": payload["2019_INTEGRITY"],
        "DISK_USAGE": {"free_gb": round(shutil_disk_free(DATA2), 2)},
        "OVERALL_STATUS": overall,
    }
    lines = ["# Data2 multi-year profiling audit (data2_2017_2022, "
             "PROFILING_ONLY)", "",
             f"- Execution repository: `{report['EXECUTION_REPOSITORY']}`",
             f"- Branch: `{report['BRANCH']}`",
             f"- Start: {report['START_TIME']}  End: {report['END_TIME']}",
             f"- **OVERALL_STATUS: {overall}**",
             "- Instance contract: PROFILING_ONLY / PRE_ENABLED=false / "
             "EXPERIMENT_ENABLED=false / temporal split UNDEFINED", "",
             "## Per-year summary", "",
             "| year | rows | tails | airports | routes | cancelled | "
             "episodes | nodes | station eps | months |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for year in payload["YEARS"]:
        s = summaries[str(year)]["summary"]
        lines.append(
            f"| {year} | {s['rows']} | {s['unique_tail']} | "
            f"{s['unique_airports']} | {s['unique_routes']} | "
            f"{s['cancelled']} | {s['episodes']} | {s['decision_nodes']} | "
            f"{s['episodes_with_station']} | {s['months_present']}/12 |")
    lines += ["", "## Temporal-split candidate logics (UNDECIDED)", ""]
    for candidate in report["SPLIT_CANDIDATES"]:
        lines.append(f"### {candidate['logic']} - {candidate['selection']}")
        for name, band in candidate["episode_support"].items():
            lines.append(f"- {name}: years={band['years']} "
                         f"episodes={band['episodes']} "
                         f"nodes={band['decision_nodes']}")
        for note in candidate["considerations"]:
            lines.append(f"  - note: {note}")
    lines += ["", "## Hard failures", ""]
    if hard:
        for row in hard:
            lines.append(f"- {row.get('year')} {row['source']} {row['path']} "
                         f"{row['issue']} {row['detail']}")
    else:
        lines.append("- none")
    return report, "\n".join(lines) + "\n"


def shutil_disk_free(path: Path) -> float:
    import shutil
    return shutil.disk_usage(path).free / 10 ** 9


# ------------------------------------------------------------------ main --

def _read_year_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def rebuild_audit_from_tables() -> tuple[dict, str]:
    """Reconstruct the full six-year audit from the per-year CSV tables
    (used when years were profiled in separate invocations)."""
    summaries: dict[str, dict] = {}
    month_tables: dict[str, list] = {}
    weather: dict[str, list] = {}
    references: dict[str, list] = {}
    failures: list[dict] = []
    for year in YEARS:
        out = OUT_ROOT / str(year)
        if not (out / "_COMPLETE").is_file():
            continue
        summary = _read_year_csv(out / "on_time_summary.csv")[0]
        for key in ("rows", "unique_tail", "unique_airports", "unique_routes",
                    "cancelled", "diverted", "months_present", "episodes",
                    "decision_nodes", "candidate_chains", "rejected_chains",
                    "episodes_with_station", "nodes_with_station"):
            summary[key] = int(summary[key]) if summary.get(key) else 0
        for key in ("cancelled_rate", "diverted_rate"):
            summary[key] = float(summary[key]) if summary[key] else None
        summaries[str(year)] = {"summary": summary}
        month_tables[str(year)] = _read_year_csv(out / "episodes_nodes.csv")
        weather[str(year)] = _read_year_csv(out / "weather_support.csv")
        references[str(year)] = _read_year_csv(out / "references.csv")
        for row in _read_year_csv(out / "source_failures.csv"):
            failures.append(row)
    return build_audit({
        "START_TIME": now(),
        "STATIC_REUSE_AUDIT": static_reuse_audit(),
        "YEARS": sorted(summaries),
        "YEAR_SUMMARIES": summaries,
        "MONTH_TABLES": month_tables,
        "WEATHER": weather,
        "REFERENCES": references,
        "SOURCE_FAILURES": failures,
        "2019_INTEGRITY": integrity_2019(),
    })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", type=int, nargs="*", default=list(YEARS))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--rebuild-audit", action="store_true",
                        help="rebuild the six-year audit from existing "
                             "per-year tables without re-profiling")
    args = parser.parse_args()

    if args.rebuild_audit:
        audit = static_reuse_audit()
        if audit["status"] != "PASS":
            print(json.dumps(audit, indent=2))
            return 2
        report, markdown = rebuild_audit_from_tables()
        OUT_ROOT.mkdir(parents=True, exist_ok=True)
        (OUT_ROOT / "data2_multiyear_profiling_audit.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        (OUT_ROOT / "data2_multiyear_profiling_audit.md").write_text(
            markdown, encoding="utf-8")
        print(f"AUDIT_REBUILT overall={report['OVERALL_STATUS']} "
              f"years={report['YEARS']}")
        return 0

    audit = static_reuse_audit()
    if audit["status"] != "PASS":
        print(json.dumps(audit, indent=2))
        print("STATIC_REUSE_AUDIT=FAIL - profiling aborted (hard constraint)")
        return 2
    print(f"STATIC_REUSE_AUDIT=PASS ({len(audit['clean_functions'])} functions)")

    zones = load_zones()
    station_map = load_station_map()
    print(f"zones={len(zones)} station_mapped_airports={len(station_map)}")

    year_summaries: dict[int, dict] = {}
    month_tables: dict[str, list] = {}
    weather_all: dict[str, list] = {}
    references_all: dict[str, list] = {}
    failures_all: list[dict] = []
    started = now()

    for year in args.years:
        if year not in YEARS:
            print(f"skip {year}: not in {YEARS}")
            continue
        out = OUT_ROOT / str(year)
        if (out / "_COMPLETE").is_file() and not args.force:
            print(f"skip {year}: complete (use --force to redo)")
            continue
        print(f"=== profiling {year} ===", flush=True)
        data = ontime_year_pass(year, zones, station_map)
        weather_rows, weather_failures = weather_year_pass(year)
        references, ref_failures = db1b_year_pass(year)
        t100_rows, t100_failures = t100_year_pass(year)
        references.extend(t100_rows)
        failures = (data["failures"] + weather_failures + ref_failures
                    + t100_failures)
        write_year_tables(year, data, weather_rows, references, failures)
        year_summaries[year] = data
        month_tables[str(year)] = data["month_table"]
        weather_all[str(year)] = weather_rows
        references_all[str(year)] = references
        failures_all.extend({"year": year, **row} for row in failures)

    if not year_summaries:
        print("nothing to do")
        return 0

    report, markdown = build_audit({
        "START_TIME": started,
        "STATIC_REUSE_AUDIT": audit,
        "YEARS": sorted(year_summaries),
        "YEAR_SUMMARIES": {str(y): d for y, d in year_summaries.items()},
        "MONTH_TABLES": month_tables,
        "WEATHER": weather_all,
        "REFERENCES": references_all,
        "SOURCE_FAILURES": failures_all,
        "2019_INTEGRITY": integrity_2019(),
    })
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "data2_multiyear_profiling_audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_ROOT / "data2_multiyear_profiling_audit.md").write_text(
        markdown, encoding="utf-8")
    print(f"AUDIT_WRITTEN overall={report['OVERALL_STATUS']} -> {OUT_ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
