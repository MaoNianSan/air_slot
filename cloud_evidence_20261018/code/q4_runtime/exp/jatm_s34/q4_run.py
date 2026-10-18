"""Run six independent Q4 year jobs with bounded parallelism and live progress."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

YEARS = tuple(range(2017, 2023))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_year_status(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "STARTING", "completed_stages": []}


def run(*, repo: Path, results_root: Path, frozen_e4_root: Path,
        bundle_root: Path, years: tuple[int, ...] = YEARS,
        max_workers: int = 3, n_grid: tuple[int, ...] = (128, 256, 512, 1024, 2048, 4096),
        bootstrap_replicates: int = 2000) -> dict:
    if max_workers < 1 or max_workers > 3:
        raise ValueError(f"Q4_MAX_WORKERS_OUT_OF_RANGE:{max_workers}")
    repo = Path(repo).resolve()
    results_root = Path(results_root).resolve()
    binding_path = repo / "Q4_PRE_RUN_BINDING_MANIFEST.json"
    if not binding_path.is_file():
        raise RuntimeError(f"Q4_PRE_RUN_BINDING_MANIFEST_MISSING:{binding_path}")
    results_root.mkdir(parents=True, exist_ok=True)
    manifest_path = results_root / "Q4_MULTIYEAR_MANIFEST.json"
    started = time.monotonic()
    manifest = {"schema_version": "JATM_S34_Q4_MULTIYEAR_RUN_V1",
                "status": "RUNNING", "split": "test", "years": list(years),
                "max_workers": max_workers, "n": 4096, "n_grid": list(n_grid),
                "started_at": _now(), "year_status": {str(y): "PENDING" for y in years}}
    manifest["pre_run_binding_manifest"] = str(binding_path)
    manifest["pre_run_binding_manifest_sha256"] = _sha256(binding_path)
    _atomic_json(manifest_path, manifest)
    pending = list(years)
    running: dict[int, tuple[subprocess.Popen, object, Path]] = {}
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4",
                "OPENBLAS_NUM_THREADS": "4", "NUMEXPR_MAX_THREADS": "4",
                "PYTHONUNBUFFERED": "1"})

    def launch(year: int) -> None:
        year_root = results_root / str(year)
        year_root.mkdir(parents=True, exist_ok=True)
        log_handle = (year_root / "worker.log").open("a", encoding="utf-8")
        command = [sys.executable, "-u", "-m", "exp.jatm_s34.q4_year_run",
                   "--repo-root", str(repo), "--results-root", str(results_root),
                   "--frozen-e4-root", str(frozen_e4_root), "--bundle-root", str(bundle_root),
                   "--year", str(year), "--n", *map(str, n_grid),
                   "--bootstrap-replicates", str(bootstrap_replicates)]
        process = subprocess.Popen(command, cwd=repo, env=env, stdout=log_handle,
                                   stderr=subprocess.STDOUT, text=True)
        running[year] = (process, log_handle, year_root / "Q4_YEAR_MANIFEST.json")
        manifest["year_status"][str(year)] = "RUNNING"
        manifest["updated_at"] = _now()
        _atomic_json(manifest_path, manifest)
        print(json.dumps({"event": "year_started", "year": year,
                          "pid": process.pid, "utc": _now()}, separators=(",", ":")), flush=True)

    last_report = time.monotonic()
    while pending or running:
        while pending and len(running) < max_workers:
            launch(pending.pop(0))
        finished = []
        for year, (process, log_handle, status_path) in list(running.items()):
            child = _read_year_status(status_path)
            manifest["year_status"][str(year)] = child.get("status", "RUNNING")
            rc = process.poll()
            if rc is not None:
                log_handle.close()
                if rc != 0 and child.get("status") == "RUNNING":
                    child["status"] = "ENGINEERING_INCOMPLETE"
                    child["error"] = f"WORKER_EXIT_CODE:{rc}"
                manifest["year_status"][str(year)] = child.get("status", "ENGINEERING_INCOMPLETE")
                finished.append(year)
        for year in finished:
            running.pop(year)
            print(json.dumps({"event": "year_finished", "year": year,
                              "status": manifest["year_status"][str(year)],
                              "utc": _now()}, separators=(",", ":")), flush=True)
        now = time.monotonic()
        if now - last_report >= 30:
            active = {}
            for year, (_process, _handle, status_path) in running.items():
                child = _read_year_status(status_path)
                active[str(year)] = {
                    "status": child.get("status", "RUNNING"),
                    "completed_stages": child.get("completed_stages", []),
                }
            print(json.dumps({"event": "progress", "elapsed_hours": round((now-started)/3600, 2),
                              "active": active, "finished": {k:v for k,v in manifest["year_status"].items()
                                                                if v not in {"PENDING", "RUNNING"}},
                              "utc": _now()}, separators=(",", ":")), flush=True)
            last_report = now
        manifest["updated_at"] = _now()
        _atomic_json(manifest_path, manifest)
        if running:
            time.sleep(5)
    manifest["status"] = ("TEST_COMPLETE" if all(
        value == "TEST_COMPLETE" for value in manifest["year_status"].values()
    ) else "ENGINEERING_INCOMPLETE")
    manifest["finished_at"] = _now()
    manifest["elapsed_seconds"] = round(time.monotonic() - started, 1)
    _atomic_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--frozen-e4-root", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--years", type=int, nargs="+", default=list(YEARS), choices=YEARS)
    parser.add_argument("--max-workers", type=int, default=3)
    parser.add_argument("--n", type=int, nargs="+", default=[128, 256, 512, 1024, 2048, 4096])
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    args = parser.parse_args()
    result = run(repo=args.repo_root, results_root=args.results_root,
                 frozen_e4_root=args.frozen_e4_root, bundle_root=args.bundle_root,
                 years=tuple(args.years), max_workers=args.max_workers,
                 n_grid=tuple(args.n), bootstrap_replicates=args.bootstrap_replicates)
    print(json.dumps({"status": result["status"], "year_status": result["year_status"]}, separators=(",", ":")), flush=True)
    return 0 if result["status"] == "TEST_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
