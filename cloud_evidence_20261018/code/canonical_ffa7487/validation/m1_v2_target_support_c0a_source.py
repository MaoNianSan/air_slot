"""PRE-owned Jan-Sep source-clock reconstruction for M1 Gate C0A."""

from __future__ import annotations

import csv
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from model.PRE.canonical.data2_timestamps import resolve_bts_actual_timestamp
from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.canonical.normalization_common import deterministic_id, number
from model.PRE.canonical.timezone import local_hhmm_to_utc
from model.PRE.streaming.data2 import load_timezones, ontime_paths

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("T_IB_REMAINING_HAZARD", "D_OB", "D_TX")
SPLITS = ("train", "calibration", "development")
CURRENT_SUPPORT = {"T_IB_REMAINING_HAZARD": 360, "D_OB": 180, "D_TX": 60}


def _active_label_rows(cache, target: str, split: str) -> list[tuple[int, float]]:
    store = cache.store
    return [
        (index, float(store.labels[target][index]))
        for index, current_split in enumerate(store.sample_splits)
        if current_split == split and bool(store.active[target][index])
    ]


def _local_wall_candidates(naive: datetime, timezone_name: str) -> tuple[datetime, ...]:
    zone = ZoneInfo(timezone_name)
    candidates = []
    for fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=fold)
        roundtrip = aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
        utc_value = aware.astimezone(timezone.utc)
        if roundtrip == naive and utc_value not in candidates:
            candidates.append(utc_value)
    return tuple(candidates)


def classify_departure_values(
    *,
    schedule_utc: datetime,
    direct_utc: datetime,
    timezone_name: str,
    signed_delay: float,
    old_difference: float | None = None,
    date_offset_resolved: bool = False,
) -> dict[str, Any]:
    zone = ZoneInfo(timezone_name)
    schedule_local = schedule_utc.astimezone(zone)
    actual_local = direct_utc.astimezone(zone)
    schedule_naive = schedule_local.replace(tzinfo=None)
    actual_naive = actual_local.replace(tzinfo=None)
    offset_change = (
        actual_local.utcoffset() - schedule_local.utcoffset()
    ).total_seconds() / 60.0
    direct_elapsed = (direct_utc - schedule_utc).total_seconds() / 60.0
    expected_utc_elapsed = float(signed_delay) - offset_change
    residual = direct_elapsed - expected_utc_elapsed
    expected_wall = schedule_naive + timedelta(minutes=float(signed_delay))
    wall_residual = (actual_naive - expected_wall).total_seconds() / 60.0
    wall_candidates = _local_wall_candidates(expected_wall, timezone_name)
    if abs(wall_residual) <= 1 and offset_change != 0:
        category = "DST_CLOCK_BASIS_EXPLAINED"
    elif abs(wall_residual) <= 1:
        category = (
            "SOURCE_CONSISTENT"
            if old_difference is None or old_difference <= 1
            else "SOURCE_CLOCK_ROUNDING"
        )
    elif offset_change != 0 and not wall_candidates:
        category = "DATE_OFFSET_AMBIGUOUS"
    elif abs(residual) <= 1 and offset_change != 0:
        category = "DATE_OFFSET_AMBIGUOUS"
    elif abs(wall_residual) <= 5:
        category = "SOURCE_CLOCK_ROUNDING"
    else:
        category = "DIRECT_CLOCK_SIGNED_DELAY_CONFLICT"
    return {
        "schedule_local_datetime": schedule_local.isoformat(),
        "actual_direct_local_datetime": actual_local.isoformat(),
        "schedule_utc_offset_minutes": schedule_local.utcoffset().total_seconds()
        / 60.0,
        "actual_utc_offset_minutes": actual_local.utcoffset().total_seconds() / 60.0,
        "offset_change_minutes": offset_change,
        "signed_dep_delay": float(signed_delay),
        "direct_utc_elapsed_minutes": direct_elapsed,
        "expected_utc_elapsed_from_local_delay": expected_utc_elapsed,
        "residual_minutes": residual,
        "expected_actual_local_wall_datetime": expected_wall.isoformat(),
        "local_wall_clock_residual_minutes": wall_residual,
        "local_wall_clock_candidate_count": len(wall_candidates),
        "classification": category,
        "date_offset_resolved": bool(date_offset_resolved),
    }


def classify_departure_consistency(
    *,
    schedule_utc: datetime,
    direct_utc: datetime,
    timezone_name: str,
    signed_delay: float,
) -> str:
    """Public seam for synthetic DST/source-clock contract tests."""
    return classify_departure_values(
        schedule_utc=schedule_utc,
        direct_utc=direct_utc,
        timezone_name=timezone_name,
        signed_delay=signed_delay,
    )["classification"]


def _dst_candidate(
    clock: dict[str, Any], timezone_name: str, direct_utc: datetime
) -> datetime | None:
    naive = datetime.fromisoformat(clock["expected_actual_local_wall_datetime"])
    candidates = _local_wall_candidates(naive, timezone_name)
    if not candidates:
        return None
    return min(
        candidates, key=lambda value: (abs((value - direct_utc).total_seconds()), value)
    )


def _flight_id(row: dict[str, Any]) -> str:
    return deterministic_id(
        "flight",
        {
            key: row.get(key)
            for key in (
                "FlightDate",
                "Reporting_Airline",
                "Flight_Number_Reporting_Airline",
                "Origin",
                "Dest",
            )
        },
    )


def _hhmm(value: object) -> str | None:
    text = str(value or "").strip().split(".", 1)[0]
    if not text or not text.lstrip("-").isdigit():
        return None
    number_value = int(text)
    if number_value == 2400:
        number_value = 0
    return f"{number_value:04d}" if 0 <= number_value <= 2359 else None


def scan_source_clock(cache, episodes: dict[str, Any]) -> dict[str, Any]:
    """Scan all departure mismatches and canonicalize only selected cohort rows."""
    store = cache.store
    cohort_episode_ids = set(store.sample_episode_ids)
    overflow_episode_ids = set()
    for target in TARGETS:
        for split in SPLITS:
            for index, value in _active_label_rows(cache, target, split):
                if value >= CURRENT_SUPPORT[target]:
                    overflow_episode_ids.add(store.sample_episode_ids[index])

    cohort_flights: set[str] = set()
    episode_flight_ids: dict[str, set[str]] = {}
    for episode_id in cohort_episode_ids:
        episode = episodes.get(episode_id)
        if episode is None:
            continue
        flight_ids = {episode.predecessor_flight_id, episode.successor_flight_id}
        cohort_flights.update(flight_ids)
        episode_flight_ids[episode_id] = flight_ids
    b2_lineage_flights = {
        str((lineage or {}).get("schedule_reference", {}).get("flight_id"))
        for lineage in store.static_context_lineages
        if (lineage or {}).get("schedule_reference", {}).get("flight_id")
    }
    overflow_by_split = {
        split: {
            store.sample_episode_ids[index]
            for target in TARGETS
            for index, value in _active_label_rows(cache, target, split)
            if value >= CURRENT_SUPPORT[target]
        }
        for split in SPLITS
    }
    train_d_ob_overflow = {
        store.sample_episode_ids[index]
        for index, value in _active_label_rows(cache, "D_OB", "train")
        if value >= CURRENT_SUPPORT["D_OB"]
    }

    zones = load_timezones(ROOT / "data2" / "refs" / "us_airport_timezones.csv")
    mismatch_rows: list[dict[str, Any]] = []
    source_records: dict[str, dict[str, Any]] = {}
    paths = ontime_paths(ROOT, range(1, 10))
    rows_by_split = Counter()
    for month, path in enumerate(paths, start=1):
        split = (
            "train" if month <= 6 else "calibration" if month == 7 else "development"
        )
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            for row_number, row in enumerate(csv.DictReader(handle), start=2):
                row_flight_id = _flight_id(row)
                if row_flight_id in cohort_flights:
                    schedule, outcome = canonicalize_ontime_row(row, zones)
                    source_records[row_flight_id] = {
                        "flight_id": row_flight_id,
                        "flight_date": row.get("FlightDate"),
                        "origin": row.get("Origin"),
                        "destination": row.get("Dest"),
                        "carrier": row.get("Reporting_Airline"),
                        "flight_number": row.get("Flight_Number_Reporting_Airline"),
                        "timezone_name": zones.get(row.get("Origin", "")),
                        "CRSDepTime": row.get("CRSDepTime"),
                        "DepTime": row.get("DepTime"),
                        "DepDelay": number(row.get("DepDelay")),
                        "DepDelayMinutes": number(row.get("DepDelayMinutes")),
                        "schedule_departure_utc": schedule.scheduled_departure_utc,
                        "schedule_arrival_utc": schedule.scheduled_arrival_utc,
                        "actual_departure_utc": outcome.actual_departure_utc,
                        "actual_departure_direct_utc": outcome.actual_departure_direct_utc,
                        "actual_departure_derived_utc": outcome.actual_departure_derived_utc,
                        "actual_arrival_utc": outcome.actual_arrival_utc,
                        "taxi_out_minutes": outcome.taxi_out_minutes,
                        "quality_flags": tuple(outcome.quality_flags),
                    }
                try:
                    day = date.fromisoformat(str(row["FlightDate"])[:10])
                    zone = zones.get(row.get("Origin", ""))
                    schedule_utc = (
                        local_hhmm_to_utc(day, row.get("CRSDepTime"), zone)
                        if zone
                        else None
                    )
                    signed = number(row.get("DepDelay"))
                    if schedule_utc is None or signed is None or not zone:
                        continue
                    resolution = resolve_bts_actual_timestamp(
                        service_day=day,
                        schedule_utc=schedule_utc,
                        direct_hhmm=row.get("DepTime"),
                        timezone_name=zone,
                        signed_delay_value=row.get("DepDelay"),
                        reporting_delay_minutes_value=row.get("DepDelayMinutes"),
                        label="DEPARTURE",
                    )
                    if (
                        resolution.difference_minutes is None
                        or resolution.direct_utc is None
                    ):
                        continue
                    rows_by_split[split] += 1
                    clock = classify_departure_values(
                        schedule_utc=schedule_utc,
                        direct_utc=resolution.direct_utc,
                        timezone_name=zone,
                        signed_delay=float(signed),
                        old_difference=resolution.difference_minutes,
                        date_offset_resolved=resolution.date_offset_resolved,
                    )
                    if resolution.difference_minutes <= 1:
                        continue
                    direct_hhmm = _hhmm(row.get("DepTime"))
                    resolved_hhmm = resolution.direct_utc.astimezone(
                        ZoneInfo(zone)
                    ).strftime("%H%M")
                    if direct_hhmm is not None and direct_hhmm != resolved_hhmm:
                        clock["classification"] = "DATE_OFFSET_AMBIGUOUS"
                        clock["direct_clock_roundtrip_hhmm"] = resolved_hhmm
                        clock["raw_direct_hhmm"] = direct_hhmm
                    candidate = _dst_candidate(clock, zone, resolution.direct_utc)
                    repairable_class = clock["classification"] in {
                        "DST_CLOCK_BASIS_EXPLAINED",
                        "SOURCE_CLOCK_ROUNDING",
                    }
                    interpretation = {
                        "DST_CLOCK_BASIS_EXPLAINED": "DST_LOCAL_CLOCK_BASIS_EFFECT",
                        "SOURCE_CLOCK_ROUNDING": "SOURCE_CLOCK_ROUNDING",
                        "DATE_OFFSET_AMBIGUOUS": "RAW_DIRECT_CLOCK_NONEXISTENT_OR_AMBIGUOUS_LOCAL_TIME",
                        "DIRECT_CLOCK_SIGNED_DELAY_CONFLICT": "RAW_BTS_DIRECT_CLOCK_SIGNED_DELAY_CONTRADICTION",
                    }.get(clock["classification"], "OTHER_SOURCE_CONDITION")
                    mismatch_rows.append(
                        {
                            "split": split,
                            "source_path": str(path.relative_to(ROOT)),
                            "source_row_number": row_number,
                            "flight_id": row_flight_id,
                            "FlightDate": row.get("FlightDate"),
                            "Origin": row.get("Origin"),
                            "Dest": row.get("Dest"),
                            "Carrier": row.get("Reporting_Airline"),
                            "Flight_Number": row.get("Flight_Number_Reporting_Airline"),
                            "Tail_Number": row.get("Tail_Number"),
                            "CRSDepTime": row.get("CRSDepTime"),
                            "DepTime": row.get("DepTime"),
                            "DepDelay": float(signed),
                            "DepDelayMinutes": number(row.get("DepDelayMinutes")),
                            "old_difference_minutes": resolution.difference_minutes,
                            "timezone": zone,
                            "schedule_utc": schedule_utc,
                            "actual_direct_utc": resolution.direct_utc,
                            "current_canonical_timestamp": resolution.canonical_utc,
                            "dst_aware_candidate_timestamp": candidate,
                            "canonical_timestamp_changed": (
                                repairable_class
                                and candidate is not None
                                and resolution.canonical_utc is not None
                                and abs(
                                    (
                                        candidate - resolution.canonical_utc
                                    ).total_seconds()
                                )
                                > 1
                            ),
                            "forensic_interpretation": interpretation,
                            **clock,
                        }
                    )
                except Exception:
                    continue

    inconsistent = {row["flight_id"] for row in mismatch_rows}
    selected_inconsistent = inconsistent & cohort_flights
    source_conflicts = {
        row["flight_id"]
        for row in mismatch_rows
        if row["classification"] == "DIRECT_CLOCK_SIGNED_DELAY_CONFLICT"
    }

    def flights_in_episodes(episode_ids: set[str]) -> set[str]:
        output: set[str] = set()
        for episode_id in episode_ids:
            output.update(episode_flight_ids.get(episode_id, ()))
        return output

    return {
        "scope": "TRAIN_CALIBRATION_DEVELOPMENT_ONLY_MONTHS_01_09",
        "source_paths": [str(path.relative_to(ROOT)) for path in paths],
        "row_counts_with_direct_departure": dict(rows_by_split),
        "departure_inconsistency_rows": mismatch_rows,
        "departure_inconsistency_count": len(mismatch_rows),
        "departure_classification_counts": dict(
            Counter(row["classification"] for row in mismatch_rows)
        ),
        "inconsistent_flight_ids": sorted(inconsistent),
        "cohort_flight_ids": sorted(cohort_flights),
        "selected_canonical_records": source_records,
        "source_record_count": len(source_records),
        "intersection": {
            "total_inconsistent_flights": len(inconsistent),
            "in_a2_episode_cohort": len(selected_inconsistent),
            "in_b2_frozen_samples": len(inconsistent & b2_lineage_flights),
            "in_c0_train_overflow": len(
                inconsistent & flights_in_episodes(overflow_by_split["train"])
            ),
            "in_c0_calibration_overflow": len(
                inconsistent & flights_in_episodes(overflow_by_split["calibration"])
            ),
            "in_c0_development_overflow": len(
                inconsistent & flights_in_episodes(overflow_by_split["development"])
            ),
            "in_c0_train_d_ob_overflow": len(
                inconsistent & flights_in_episodes(train_d_ob_overflow)
            ),
            "conflict_flights_in_a2_cohort": len(
                source_conflicts & selected_inconsistent
            ),
        },
        "canonical_timestamp_change_count": sum(
            bool(row["canonical_timestamp_changed"]) for row in mismatch_rows
        ),
        "canonical_timestamp_change_count_in_b2": sum(
            bool(row["canonical_timestamp_changed"])
            and row["flight_id"] in b2_lineage_flights
            for row in mismatch_rows
        ),
        "max_difference_case": (
            max(mismatch_rows, key=lambda row: float(row["old_difference_minutes"]))
            if mismatch_rows
            else None
        ),
        "overflow_episode_ids": sorted(overflow_episode_ids),
        "final_test_access_count": 0,
    }


__all__ = [
    "classify_departure_consistency",
    "classify_departure_values",
    "scan_source_clock",
]
