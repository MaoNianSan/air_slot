#!/usr/bin/env python3
"""Generate ANNUAL_TAIL_2019_2022_VERIFICATION.json (round 4 deliverable).

Re-runs the official tail validator (load_annual_tail) for 2019-2022 and
records task-level metrics; also pins the frozen 2017/2018 tail hashes as
untouched references.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/data/airslot/worktree")
B = Path("/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013")
OUT = B / "ANNUAL_TAIL_2019_2022_VERIFICATION.json"
sys.path.insert(0, str(REPO))
from exp.jatm_s34.annual_tail import annual_tail_path, load_annual_tail, tail_manifest_summary  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read(path: Path, default=""):
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return default


report = {
    "schema_version": "AIRSLOT_ANNUAL_TAIL_VERIFICATION_V1",
    "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "years": {},
}
for year in (2019, 2020, 2021, 2022):
    tag = f"tail_{year}"
    tdir = B / "tasks" / tag
    time_v = read(tdir / "time_v.txt")
    mana = annual_tail_path(year)
    entry = {
        "task_tag": tag,
        "task_status": read(tdir / "status"),
        "exit_code": read(tdir / "exitcode"),
        "wall": next((ln.split(": ", 1)[1] for ln in time_v.splitlines() if "Elapsed (wall clock)" in ln), ""),
        "peak_rss_kib": next((ln.split(": ", 1)[1] for ln in time_v.splitlines() if "Maximum resident" in ln), ""),
        "manifest_path": str(mana),
        "manifest_sha256": sha256_file(mana) if mana.is_file() else None,
    }
    try:
        tails = load_annual_tail(year)
        entry["official_load_validation"] = "PASS"
        entry["targets"] = sorted(tails)
        entry["summary"] = tail_manifest_summary(year)
    except Exception as error:  # noqa: BLE001
        entry["official_load_validation"] = f"FAIL: {type(error).__name__}: {error}"
    report["years"][str(year)] = entry

# frozen references (must remain untouched)
report["frozen_2017_2018"] = {}
for year in (2017, 2018):
    mana = annual_tail_path(year)
    report["frozen_2017_2018"][str(year)] = {
        "manifest_sha256": sha256_file(mana) if mana.is_file() else None,
        "note": "frozen this round; never rebuilt",
    }
report["all_2019_2022_valid"] = all(
    v.get("official_load_validation") == "PASS" and v.get("task_status") == "PASS"
    for v in report["years"].values())
OUT.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
print("written:", OUT, "| all_valid:", report["all_2019_2022_valid"])
for y, v in report["years"].items():
    print(f"  {y}: {v['task_status']} load={v.get('official_load_validation')} sha={str(v['manifest_sha256'])[:16]}")
