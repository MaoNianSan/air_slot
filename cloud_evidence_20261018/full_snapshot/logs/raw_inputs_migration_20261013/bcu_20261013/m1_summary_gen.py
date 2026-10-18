#!/usr/bin/env python3
"""Generate M1_2019_2022_TRAINING_SUMMARY.json (round 4 deliverable)."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

B = Path("/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013")
SLOG = B.parent
OUT = B / "M1_2019_2022_TRAINING_SUMMARY.json"


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


summary = {
    "schema_version": "AIRSLOT_M1_TRAINING_SUMMARY_V1",
    "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "code_state": "snapshot 583f2c12 + patch 8cc7a1b7 (d1c72a7) + patch 1d3ba5d3 (ffa7487)",
    "approval_binding": {
        "canonical_record": "/data/airslot/logs/raw_inputs_migration_20261013/M1_TRAINING_AUTHORIZATION_APPROVED_2019_2022.json",
        "canonical_record_sha256": sha256_file(SLOG / "M1_TRAINING_AUTHORIZATION_APPROVED_2019_2022.json"),
        "launch_record_used": "/data/airslot/logs/raw_inputs_migration_20261013/M1_TRAINING_AUTHORIZATION_USER_APPROVED_20261013.json",
        "launch_record_sha256": sha256_file(SLOG / "M1_TRAINING_AUTHORIZATION_USER_APPROVED_20261013.json"),
        "equivalence_note": ("The first run (m1_2019) was launched under the transcription record before the "
                             "canonical record was requested; both records carry byte-identical fixed fields "
                             "(schema/status/years/n/roles/months/development_used_for_fit/final_test_access_count). "
                             "Per the no-duplicate-formal-training rule the run was not restarted; receipts embed the "
                             "launch record hash."),
        "scope": "2019-2022 M1 only; NOT for 2017/2018 retraining, model changes, or E1-E4.",
    },
    "training_config_constants": {
        "source": "exp/jatm_s34/annual_models.py (same code path that produced the frozen 2017/2018 models)",
        "seed": 20260813, "epochs": 8, "learning_rate": 0.001, "batch_size": 64,
        "bucketed": True, "teacher_forcing": True,
        "roles": ["M1_HISTORY_PRIMARY (FULL_ADAPTIVE_CAUSAL_PREFIX)",
                  "M1_CURRENT_COMPARATOR (NO_HISTORY_CURRENT_OBSERVATION)"],
        "n": 4096, "train_months": [1, 2, 3, 4, 5, 6], "calibration_months": [7],
        "development_used_for_fit": False, "final_test_access_count": 0,
    },
    "years": {},
}
for year in (2019, 2020, 2021, 2022):
    tag = f"m1_{year}"
    tdir = B / "tasks" / tag
    time_v = read(tdir / "time_v.txt")
    entry = {
        "task_tag": tag,
        "status": read(tdir / "status"),
        "exit_code": read(tdir / "exitcode"),
        "wall": next((ln.split(": ", 1)[1] for ln in time_v.splitlines() if "Elapsed (wall clock)" in ln), ""),
        "user_time_s": next((ln.split(": ", 1)[1] for ln in time_v.splitlines() if "User time (seconds)" in ln), ""),
        "percent_cpu": next((ln.split(": ", 1)[1] for ln in time_v.splitlines() if "Percent of CPU" in ln), ""),
        "peak_rss_kib": next((ln.split(": ", 1)[1] for ln in time_v.splitlines() if "Maximum resident" in ln), ""),
        "output_sha256": read(tdir / "output_sha256.txt").splitlines(),
        "meta": read(tdir / "meta").splitlines(),
    }
    ydir = Path("/data/airslot/worktree/artifacts/models/m1") / f"YEAR_{year}"
    entry["files"] = sorted(p.name for p in ydir.iterdir()) if ydir.is_dir() else []
    receipt = ydir / "ANNUAL_M1_TRAINING_RECEIPT.json"
    entry["receipt_sha256"] = sha256_file(receipt) if receipt.is_file() else None
    if receipt.is_file():
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        entry["receipt_status"] = payload.get("status")
        entry["receipt_approval_sha256"] = payload.get("approval_sha256")
        entry["final_test_access_count"] = payload.get("final_test_access_count")
    summary["years"][str(year)] = entry

summary["all_pass"] = all(v["status"] == "PASS" for v in summary["years"].values())
OUT.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("written:", OUT)
print("all_pass:", summary["all_pass"])
for y, v in summary["years"].items():
    print(f"  {y}: {v['status']} wall={v['wall']} peak_rss_kib={v['peak_rss_kib']} receipt={v.get('receipt_status')}")
