# -*- coding: utf-8 -*-
"""Lightweight per-month pre-classification health check for the Data2
multi-year instance (user direction 2026-09-28: "像 2019 当年那样做预分类").

    python data2/scripts/precheck_data2_years.py              # six years
    python data2/scripts/precheck_data2_years.py --years 2017

Per month (fast, bounded):
- file presence + header carries the 20 projected On-Time columns
- row count (pandas)
- FlightDate first/last and whether every sampled date stays in the month
- resolvability probe on the first 50,000 rows (production-mirroring
  projection via cohort_audit_data2_multiyear.build_audit_rows)

Per year: DB1B Coupon Q1-4 / Market Q1 / T-100 / NOAA 48-station presence and
manifest presence. Outputs land under data2/reports/multiyear_precheck/ and a
top-level DATA2_2017_2022_PRECLASSIFICATION_REPORT.{json,md}. Read-only over
raw; this is a health check, not a cohort audit.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT / "data2" / "scripts"), str(_REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from cohort_audit_data2_multiyear import (  # noqa: E402
    INSTANCE_ID,
    PROJECTED_ONTIME_COLUMNS,
    build_audit_rows,
)
from profile_data2_years import load_zones  # noqa: E402

REPO = _REPO_ROOT
DATA2 = REPO / "data2"
RAW = DATA2 / "raw"
OUT_ROOT = DATA2 / "reports" / "multiyear_precheck"
YEARS = (2017, 2018, 2019, 2020, 2021, 2022)
PROBE_ROWS = 50_000


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


def month_precheck(path: Path, month: int, year: int,
                   zones: dict[str, str]) -> dict:
    started = time.perf_counter()
    row = {"year": year, "month": month, "status": "MISSING_FILE"}
    if path is None:
        return row
    frame = pd.read_csv(path, usecols=list(PROJECTED_ONTIME_COLUMNS),
                        dtype=str, keep_default_na=False,
                        encoding="utf-8-sig")
    header_ok = all(column in frame.columns
                    for column in PROJECTED_ONTIME_COLUMNS)
    dates = pd.to_datetime(frame["FlightDate"], errors="coerce").dropna()
    first, last = str(dates.min().date()) if len(dates) else "", \
        str(dates.max().date()) if len(dates) else ""
    dates_in_month = bool(dates.dt.month.eq(month).all()) if len(dates) else None
    probe = frame.head(PROBE_ROWS)
    used, skipped = build_audit_rows(probe, zones)
    row.update({
        "status": "OK", "rows": len(frame), "header_ok": header_ok,
        "first_flightdate": first, "last_flightdate": last,
        "all_dates_in_month": dates_in_month,
        "probe_rows": len(probe), "probe_used": len(used),
        "probe_skipped": len(probe) - len(used),
        "probe_resolvable_rate": round(len(used) / len(probe), 6)
        if len(probe) else None,
        "seconds": round(time.perf_counter() - started, 1),
    })
    return row


def year_reference_checks(year: int) -> dict:
    coupon = [((RAW / "bts" / "db1b" / str(year) / "coupon" /
                f"Origin_and_Destination_Survey_DB1BCoupon_{year}_{q}.csv")
               .is_file()) for q in (1, 2, 3, 4)]
    market = (RAW / "bts" / "db1b" / str(year) / "market" /
              f"Origin_and_Destination_Survey_DB1BMarket_{year}_1.csv").is_file()
    t100 = (RAW / "bts" / "t100" / str(year) /
            "T_T100_SEGMENT_ALL_CARRIER.csv").is_file()
    noaa_files = len(list((RAW / "weather" / "noaa" / str(year)).glob("*.csv")))
    manifest = (DATA2 / "manifests" /
                f"data2_bts_{year}_sha256.csv").is_file()
    return {"coupon_q1_q4_present": coupon, "market_q1_present": market,
            "t100_present": t100, "noaa_station_files": noaa_files,
            "manifest_present": manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", type=int, nargs="*", default=list(YEARS))
    args = parser.parse_args()
    zones = load_zones()
    started = now()
    year_reports: dict[str, dict] = {}
    for year in args.years:
        if year not in YEARS:
            continue
        print(f"=== precheck {year} ===", flush=True)
        files = [next(iter(sorted(
            (RAW / "bts" / "ontime" / str(year) / f"month={m:02d}")
            .glob("*.csv"))), None) for m in range(1, 13)]
        monthly = [month_precheck(path, month, year, zones)
                   for month, path in enumerate(files, start=1)]
        references = year_reference_checks(year)
        ok_months = sum(1 for m in monthly if m["status"] == "OK")
        year_reports[str(year)] = {
            "months_ok": ok_months, "monthly": monthly,
            "references": references,
            "overall": "OK" if ok_months == 12 and all(
                m.get("header_ok") and m.get("all_dates_in_month")
                for m in monthly if m["status"] == "OK") else "ATTENTION"}
        for m in monthly:
            print(f"  {year}-{m['month']:02d} {m['status']} rows={m.get('rows')} "
                  f"probe_rate={m.get('probe_resolvable_rate')}", flush=True)
        write_csv(OUT_ROOT / str(year) / "monthly_precheck.csv",
                  ["year", "month", "status", "rows", "header_ok",
                   "first_flightdate", "last_flightdate", "all_dates_in_month",
                   "probe_rows", "probe_used", "probe_skipped",
                   "probe_resolvable_rate", "seconds"], monthly)

    overall = "OK" if all(r["overall"] == "OK"
                          for r in year_reports.values()) else "ATTENTION"
    report = {
        "EXECUTION_REPOSITORY": str(REPO), "BRANCH": _git("branch", "--show-current"),
        "START_TIME": started, "END_TIME": now(),
        "INSTANCE_ID": INSTANCE_ID, "PURPOSE":
            "pre-classification health check before formal preprocessing",
        "YEARS": sorted(year_reports), "YEAR_REPORTS": year_reports,
        "OVERALL_STATUS": overall,
    }
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "DATA2_2017_2022_PRECLASSIFICATION_REPORT.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Data2 2017-2022 pre-classification health check", "",
             f"- Branch: `{report['BRANCH']}`",
             f"- **OVERALL_STATUS: {overall}**", "",
             "| year | months OK | header OK | dates in month | coupon Q1-4 | "
             "market Q1 | t100 | noaa | manifest |", "|---|---|---|---|---|---|---|---|---|"]
    for year, r in year_reports.items():
        refs = r["references"]
        lines.append(f"| {year} | {r['months_ok']}/12 | "
                     f"{all(m.get('header_ok') for m in r['monthly'])} | "
                     f"{all(m.get('all_dates_in_month') for m in r['monthly'])} | "
                     f"{all(refs['coupon_q1_q4_present'])} | "
                     f"{refs['market_q1_present']} | {refs['t100_present']} | "
                     f"{refs['noaa_station_files']}/48 | "
                     f"{refs['manifest_present']} |")
    (OUT_ROOT / "DATA2_2017_2022_PRECLASSIFICATION_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    print(f"PRECLASSIFICATION_REPORT_WRITTEN overall={overall}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
