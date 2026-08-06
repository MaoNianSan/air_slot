from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


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


def output_fingerprint(root: Path) -> tuple[int, int, float, str | None]:
    files = [path for path in root.rglob("*") if path.is_file()] if root.exists() else []
    if not files:
        return 0, 0, 0.0, None
    recent = max(files, key=lambda path: path.stat().st_mtime)
    return len(files), sum(path.stat().st_size for path in files), recent.stat().st_mtime, str(recent)


def log_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"current_stage": "STARTING", "rows_read": 0, "rows_emitted": 0}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
    stages = [line for line in lines if line.startswith("[") and "]" in line]
    return {
        "current_stage": stages[-1] if stages else "RUNNING",
        "rows_read": 0,
        "rows_emitted": 0,
    }


def duplicate_active(reports: Path, identity: dict[str, str]) -> bool:
    for launch_path in reports.glob("*_launch_manifest.json"):
        launch = json.loads(launch_path.read_text(encoding="utf-8"))
        if any(launch.get(key) != value for key, value in identity.items()):
            continue
        heartbeat_path = launch_path.with_name(
            launch_path.name.replace("_launch_manifest.json", "_heartbeat.json")
        )
        heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8")) if heartbeat_path.exists() else {}
        pid = int(heartbeat.get("pid") or launch.get("pid") or 0)
        if heartbeat.get("process_alive") and pid > 0 and psutil.pid_exists(pid):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config-hash", required=True)
    parser.add_argument("--data-design-id", required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--n-jobs", type=int, required=True)
    parser.add_argument("--reports-root", type=Path, required=True)
    parser.add_argument("--logs-root", type=Path, required=True)
    parser.add_argument("--heartbeat-seconds", type=int, default=60)
    parser.add_argument("--no-progress-minutes", type=int, default=20)
    parser.add_argument("--wall-limit-minutes", type=int, default=150)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        raise ValueError("GUARDED_COMMAND_MISSING")

    reports = args.reports_root.resolve()
    logs = args.logs_root.resolve()
    reports.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    launch_path = reports / f"{args.run_id}_launch_manifest.json"
    heartbeat_path = reports / f"{args.run_id}_heartbeat.json"
    progress_path = reports / f"{args.run_id}_progress.log"
    stdout_path = logs / f"{args.run_id}.stdout.log"
    stderr_path = logs / f"{args.run_id}.stderr.log"
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    identity = {
        "git_commit": git_commit,
        "config_hash": args.config_hash,
        "data_design_id": args.data_design_id,
        "input_manifest_hash": sha256_file(args.input_manifest),
    }
    if duplicate_active(reports, identity):
        print("DUPLICATE_RUN_DETECTED=YES")
        return 3

    started = datetime.now(timezone.utc)
    launch = {
        "run_id": args.run_id,
        "module": args.module,
        "run_profile": args.profile,
        "command": subprocess.list2cmdline(command),
        **identity,
        "input_manifest": str(args.input_manifest.resolve()),
        "output_dir": str(args.output_dir.resolve()),
        "start_time": started,
        "n_jobs": args.n_jobs,
        "expected_stage_sequence": "MODULE_DECLARED_PROGRESS_AND_CHECKPOINTS",
        "duplicate_run_detected": False,
        "status": "LAUNCHING",
    }
    write_json_atomic(launch_path, launch)

    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=args.cwd, stdout=stdout, stderr=stderr)
    launch.update({"pid": process.pid, "status": "RUNNING"})
    write_json_atomic(launch_path, launch)

    ps_process = psutil.Process(process.pid)
    last_progress = time.monotonic()
    previous_cpu = -1.0
    previous_io = (-1, -1)
    previous_output = (-1, -1, -1.0, None)
    previous_stage = ""
    stopped_for_diagnosis = False
    while process.poll() is None:
        with ps_process.oneshot():
            cpu_times = ps_process.cpu_times()
            memory = ps_process.memory_info()
            io = ps_process.io_counters()
        cpu = cpu_times.user + cpu_times.system
        output = output_fingerprint(args.output_dir)
        stage = log_state(stderr_path)
        progress_signals = sum((
            cpu > previous_cpu + 0.1,
            (io.read_bytes, io.write_bytes) != previous_io,
            output[:3] != previous_output[:3],
            stage["current_stage"] != previous_stage,
        ))
        if progress_signals >= 2:
            last_progress = time.monotonic()
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        heartbeat = {
            "run_id": args.run_id,
            "run_profile": args.profile,
            "module": args.module,
            "pid": process.pid,
            "process_alive": True,
            "timestamp": datetime.now(timezone.utc),
            **stage,
            "last_output_file": output[3],
            "last_output_size": output[1],
            "memory_rss": memory.rss,
            "cpu_time": cpu,
            "disk_read_bytes": io.read_bytes,
            "disk_write_bytes": io.write_bytes,
            "elapsed_time": elapsed,
            "seconds_since_verified_progress": time.monotonic() - last_progress,
            "progress_status": "PROGRESSING" if progress_signals >= 2 else "OBSERVING",
        }
        write_json_atomic(heartbeat_path, heartbeat)
        with progress_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(heartbeat, default=str) + "\n")
        print(json.dumps(heartbeat, default=str), flush=True)
        previous_cpu = cpu
        previous_io = (io.read_bytes, io.write_bytes)
        previous_output = output
        previous_stage = stage["current_stage"]
        if time.monotonic() - last_progress >= args.no_progress_minutes * 60:
            process.terminate()
            stopped_for_diagnosis = True
            break
        if elapsed >= args.wall_limit_minutes * 60:
            process.terminate()
            stopped_for_diagnosis = True
            break
        time.sleep(args.heartbeat_seconds)

    exit_code = process.wait(timeout=30)
    final = {
        "run_id": args.run_id,
        "run_profile": args.profile,
        "module": args.module,
        "pid": process.pid,
        "process_alive": False,
        "timestamp": datetime.now(timezone.utc),
        **log_state(stderr_path),
        "process_exit_code": exit_code,
        "process_exit_status": "STOPPED_FOR_DIAGNOSIS" if stopped_for_diagnosis else ("PASS" if exit_code == 0 else "FAIL"),
        "progress_status": "PARTIAL" if stopped_for_diagnosis else ("COMPLETE" if exit_code == 0 else "PARTIAL"),
        "duplicate_run_detected": False,
        "clean_executed": False,
        "rerun_allowed": False if exit_code == 0 else None,
    }
    write_json_atomic(heartbeat_path, final)
    with progress_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(final, default=str) + "\n")
    print(json.dumps(final, indent=2, default=str))
    if stderr_path.exists() and exit_code:
        print(stderr_path.read_text(encoding="utf-8", errors="replace")[-8000:], file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
