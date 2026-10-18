#!/usr/bin/env python3
"""T-100 H1 sealing (2026-10-13): construct H1-only active inputs and relocate
the audited annual originals out of the active computation tree.

Requirement (authorized 2026-10-13):
  * the reference fits admit ONLY T-100 rows with MONTH <= 6 (H1);
  * the active computation directory must contain ONLY H1 rows;
  * months 7-12 must not remain in the active tree;
  * original annual files are preserved as audit records (moved, never deleted,
    hash-verified at the new location against the frozen manifest hash).

Method: the H1 file is a byte-verbatim LINE SUBSET of the audited annual file
(header line kept as-is; a data line is kept iff its MONTH field parses, by the
code's own _parse_month rule, to 1..6).  The admissible row set is therefore
identical to what the builder would consume from the annual file, and every
kept row is byte-identical to the audited source.

Usage: seal_t100_h1.py <active_t100_root> <audit_root> <staging_root> <manifest_out>
Exit 0 iff every year sealed and every verification passed; on any anomaly it
aborts before touching the active tree.
"""
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Frozen expectations (from the 2026-10-13 migration: local manifest hashes,
# Phase-2 full-parse H1 row counts).
EXPECTED = {
    2017: {"sha256": "7bb2512e174d40e1d1fe13e54be8ae4e702645c08f6516b3cbc20ad8866d16a9",
           "h1_rows": 232055, "total_rows": 464429},
    2018: {"sha256": "4391a96142cbae4cb26757a6b5eb2eac69a6dadc62dc803ce55ab29ced5826ea",
           "h1_rows": 233342, "total_rows": 474138},
    2019: {"sha256": "9b838fd6f15594f0481b03380e6744b2dc0e3061248188a587b61fd5fe96b667",
           "h1_rows": 241110, "total_rows": 487923},
    2020: {"sha256": "84113e14e9323f3a4835aa0785b1b7af2da94e8865d73001c2aa55e7b4f818ce",
           "h1_rows": 184853, "total_rows": 355301},
    2021: {"sha256": "1415fef5df6796f8ff9f82783412326ed48d5e16fd21c5bf6493cc4cb13776a3",
           "h1_rows": 208542, "total_rows": 459687},
    2022: {"sha256": "137ab84cacaaaa5a35082660f7842ef1b4f99b4abe38291646a641c29b6e63ec",
           "h1_rows": 252950, "total_rows": 508848},
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_month(value):
    """Same rule as model/PRE/reference/data2_m2_train_fit._parse_month."""
    if value is None or str(value).strip() == "":
        return None
    try:
        numeric = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not numeric.is_integer() or not 1 <= int(numeric) <= 12:
        return None
    return int(numeric)


def build_h1(annual_path: Path, staging_path: Path):
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    total = kept = invalid = 0
    dropped_months = {}
    with annual_path.open(encoding="utf-8-sig", newline="") as src, \
            staging_path.open("w", encoding="utf-8", newline="") as dst:
        first = True
        month_idx = None
        header_fields = None
        for line in src:
            if first:
                first = False
                dst.write(line)
                header_fields = next(csv.reader([line]))
                try:
                    month_idx = [f.strip().upper() for f in header_fields].index("MONTH")
                except ValueError as exc:
                    raise SystemExit(f"MONTH_COLUMN_MISSING:{annual_path}") from exc
                continue
            if line.strip() == "":
                invalid += 1
                continue
            fields = next(csv.reader([line]))
            if len(fields) != len(header_fields):
                raise SystemExit(
                    f"LINE_FIELD_COUNT_MISMATCH:{annual_path}:{total + 1}")
            total += 1
            month = parse_month(fields[month_idx])
            if month is None:
                invalid += 1
                continue
            if 1 <= month <= 6:
                kept += 1
                dst.write(line)
            else:
                dropped_months[month] = dropped_months.get(month, 0) + 1
    return {"total_rows": total, "h1_rows": kept, "invalid_month_rows": invalid,
            "dropped_months_7_12": {str(k): v for k, v in sorted(dropped_months.items())}}


def main() -> int:
    active_root = Path(sys.argv[1]).resolve()
    audit_root = Path(sys.argv[2]).resolve()
    staging_root = Path(sys.argv[3]).resolve()
    manifest_out = Path(sys.argv[4]).resolve()

    plan = {}
    # ---- Phase 1: build + verify ALL H1 files before touching anything.
    for year, expected in sorted(EXPECTED.items()):
        annual = active_root / str(year) / "T_T100_SEGMENT_ALL_CARRIER.csv"
        if not annual.is_file():
            raise SystemExit(f"ANNUAL_MISSING:{annual}")
        annual_sha = sha256_file(annual)
        if annual_sha != expected["sha256"]:
            raise SystemExit(
                f"ANNUAL_HASH_MISMATCH:{year}: {annual_sha} != {expected['sha256']}")
        staged = staging_root / str(year) / "T_T100_SEGMENT_ALL_CARRIER.csv"
        stats = build_h1(annual, staged)
        if stats["h1_rows"] != expected["h1_rows"]:
            raise SystemExit(
                f"H1_ROW_COUNT_MISMATCH:{year}: {stats['h1_rows']} != "
                f"{expected['h1_rows']}")
        if stats["total_rows"] != expected["total_rows"]:
            raise SystemExit(
                f"TOTAL_ROW_COUNT_MISMATCH:{year}: {stats['total_rows']} != "
                f"{expected['total_rows']}")
        if stats["invalid_month_rows"] != 0:
            raise SystemExit(f"INVALID_MONTH_ROWS:{year}: {stats['invalid_month_rows']}")
        staged_sha = sha256_file(staged)
        plan[year] = {"annual": annual, "staged": staged, "stats": stats,
                      "annual_sha": annual_sha, "staged_sha": staged_sha,
                      "staged_bytes": staged.stat().st_size}
        print(f"built {year}: h1_rows={stats['h1_rows']} "
              f"dropped={stats['dropped_months_7_12']} sha256={staged_sha[:16]}…")

    # ---- Phase 2: atomic swaps (same /data volume; os.replace = rename).
    years_report = {}
    for year, item in sorted(plan.items()):
        audit_dir = audit_root / str(year)
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_path = audit_dir / "T_T100_SEGMENT_ALL_CARRIER_annual.csv"
        if audit_path.exists():
            raise SystemExit(f"AUDIT_TARGET_EXISTS:{audit_path}")
        os.replace(item["annual"], audit_path)          # annual -> audit
        os.replace(item["staged"], item["annual"])      # H1 -> active
        audit_sha = sha256_file(audit_path)
        active_sha = sha256_file(item["annual"])
        if audit_sha != item["annual_sha"]:
            raise SystemExit(f"AUDIT_HASH_MISMATCH:{year}")
        if active_sha != item["staged_sha"]:
            raise SystemExit(f"ACTIVE_HASH_MISMATCH:{year}")
        years_report[str(year)] = {
            "annual": {
                "audit_path": str(audit_path),
                "bytes": audit_path.stat().st_size,
                "sha256": audit_sha,
                "expected_frozen_sha256": EXPECTED[year]["sha256"],
                "sha256_match_frozen_manifest": audit_sha == EXPECTED[year]["sha256"],
            },
            "h1": {
                "path": str(item["annual"]),
                "bytes": item["staged_bytes"],
                "rows": item["stats"]["h1_rows"],
                "months": [1, 2, 3, 4, 5, 6],
                "sha256": active_sha,
                "dropped_months_7_12": item["stats"]["dropped_months_7_12"],
                "invalid_month_rows": item["stats"]["invalid_month_rows"],
                "line_subset_guard": "field-count verified for every line; rows byte-verbatim copies of audited annual lines",
            },
        }
        print(f"sealed {year}: active_h1_sha={active_sha[:16]}… "
              f"audit_sha={audit_sha[:16]}… audit_match={audit_sha == EXPECTED[year]['sha256']}")

    manifest = {
        "schema_version": "T100_H1_SEAL_V1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "purpose": (
            "Seal the T-100 storage/admissibility boundary: the reference fits "
            "admit only MONTH<=6 rows; the active computation tree now contains "
            "H1-only files, and the audited annual originals live outside the "
            "active tree."),
        "method": (
            "H1 file = byte-verbatim line subset of the audited annual file "
            "(header kept verbatim; data line kept iff its MONTH parses by the "
            "code's _parse_month rule to 1..6)."),
        "scientific_invariant": (
            "The admissible row set is identical to what the builder consumed "
            "from the annual file (the builder admits exactly MONTH<=6); every "
            "kept row is byte-identical to the audited source."),
        "honest_scan_record": (
            "Pre-seal, every annual file was read in FULL on disk by SHA-256 "
            "sweeps and the Phase-2 structural parse, INCLUDING months 7-12; "
            "those reads were verification/administration only and were never "
            "fit inputs. Post-seal, months 7-12 rows exist only in the audit "
            "copy outside the active computation tree."),
        "root_active": str(active_root),
        "root_audit": str(audit_root),
        "years": years_report,
        "all_ok": True,
    }
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    print(f"manifest written: {manifest_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
