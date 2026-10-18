#!/usr/bin/env python3
"""R5 H1 input acceptance (READ-ONLY).

Per year 2017-2022, against the seal manifest produced by seal_t100_h1.py:
  * active H1 file: SHA-256 matches the manifest; FULL scan rows == manifest
    rows; months present == {1..6} exactly (no months 7-12 anywhere);
  * frozen downstream reader acceptance: stream_t100_rows(path,
    allowed_months=(1..6)) consumes 100% of the file with zero exclusions and
    used_months == [1..6];
  * audit annual file: exists outside the active tree, SHA-256 equals the
    frozen pre-seal manifest hash, and its month distribution reconciles
    exactly (months 1-6 == H1 rows; months 7-12 == the recorded dropped
    counts).

Usage: R5_h1_acceptance.py <repo_root> <seal_manifest> <out_txt>
Exit 0 iff every year passes.
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
MANIFEST = Path(sys.argv[2]).resolve()
OUT = Path(sys.argv[3]).resolve()
sys.path.insert(0, str(REPO))

from model.PRE.reference.data2_m2_train_fit import stream_t100_rows  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_month(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        numeric = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not numeric.is_integer() or not 1 <= int(numeric) <= 12:
        return None
    return int(numeric)


def scan_months(path: Path):
    months: dict[int, int] = {}
    rows = 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        idx = [h.strip().upper() for h in header].index("MONTH")
        for raw in reader:
            if not raw or len(raw) <= idx:
                continue
            rows += 1
            month = parse_month(raw[idx])
            months[month] = months.get(month, 0) + 1
    return rows, months


manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
problems: list[str] = []
print_lines: list[str] = []

for year_str, yr in sorted(manifest["years"].items()):
    year = int(year_str)
    active = Path(yr["h1"]["path"])
    audit = Path(yr["annual"]["audit_path"])

    if not active.is_file():
        problems.append(f"{year}: H1_ACTIVE_MISSING {active}")
        continue
    if sha256_file(active) != yr["h1"]["sha256"]:
        problems.append(f"{year}: H1_HASH_MISMATCH")

    rows, months = scan_months(active)
    if rows != yr["h1"]["rows"]:
        problems.append(f"{year}: H1_ROWS {rows} != {yr['h1']['rows']}")
    if set(months) != {1, 2, 3, 4, 5, 6}:
        problems.append(f"{year}: H1_MONTHS {sorted(months)} != 1..6")

    stream = stream_t100_rows(active, fit_partition="TRAIN",
                              allowed_months=(1, 2, 3, 4, 5, 6))
    used = sum(1 for _ in stream)
    audit_stats = dict(stream.audit)
    if audit_stats["rows_seen"] != rows or used != rows:
        problems.append(f"{year}: READER rows_seen={audit_stats['rows_seen']} "
                        f"used={used} != {rows}")
    if audit_stats["rows_excluded_outside_fit_period"] != 0:
        problems.append(f"{year}: READER excluded_outside="
                        f"{audit_stats['rows_excluded_outside_fit_period']}")
    if audit_stats["rows_excluded_invalid_month"] != 0:
        problems.append(f"{year}: READER excluded_invalid="
                        f"{audit_stats['rows_excluded_invalid_month']}")
    if sorted(audit_stats["used_months"]) != [1, 2, 3, 4, 5, 6]:
        problems.append(f"{year}: READER used_months={audit_stats['used_months']}")

    if not audit.is_file():
        problems.append(f"{year}: AUDIT_MISSING {audit}")
    else:
        audit_sha = sha256_file(audit)
        if audit_sha != yr["annual"]["expected_frozen_sha256"]:
            problems.append(f"{year}: AUDIT_HASH_MISMATCH")
        a_rows, a_months = scan_months(audit)
        h1_part = sum(a_months.get(m, 0) for m in range(1, 7))
        if h1_part != yr["h1"]["rows"]:
            problems.append(f"{year}: AUDIT_H1_PART {h1_part} != {yr['h1']['rows']}")
        for month_str, count in yr["h1"]["dropped_months_7_12"].items():
            if a_months.get(int(month_str), 0) != count:
                problems.append(f"{year}: AUDIT_MONTH_{month_str} "
                                f"{a_months.get(int(month_str), 0)} != {count}")
        print_lines.append(
            f"{year}: PASS rows={rows} months=1..6 reader_admits_all=true "
            f"audit_sha_ok=true audit_rows={a_rows}")

summary = ("ALL_PASS" if not problems else "FAIL") + f" ({len(problems)} problems)"
print_lines.append(summary)
if problems:
    print_lines.extend(problems)
OUT.write_text("\n".join(print_lines) + "\n", encoding="utf-8")
print("\n".join(print_lines))
sys.exit(0 if not problems else 1)
