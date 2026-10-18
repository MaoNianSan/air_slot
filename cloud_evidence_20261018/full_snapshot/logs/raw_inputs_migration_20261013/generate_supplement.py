#!/usr/bin/env python3
"""Generate the 2026-10-13 raw-input migration supplement manifest.

Inputs (all in this directory):
  expected_hashes.txt        - path,sha256 from the frozen per-year manifests
  server_final_sha256.txt    - post-commit server sweep (sha256sum output)
  upload_log.txt             - driver log (COMMIT / SKIP_IDENTICAL lines)

Outputs:
  MIGRATION_MANIFEST_SUPPLEMENT_20261013.json
  MIGRATION_MANIFEST_SUPPLEMENT_20261013.csv

The JSON mirrors the schema of the original 439-file
DATA_TRANSFER_MANIFEST.json (bytes / path / scope / sha256 / source_root)
so the two files can be concatenated; the original is not modified.
"""
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL_DATA = Path("D:/research/air_slot/code/explore/data2")

expected = {}
for line in (HERE / "expected_hashes.txt").read_text().splitlines():
    h, rel = line.split(",", 1)
    expected[rel] = h.lower()

server = {}
for line in (HERE / "server_final_sha256.txt").read_text().splitlines():
    m = re.match(r"^([0-9a-f]{64})\s+(\S+)$", line.strip())
    if m:
        server["raw/bts/" + m.group(2)] = m.group(1)

disposition = {}
ts_re = re.compile(r"^\[(\S+)\] (COMMIT|SKIP_IDENTICAL) (\S+)")
for line in (HERE / "upload_log.txt").read_text().splitlines():
    m = ts_re.match(line.strip())
    if m:
        ts, kind, rel = m.groups()
        disposition[rel] = (
            "uploaded-temp-verified-atomic-rename"
            if kind == "COMMIT" else "existing-identical-verified-skipped",
            ts,
        )

files = []
problems = []
bytes_new = 0
for rel, exp in expected.items():
    lf = LOCAL_DATA / rel
    size = lf.stat().st_size if lf.is_file() else None
    entry = {
        "path": "data2/" + rel,
        "bytes": size,
        "sha256": "sha256:" + exp,
        "scope": "raw-input",
        "source_root": "local:" + str(LOCAL_DATA / rel).replace("\\", "/"),
        "disposition": disposition.get(rel, ("UNRECORDED", ""))[0],
        "recorded_at_utc": disposition.get(rel, ("", ""))[1],
        "server_final_sha256": "sha256:" + server.get(rel, "MISSING"),
        "server_final_verified": server.get(rel) == exp,
    }
    if entry["disposition"].startswith("uploaded"):
        bytes_new += size or 0
    files.append(entry)
    if server.get(rel) != exp:
        problems.append(rel)

payload = {
    "schema_version": "RAW_INPUTS_MIGRATION_SUPPLEMENT_V1",
    "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "migration_id": "DATA2_RAW_BTS_T100_DB1B_SUPPLEMENT_20261013",
    "relationship": (
        "Supplement to cloud_upload_package_20261013_v3/inputs/"
        "DATA_TRANSFER_MANIFEST.json (439 files). Pins the 18 raw BTS input "
        "files (T-100 segment 2017-2022; DB1B Coupon Q1/Q2 2017-2022) "
        "transferred on 2026-10-13. The original 439-file manifest is NOT "
        "modified; together the two manifests pin the full server input tree."
    ),
    "authority_local_manifests": (
        "D:/research/air_slot/code/explore/data2/manifests/"
        "data2_bts_{year}_sha256.csv"
    ),
    "local_root": "D:/research/air_slot/code/explore/data2",
    "server_root": "/data/airslot/worktree/data2",
    "files_count": len(files),
    "bytes_total": sum(f["bytes"] or 0 for f in files),
    "bytes_uploaded_new": bytes_new,
    "files": sorted(files, key=lambda f: f["path"]),
}
(HERE / "MIGRATION_MANIFEST_SUPPLEMENT_20261013.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

with (HERE / "MIGRATION_MANIFEST_SUPPLEMENT_20261013.csv").open(
        "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["Path", "Bytes", "Sha256", "Disposition",
                "ServerFinalSha256", "ServerFinalVerified", "RecordedAtUtc"])
    for f in payload["files"]:
        w.writerow([f["path"], f["bytes"], f["sha256"], f["disposition"],
                    f["server_final_sha256"], f["server_final_verified"],
                    f["recorded_at_utc"]])

print(json.dumps({
    "files": len(files),
    "bytes_total": payload["bytes_total"],
    "bytes_uploaded_new": bytes_new,
    "all_server_final_verified": not problems,
    "problems": problems,
}, indent=2))
