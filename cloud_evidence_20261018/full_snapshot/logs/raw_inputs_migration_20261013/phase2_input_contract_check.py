#!/usr/bin/env python3
"""Phase-2 input & scientific-contract check for data2 raw BTS inputs (READ-ONLY).

Verifies, per year 2017-2022, against the frozen code contracts
(data2/scripts/build_year_references.py + model/PRE/reference/*):
  * T-100 segment file at the exact code path; header carries
    MONTH/PASSENGERS/DEPARTURES_PERFORMED/ORIGIN/DEST/UNIQUE_CARRIER;
    month distribution shows the annual file holds 12 months while the
    admissible Y-H1 window (MONTH<=6) has positive rows.
  * DB1B Coupon Q1/Q2 at the exact code paths
    (glob `Origin_and_Destination_Survey_DB1BCoupon_{year}_[12].csv`);
    exact-case Passengers/Origin/Dest header fields (binding requirement of
    stream_passenger_routes), a tripbreak alias field (Break/TripBreak/
    TRIPBREAK/TRIP_BREAK), Quarter column value == q for every row when the
    column exists, Year column == year for every row when the column exists.
  * Coupon dir contains no Q3/Q4 csv, no foreign csv, no temp upload file.

Exit code 0 = every check passed. Writes a JSON report next to this script's
sibling log dir. Never reads Test / Final-Test data and never writes to raw.
"""
import csv
import json
import sys
from pathlib import Path

RAW = Path("/data/airslot/worktree/data2/raw/bts")
REPORT = Path("/data/airslot/logs/raw_inputs_migration_20261013/"
              "PHASE2_INPUT_CONTRACT_CHECK.json")
TB_ALIASES = ("Break", "TripBreak", "TRIPBREAK", "TRIP_BREAK")
T100_REQUIRED = ("MONTH", "PASSENGERS", "DEPARTURES_PERFORMED",
                 "ORIGIN", "DEST", "UNIQUE_CARRIER")

problems: list[str] = []
report = {"schema": "PHASE2_INPUT_CONTRACT_CHECK_V1", "years": {}}


def upper_map(fields):
    return {str(f).strip().upper(): str(f).strip()
            for f in fields if f is not None}


for year in range(2017, 2023):
    y = {}

    # ---------------- T-100 ----------------
    t = RAW / "t100" / str(year) / "T_T100_SEGMENT_ALL_CARRIER.csv"
    if not t.is_file():
        problems.append(f"{year}: T100_MISSING {t}")
        y["t100"] = {"status": "MISSING"}
    else:
        with t.open(encoding="utf-8-sig", newline="") as fh:
            rd = csv.reader(fh)
            try:
                header = [h.strip() for h in next(rd)]
            except StopIteration:
                header = []
            hset = {h.upper() for h in header}
            for need in T100_REQUIRED:
                if need not in hset:
                    problems.append(f"{year}: T100_FIELD_MISSING {need}")
            midx = next((i for i, h in enumerate(header)
                         if h.upper() == "MONTH"), None)
            if midx is None:
                y["t100"] = {"status": "BAD_HEADER"}
                problems.append(f"{year}: T100_MONTH_COLUMN_UNRESOLVED")
            else:
                months: dict[int, int] = {}
                rows = 0
                h1 = 0
                for raw in rd:
                    if not raw or len(raw) <= midx:
                        continue
                    rows += 1
                    try:
                        m = int(float(raw[midx].strip()))
                    except (TypeError, ValueError):
                        m = None
                    if m is not None:
                        months[m] = months.get(m, 0) + 1
                        if 1 <= m <= 6:
                            h1 += 1
                y["t100"] = {
                    "status": "OK", "rows": rows, "h1_rows": h1,
                    "months": {str(k): months[k] for k in sorted(months)},
                }
                if h1 <= 0:
                    problems.append(f"{year}: T100_H1_ROWS_ZERO")
                for m in range(1, 7):
                    if months.get(m, 0) == 0:
                        problems.append(f"{year}: T100_H1_MONTH_{m}_EMPTY")

    # ---------------- DB1B Coupon Q1/Q2 ----------------
    for q in (1, 2):
        c = (RAW / "db1b" / str(year) / "coupon"
             / f"Origin_and_Destination_Survey_DB1BCoupon_{year}_{q}.csv")
        key = f"db1b_q{q}"
        if not c.is_file():
            problems.append(f"{year}: DB1B_Q{q}_MISSING {c}")
            y[key] = {"status": "MISSING"}
            continue
        with c.open(encoding="utf-8-sig", newline="") as fh:
            rd = csv.DictReader(fh)
            fields = [str(f).strip() for f in (rd.fieldnames or [])]
            fset = set(fields)
            for need in ("Passengers", "Origin", "Dest"):
                if need not in fset:
                    problems.append(
                        f"{year}: DB1B_Q{q}_EXACT_FIELD_MISSING {need}")
            um = upper_map(fields)
            tb = next((um[a.upper()] for a in TB_ALIASES
                       if a.upper() in um), None)
            if tb is None:
                problems.append(f"{year}: DB1B_Q{q}_TRIPBREAK_FIELD_MISSING")
            qf = next((um[k] for k in ("QUARTER", "QTR") if k in um), None)
            yf = um.get("YEAR")
            pax_f = um.get("PASSENGERS")
            org_f = um.get("ORIGIN")
            dst_f = um.get("DEST")
            rows = 0
            bad_q = 0
            bad_y = 0
            pax = 0.0
            routes = set()
            for row in rd:
                rows += 1
                if qf is not None:
                    try:
                        if int(float(str(row.get(qf, "")).strip())) != q:
                            bad_q += 1
                    except (TypeError, ValueError):
                        bad_q += 1
                if yf is not None and str(row.get(yf, "")).strip() != str(year):
                    bad_y += 1
                if pax_f:
                    try:
                        pax += float(row.get(pax_f) or 0)
                    except (TypeError, ValueError):
                        pass
                if org_f and dst_f:
                    o = (row.get(org_f) or "").strip()
                    d = (row.get(dst_f) or "").strip()
                    if o and d:
                        routes.add((o, d))
            y[key] = {
                "status": "OK", "rows": rows, "bad_quarter_rows": bad_q,
                "bad_year_rows": bad_y, "passengers_sum": pax,
                "directed_routes": len(routes), "tripbreak_field": tb,
                "quarter_field": qf, "year_field": yf,
            }
            if bad_q:
                problems.append(
                    f"{year}: DB1B_Q{q}_QUARTER_COLUMN_MISMATCH rows={bad_q}")
            if bad_y:
                problems.append(
                    f"{year}: DB1B_Q{q}_YEAR_COLUMN_MISMATCH rows={bad_y}")

    cdir = RAW / "db1b" / str(year) / "coupon"
    if cdir.is_dir():
        names = sorted(p.name for p in cdir.iterdir())
        q34 = [n for n in names if n.endswith(("_3.csv", "_4.csv"))]
        foreign = [n for n in names
                   if n.endswith(".csv")
                   and not n.startswith(
                       "Origin_and_Destination_Survey_DB1BCoupon_")]
        tmps = [n for n in names if n.startswith(".upload_tmp_")]
        y["coupon_dir"] = {"files": names, "q34": q34,
                           "foreign_csv": foreign, "tmp": tmps}
        if q34:
            problems.append(f"{year}: Q3_Q4_FILES_PRESENT {q34}")
        if foreign:
            problems.append(f"{year}: FOREIGN_CSV_PRESENT {foreign}")
        if tmps:
            problems.append(f"{year}: TEMP_UPLOAD_FILE_PRESENT {tmps}")

    report["years"][str(year)] = y

report["problems"] = problems
report["status"] = "PASS" if not problems else "FAIL"
REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                  encoding="utf-8")
print(json.dumps({"status": report["status"], "n_problems": len(problems),
                  "problems": problems}, indent=2))
sys.exit(0 if not problems else 1)
