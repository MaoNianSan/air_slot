"""BTS source-semantic diagnostics for M1 V2 Data Gate A2."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from model.PRE.canonical.data2_timestamps import resolve_bts_actual_timestamp
from model.PRE.canonical.normalization_common import number
from model.PRE.canonical.timezone import infer_rollover, local_hhmm_to_utc
from model.PRE.streaming.data2 import load_timezones, ontime_paths

SIGNED_REPORTING_FIELDS = {
    "departure": ("DepDelay", "DepDelayMinutes"),
    "arrival": ("ArrDelay", "ArrDelayMinutes"),
}
REQUIRED_COLUMNS = ("DepDelay", "ArrDelay", "DepDelayMinutes", "ArrDelayMinutes")
Heartbeat = Callable[..., None]


def _number(value: object) -> float | None:
    try:
        return number(value)
    except (TypeError, ValueError):
        return None


def _split(month: int) -> str:
    if month <= 6:
        return "train"
    if month == 7:
        return "calibration"
    if month <= 9:
        return "development"
    raise RuntimeError("FINAL_TEST_SOURCE_PATH_SELECTED")


def _quantile(histogram: Counter[float], q: float) -> float | None:
    total = sum(histogram.values())
    if not total:
        return None
    target = round((total - 1) * q)
    cumulative = 0
    for value in sorted(histogram):
        cumulative += histogram[value]
        if cumulative > target:
            return value
    raise AssertionError("quantile histogram exhausted")


@dataclass
class RelationshipAccumulator:
    both_available: int = 0
    negative_signed: int = 0
    exact: int = 0
    within_1min: int = 0
    violations: int = 0
    samples: list[dict[str, Any]] = field(default_factory=list)

    def add(
        self, signed: float | None, reporting: float | None, context: dict[str, Any]
    ) -> None:
        if signed is None or reporting is None:
            return
        self.both_available += 1
        self.negative_signed += int(signed < 0)
        difference = abs(reporting - max(signed, 0.0))
        self.exact += int(difference == 0)
        self.within_1min += int(difference <= 1)
        if difference > 1:
            self.violations += 1
            if len(self.samples) < 10:
                self.samples.append(
                    {
                        **context,
                        "signed_delay": signed,
                        "reporting_delay_minutes": reporting,
                        "expected_reporting_delay_minutes": max(signed, 0.0),
                        "absolute_difference_minutes": difference,
                    }
                )

    def payload(self) -> dict[str, Any]:
        denominator = self.both_available
        return {
            "both_available": denominator,
            "negative_signed_count": self.negative_signed,
            "exact_relation_rate": self.exact / denominator if denominator else None,
            "within_1min_relation_rate": (
                self.within_1min / denominator if denominator else None
            ),
            "violation_count": self.violations,
            "deterministic_violation_samples": self.samples,
        }


@dataclass
class GroupAccumulator:
    count: int = 0
    exact: int = 0
    within_1min: int = 0
    within_5min: int = 0
    max_difference: float = 0.0

    def add(self, difference: float) -> None:
        self.count += 1
        self.exact += int(difference == 0)
        self.within_1min += int(difference <= 1)
        self.within_5min += int(difference <= 5)
        self.max_difference = max(self.max_difference, difference)

    def payload(self, key: str) -> dict[str, Any]:
        if not self.count:
            return {
                "group": key,
                "count": 0,
                "exact_agreement_rate": None,
                "within_1min_rate": None,
                "within_5min_rate": None,
                "max_abs_difference_minutes": None,
            }
        return {
            "group": key,
            "count": self.count,
            "exact_agreement_rate": self.exact / self.count,
            "within_1min_rate": self.within_1min / self.count,
            "within_5min_rate": self.within_5min / self.count,
            "max_abs_difference_minutes": self.max_difference,
        }


@dataclass
class ConsistencyAccumulator:
    both_available: int = 0
    exact: int = 0
    within_1min: int = 0
    within_5min: int = 0
    differences: Counter[float] = field(default_factory=Counter)
    date_offset_resolved: int = 0
    multi_day_offset: int = 0
    samples: list[dict[str, Any]] = field(default_factory=list)
    negative: GroupAccumulator = field(default_factory=GroupAccumulator)
    cross_midnight: GroupAccumulator = field(default_factory=GroupAccumulator)
    multi_day: GroupAccumulator = field(default_factory=GroupAccumulator)
    carriers: dict[str, GroupAccumulator] = field(
        default_factory=lambda: defaultdict(GroupAccumulator)
    )
    airports: dict[str, GroupAccumulator] = field(
        default_factory=lambda: defaultdict(GroupAccumulator)
    )

    def add(
        self,
        *,
        difference: float,
        signed_delay: float,
        carrier: str,
        airport: str,
        cross_midnight: bool,
        date_offset_resolved: bool,
        multi_day: bool,
        context: dict[str, Any],
    ) -> None:
        difference = round(float(difference), 6)
        self.both_available += 1
        self.exact += int(difference == 0)
        self.within_1min += int(difference <= 1)
        self.within_5min += int(difference <= 5)
        self.differences[difference] += 1
        self.date_offset_resolved += int(date_offset_resolved)
        self.multi_day_offset += int(multi_day)
        self.carriers[carrier or "<MISSING>"].add(difference)
        self.airports[airport or "<MISSING>"].add(difference)
        if signed_delay < 0:
            self.negative.add(difference)
        if cross_midnight:
            self.cross_midnight.add(difference)
        if multi_day:
            self.multi_day.add(difference)
        if difference > 1 and len(self.samples) < 10:
            self.samples.append({**context, "abs_difference_minutes": difference})

    @staticmethod
    def _groups(groups: dict[str, GroupAccumulator]) -> list[dict[str, Any]]:
        eligible = (
            item.payload(key) for key, item in groups.items() if item.count >= 100
        )
        return sorted(
            eligible,
            key=lambda item: (
                item["within_1min_rate"],
                item["within_5min_rate"],
                -item["count"],
                item["group"],
            ),
        )[:20]

    def payload(self) -> dict[str, Any]:
        denominator = self.both_available
        return {
            "both_available_count": denominator,
            "exact_agreement_rate": self.exact / denominator if denominator else None,
            "within_1min_rate": self.within_1min / denominator if denominator else None,
            "within_5min_rate": self.within_5min / denominator if denominator else None,
            "median_abs_difference_minutes": _quantile(self.differences, 0.5),
            "p95_abs_difference_minutes": _quantile(self.differences, 0.95),
            "p99_abs_difference_minutes": _quantile(self.differences, 0.99),
            "max_abs_difference_minutes": max(self.differences, default=None),
            "date_offset_resolved_count": self.date_offset_resolved,
            "multi_day_offset_count": self.multi_day_offset,
            "deterministic_inconsistency_samples": self.samples,
            "stratification": {
                "negative_delay": self.negative.payload("negative_delay"),
                "cross_midnight": self.cross_midnight.payload("cross_midnight"),
                "multi_day": self.multi_day.payload("multi_day"),
                "lowest_within_1min_carriers_min_n_100": self._groups(self.carriers),
                "lowest_within_1min_airports_min_n_100": self._groups(self.airports),
            },
        }


def _local(value: datetime | None, timezone_name: str) -> str | None:
    return (
        None if value is None else value.astimezone(ZoneInfo(timezone_name)).isoformat()
    )


def _gate_status(consistency: dict[str, dict[str, dict[str, Any]]]) -> str:
    statuses = []
    for split in ("train", "calibration", "development"):
        for side in ("departure", "arrival"):
            item = consistency[split][side]
            within_1 = item["within_1min_rate"]
            within_5 = item["within_5min_rate"]
            if within_1 is not None and within_1 >= 0.99:
                statuses.append("PASS_STRONG")
            elif within_1 is not None and within_1 >= 0.95 and within_5 >= 0.99:
                statuses.append("PASS_WITH_SOURCE_ROUNDING")
            else:
                statuses.append("HUMAN_REVIEW")
    if "HUMAN_REVIEW" in statuses:
        return "HUMAN_REVIEW"
    if "PASS_WITH_SOURCE_ROUNDING" in statuses:
        return "PASS_WITH_SOURCE_ROUNDING"
    return "PASS_STRONG"


def scan_bts_signed_delay_semantics(
    root: Path, *, heartbeat: Heartbeat | None = None
) -> dict[str, Any]:
    paths = ontime_paths(root, range(1, 10))
    if any(path.parent.name in {"month=10", "month=11", "month=12"} for path in paths):
        raise RuntimeError("FINAL_TEST_SOURCE_PATH_SELECTED")
    zones = load_timezones(root / "data2" / "refs" / "us_airport_timezones.csv")
    header_checks: dict[str, dict[str, bool]] = {}
    for path in paths:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            header = set(next(csv.reader(handle), ()))
        header_checks[str(path.relative_to(root))] = {
            column: column in header for column in REQUIRED_COLUMNS
        }
    columns = {
        column: all(check[column] for check in header_checks.values())
        for column in REQUIRED_COLUMNS
    }
    if not all(columns.values()):
        return {
            "scope": "TRAIN_CALIBRATION_DEVELOPMENT_ONLY",
            "source_paths": list(header_checks),
            "source_column_available": columns,
            "header_checks": header_checks,
            "row_counts": {},
            "delay_reporting_relationship": {},
            "direct_signed_consistency": {},
            "early_operation_examples": {"departure": [], "arrival": []},
            "gate_status": "BTS_SIGNED_DELAY_SOURCE_COLUMN_MISSING",
            "final_test_access_count": 0,
        }

    relationships = {
        split: {side: RelationshipAccumulator() for side in SIGNED_REPORTING_FIELDS}
        for split in ("train", "calibration", "development")
    }
    consistency = {
        split: {side: ConsistencyAccumulator() for side in SIGNED_REPORTING_FIELDS}
        for split in ("train", "calibration", "development")
    }
    early_examples = {"departure": [], "arrival": []}
    row_counts = Counter()

    for month, path in enumerate(paths, start=1):
        split = _split(month)
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_number, row in enumerate(reader, start=2):
                row_counts[split] += 1
                context = {
                    "source_path": str(path.relative_to(root)),
                    "source_row_number": row_number,
                    "FlightDate": row.get("FlightDate"),
                    "Reporting_Airline": row.get("Reporting_Airline"),
                    "Origin": row.get("Origin"),
                    "Dest": row.get("Dest"),
                }
                for side, (
                    signed_name,
                    reporting_name,
                ) in SIGNED_REPORTING_FIELDS.items():
                    relationships[split][side].add(
                        _number(row.get(signed_name)),
                        _number(row.get(reporting_name)),
                        context,
                    )
                try:
                    service_day = date.fromisoformat(str(row["FlightDate"])[:10])
                    origin, destination = row.get("Origin", ""), row.get("Dest", "")
                    if origin not in zones or destination not in zones:
                        continue
                    scheduled_departure = local_hhmm_to_utc(
                        service_day, row.get("CRSDepTime"), zones[origin]
                    )
                    scheduled_arrival = local_hhmm_to_utc(
                        service_day, row.get("CRSArrTime"), zones[destination]
                    )
                    if scheduled_departure is None or scheduled_arrival is None:
                        continue
                    scheduled_arrival = infer_rollover(
                        scheduled_departure, scheduled_arrival
                    )
                except Exception:
                    continue

                for (
                    side,
                    schedule,
                    direct_name,
                    signed_name,
                    reporting_name,
                    airport,
                    zone,
                ) in (
                    (
                        "departure",
                        scheduled_departure,
                        "DepTime",
                        "DepDelay",
                        "DepDelayMinutes",
                        origin,
                        zones[origin],
                    ),
                    (
                        "arrival",
                        scheduled_arrival,
                        "ArrTime",
                        "ArrDelay",
                        "ArrDelayMinutes",
                        destination,
                        zones[destination],
                    ),
                ):
                    signed_delay = _number(row.get(signed_name))
                    resolution = resolve_bts_actual_timestamp(
                        service_day=service_day,
                        schedule_utc=schedule,
                        direct_hhmm=row.get(direct_name),
                        timezone_name=zone,
                        signed_delay_value=row.get(signed_name),
                        reporting_delay_minutes_value=row.get(reporting_name),
                        label=side.upper(),
                    )
                    if signed_delay is None or resolution.difference_minutes is None:
                        continue
                    target = resolution.signed_target_utc
                    cross_midnight = bool(
                        target is not None
                        and target.astimezone(ZoneInfo(zone)).date()
                        != schedule.astimezone(ZoneInfo(zone)).date()
                    )
                    detailed = {
                        **context,
                        "CRS_time": row.get(
                            "CRSDepTime" if side == "departure" else "CRSArrTime"
                        ),
                        "direct_actual_clock": row.get(direct_name),
                        "signed_delay": signed_delay,
                        "reporting_delay_minutes": _number(row.get(reporting_name)),
                        "direct_date_resolved": _local(resolution.direct_utc, zone),
                        "signed_target": _local(target, zone),
                    }
                    consistency[split][side].add(
                        difference=resolution.difference_minutes,
                        signed_delay=signed_delay,
                        carrier=row.get("Reporting_Airline", ""),
                        airport=airport,
                        cross_midnight=cross_midnight,
                        date_offset_resolved=resolution.date_offset_resolved,
                        multi_day=resolution.multi_day_offset,
                        context=detailed,
                    )
                    if signed_delay < 0 and len(early_examples[side]) < 5:
                        reporting = _number(row.get(reporting_name))
                        old_target = (
                            None
                            if reporting is None
                            else schedule + timedelta(minutes=reporting)
                        )
                        early_examples[side].append(
                            {
                                **detailed,
                                "scheduled_timestamp": _local(schedule, zone),
                                "old_derived_timestamp": _local(old_target, zone),
                                "new_derived_timestamp": _local(target, zone),
                                "canonical_actual_timestamp": _local(
                                    resolution.canonical_utc, zone
                                ),
                            }
                        )
        if heartbeat is not None:
            heartbeat(
                "SOURCE_SEMANTICS_MONTH_COMPLETE",
                current_month=f"2019-{month:02d}",
                current_file=path.name,
                rows=row_counts[split],
                progress=month / len(paths),
                final_test_access_count=0,
            )

    status = _gate_status(
        {
            split: {side: value.payload() for side, value in sides.items()}
            for split, sides in consistency.items()
        }
    )
    return {
        "scope": "TRAIN_CALIBRATION_DEVELOPMENT_ONLY",
        "source_paths": list(header_checks),
        "source_column_available": columns,
        "header_checks": header_checks,
        "row_counts": dict(row_counts),
        "delay_reporting_relationship": {
            split: {side: value.payload() for side, value in sides.items()}
            for split, sides in relationships.items()
        },
        "direct_signed_consistency": {
            split: {side: value.payload() for side, value in sides.items()}
            for split, sides in consistency.items()
        },
        "early_operation_examples": early_examples,
        "gate_status": status,
        "final_test_access_count": 0,
    }


__all__ = [
    "ConsistencyAccumulator",
    "RelationshipAccumulator",
    "scan_bts_signed_delay_semantics",
]
