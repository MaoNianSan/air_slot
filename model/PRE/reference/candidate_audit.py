"""Development-only M2 reference diagnostics; never a production artifact."""

from __future__ import annotations

import csv
import io
import json
import math
import sqlite3
import tempfile
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data2"
OUT = ROOT / "outputs" / "m2_audit"
MONTHS = {"train": range(1, 7), "development": (8, 9)}
HORIZONS = (180, 360, 480)


def _missing(value) -> bool:
    return value is None or str(value).strip().upper() in {
        "",
        "NA",
        "N/A",
        "NAN",
        "NONE",
        "NULL",
    }


def _number(value):
    if _missing(value):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _utc(day: date, hhmm, zone: str):
    if _missing(hhmm):
        return None
    text = str(hhmm).strip().split(".")[0].zfill(4)
    try:
        hour, minute = int(text[:-2]), int(text[-2:])
    except ValueError:
        return None
    if hour == 24 and minute == 0:
        day += timedelta(days=1)
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return (
        datetime(
            day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(zone)
        ).timestamp()
        / 60
    )


def _actual_utc_minutes(
    day: date, schedule: float, direct_hhmm, signed_delay, zone: str
):
    """Mirror PRE direct-clock precedence with signed-delay date disambiguation."""
    direct = _utc(day, direct_hhmm, zone)
    delay = _number(signed_delay)
    signed_target = None if delay is None else schedule + delay
    if direct is not None and signed_target is not None:
        day_offset = int(round((signed_target - direct) / (24 * 60)))
        candidates = (direct + (day_offset + shift) * 24 * 60 for shift in (-1, 0, 1))
        return min(candidates, key=lambda value: (abs(value - signed_target), value))
    if direct is not None:
        while direct < schedule - 12 * 60:
            direct += 24 * 60
        return direct
    return signed_target


def _zip(month: int) -> Path:
    return (
        DATA
        / "_download"
        / "bts"
        / "ontime"
        / "2019"
        / (
            f"On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2019_{month}.zip"
        )
    )


def _iter_rows(month: int):
    path = _zip(month)
    with zipfile.ZipFile(path) as archive:
        member = next(
            name for name in archive.namelist() if name.lower().endswith(".csv")
        )
        with (
            archive.open(member) as raw,
            io.TextIOWrapper(
                raw, encoding="utf-8-sig", errors="replace", newline=""
            ) as stream,
        ):
            yield from csv.DictReader(stream)


def _quantile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    index = p * (len(ordered) - 1)
    lo, hi = math.floor(index), math.ceil(index)
    return (
        ordered[lo]
        if lo == hi
        else ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)
    )


def _summary(values):
    return {
        "n": len(values),
        "mean": sum(values) / len(values) if values else None,
        **{
            f"p{int(p*100):02d}": _quantile(values, p)
            for p in (0.05, 0.20, 0.50, 0.80, 0.95)
        },
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def _hist_summary(hist):
    count = sum(hist.values())
    if not count:
        return {
            "n": 0,
            "mean": None,
            "p05": None,
            "p20": None,
            "p50": None,
            "p80": None,
            "p95": None,
            "min": None,
            "max": None,
        }
    ordered = sorted(hist)

    def quantile(p):
        index = p * (count - 1)
        lo, hi = math.floor(index), math.ceil(index)

        def at(position):
            cumulative = 0
            for value in ordered:
                cumulative += hist[value]
                if cumulative > position:
                    return value

        a, b = at(lo), at(hi)
        return a if lo == hi else a + (b - a) * (index - lo)

    return {
        "n": count,
        "mean": sum(value * n for value, n in hist.items()) / count,
        **{f"p{int(p*100):02d}": quantile(p) for p in (0.05, 0.20, 0.50, 0.80, 0.95)},
        "min": ordered[0],
        "max": ordered[-1],
    }


def _sql_values(db, kind, part):
    return (
        row[0]
        for row in db.execute(
            "SELECT value FROM refs WHERE kind=? AND part=? ORDER BY value",
            (kind, part),
        )
    )


def _sql_summary(db, kind, part, *, eligibility_max=None):
    extra = "" if eligibility_max is None else " AND eligibility>=0 AND eligibility<=?"
    args = (kind, part) if eligibility_max is None else (kind, part, eligibility_max)
    count, mean, minimum, maximum = db.execute(
        "SELECT count(*),avg(value),min(value),max(value) FROM refs WHERE kind=? AND part=?"
        + extra,
        args,
    ).fetchone()
    result = {"n": count, "mean": mean, "min": minimum, "max": maximum}
    for p in (0.05, 0.20, 0.50, 0.80, 0.95):
        if not count:
            value = None
        else:
            index = p * (count - 1)
            lo, hi = math.floor(index), math.ceil(index)
            values = [
                row[0]
                for row in db.execute(
                    "SELECT value FROM refs WHERE kind=? AND part=?"
                    + extra
                    + " ORDER BY value LIMIT 2 OFFSET ?",
                    args + (lo,),
                )
            ]
            value = (
                values[0]
                if lo == hi
                else values[0] + (values[1] - values[0]) * (index - lo)
            )
        result[f"p{int(p*100):02d}"] = value
    return result


def _group_refs(db, kind, keys, percentile, min_n, *, eligibility_max=None):
    columns = "k1" if len(keys) == 1 else "k1,k2"
    extra = "" if eligibility_max is None else " AND eligibility>=0 AND eligibility<=?"
    args = (kind,) if eligibility_max is None else (kind, eligibility_max)
    ordered = db.execute(
        f"SELECT {columns},value FROM refs WHERE kind=? AND part='train'{extra} ORDER BY {columns},value",
        args,
    )
    refs, cell_counts, current, values = {}, {}, None, []

    def flush():
        if current is not None:
            cell_counts[current] = len(values)
            if len(values) >= min_n:
                refs[current] = _quantile(values, percentile)

    for row in ordered:
        key = (row[0],) if len(keys) == 1 else (row[0], row[1])
        if current is not None and key != current:
            flush()
            values = []
        current = key
        values.append(row[-1])
    flush()
    return refs, cell_counts


def _coverage(rows, levels):
    counts = defaultdict(int)
    total = 0
    for row in rows:
        total += 1
        selected = "UNSUPPORTED"
        for name, keys, refs in levels:
            if tuple(row[key] for key in keys) in refs:
                selected = name
                break
        counts[selected] += 1
    return {
        name: {"n": count, "fraction": count / total if total else 0}
        for name, count in sorted(counts.items())
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    zones_path = DATA / "refs" / "us_airport_timezones.csv"
    with zones_path.open(encoding="utf-8-sig", newline="") as stream:
        zones = {row["iata"]: row["timezone"] for row in csv.DictReader(stream)}
    source_paths = [zones_path] + [
        _zip(month) for months in MONTHS.values() for month in months
    ]
    before = {
        str(path.relative_to(ROOT)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in source_paths
    }

    with tempfile.TemporaryDirectory(prefix="m2_audit_") as temporary:
        db = sqlite3.connect(Path(temporary) / "audit.sqlite")
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute(
            "CREATE TABLE flights(part TEXT, carrier TEXT, tail TEXT, origin TEXT, dest TEXT, sdep REAL, sarr REAL, adep REAL, aarr REAL, taxi REAL)"
        )
        db.execute(
            "CREATE TABLE refs(kind TEXT, part TEXT, k1 TEXT, k2 TEXT, value REAL, eligibility REAL)"
        )
        counts = defaultdict(int)
        for part, months in MONTHS.items():
            for month in months:
                batch = []
                for row in _iter_rows(month):
                    counts[f"{part}_raw_rows"] += 1
                    origin, dest = row.get("Origin", ""), row.get("Dest", "")
                    tail = row.get("Tail_Number", "").strip()
                    if not tail or origin not in zones or dest not in zones:
                        continue
                    try:
                        day = date.fromisoformat(row["FlightDate"][:10])
                    except (ValueError, TypeError):
                        continue
                    sdep = _utc(day, row.get("CRSDepTime"), zones[origin])
                    sarr = _utc(day, row.get("CRSArrTime"), zones[dest])
                    if sdep is None or sarr is None:
                        continue
                    while sarr < sdep:
                        sarr += 1440
                    cancelled = (_number(row.get("Cancelled")) or 0) != 0
                    diverted = (_number(row.get("Diverted")) or 0) != 0
                    adep = (
                        None
                        if cancelled or diverted
                        else _actual_utc_minutes(
                            day,
                            sdep,
                            row.get("DepTime"),
                            row.get("DepDelay"),
                            zones[origin],
                        )
                    )
                    aarr = (
                        None
                        if cancelled or diverted
                        else _actual_utc_minutes(
                            day,
                            sarr,
                            row.get("ArrTime"),
                            row.get("ArrDelay"),
                            zones[dest],
                        )
                    )
                    taxi = (
                        None if cancelled or diverted else _number(row.get("TaxiOut"))
                    )
                    batch.append(
                        (
                            part,
                            row.get("Reporting_Airline", ""),
                            tail,
                            origin,
                            dest,
                            sdep,
                            sarr,
                            adep,
                            aarr,
                            taxi,
                        )
                    )
                    if len(batch) >= 20_000:
                        db.executemany(
                            "INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?)", batch
                        )
                        batch.clear()
                if batch:
                    db.executemany(
                        "INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?)", batch
                    )
                db.commit()
        db.execute("CREATE INDEX ix_flights ON flights(part,tail,sdep)")
        db.execute(
            "INSERT INTO refs SELECT 'taxi',part,origin,carrier,taxi,NULL FROM flights WHERE taxi IS NOT NULL AND taxi>=0"
        )
        db.execute(
            """INSERT INTO refs
            WITH ordered AS (
              SELECT part,carrier,tail,origin,dest,sdep,adep,aarr,
                     lag(dest) OVER (PARTITION BY part,tail ORDER BY sdep) AS prev_dest,
                     lag(aarr) OVER (PARTITION BY part,tail ORDER BY sdep) AS prev_aarr,
                     lag(sarr) OVER (PARTITION BY part,tail ORDER BY sdep) AS prev_sarr
              FROM flights)
            SELECT 'turn',part,origin,carrier,adep-prev_aarr,sdep-prev_sarr FROM ordered
            WHERE prev_dest=origin AND prev_aarr IS NOT NULL AND adep IS NOT NULL AND adep>=prev_aarr"""
        )
        db.execute("CREATE INDEX ix_refs_value ON refs(kind,part,value)")
        db.execute("CREATE INDEX ix_refs_group ON refs(kind,part,k1,k2,value)")
        db.commit()

        horizon_by_part = {}
        for part in MONTHS:
            horizon_values = {horizon: defaultdict(int) for horizon in HORIZONS}
            current_tail, departures = None, []

            def flush_tail():
                if not departures:
                    return
                for horizon in HORIZONS:
                    right = 0
                    for left, departure in enumerate(departures):
                        right = max(right, left + 1)
                        while (
                            right < len(departures)
                            and departures[right] <= departure + horizon
                        ):
                            right += 1
                        horizon_values[horizon][right - left - 1] += 1

            for tail, departure in db.execute(
                "SELECT tail,sdep FROM flights WHERE part=? ORDER BY tail,sdep", (part,)
            ):
                if current_tail is not None and tail != current_tail:
                    flush_tail()
                    departures = []
                current_tail = tail
                departures.append(departure)
            flush_tail()
            horizon_by_part[part] = {
                str(h): {
                    **_hist_summary(values),
                    "positive_fraction": sum(
                        n for value, n in values.items() if value > 0
                    )
                    / sum(values.values()),
                }
                for h, values in horizon_values.items()
            }
            counts[f"{part}_flights"] = sum(
                next(iter(horizon_values.values())).values()
            )

        turn_train_summary = _sql_summary(db, "turn", "train")
        taxi_train_summary = _sql_summary(db, "taxi", "train")
        global_turn = {(): turn_train_summary["p50"]}
        airport_turn, airport_turn_n = _group_refs(db, "turn", ("airport",), 0.5, 100)
        airport_carrier_turn, airport_carrier_turn_n = _group_refs(
            db, "turn", ("airport", "carrier"), 0.5, 100
        )
        global_taxi_median = {(): taxi_train_summary["p50"]}
        airport_taxi_median, airport_taxi_n = _group_refs(
            db, "taxi", ("origin",), 0.5, 100
        )
        global_taxi_p20 = {(): taxi_train_summary["p20"]}
        airport_taxi_p20, _ = _group_refs(db, "taxi", ("origin",), 0.2, 100)
        airport_carrier_taxi_p20, airport_carrier_taxi_n = _group_refs(
            db, "taxi", ("origin", "carrier"), 0.2, 100
        )

        def dev_rows(kind, names, eligibility_max=None):
            columns = "k1,value" if len(names) == 1 else "k1,k2,value"
            extra = (
                ""
                if eligibility_max is None
                else " AND eligibility>=0 AND eligibility<=?"
            )
            args = (kind,) if eligibility_max is None else (kind, eligibility_max)
            for row in db.execute(
                f"SELECT {columns} FROM refs WHERE kind=? AND part='development'{extra}",
                args,
            ):
                yield {**dict(zip(names, row[:-1])), "value": row[-1]}

        turn_window_candidates = {}
        for window in HORIZONS:
            summary = _sql_summary(db, "turn", "train", eligibility_max=window)
            global_ref = {(): summary["p50"]}
            airport_ref, airport_n = _group_refs(
                db, "turn", ("airport",), 0.5, 100, eligibility_max=window
            )
            airport_carrier_ref, airport_carrier_n = _group_refs(
                db, "turn", ("airport", "carrier"), 0.5, 100, eligibility_max=window
            )
            turn_window_candidates[str(window)] = {
                "train_actual_turnaround_minutes": summary,
                "development_actual_turnaround_minutes": _sql_summary(
                    db, "turn", "development", eligibility_max=window
                ),
                "eligible_airport_cells": len(airport_ref),
                "eligible_airport_carrier_cells": len(airport_carrier_ref),
                "airport_cell_count_distribution": _summary(list(airport_n.values())),
                "airport_carrier_cell_count_distribution": _summary(
                    list(airport_carrier_n.values())
                ),
                "development_fallback_coverage": _coverage(
                    dev_rows("turn", ("airport", "carrier"), window),
                    (
                        (
                            "AIRPORT_CARRIER",
                            ("airport", "carrier"),
                            airport_carrier_ref,
                        ),
                        ("AIRPORT", ("airport",), airport_ref),
                        ("GLOBAL", (), global_ref),
                    ),
                ),
            }

        metrics = {
            "status": "DEVELOPMENT_CANDIDATES_ONLY",
            "production_artifact": False,
            "partitions": {
                "fit": "2019-01--2019-06",
                "diagnostic": "2019-08--2019-09",
                "excluded": ["2019-07", "2019-10--2019-12"],
            },
            "sources": list(before),
            "raw_read_only": before
            == {
                str(path.relative_to(ROOT)): (
                    path.stat().st_size,
                    path.stat().st_mtime_ns,
                )
                for path in source_paths
            },
            "counts": {
                key: value
                for key, value in counts.items()
                if not key.endswith("horizon_metrics")
            },
            "turnaround": {
                "train_distribution_minutes": turn_train_summary,
                "development_distribution_minutes": _sql_summary(
                    db, "turn", "development"
                ),
                "scheduled_connection_window_candidates": turn_window_candidates,
                "candidates": {
                    "T1_GLOBAL_MEDIAN": {
                        "value_minutes": global_turn[()],
                        "development_coverage": _coverage(
                            dev_rows("turn", ("airport",)),
                            (("GLOBAL", (), global_turn),),
                        ),
                    },
                    "T2_AIRPORT_MEDIAN_N100_GLOBAL": {
                        "eligible_airport_cells": len(airport_turn),
                        "cell_count_distribution": _summary(
                            list(airport_turn_n.values())
                        ),
                        "development_coverage": _coverage(
                            dev_rows("turn", ("airport",)),
                            (
                                ("AIRPORT", ("airport",), airport_turn),
                                ("GLOBAL", (), global_turn),
                            ),
                        ),
                    },
                    "T3_AIRPORT_CARRIER_MEDIAN_N100_AIRPORT_GLOBAL": {
                        "eligible_airport_carrier_cells": len(airport_carrier_turn),
                        "cell_count_distribution": _summary(
                            list(airport_carrier_turn_n.values())
                        ),
                        "development_coverage": _coverage(
                            dev_rows("turn", ("airport", "carrier")),
                            (
                                (
                                    "AIRPORT_CARRIER",
                                    ("airport", "carrier"),
                                    airport_carrier_turn,
                                ),
                                ("AIRPORT", ("airport",), airport_turn),
                                ("GLOBAL", (), global_turn),
                            ),
                        ),
                    },
                },
            },
            "taxi": {
                "train_distribution_minutes": taxi_train_summary,
                "development_distribution_minutes": _sql_summary(
                    db, "taxi", "development"
                ),
                "candidates": {
                    "X1_GLOBAL_MEDIAN": {
                        "value_minutes": global_taxi_median[()],
                        "development_coverage": _coverage(
                            dev_rows("taxi", ("origin",)),
                            (("GLOBAL", (), global_taxi_median),),
                        ),
                    },
                    "X2_AIRPORT_MEDIAN_N100_GLOBAL": {
                        "eligible_airport_cells": len(airport_taxi_median),
                        "cell_count_distribution": _summary(
                            list(airport_taxi_n.values())
                        ),
                        "development_coverage": _coverage(
                            dev_rows("taxi", ("origin",)),
                            (
                                ("AIRPORT", ("origin",), airport_taxi_median),
                                ("GLOBAL", (), global_taxi_median),
                            ),
                        ),
                    },
                    "X3_AIRPORT_CARRIER_P20_N100_AIRPORT_GLOBAL": {
                        "global_p20_minutes": global_taxi_p20[()],
                        "eligible_airport_carrier_cells": len(airport_carrier_taxi_p20),
                        "cell_count_distribution": _summary(
                            list(airport_carrier_taxi_n.values())
                        ),
                        "development_coverage": _coverage(
                            dev_rows("taxi", ("origin", "carrier")),
                            (
                                (
                                    "AIRPORT_CARRIER",
                                    ("origin", "carrier"),
                                    airport_carrier_taxi_p20,
                                ),
                                ("AIRPORT", ("origin",), airport_taxi_p20),
                                ("GLOBAL", (), global_taxi_p20),
                            ),
                        ),
                    },
                },
            },
            "downstream_horizon_candidates_minutes": {
                "train": horizon_by_part["train"],
                "development": horizon_by_part["development"],
            },
        }
        payload = json.dumps(metrics, indent=2, sort_keys=True)
        metrics["candidate_metrics_sha256"] = (
            f"sha256:{sha256(payload.encode()).hexdigest()}"
        )
        (OUT / "reference_candidate_metrics.json").write_text(
            json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(metrics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
