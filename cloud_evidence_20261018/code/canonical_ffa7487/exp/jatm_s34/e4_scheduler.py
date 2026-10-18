"""Bounded parallel scheduler for isolated E4 Development year workers.

The scheduler does not implement scientific computation.  It starts the
existing yearly runner in independent worker directories, records process and
resource checkpoints, and never opens Test paths.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

YEARS = tuple(range(2017, 2023))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _memory_available_mb() -> int | None:
    try:
        import psutil  # type: ignore
    except ImportError:
        return None
    return int(psutil.virtual_memory().available // (1024 * 1024))


def _state_path(root: Path, year: int) -> Path:
    return root / f"worker_{year}" / f"YEAR_{year}" / "E4_YEAR_STATE.json"


def _read_state(root: Path, year: int) -> dict:
    path = _state_path(root, year)
    if not path.is_file():
        return {"year": year, "status": "NOT_STARTED", "path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"year": year, "status": "INVALID_CHECKPOINT", "path": str(path)}
    payload["path"] = str(path)
    return payload


def run(*, repo: Path, output_root: Path, bundle_root: Path, years: tuple[int, ...],
        n_grid: tuple[int, ...], max_workers: int = 2,
        min_free_memory_mb: int = 8_000, poll_seconds: int = 10) -> dict:
    if max_workers < 1 or max_workers > 2:
        raise ValueError("max_workers must be between 1 and 2")
    if "final_test" in str(output_root).lower() or "final_test" in str(bundle_root).lower():
        raise RuntimeError("E4_FINAL_TEST_PATH_FORBIDDEN")
    output_root = output_root.resolve()
    bundle_root = bundle_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    queue = list(dict.fromkeys(years))
    active: dict[int, subprocess.Popen[str]] = {}
    records: dict[int, dict] = {year: _read_state(output_root, year) for year in queue}
    queue = [year for year in queue if records[year].get("status") != "DEVELOPMENT_COMPLETE"]
    scheduler_state = output_root / "E4_SCHEDULER_STATE.json"

    def write_state() -> None:
        payload = {
            "schema_version": "JATM_S34_E4_SCHEDULER_V1",
            "status": "RUNNING" if active or queue else "COMPLETE",
            "max_workers": max_workers,
            "min_free_memory_mb": min_free_memory_mb,
            "n_grid": list(n_grid),
            "years": {str(year): records[year] for year in sorted(records)},
            "active_pids": {str(year): proc.pid for year, proc in active.items()},
            "updated_at": _now(),
        }
        scheduler_state.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    write_state()
    while queue or active:
        while queue and len(active) < max_workers:
            available = _memory_available_mb()
            if available is not None and available < min_free_memory_mb:
                for year in queue:
                    records[year] = {**records[year], "status": "WAITING_RESOURCE", "available_memory_mb": available}
                write_state()
                break
            year = queue.pop(0)
            worker_root = output_root / f"worker_{year}"
            command = [sys.executable, "-m", "exp.jatm_s34.e4_run",
                       "--output-root", str(worker_root),
                       "--bundle-root", str(bundle_root),
                       "--years", str(year), "--n", *[str(value) for value in n_grid]]
            log_path = output_root / f"scheduler_{year}.log"
            handle = log_path.open("a", encoding="utf-8")
            proc = subprocess.Popen(command, cwd=repo, stdout=handle, stderr=subprocess.STDOUT, text=True)
            handle.close()
            active[year] = proc
            records[year] = {"year": year, "status": "RUNNING", "pid": proc.pid,
                             "worker_root": str(worker_root), "started_at": _now(),
                             "n_grid": list(n_grid)}
            write_state()
        if not active:
            time.sleep(poll_seconds)
            continue
        time.sleep(poll_seconds)
        for year, proc in list(active.items()):
            return_code = proc.poll()
            if return_code is None:
                continue
            records[year] = {**_read_state(output_root, year),
                             "return_code": return_code,
                             "finished_at": _now()}
            active.pop(year)
            write_state()
    payload = {
        "schema_version": "JATM_S34_E4_PARALLEL_DEVELOPMENT_V1",
        "status": "DEVELOPMENT_COMPLETE" if all(record.get("status") == "DEVELOPMENT_COMPLETE" for record in records.values()) else "ENGINEERING_INCOMPLETE",
        "years": {str(year): records[year] for year in sorted(records)},
        "n_grid": list(n_grid),
        "test_access_count": 0,
        "updated_at": _now(),
    }
    (output_root / "E4_PARALLEL_DEVELOPMENT_MANIFEST.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_state()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--years", type=int, nargs="+", default=list(YEARS))
    parser.add_argument("--n", type=int, nargs="+", default=[128])
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--min-free-memory-mb", type=int, default=8000)
    parser.add_argument("--poll-seconds", type=int, default=10)
    args = parser.parse_args(argv)
    payload = run(repo=args.repo_root.resolve(), output_root=args.output_root,
                  bundle_root=args.bundle_root, years=tuple(args.years),
                  n_grid=tuple(args.n), max_workers=args.max_workers,
                  min_free_memory_mb=args.min_free_memory_mb,
                  poll_seconds=args.poll_seconds)
    print(json.dumps({"status": payload["status"], "years": len(payload["years"])}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
