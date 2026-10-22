# -*- coding: utf-8 -*-
"""PRE-split cohort eligibility audit for data2_2017_2022 (M4a-5/6/7).

    python data2/scripts/cohort_audit_data2_multiyear.py --years 2019
    python data2/scripts/cohort_audit_data2_multiyear.py            # six years

Scope (M4a): multi-year raw ingestion, canonicalization-style projection, and
cohort-eligibility accounting ONLY. No PRE materialization, no model
training, no reference fitting, no temporal split, no experiment. All cohort
totals are named PRE_SPLIT_ELIGIBLE_* because no temporal split, reference
fit/freeze, or experimental-eligibility decision exists yet.

Hard gates (any failure aborts before totals are published):
- M4A_BLOCKED_LEGACY_REGRESSION       - 2019 instance-aware ingestion must
  reproduce the legacy data2_2019 ingestion exactly (12-month sampled
  identity fields + full-year structural episode/rejection/node counts).
- M4A_BLOCKED_AUDIT_SEMANTIC_MISMATCH - the optimized interval/searchsorted
  implementation must match the production node/evidence functions node by
  node on a deterministic stratified sample (>=1000 episodes/year, enriched
  with stage-boundary, missing/stale weather, cutoff-equality and
  immediately-after-cutoff cases); all three mismatch counters must be 0.
- M4A_BLOCKED_CANONICAL_PROVENANCE_LEAKAGE - MULTIYEAR_CANONICAL_PROVENANCE_
  AUDIT scans produced records for literal-2019 provenance
  (dataset_instance_id / source_version / reference_period / fit_year /
  period) and blocks on any YEAR_SEMANTIC_LEAKAGE_BLOCKING finding.

Naming discipline: LABEL_SUPPORT (post-hoc realization masks built from
actuals: R_IB / D_OB / D_TX / JOINT_RIB_DOB_DTX) and
DECISION_TIME_EVIDENCE_SUPPORT (admissible decision-time evidence: weather
within the frozen 5-minute availability lag and 60-minute freshness window,
schedule inputs, DB1B/T-100 PREFIT route coverage) are reported separately
and never mixed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import json
import math
import random
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT / "data2" / "scripts"), str(_REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

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
from model.PRE.episode.node_builder import stage_at
from model.PRE.factual.availability import (
    Data2FactualReplayAvailabilityPolicy,
    factual_availability_time,
)
from profile_data2_years import _db1b_file_stats, load_station_map, load_zones

REPO = _REPO_ROOT
DATA2 = REPO / "data2"
RAW = DATA2 / "raw"
OUT_ROOT = DATA2 / "reports" / "multiyear_cohort_audit"
YEARS = (2017, 2018, 2019, 2020, 2021, 2022)
INSTANCE_ID = "data2_2017_2022"
MAX_GAP_MINUTES = 360
REPLAY_LAG_MINUTES = 5          # foundation.yaml data2_weather_replay_lag_minutes
WEATHER_MAX_AGE_MINUTES = 60    # foundation.yaml weather_max_age_minutes (FROZEN)
GRID_SECONDS = 300
POLICY = Data2FactualReplayAvailabilityPolicy.DECLARED_EVENT_TIME_REPLAY
SAMPLE_TARGET = 1000
SAMPLE_PER_MONTH = 150
ENRICHMENT_CAP = 250

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
    "stage_at": "model.PRE.episode.node_builder",
    "factual_availability_time": "model.PRE.factual.availability",
    "count_at_or_after": "LOCAL",
    "weather_support_count": "LOCAL",
    "label_support_counts": "LOCAL",
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
    """Fail-closed: no reused or local audit function may depend on the
    legacy temporal-split machinery."""
    clean, violations = [], []
    for function_name, module_name in sorted(REUSE_ALLOWLIST.items()):
        if module_name == "LOCAL":
            function = globals()[function_name]
        else:
            module = __import__(module_name, fromlist=[function_name])
            function = getattr(module, function_name)
        source = inspect.getsource(function)
        hits = [token for token in STATIC_FORBIDDEN_TOKENS if token in source]
        if hits:
            violations.append({"function": function_name, "tokens": hits})
        else:
            clean.append(function_name)
    return {"status": "PASS" if not violations else "FAIL",
            "clean_functions": clean, "violations": violations}


def _git(*args: str) -> str:
    out = subprocess.run(["git", "-C", str(REPO), *args],
                         capture_output=True, text=True)
    return (out.stdout + out.stderr).strip()


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames,
                                lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


# --------------------------------- optimized implementations (audited) ------

def count_at_or_after(episode_start: datetime, episode_end: datetime,
                      threshold: datetime | None) -> int:
    """Grid points t_k = start + 300k (k = 0..n-1) with t_k >= threshold.
    Exact arithmetic equivalent of the production stage-mask boundaries."""
    if threshold is None:
        return 0
    n = episode_node_count(episode_start_time=episode_start,
                           episode_end_time=episode_end)
    if n <= 0:
        return 0
    offset = int((threshold - episode_start).total_seconds())
    if offset <= 0:
        return n
    k_min = -(-offset // GRID_SECONDS)  # ceil division on integers
    return max(0, n - k_min)


def label_support_counts(episode_start: datetime, episode_end: datetime,
                         predecessor_in_block: datetime | None,
                         successor_off_block: datetime | None,
                         successor_takeoff: datetime | None) -> dict:
    """LABEL_SUPPORT (post-hoc realization masks; never decision-time
    evidence). Boundaries identical to production stage_at. JOINT requires
    all three realizations to be present (production stage never reaches
    COMPLETED when the wheels-off realization is missing)."""
    rib = count_at_or_after(episode_start, episode_end, predecessor_in_block)
    dob = count_at_or_after(episode_start, episode_end, successor_off_block)
    dtx = count_at_or_after(episode_start, episode_end, successor_takeoff)
    stamps = [s for s in (predecessor_in_block, successor_off_block,
                          successor_takeoff) if s is not None]
    joint = (count_at_or_after(episode_start, episode_end, max(stamps))
             if len(stamps) == 3 else 0)
    return {"R_IB": rib, "D_OB": dob, "D_TX": dtx,
            "JOINT_RIB_DOB_DTX": joint}


def weather_support_count(episode_start: datetime, episode_end: datetime,
                          availability: np.ndarray | None) -> int:
    """DECISION_TIME_EVIDENCE_SUPPORT (weather): grid points t with an ISD
    observation whose availability_time (event + 5-minute frozen lag) lies in
    (t - 60min, t] - exactly the production latest_weather semantics."""
    n = episode_node_count(episode_start_time=episode_start,
                           episode_end_time=episode_end)
    if n <= 0 or availability is None or len(availability) == 0:
        return 0
    grid = int(episode_start.timestamp()) + np.arange(
        n, dtype=np.int64) * GRID_SECONDS
    avail = availability.astype(np.int64)
    idx = np.searchsorted(avail, grid, side="right") - 1
    supported = (idx >= 0) & (
        (grid - avail[np.clip(idx, 0, None)]) <= WEATHER_MAX_AGE_MINUTES * 60)
    return int(supported.sum())


def on_grid_offset(stamp: datetime, episode_start: datetime) -> bool:
    offset = int((stamp - episode_start).total_seconds())
    return offset > 0 and offset % GRID_SECONDS == 0


# ---------------------------------------------------------------- ingestion

def build_audit_rows(frame: "pd.DataFrame",
                     zones: dict[str, str]) -> tuple[list[dict], Counter]:
    """Production-mirroring lightweight projection, plus wheels_off
    resolution (needed for the D_TX label-support mask)."""
    skipped: Counter = Counter()
    rows: list[dict] = []
    columns = {name: frame[name].tolist() for name in PROJECTED_ONTIME_COLUMNS}
    date_cache: dict[str, date] = {}
    order_keys_seen: set[tuple] = set()
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
            taxi_out = number(columns["TaxiOut"][index])
            direct_wheels_off = resolve_bts_event_clock(
                service_day=day,
                reference_utc=actual_departure,
                direct_hhmm=columns["WheelsOff"][index],
                timezone_name=zone_origin,
            )
            wheels_off = direct_wheels_off or (
                None if taxi_out is None
                else actual_departure + timedelta(minutes=taxi_out))
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
            "wheels_off_utc": wheels_off,
            "dataset_instance_id": INSTANCE_ID,
            "service_date": day.isoformat(),
            "airline": columns["Reporting_Airline"][index],
        }
        order_key = (
            row["dataset_instance_id"], row["aircraft_id_namespace"],
            row["aircraft_id"], row["actual_departure_utc"],
            row["actual_arrival_utc"], row["flight_id"])
        if order_key in order_keys_seen:
            skipped["duplicate_ordering_key"] += 1
            continue
        order_keys_seen.add(order_key)
        rows.append(row)
    return rows, skipped


def pairwise_episodes(rows: list[dict]) -> tuple[list[tuple], Counter]:
    """Chain adjacency via the production chain builder with rejection
    reasons; ordering mirrors the frozen CHAIN_ORDERING_RULE."""
    ordered = sorted(rows, key=lambda row: (
        row["dataset_instance_id"], row["aircraft_id_namespace"],
        row["aircraft_id"], row["actual_departure_utc"],
        row["actual_arrival_utc"], row["flight_id"]))
    episodes: list[tuple] = []
    rejected: Counter = Counter()
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
        episodes.append((episode, predecessor, successor))
    return episodes, rejected


def dedupe_ordering_keys(rows: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out = []
    for row in rows:
        key = (row["dataset_instance_id"], row["aircraft_id_namespace"],
               row["aircraft_id"], row["actual_departure_utc"],
               row["actual_arrival_utc"], row["flight_id"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def weather_availability_by_airport(year: int,
                                    station_map: dict[str, str]) -> dict:
    """station airport -> sorted availability_time seconds array
    (event + 5-minute frozen lag)."""
    by_station: dict[str, np.ndarray] = {}
    for path in sorted((RAW / "weather" / "noaa" / str(year)).glob("*.csv")):
        frame = pd.read_csv(path, usecols=["STATION", "DATE"], dtype=str,
                            keep_default_na=False, encoding="utf-8-sig")
        stamps = pd.to_datetime(frame["DATE"], errors="coerce", utc=True)
        avail = ((stamps.astype("int64") // 10 ** 9)
                 + REPLAY_LAG_MINUTES * 60).to_numpy(dtype=np.int64)
        avail.sort()
        by_station[path.stem] = avail
    return {airport: by_station[station]
            for airport, station in station_map.items()
            if station in by_station}


# --------------------------------- production-semantic equivalence audit ----

def production_semantic_equivalence_audit(
        sampled: list[tuple], weather_by_airport: dict) -> dict:
    """Call the PRODUCTION functions node by node on the sample
    (factual_availability_time + stage_at + latest_weather) and compare
    stage / label-support masks / weather-support masks against the
    optimized implementations. All three mismatch counters must be 0."""
    import model.PRE.streaming.data2 as streaming

    class _Obs:
        __slots__ = ("availability_time",)

        def __init__(self, availability_time):
            self.availability_time = availability_time

    stage_mismatch = label_mask_mismatch = weather_mask_mismatch = 0
    nodes_compared = 0
    boundary_hits: Counter = Counter()
    for episode, predecessor, successor in sampled:
        start = episode.episode_start_time
        end = episode.episode_end_time
        pred_actual = predecessor["actual_arrival_utc"]
        dep_actual = successor["actual_departure_utc"]
        wheels_actual = successor.get("wheels_off_utc")
        pred_available = factual_availability_time(
            pred_actual, POLICY, declared_lag_minutes=0)
        dep_available = factual_availability_time(
            dep_actual, POLICY, declared_lag_minutes=0)
        wheels_available = factual_availability_time(
            wheels_actual, POLICY, declared_lag_minutes=0)
        opt_labels = label_support_counts(start, end, pred_actual,
                                          dep_actual, wheels_actual)
        airport = episode.connection_airport_id
        availability = weather_by_airport.get(airport)
        if availability is None or len(availability) == 0:
            boundary_hits["missing_weather_episodes"] += 1
            packed_index = None
        else:
            times = tuple(datetime.fromtimestamp(int(s), timezone.utc)
                          for s in availability)
            packed_index = {airport: (times,
                                      tuple(_Obs(t) for t in times))}
        opt_weather = weather_support_count(start, end, availability)
        prod_weather = 0
        node_index = 0
        decision_time = start
        while decision_time <= end:
            available_pred = factual_availability_time(
                pred_actual, POLICY, declared_lag_minutes=0)
            available_dep = factual_availability_time(
                dep_actual, POLICY, declared_lag_minutes=0)
            available_wheels = factual_availability_time(
                wheels_actual, POLICY, declared_lag_minutes=0)
            stage = stage_at(
                decision_time,
                predecessor_in_block=(available_pred
                                      if available_pred is not None
                                      and available_pred <= decision_time
                                      else None),
                successor_off_block=(available_dep
                                     if available_dep is not None
                                     and available_dep <= decision_time
                                     else None),
                successor_takeoff=(available_wheels
                                   if available_wheels is not None
                                   and available_wheels <= decision_time
                                   else None))
            prod_rib = stage.value != "PRE_IB"
            prod_dob = stage.value in ("POST_OB_PRE_TO", "COMPLETED")
            prod_dtx = stage.value == "COMPLETED"
            opt_rib = node_index < opt_labels["R_IB"]
            opt_dob = node_index < opt_labels["D_OB"]
            opt_dtx = node_index < opt_labels["D_TX"]
            if prod_rib != opt_rib or prod_dob != opt_dob \
                    or prod_dtx != opt_dtx:
                label_mask_mismatch += 1
            opt_stage = ("PRE_IB" if not opt_rib else
                         "POST_IB_PRE_OB" if not opt_dob else
                         "POST_OB_PRE_TO" if not opt_dtx else "COMPLETED")
            if opt_stage != stage.value:
                stage_mismatch += 1
            if decision_time == pred_available and prod_rib:
                boundary_hits["label_boundary_exactly_at_grid"] += 1
            if on_grid_offset(wheels_actual or start, start):
                boundary_hits["wheels_off_on_grid"] += 1
            if packed_index is not None:
                observation = streaming.latest_weather(
                    packed_index, airport, decision_time,
                    WEATHER_MAX_AGE_MINUTES)
                prod_flag = observation is not None
                stamp_s = int(decision_time.timestamp())
                idx = int(np.searchsorted(availability, stamp_s,
                                          side="right")) - 1
                opt_flag = bool(
                    idx >= 0
                    and (stamp_s - int(availability[idx]))
                    <= WEATHER_MAX_AGE_MINUTES * 60)
                if opt_flag and stamp_s == int(availability[idx]):
                    boundary_hits["weather_exactly_at_cutoff"] += 1
                if (not opt_flag and idx + 1 < len(availability)
                        and 0 < int(availability[idx + 1]) - stamp_s <= 60):
                    boundary_hits["weather_immediately_after_cutoff"] += 1
                if prod_flag != opt_flag:
                    weather_mask_mismatch += 1
                prod_weather += 1 if prod_flag else 0
            nodes_compared += 1
            node_index += 1
            decision_time += timedelta(minutes=5)
    return {"status": ("PASS" if stage_mismatch == 0
                       and label_mask_mismatch == 0
                       and weather_mask_mismatch == 0 else "FAIL"),
            "episodes_sampled": len(sampled),
            "nodes_compared": nodes_compared,
            "stage_mismatch": stage_mismatch,
            "label_mask_mismatch": label_mask_mismatch,
            "weather_mask_mismatch": weather_mask_mismatch,
            "boundary_coverage": dict(boundary_hits)}


# --------------------------------------- MULTIYEAR_CANONICAL_PROVENANCE ----

PROVENANCE_FIELDS = ("dataset_instance_id", "source_version",
                     "reference_period", "fit_year", "period")


def _walk_records(record, path: str, findings: list[dict]) -> None:
    if isinstance(record, dict):
        for key, value in record.items():
            child = f"{path}.{key}" if path else str(key)
            if key in PROVENANCE_FIELDS or not isinstance(value, (dict, list)):
                if isinstance(value, str) and "2019" in value:
                    findings.append({"field": child, "value": value[:120]})
            _walk_records(value, child, findings)
    elif isinstance(record, list):
        for index, value in enumerate(record):
            _walk_records(value, f"{path}[{index}]", findings)


def multiyear_canonical_provenance_audit(records: list) -> dict:
    """Scan produced new-instance records for literal-2019 provenance.
    Every hit is classified; YEAR_SEMANTIC_LEAKAGE_BLOCKING blocks M4a."""
    findings: list[dict] = []
    for record in records:
        payload = record.model_dump(mode="json") if hasattr(
            record, "model_dump") else record
        _walk_records(payload, "", findings)
    classified = []
    for finding in findings:
        field = finding["field"]
        if field.endswith("dataset_instance_id") and "data2_2019" \
                in finding["value"]:
            classification = "YEAR_SEMANTIC_LEAKAGE_BLOCKING"
        elif field.split(".")[-1] in ("source_version", "reference_period",
                                      "fit_year", "period"):
            classification = "YEAR_SEMANTIC_LEAKAGE_BLOCKING"
        else:
            classification = "YEAR_SEMANTIC_LEAKAGE_BLOCKING"
        classified.append({**finding, "classification": classification})
    blocking = [c for c in classified
                if c["classification"] == "YEAR_SEMANTIC_LEAKAGE_BLOCKING"]
    return {"status": "PASS" if not blocking else "FAIL",
            "records_scanned": len(records),
            "LEGACY_VERSION_LABEL_ALLOWED":
                sum(1 for c in classified
                    if c["classification"] == "LEGACY_VERSION_LABEL_ALLOWED"),
            "YEAR_SEMANTIC_LEAKAGE_BLOCKING": len(blocking),
            "findings": classified[:40]}


# ------------------------------------------------- M4a-7 legacy equivalence -

IDENTITY_FIELDS = ("flight_id", "event_start_time", "event_end_time",
                   "actual_arrival_utc", "actual_departure_utc",
                   "aircraft_id", "origin_airport_id",
                   "destination_airport_id", "service_date")


def legacy_2019_equivalence(zones: dict[str, str]) -> dict:
    """M4a-7: the instance-aware ingestion must reproduce the legacy
    data2_2019 ingestion for year=2019 - sampled identity fields (first /
    middle / last per month) and full-year structural episode, rejection and
    node counts, per month. Per-month results are checkpointed so a restart
    resumes instead of recomputing completed months."""
    import gc

    from model.PRE.streaming.data2 import iter_lightweight_flights
    mismatches: list[dict] = []
    per_month: list[dict] = []
    checkpoint = OUT_ROOT / "2019" / "legacy_2019_equivalence_partial.json"
    done: dict[str, dict] = {}
    if checkpoint.is_file():
        done = json.loads(checkpoint.read_text(encoding="utf-8"))
    base = RAW / "bts" / "ontime" / "2019"
    for month in range(1, 13):
        if str(month) in done:
            per_month.append(done[str(month)])
            print(f"  equivalence 2019-{month:02d}: cached "
                  f"(rows={done[str(month)]['multiyear_rows']})", flush=True)
            continue
        matches = sorted((base / f"month={month:02d}").glob("*.csv"))
        if not matches:
            mismatches.append({"month": month, "issue": "MISSING_FILE"})
            continue
        path = matches[0]
        frame = pd.read_csv(path, usecols=list(PROJECTED_ONTIME_COLUMNS),
                            dtype=str, keep_default_na=False,
                            encoding="utf-8-sig")
        mine, _skipped = build_audit_rows(frame, zones)
        del frame
        gc.collect()
        # stream the legacy generator: identity fields are compared on the
        # fly, and only the deduped rows needed for the structural counts
        # are retained
        legacy: list[dict] = []
        identity_mismatch = 0
        identity_checked = {"first": False, "middle": False, "last": False}
        index = 0
        for legacy_row in iter_lightweight_flights(path, zones):
            legacy.append(legacy_row)
            index += 1
        del legacy_row
        legacy = dedupe_ordering_keys(legacy)
        gc.collect()
        if len(legacy) != len(mine):
            mismatches.append({"month": month, "issue": "ROW_COUNT",
                               "legacy": len(legacy), "multiyear": len(mine)})
        for label, position in (("first", 0),
                                ("middle", len(mine) // 2),
                                ("last", len(mine) - 1)):
            if not mine or position >= len(legacy) or position >= len(mine):
                continue
            identity_checked[label] = True
            for field in IDENTITY_FIELDS:
                if str(mine[position].get(field)) != str(
                        legacy[position].get(field)):
                    identity_mismatch += 1
                    mismatches.append({
                        "month": month, "issue": "IDENTITY",
                        "position": label, "field": field,
                        "legacy": str(legacy[position].get(field)),
                        "multiyear": str(mine[position].get(field))})
        legacy_episodes, legacy_rejected = pairwise_episodes(legacy)
        del legacy
        gc.collect()
        mine_episodes, mine_rejected = pairwise_episodes(mine)
        legacy_episode_count = len(legacy_episodes)
        legacy_nodes = sum(
            episode_node_count(episode_start_time=episode.episode_start_time,
                               episode_end_time=episode.episode_end_time)
            for episode, _p, _s in legacy_episodes)
        del legacy_episodes
        mine_episode_count = len(mine_episodes)
        mine_nodes = sum(
            episode_node_count(episode_start_time=episode.episode_start_time,
                               episode_end_time=episode.episode_end_time)
            for episode, _p, _s in mine_episodes)
        del mine_episodes
        gc.collect()
        if legacy_episode_count != mine_episode_count:
            mismatches.append({"month": month, "issue": "EPISODE_COUNT",
                               "legacy": legacy_episode_count,
                               "multiyear": mine_episode_count})
        if dict(legacy_rejected) != dict(mine_rejected):
            mismatches.append({"month": month, "issue": "REJECTION_REASONS",
                               "legacy": dict(legacy_rejected),
                               "multiyear": dict(mine_rejected)})
        if legacy_nodes != mine_nodes:
            mismatches.append({"month": month, "issue": "NODE_COUNT",
                               "legacy": legacy_nodes,
                               "multiyear": mine_nodes})
        record = {"month": month, "legacy_rows": index,
                  "multiyear_rows": len(mine),
                  "legacy_episodes": legacy_episode_count,
                  "multiyear_episodes": mine_episode_count,
                  "legacy_nodes": legacy_nodes,
                  "multiyear_nodes": mine_nodes,
                  "identity_mismatches": identity_mismatch,
                  "identity_checked": identity_checked}
        per_month.append(record)
        done[str(month)] = record
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps(done, indent=1), encoding="utf-8")
        print(f"  equivalence 2019-{month:02d}: rows={len(mine)} "
              f"episodes={mine_episode_count} nodes={mine_nodes} "
              f"identity_mismatch={identity_mismatch}", flush=True)
        del mine, legacy_rejected, mine_rejected
        gc.collect()
    return {"status": "PASS" if not mismatches else "FAIL",
            "per_month": per_month, "mismatches": mismatches[:40]}


def dedupe_ordering_key_rows(rows: list[dict]) -> list[dict]:
    return dedupe_ordering_keys(rows)


# ------------------------------------------------------------- year pass ---

def ontime_month_files(year: int) -> list[Path | None]:
    base = RAW / "bts" / "ontime" / str(year)
    return [next(iter(sorted((base / f"month={month:02d}").glob("*.csv"))), None)
            for month in range(1, 13)]


def route_set_db1b(year: int) -> set[str]:
    routes: set[str] = set()
    coupon_dir = RAW / "bts" / "db1b" / str(year) / "coupon"
    for quarter in (1, 2, 3, 4):
        path = coupon_dir / (f"Origin_and_Destination_Survey_DB1BCoupon_"
                             f"{year}_{quarter}.csv")
        if not path.is_file():
            continue
        for chunk in pd.read_csv(path, usecols=["Origin", "Dest"], dtype=str,
                                 keep_default_na=False, chunksize=3_000_000,
                                 encoding="utf-8-sig"):
            routes.update((chunk["Origin"] + ">" + chunk["Dest"]).tolist())
    return routes


def route_set_t100(year: int) -> set[str]:
    path = RAW / "bts" / "t100" / str(year) / "T_T100_SEGMENT_ALL_CARRIER.csv"
    routes: set[str] = set()
    if not path.is_file():
        return routes
    for chunk in pd.read_csv(path, usecols=["ORIGIN", "DEST"], dtype=str,
                             keep_default_na=False, chunksize=3_000_000,
                             encoding="utf-8-sig"):
        routes.update((chunk["ORIGIN"] + ">" + chunk["DEST"]).tolist())
    return routes


def cohort_year_pass(year: int, zones: dict[str, str],
                     station_map: dict[str, str]) -> dict:
    rng = random.Random(f"m4a-cohort-{year}")
    weather_by_airport = weather_availability_by_airport(year, station_map)
    db1b_routes = route_set_db1b(year)
    t100_routes = route_set_t100(year)
    print(f"  db1b routes={len(db1b_routes)} t100 routes={len(t100_routes)}",
          flush=True)

    totals = {
        "raw_flights": 0, "cancelled_excluded": 0, "diverted_excluded": 0,
        "skipped_other": 0, "duplicate_ordering_keys": 0,
        "structural_candidate_chains": 0,
        "pre_split_eligible_chains": 0,
        "pre_split_eligible_episodes": 0,
        "pre_split_eligible_decision_nodes": 0,
        "label_R_IB_nodes": 0, "label_D_OB_nodes": 0, "label_D_TX_nodes": 0,
        "label_JOINT_RIB_DOB_DTX_nodes": 0,
        "weather_supported_nodes": 0,
        "schedule_evidence_nodes": 0,
        "db1b_prefit_route_coverage_episodes": 0,
        "t100_prefit_route_coverage_episodes": 0,
    }
    rejected_total: Counter = Counter()
    monthly: list[dict] = []
    reservoir: list[tuple] = []
    enrichment: dict[str, list[tuple]] = {
        "label_boundary": [], "wheels_on_grid": [], "missing_weather": []}

    for month, path in enumerate(ontime_month_files(year), start=1):
        if path is None:
            monthly.append({"year": year, "month": month,
                            "status": "MISSING_FILE"})
            continue
        started = time.perf_counter()
        frame = pd.read_csv(path, usecols=list(PROJECTED_ONTIME_COLUMNS),
                            dtype=str, keep_default_na=False,
                            encoding="utf-8-sig")
        rows, skipped = build_audit_rows(frame, zones)
        episodes, rejected = pairwise_episodes(rows)
        month_nodes = month_rib = month_dob = month_dtx = month_joint = 0
        month_weather = 0
        month_db1b = month_t100 = 0
        for episode, predecessor, successor in episodes:
            nodes = episode_node_count(
                episode_start_time=episode.episode_start_time,
                episode_end_time=episode.episode_end_time)
            labels = label_support_counts(
                episode.episode_start_time, episode.episode_end_time,
                predecessor["actual_arrival_utc"],
                successor["actual_departure_utc"],
                successor.get("wheels_off_utc"))
            availability = weather_by_airport.get(
                episode.connection_airport_id)
            weather_nodes = weather_support_count(
                episode.episode_start_time, episode.episode_end_time,
                availability)
            route = (successor["origin_airport_id"] + ">"
                     + successor["destination_airport_id"])
            month_nodes += nodes
            month_rib += labels["R_IB"]
            month_dob += labels["D_OB"]
            month_dtx += labels["D_TX"]
            month_joint += labels["JOINT_RIB_DOB_DTX"]
            month_weather += weather_nodes
            month_db1b += 1 if route in db1b_routes else 0
            month_t100 += 1 if route in t100_routes else 0
            item = (episode, predecessor, successor)
            if len(reservoir) < SAMPLE_PER_MONTH * 12:
                reservoir.append(item)
            else:
                j = rng.randrange(len(reservoir))
                if j < SAMPLE_PER_MONTH * 12:
                    reservoir[j] = item
            pred_arr = predecessor["actual_arrival_utc"]
            if pred_arr is not None and on_grid_offset(pred_arr,
                                                       episode.episode_start_time):
                if len(enrichment["label_boundary"]) < ENRICHMENT_CAP:
                    enrichment["label_boundary"].append(item)
            if successor.get("wheels_off_utc") is not None and on_grid_offset(
                    successor["wheels_off_utc"], episode.episode_start_time):
                if len(enrichment["wheels_on_grid"]) < ENRICHMENT_CAP:
                    enrichment["wheels_on_grid"].append(item)
            if availability is None or len(availability) == 0:
                if len(enrichment["missing_weather"]) < ENRICHMENT_CAP:
                    enrichment["missing_weather"].append(item)
        totals["raw_flights"] += len(frame)
        totals["cancelled_excluded"] += skipped.get("cancelled", 0)
        totals["diverted_excluded"] += skipped.get("diverted", 0)
        totals["skipped_other"] += sum(
            count for key, count in skipped.items()
            if key not in ("cancelled", "diverted"))
        totals["structural_candidate_chains"] += len(episodes) + sum(
            rejected.values())
        totals["pre_split_eligible_chains"] += len(episodes)
        totals["pre_split_eligible_episodes"] += len(episodes)
        totals["pre_split_eligible_decision_nodes"] += month_nodes
        totals["label_R_IB_nodes"] += month_rib
        totals["label_D_OB_nodes"] += month_dob
        totals["label_D_TX_nodes"] += month_dtx
        totals["label_JOINT_RIB_DOB_DTX_nodes"] += month_joint
        totals["weather_supported_nodes"] += month_weather
        totals["schedule_evidence_nodes"] += month_nodes
        totals["db1b_prefit_route_coverage_episodes"] += month_db1b
        totals["t100_prefit_route_coverage_episodes"] += month_t100
        rejected_total.update(rejected)
        monthly.append({
            "year": year, "month": month, "status": "OK",
            "raw_flights": len(frame), "rows_used": len(rows),
            "pre_split_eligible_chains": len(episodes),
            "pre_split_eligible_decision_nodes": month_nodes,
            "label_R_IB_nodes": month_rib, "label_D_OB_nodes": month_dob,
            "label_D_TX_nodes": month_dtx,
            "label_JOINT_RIB_DOB_DTX_nodes": month_joint,
            "weather_supported_nodes": month_weather,
            "db1b_prefit_route_coverage_episodes": month_db1b,
            "t100_prefit_route_coverage_episodes": month_t100,
            "seconds": round(time.perf_counter() - started, 1),
        })
        print(f"  {year}-{month:02d} episodes={len(episodes)} "
              f"nodes={month_nodes} ({monthly[-1]['seconds']}s)", flush=True)
        del frame, rows, episodes
        import gc
        gc.collect()

    # deterministic stratified sample: enrichment categories first, then
    # reservoir fill to SAMPLE_TARGET
    sample: dict[str, tuple] = {}
    for category in ("label_boundary", "wheels_on_grid", "missing_weather"):
        for item in enrichment[category]:
            sample.setdefault(item[0].episode_id, item)
    shuffled = list(reservoir)
    rng.shuffle(shuffled)
    for item in shuffled:
        if len(sample) >= SAMPLE_TARGET:
            break
        sample.setdefault(item[0].episode_id, item)
    sampled = list(sample.values())[: max(SAMPLE_TARGET, 0)] or []

    return {"year": year, "totals": totals, "monthly": monthly,
            "rejection_reasons": dict(rejected_total),
            "sampled": sampled, "weather_by_airport": weather_by_airport}


# ---------------------------------------------------------------- report ---

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", type=int, nargs="*", default=list(YEARS))
    parser.add_argument("--skip-equivalence", action="store_true")
    args = parser.parse_args()

    audit = static_reuse_audit()
    if audit["status"] != "PASS":
        print(json.dumps(audit, indent=2))
        print("STATIC_REUSE_AUDIT=FAIL - M4A_BLOCKED (hard constraint)")
        return 2
    print(f"STATIC_REUSE_AUDIT=PASS ({len(audit['clean_functions'])} functions)")

    zones = load_zones()
    station_map = load_station_map()
    started = now()
    year_results: dict[int, dict] = {}

    # M4a-7: strengthened 2019 legacy equivalence runs first and gates all.
    if 2019 in args.years or not args.years:
        equivalence = legacy_2019_equivalence(zones)
        if equivalence["status"] != "PASS":
            print(json.dumps(equivalence["mismatches"], indent=2))
            print("M4A_BLOCKED_LEGACY_REGRESSION")
            return 3
        (OUT_ROOT / "2019").mkdir(parents=True, exist_ok=True)
        (OUT_ROOT / "2019" / "legacy_2019_equivalence.json").write_text(
            json.dumps(equivalence, indent=2), encoding="utf-8")
        print("LEGACY_2019_EQUIVALENCE=PASS")

    for year in args.years:
        if year not in YEARS:
            continue
        print(f"=== cohort audit {year} ===", flush=True)
        result = cohort_year_pass(year, zones, station_map)

        equivalence = production_semantic_equivalence_audit(
            result["sampled"], result["weather_by_airport"])
        print(f"  semantic equivalence: {equivalence['status']} "
              f"(nodes={equivalence['nodes_compared']}, "
              f"stage={equivalence['stage_mismatch']}, "
              f"label={equivalence['label_mask_mismatch']}, "
              f"weather={equivalence['weather_mask_mismatch']})")
        if equivalence["status"] != "PASS":
            print(json.dumps(equivalence, indent=2))
            print("M4A_BLOCKED_AUDIT_SEMANTIC_MISMATCH")
            return 3

        provenance_records = [item[0] for item in result["sampled"][:200]]
        provenance_records.extend(
            {"row": {k: str(v) for k, v in item[1].items()
                     if k in ("flight_id", "dataset_instance_id")}}
            for item in result["sampled"][:100])
        provenance = multiyear_canonical_provenance_audit(provenance_records)
        if provenance["status"] != "PASS":
            print(json.dumps(provenance, indent=2))
            print("M4A_BLOCKED_CANONICAL_PROVENANCE_LEAKAGE")
            return 3

        year_results[year] = result
        out = OUT_ROOT / str(year)
        totals = result["totals"]
        nodes = totals["pre_split_eligible_decision_nodes"]
        episodes = totals["pre_split_eligible_episodes"]
        write_csv(out / "pre_split_cohort_summary.csv",
                  ["metric", "value"],
                  [{"metric": k, "value": v} for k, v in totals.items()]
                  + [{"metric": "weather_support_rate",
                      "value": round(totals["weather_supported_nodes"] / nodes, 6)
                      if nodes else None},
                     {"metric": "DB1B_PREFIT_ROUTE_COVERAGE_rate",
                      "value": round(
                          totals["db1b_prefit_route_coverage_episodes"]
                          / episodes, 6) if episodes else None},
                     {"metric": "T100_PREFIT_ROUTE_COVERAGE_rate",
                      "value": round(
                          totals["t100_prefit_route_coverage_episodes"]
                          / episodes, 6) if episodes else None}])
        write_csv(out / "monthly.csv",
                  ["year", "month", "status", "raw_flights", "rows_used",
                   "pre_split_eligible_chains",
                   "pre_split_eligible_decision_nodes", "label_R_IB_nodes",
                   "label_D_OB_nodes", "label_D_TX_nodes",
                   "label_JOINT_RIB_DOB_DTX_nodes", "weather_supported_nodes",
                   "db1b_prefit_route_coverage_episodes",
                   "t100_prefit_route_coverage_episodes", "seconds"],
                  result["monthly"])
        write_csv(out / "rejection_reasons.csv",
                  ["year", "reason", "count"],
                  [{"year": year, "reason": reason, "count": count}
                   for reason, count in sorted(
                       result["rejection_reasons"].items(),
                       key=lambda item: -item[1])])
        (out / "production_semantic_equivalence.json").write_text(
            json.dumps(equivalence, indent=2), encoding="utf-8")
        (out / "provenance_audit.json").write_text(
            json.dumps(provenance, indent=2), encoding="utf-8")
        (out / "_COMPLETE").write_text(now() + "\n", encoding="utf-8")

    # scale estimate (M4a-6) + top-level report
    report = build_report(started, year_results)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "DATA2_2017_2022_PRE_SPLIT_COHORT_AUDIT.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_ROOT / "DATA2_2017_2022_PRE_SPLIT_COHORT_AUDIT.md").write_text(
        report["MARKDOWN"], encoding="utf-8")
    write_csv(OUT_ROOT / "DATA2_2017_2022_PRE_SPLIT_COHORT_AUDIT.csv",
              ["year", "raw_flights", "cancelled_excluded", "diverted_excluded",
               "structural_candidate_chains", "pre_split_eligible_chains",
               "pre_split_eligible_episodes",
               "pre_split_eligible_decision_nodes", "label_R_IB_nodes",
               "label_D_OB_nodes", "label_D_TX_nodes",
               "label_JOINT_RIB_DOB_DTX_nodes", "weather_supported_nodes",
               "weather_support_rate", "db1b_prefit_route_coverage_episodes",
               "t100_prefit_route_coverage_episodes"],
              report["CSV_ROWS"])
    print(f"PRE_SPLIT_COHORT_AUDIT_WRITTEN overall={report['OVERALL_STATUS']}")
    return 0


def build_report(started: str, year_results: dict[int, dict]) -> dict:
    csv_rows, summaries = [], {}
    for year in sorted(year_results):
        totals = dict(year_results[year]["totals"])
        nodes = totals["pre_split_eligible_decision_nodes"]
        episodes = totals["pre_split_eligible_episodes"]
        totals["weather_support_rate"] = round(
            totals["weather_supported_nodes"] / nodes, 6) if nodes else None
        csv_rows.append({"year": year, **{k: v for k, v in totals.items()
                                          if k != "schedule_evidence_nodes"}})
        summaries[str(year)] = totals
    total_nodes = sum(t["pre_split_eligible_decision_nodes"]
                      for t in summaries.values())
    overall = "PASS" if year_results else "PARTIAL_WITH_BLOCKERS"
    lines = ["# Data2 2017-2022 PRE-split cohort eligibility audit "
             "(data2_2017_2022, COHORT_PROFILING)", "",
             f"- Execution repository: `{REPO}`", f"- Branch: `{_git('branch', '--show-current')}`",
             f"- Start: {started}  End: {now()}",
             f"- **OVERALL_STATUS: {overall}**",
             "- Naming: PRE_SPLIT_ELIGIBLE_* (no temporal split, no reference "
             "fit/freeze, no experimental eligibility yet)", "",
             "| year | raw_flights | cancelled_excl | diverted_excl | "
             "candidate_chains | PRE_SPLIT_ELIGIBLE_EPISODES | "
             "PRE_SPLIT_ELIGIBLE_DECISION_NODES |",
             "|---|---|---|---|---|---|---|"]
    for row in csv_rows:
        lines.append(f"| {row['year']} | {row['raw_flights']} | "
                     f"{row['cancelled_excluded']} | {row['diverted_excluded']} | "
                     f"{row['structural_candidate_chains']} | "
                     f"{row['pre_split_eligible_episodes']} | "
                     f"{row['pre_split_eligible_decision_nodes']} |")
    lines += ["", "## LABEL_SUPPORT vs DECISION_TIME_EVIDENCE_SUPPORT", "",
              "| year | R_IB | D_OB | D_TX | JOINT | weather nodes | "
              "weather rate | DB1B prefit | T100 prefit |",
              "|---|---|---|---|---|---|---|---|---|"]
    for row in csv_rows:
        lines.append(
            f"| {row['year']} | {row['label_R_IB_nodes']} | "
            f"{row['label_D_OB_nodes']} | {row['label_D_TX_nodes']} | "
            f"{row['label_JOINT_RIB_DOB_DTX_nodes']} | "
            f"{row['weather_supported_nodes']} | "
            f"{row['weather_support_rate']} | "
            f"{row['db1b_prefit_route_coverage_episodes']} | "
            f"{row['t100_prefit_route_coverage_episodes']} |")
    lines += ["", "## Full-materialization scale estimate (M4a-6)", "",
              f"- total PRE_SPLIT_ELIGIBLE_DECISION_NODES: {total_nodes:,}",
              f"- estimated storage at ~{NODE_RECORD_BYTES_ESTIMATE} B/node "
              f"(empirical node-record size): "
              f"{total_nodes * NODE_RECORD_BYTES_ESTIMATE / 10 ** 9:.1f} GB",
              "- estimated M1 training rows: cannot be fixed before the "
              "temporal split exists; the per-year node table above is the "
              "upper-bound basis",
              "- runtime order: ingestion measured live in this run; node "
              "materialization scales with the node count above", ""]
    return {"EXECUTION_REPOSITORY": str(REPO), "BRANCH":
            _git("branch", "--show-current"), "START_TIME": started,
            "END_TIME": now(), "INSTANCE_CONTRACT": {
                "instance_id": INSTANCE_ID, "status": "COHORT_PROFILING",
                "RAW_INGESTION_ENABLED": True,
                "CANONICALIZATION_ENABLED": True,
                "COHORT_PROFILING_ENABLED": True,
                "PRE_MATERIALIZATION_ENABLED": False,
                "MODEL_TRAINING_ENABLED": False,
                "EXPERIMENT_ENABLED": False,
                "split_rule_id": None},
            "YEARS": sorted(year_results), "YEAR_SUMMARIES": summaries,
            "SCALE_ESTIMATE": {
                "total_pre_split_eligible_decision_nodes": total_nodes,
                "node_record_bytes_estimate": NODE_RECORD_BYTES_ESTIMATE,
                "estimated_storage_gb": round(
                    total_nodes * NODE_RECORD_BYTES_ESTIMATE / 10 ** 9, 1)},
            "CSV_ROWS": csv_rows, "OVERALL_STATUS": overall,
            "MARKDOWN": "\n".join(lines) + "\n"}


if __name__ == "__main__":
    sys.exit(main())
