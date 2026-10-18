# -*- coding: utf-8 -*-
"""Formal paper experiment runner (M5-b battery, validation gates removed).

    python -u data2/scripts/run_paper_formal.py \
        --years 2017 2018 2019 2020 2021 2022 --parallel 2

Rolling scheduler: at most ``--parallel`` year-chains run concurrently; the
moment one chain finishes, the next queued year starts.  Per-year chain:

    bundle -> headroom -> fit -> ladder(runtime probe) -> eval

(fit runs before the ladder probe so the probe can time the year's own N128
checkpoint; the probe is the protocol-preregistered runtime cost selector for
``evaluation_E``, not a stability gate.)  Reads the frozen PRE cohort records
and existing M2 bundles; writes EVERYTHING to its own
``data2/reports/paper_formal/{year}/`` output root with an independent
PAPER_FORMAL_STATE.json, log, and PAPER_FORMAL_MANIFEST.json.  No sentinel,
no floor, no pilot stability gate.  Final Test is never read (guards inherited
from the battery/metrics layer).
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

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "data2" / "scripts"))

import consequence_stability_metrics as m5b  # noqa: E402

N_GRID = (128, 256, 512, 1024, 2048, 4096)
FORMAL_ROOT = REPO / "data2" / "reports" / "paper_formal"
PILOT_BUNDLE_ROOT = REPO / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1"
LOG_ROOT = REPO / "data2" / "logs"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(year: int, message: str) -> None:
    print(f"[{now_iso()}] [formal {year}] {message}", flush=True)


def write_state(year: int, output_root: Path, **fields) -> None:
    payload = {"schema_version": "PAPER_FORMAL_STATE_V1", "year": year,
               "pid": os.getpid(), "updated_at": now_iso(), **fields}
    m5b.write_json_atomic(output_root / "PAPER_FORMAL_STATE.json", payload)


def run_battery(year: int, output_root: Path, bundle_base: Path,
                *args: str) -> int:
    command = [sys.executable, "-u",
               "data2/scripts/consequence_stability_battery.py",
               "--output-root", str(output_root),
               "--bundle-base", str(bundle_base), *args]
    log(year, f"RUN {' '.join(args[:2])}")
    started = time.perf_counter()
    process = subprocess.run(command, cwd=str(REPO))
    log(year, f"  rc={process.returncode} in {time.perf_counter()-started:.0f}s")
    return process.returncode


def year_chain(year: int) -> tuple[int, dict]:
    output_root = FORMAL_ROOT / str(year)
    output_root.mkdir(parents=True, exist_ok=True)
    write_state(year, output_root, status="RUNNING", stage="bundle")
    try:
        code, record = _year_chain(year, output_root)
    except Exception as error:  # noqa: BLE001 - record the failure, then raise
        write_state(year, output_root, status="FAILED", stage=None,
                    error=f"{type(error).__name__}: {error}")
        raise
    write_state(year, output_root,
                status="COMPLETE" if code == 0 else "FAILED",
                stage="done", steps=record.get("steps", {}))
    return code, record


def _year_chain(year: int, output_root: Path) -> tuple[int, dict]:
    bundle_base = (PILOT_BUNDLE_ROOT
                   if m5b.m2_bundle_present(year, repo_root=REPO)
                   else output_root)
    record: dict = {"year": year, "output_root": str(output_root),
                    "bundle_base": str(bundle_base), "steps": {},
                    "started_at": now_iso()}

    # ---- bundle -------------------------------------------------------------
    prior_manifest = (output_root / str(year) / "M2_REFERENCES"
                      / "M2_REFERENCE_BUNDLE_MANIFEST.json")
    if bundle_base == PILOT_BUNDLE_ROOT:
        record["steps"]["bundle"] = "REUSED_FROZEN"
        log(year, "M2 bundle reused from PRE_MULTIYEAR_V1")
    elif prior_manifest.is_file():
        record["steps"]["bundle"] = "REUSED_PRIOR_BUILD"
        log(year, "M2 bundle reused from a prior build in this output root")
    else:
        rc = subprocess.run(
            [sys.executable, "-u", "data2/scripts/build_year_references.py",
             "--years", str(year), "--output-root", str(output_root)],
            cwd=str(REPO)).returncode
        if rc != 0:
            record["steps"]["bundle"] = "FAIL"
            return 3, record
        record["steps"]["bundle"] = "BUILT"
    write_state(year, output_root, status="RUNNING", stage="bundle-verify")
    m5b.set_run_context(bundle_base=bundle_base)
    m5b.load_year_m2_bundle(year)
    m5b.set_run_context(bundle_base=None)

    # ---- headroom -----------------------------------------------------------
    write_state(year, output_root, status="RUNNING", stage="headroom")
    if run_battery(year, output_root, bundle_base, "--phase", "headroom",
                   "--years", str(year)) != 0:
        record["steps"]["headroom"] = "FAIL"
        return 3, record
    record["steps"]["headroom"] = "PASS"

    # ---- fit -----------------------------------------------------------------
    write_state(year, output_root, status="RUNNING", stage="fit")
    if run_battery(year, output_root, bundle_base, "--phase", "fit",
                   "--years", str(year),
                   "--n", *[str(n) for n in N_GRID]) != 0:
        record["steps"]["fit"] = "FAIL"
        return 3, record
    record["steps"]["fit"] = "PASS"

    # ---- ladder probe (runtime-only cost selector, NOT a stability gate) ----
    # runs after fit so the probe can time this year's own N128 checkpoint
    write_state(year, output_root, status="RUNNING", stage="ladder")
    if run_battery(year, output_root, bundle_base, "--phase", "ladder",
                   "--years", str(year)) != 0:
        record["steps"]["ladder"] = "FAIL"
        return 3, record
    record["steps"]["ladder"] = "PASS"

    # ---- eval ----------------------------------------------------------------
    write_state(year, output_root, status="RUNNING", stage="eval")
    if run_battery(year, output_root, bundle_base, "--phase", "eval",
                   "--years", str(year), "--n", *[str(n) for n in N_GRID],
                   "--reuse-fit-comparison") != 0:
        record["steps"]["eval"] = "FAIL"
        return 3, record
    record["steps"]["eval"] = "PASS"
    summary = json.loads((output_root / "EVAL_SUMMARY.json")
                         .read_text(encoding="utf-8"))
    record["decision"] = summary.get("decision", {})
    record["finished_at"] = now_iso()

    payload = {"schema_version": "PAPER_FORMAL_MANIFEST_V1",
               "git": m5b.git_provenance(),
               "source_script_hashes": m5b.source_script_hashes(),
               "final_test_access_count": 0, **record}
    payload["artifact_hash"] = m5b.sha256_json(
        {k: v for k, v in payload.items() if k != "artifact_hash"})
    m5b.write_json_atomic(output_root / "PAPER_FORMAL_MANIFEST.json", payload)
    return 0, record


def _pid_alive(pid: int) -> bool:
    # tasklist prints localized (GBK on zh-CN Windows) text; never decode with
    # text=True here -- a UnicodeDecodeError in the reader thread would crash
    # the scheduler.  Capture bytes and decode permissively: the pid digits and
    # "python.exe" are ASCII and survive errors="replace".
    try:
        raw = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True).stdout
    except Exception:
        return False
    out = (raw or b"").decode("utf-8", errors="replace")
    return f'"{pid}"' in out and "python" in out.lower()


def _read_state(year: int) -> dict:
    state_path = FORMAL_ROOT / str(year) / "PAPER_FORMAL_STATE.json"
    if not state_path.is_file():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, default=None,
                        help="single-year chain mode (spawned by the "
                             "scheduler; never schedules again)")
    parser.add_argument("--years", type=int, nargs="+",
                        default=[2017, 2018, 2019, 2020, 2021, 2022])
    parser.add_argument("--parallel", type=int, default=2)
    args = parser.parse_args()
    if args.year is not None:
        # single-year chain mode: run it directly, return; NEVER schedule
        code, record = year_chain(int(args.year))
        print("PAPER_FORMAL_YEAR_COMPLETE" if code == 0
              else "PAPER_FORMAL_YEAR_FAILED")
        return code

    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    sched_log = LOG_ROOT / "paper_formal_scheduler.log"

    def slog(message: str) -> None:
        line = f"[{now_iso()}] [formal scheduler] {message}"
        print(line, flush=True)
        with open(sched_log, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    queue: list[int] = []
    running: dict[int, int] = {}          # year -> pid (spawned or adopted)
    spawned: dict[int, subprocess.Popen] = {}
    results: dict[int, dict] = {}
    retries: dict[int, int] = {}
    for year in args.years:
        if (FORMAL_ROOT / str(year) / "PAPER_FORMAL_MANIFEST.json").is_file():
            slog(f"{year}: already complete (manifest); skipped")
            continue
        state = _read_state(year)
        if state.get("status") == "COMPLETE":
            slog(f"{year}: state COMPLETE without manifest; skipped")
            continue
        if state.get("status") == "RUNNING":
            pid = int(state.get("pid") or 0)
            if pid and _pid_alive(pid):
                slog(f"{year}: adopted live chain pid={pid}")
                running[year] = pid
                continue
            slog(f"{year}: stale RUNNING state (pid {pid} dead); requeuing")
        queue.append(year)
    slog(f"formal experiment: queue={list(queue)} "
         f"adopted={sorted(running)} parallel={args.parallel}")
    while queue or running:
        while queue and len(running) < max(1, args.parallel):
            year = queue.pop(0)
            log_path = LOG_ROOT / f"paper_formal_{year}.log"
            slog(f"{year}: chain START (log {log_path.name})")
            handle = open(log_path, "a", encoding="utf-8")
            try:
                process = subprocess.Popen(
                    [sys.executable, "-u",
                     "data2/scripts/run_paper_formal.py",
                     "--year", str(year)], cwd=str(REPO),
                    stdout=handle, stderr=subprocess.STDOUT)
            finally:
                handle.close()
            spawned[year] = process
            running[year] = process.pid
            slog(f"{year}: child pid={process.pid}")
        finished = []
        for year, pid in running.items():
            process = spawned.get(year)
            if process is not None:
                if process.poll() is not None:
                    finished.append(year)
            elif not _pid_alive(pid):
                finished.append(year)
        for year in finished:
            pid = running.pop(year)
            process = spawned.pop(year, None)
            code = process.returncode if process is not None else None
            manifest = FORMAL_ROOT / str(year) / "PAPER_FORMAL_MANIFEST.json"
            if manifest.is_file():
                # chain reached its end (verdict recorded, pass or typed fail)
                record = json.loads(manifest.read_text(encoding="utf-8"))
                slog(f"{year}: chain END pid={pid} rc={code} "
                     f"decision={(record.get('decision') or {}).get('status')}")
                results[year] = {"rc": code, "record": record}
                continue
            # interrupted before completion: requeue (resume from caches)
            retries[year] = retries.get(year, 0) + 1
            if retries[year] <= 2:
                slog(f"{year}: chain incomplete (pid={pid} rc={code}); "
                     f"requeue (retry {retries[year]}/2)")
                queue.append(year)
            else:
                slog(f"{year}: chain failed after 2 retries; giving up")
                results[year] = {"rc": code, "record": {}}
        time.sleep(30)
    for year in sorted(results):
        record = results[year]["record"]
        decision = (record.get("decision") or {}).get("status")
        slog(f"RESULT year={year} rc={results[year]['rc']} decision={decision}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
