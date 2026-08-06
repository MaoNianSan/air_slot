from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


EXPECTED_STAGES = [
    "2.1_load_public_sources",
    "2.2_build_episodes_and_references",
    "2.3_build_snapshot_requests",
    "2.4_extract_candidate_state_2.5_build_airport_flow_cache",
    "2.6_attach_state_features",
    "2.7_attach_weather",
    "2.8_attach_flow",
    "2.9_attach_calibration_and_rules",
    "publish",
    "validation_complete",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    os.replace(temporary, path)


def log_state(log_path: Path) -> dict[str, Any]:
    if not log_path.is_file():
        return {"current_stage": "UNKNOWN", "rows_read": 0, "rows_emitted": 0}
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
    stages = [line for line in lines if line.startswith("[") and "]" in line]
    values = {"current_stage": stages[-1] if stages else "UNKNOWN", "rows_read": 0, "rows_emitted": 0}
    for line in lines:
        if line.startswith("Input rows:"):
            values["rows_read"] = int(line.split(":", 1)[1].strip())
        elif line.startswith("Candidate rows retained:"):
            values["rows_emitted"] = int(line.split(":", 1)[1].strip())
    return values


def output_state(output_dir: Path) -> dict[str, Any]:
    files = [path for path in output_dir.rglob("*") if path.is_file()]
    recent = max(files, key=lambda path: path.stat().st_mtime) if files else None
    checkpoints = [path for path in files if "checkpoints" in path.parts and path.suffix == ".json"]
    return {
        "files_processed": len(checkpoints),
        "files_total": len(EXPECTED_STAGES),
        "last_output_file": str(recent) if recent else None,
        "last_output_size": recent.stat().st_size if recent else 0,
        "last_output_mtime": datetime.fromtimestamp(recent.stat().st_mtime, timezone.utc).isoformat() if recent else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--config-hash", required=True)
    parser.add_argument("--data-design-id", required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start-time", required=True)
    parser.add_argument("--n-jobs", type=int, required=True)
    parser.add_argument("--source-log", type=Path, required=True)
    parser.add_argument("--reports-root", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=int, default=300)
    args = parser.parse_args()

    reports = args.reports_root.resolve()
    reports.mkdir(parents=True, exist_ok=True)
    launch_path = reports / f"{args.run_id}_launch_manifest.json"
    heartbeat_path = reports / f"{args.run_id}_heartbeat.json"
    progress_path = reports / f"{args.run_id}_progress.log"
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    identity = {
        "git_commit": git_commit,
        "config_hash": args.config_hash,
        "data_design_id": args.data_design_id,
        "input_manifest_hash": sha256_file(args.input_manifest),
    }
    launch = {
        "run_id": args.run_id,
        "command": args.command,
        **identity,
        "input_manifest": str(args.input_manifest.resolve()),
        "output_dir": str(args.output_dir.resolve()),
        "start_time": args.start_time,
        "n_jobs": args.n_jobs,
        "run_profile": args.profile,
        "expected_stage_sequence": EXPECTED_STAGES,
        "duplicate_run_detected": False,
    }
    if launch_path.exists():
        existing = json.loads(launch_path.read_text(encoding="utf-8"))
        identity_keys = {
            "run_id",
            "command",
            "git_commit",
            "config_hash",
            "data_design_id",
            "input_manifest_hash",
            "input_manifest",
            "output_dir",
            "start_time",
            "n_jobs",
            "run_profile",
        }
        if any(existing.get(key) != launch.get(key) for key in identity_keys):
            raise RuntimeError("RUNTIME_LAUNCH_MANIFEST_IDENTITY_MISMATCH")
    else:
        write_json_atomic(launch_path, launch)

    process = psutil.Process(args.pid)
    start = datetime.fromisoformat(args.start_time)
    while process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
        with process.oneshot():
            cpu = process.cpu_times()
            memory = process.memory_info()
            io = process.io_counters()
        now = datetime.now(timezone.utc)
        heartbeat = {
            "run_id": args.run_id,
            "run_profile": args.profile,
            "process_alive": True,
            "pid": args.pid,
            "timestamp": now,
            "stage_start_time": None,
            **log_state(args.source_log),
            **output_state(args.output_dir),
            "memory_rss": memory.rss,
            "cpu_time": cpu.user + cpu.system,
            "disk_read_bytes": io.read_bytes,
            "disk_write_bytes": io.write_bytes,
            "elapsed_time": (now - start).total_seconds(),
        }
        write_json_atomic(heartbeat_path, heartbeat)
        with progress_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(heartbeat, default=str) + "\n")
        time.sleep(args.interval_seconds)
    final = {
        "run_id": args.run_id,
        "run_profile": args.profile,
        "process_alive": False,
        "pid": args.pid,
        "timestamp": datetime.now(timezone.utc),
        **log_state(args.source_log),
        **output_state(args.output_dir),
    }
    write_json_atomic(heartbeat_path, final)
    with progress_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(final, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
