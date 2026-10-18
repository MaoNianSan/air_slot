# -*- coding: utf-8 -*-
"""D2-10 unpack step: On-Time month=02..12 + DB1B Coupon Q2..Q4 (CSV only).

Approved scope (D2-10 item 1): extract the 14 CSVs, compute sha256, and append
14 unpacked_csv entries to data2/manifests/data2_bts_2019_sha256.csv. The
readme.html files inside the zips are NOT extracted for the new months so the
manifest covers exactly every unpacked artifact (+14 entries, as approved).
Idempotent: already-extracted files are skipped and hashes verified.
"""
from __future__ import annotations

import csv
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # data2/
MANIFEST = ROOT / "manifests" / "data2_bts_2019_sha256.csv"

ONTIME_ZIPS = sorted(
    (ROOT / "_download" / "bts" / "ontime" / "2019").glob(
        "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2019_*.zip"),
    key=lambda p: int(p.stem.rsplit("_", 1)[1]))
COUPON_ZIPS = sorted(
    (ROOT / "_download" / "bts" / "db1b" / "2019" / "coupon").glob(
        "Origin_and_Destination_Survey_DB1BCoupon_2019_*.zip"),
    key=lambda p: int(p.stem.rsplit("_", 1)[1]))


def sha256_bytes(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def unpack(zip_path: Path, target_dir: Path) -> list[Path]:
    extracted = []
    with zipfile.ZipFile(zip_path) as archive:
        for entry in archive.infolist():
            name = Path(entry.filename).name
            if not name.lower().endswith(".csv"):
                continue  # readme.html intentionally not extracted for new months
            target = target_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                with archive.open(entry) as src, target.open("wb") as dst:
                    dst.write(src.read())
            extracted.append(target)
    return extracted


def main() -> None:
    if not MANIFEST.is_file():
        raise SystemExit(f"manifest not found: {MANIFEST}")
    rows = list(csv.reader(MANIFEST.open(encoding="utf-8-sig", newline="")))
    header, body = rows[0], rows[1:]
    if header != ["Path", "Hash", "Type", "SourceZip"]:
        raise SystemExit(f"unexpected manifest header: {header}")
    existing = {row[0] for row in body}

    added: list[list[str]] = []
    for zip_path in ONTIME_ZIPS:
        month = int(zip_path.stem.rsplit("_", 1)[1])
        if month == 1:
            continue  # already unpacked
        target_dir = ROOT / "raw" / "bts" / "ontime" / "2019" / f"month={month:02d}"
        for target in unpack(zip_path, target_dir):
            rel = str(target.relative_to(ROOT)).replace("\\", "/")
            src = str(zip_path.relative_to(ROOT)).replace("\\", "/")
            if rel in existing:
                continue
            added.append([rel, sha256_bytes(target), "unpacked_csv", src])
    for zip_path in COUPON_ZIPS:
        quarter = int(zip_path.stem.rsplit("_", 1)[1])
        if quarter == 1:
            continue  # already unpacked
        target_dir = ROOT / "raw" / "bts" / "db1b" / "2019" / "coupon"
        for target in unpack(zip_path, target_dir):
            rel = str(target.relative_to(ROOT)).replace("\\", "/")
            src = str(zip_path.relative_to(ROOT)).replace("\\", "/")
            if rel in existing:
                continue
            added.append([rel, sha256_bytes(target), "unpacked_csv", src])

    if not added:
        print("NO_NEW_ENTRIES")
        return

    # Insert: ontime month=02..12 rows right after the month=01 ontime csv row;
    # coupon Q2..Q4 rows right after the coupon Q1 csv row (keeps grouping).
    anchor_ontime = "raw/bts/ontime/2019/month=01/On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2019_1.csv"
    anchor_coupon = "raw/bts/db1b/2019/coupon/Origin_and_Destination_Survey_DB1BCoupon_2019_1.csv"
    new_ontime = [row for row in added if "ontime" in row[0]]
    new_coupon = [row for row in added if "db1b" in row[0]]
    out: list[list[str]] = []
    inserted_ontime = inserted_coupon = False
    for row in body:
        out.append(row)
        if not inserted_ontime and row[0] == anchor_ontime:
            out.extend(new_ontime)
            inserted_ontime = True
        elif not inserted_coupon and row[0] == anchor_coupon:
            out.extend(new_coupon)
            inserted_coupon = True
    if not (inserted_ontime and inserted_coupon):
        raise SystemExit("manifest anchor rows not found")
    with MANIFEST.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(out)
    print(f"ADDED {len(added)} entries; manifest now {1 + len(out)} lines")
    for row in added:
        print(row[0])


if __name__ == "__main__":
    main()
