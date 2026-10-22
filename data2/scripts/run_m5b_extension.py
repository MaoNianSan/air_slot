# -*- coding: utf-8 -*-
"""Per-year M5-b extension runner (one year per invocation).

    python -u data2/scripts/run_m5b_extension.py --year 2017

Runs the frozen battery chain for ONE extension year with
``--scope-tag ext{year}`` (shared artifacts land under
``cohort_size_stability/ext{year}/``; year-keyed artifacts keep their year
keys), reusing the existing PRE materialization and every cache the battery
already honors.  Sequence: M2 reference bundle (only if absent) -> headroom ->
ladder probe -> sentinel -> floor -> fit -> eval, each as a battery subprocess.

Typed stops: any nonzero child exit stops the chain; the floor decision is
checked (BLOCK_M5B_NONDETERMINISM stops before FIT); a per-year manifest with
hashes and the sentinel-scope note is written at the end.  Final Test is never
touched (guards inherited from the battery and the metrics layer).
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

STUDY = m5b.STUDY_ROOT
N_GRID = (128, 256, 512, 1024, 2048, 4096)
CHAIN = ("bundle", "headroom", "ladder", "sentinel", "floor", "fit", "eval")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(message: str) -> None:
    print(f"[{now_iso()}] [ext] {message}", flush=True)


def run(year: int, scope: str, output_root: Path, *args: str) -> int:
    command = [sys.executable, "-u",
               "data2/scripts/consequence_stability_battery.py",
               "--scope-tag", scope, "--output-root", str(output_root), *args]
    log(f"RUN: {' '.join(command)}")
    started = time.perf_counter()
    process = subprocess.run(command, cwd=str(REPO))
    log(f"  rc={process.returncode} in {time.perf_counter() - started:.0f}s")
    return process.returncode


def manifest_path(output_root: Path) -> Path:
    return Path(output_root) / "EXTENSION_YEAR_MANIFEST.json"


def build_manifest(year: int, scope: str, output_root: Path,
                   record: dict) -> None:
    payload = {
        "schema_version": "M5B_EXTENSION_YEAR_MANIFEST_V1",
        "year": year,
        "scope_tag": scope,
        "output_root": str(output_root),
        "generated_at": now_iso(),
        "chain": CHAIN,
        "note_sentinel_scope": (
            "the frozen protocol V2 m1_determinism_sentinel.runs names only "
            "2019 settings; the extension year applies the SAME V2 detection/"
            "quantification/decision rules to this year's N=128 and N=4096 "
            "settings and records that scope difference here, without "
            "modifying the protocol"),
        "steps": record,
        "git": m5b.git_provenance(),
        "source_script_hashes": m5b.source_script_hashes(),
        "final_test_access_count": 0,
    }
    payload["artifact_hash"] = m5b.sha256_json(
        {k: v for k, v in payload.items() if k != "artifact_hash"})
    m5b.write_json_atomic(manifest_path(output_root), payload)
    log(f"manifest written: {manifest_path(output_root)}")


PILOT_STATE = STUDY / "AUTORUN_STATE.json"
PILOT_SUMMARY = STUDY / "EVAL_SUMMARY.json"
# extension release requires the STRICT success status only; any other
# terminal state (N_GRID_UPPER_BOUND_REACHED, BLOCKED_*, FAIL_*,
# HUMAN_DECISION_REQUIRED, ...) keeps the extension blocked
PILOT_RELEASE_STATUS = "M5B_PILOT_COMPLETE_HARD_STOP"


def pilot_ready() -> tuple[bool, str]:
    """Strict release gate.

    Requires ALL of: status == M5B_PILOT_COMPLETE_HARD_STOP;
    final_test_access_count == 0; EVAL_SUMMARY exists AND its path is recorded
    in the pilot's state_output_hashes AND its current hash matches that
    record AND its generation time is not before the formal pilot run start;
    every other recorded output hash still verifies.
    """

    if not PILOT_STATE.is_file():
        return False, "pilot state missing"
    try:
        state = json.loads(PILOT_STATE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False, "pilot state unreadable"
    status = state.get("status")
    if status != PILOT_RELEASE_STATUS:
        return False, (f"pilot status {status!r} does not release extension "
                       f"(requires {PILOT_RELEASE_STATUS!r})")
    if int(state.get("final_test_access_count", -1)) != 0:
        return False, ("final_test_access_count != 0 "
                       f"({state.get('final_test_access_count')})")
    # condition 1 + 2: EVAL_SUMMARY recorded in state_output_hashes, hash match
    recorded = None
    for name, entries in (state.get("state_output_hashes") or {}).items():
        for path, expected in entries.items():
            if Path(path).resolve() == PILOT_SUMMARY.resolve():
                recorded = (name, expected)
    if recorded is None:
        return False, "EVAL_SUMMARY path not recorded in pilot state_output_hashes"
    _gate, expected = recorded
    if not PILOT_SUMMARY.is_file():
        return False, "EVAL_SUMMARY missing"
    if expected is None:
        return False, "EVAL_SUMMARY recorded without a hash"
    if m5b.file_hash(PILOT_SUMMARY) != expected:
        return False, "EVAL_SUMMARY hash mismatch vs pilot record"
    # condition 3: generation time not before the formal pilot run start
    started = state.get("started_at")
    if started:
        try:
            start_dt = datetime.fromisoformat(str(started))
            mtime_dt = datetime.fromtimestamp(
                PILOT_SUMMARY.stat().st_mtime, tz=timezone.utc)
            if mtime_dt < start_dt:
                return False, ("EVAL_SUMMARY predates the formal pilot run "
                               f"(mtime {mtime_dt.isoformat()} < start "
                               f"{start_dt.isoformat()})")
        except ValueError:
            pass
    # remaining recorded outputs must still verify
    problems = []
    for name, entries in (state.get("state_output_hashes") or {}).items():
        for path, expected in entries.items():
            if not Path(path).is_file():
                problems.append(f"{name}:{path}:missing")
            elif expected and m5b.file_hash(Path(path)) != expected:
                problems.append(f"{name}:{path}:hash_changed")
    if problems:
        return False, "hash check failed: " + "; ".join(problems[:3])
    return True, "pilot complete and hash-verified"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--n", type=int, nargs="*", default=list(N_GRID))
    parser.add_argument("--output-root", default=None,
                        help="run output root (default: data2/reports/"
                             "cohort_size_formal/ext<year>)")
    parser.add_argument("--wait-for-pilot", action="store_true",
                        help="poll the pilot state until it completes "
                             "(default timeout 12h) instead of failing fast")
    parser.add_argument("--stagger-minutes", type=float, default=0.0,
                        help="extra sleep after the pilot completes, before "
                             "starting this chain (stagger heavy phases)")
    args = parser.parse_args()
    year = int(args.year)
    if year in (2019, 2020):
        print("BLOCKED_PROTOCOL_SCOPE: extension runner is for "
              "2017/2018/2021/2022")
        return 3

    # ---- run identity + output root (created ONLY after the pilot gate) ----
    scope = f"ext{year}"
    formal_root = REPO / "data2" / "reports" / "cohort_size_formal"
    output_root = (Path(args.output_root) if args.output_root
                   else (formal_root / scope))
    n_args = [str(n) for n in args.n]
    run_id = f"ext{year}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    waiter_record = REPO / "data2" / "logs" / f"ext_waiter_{year}.json"
    waiter_record.parent.mkdir(parents=True, exist_ok=True)

    code_hashes = {
        name: m5b.file_hash(REPO / "data2" / "scripts" / name)
        for name in ("run_m5b_extension.py", "consequence_stability_battery.py",
                     "consequence_stability_metrics.py")
    }

    def _write_waiter(status: str, **extra) -> None:
        payload = {"run_id": run_id, "pid": os.getpid(),
                   "started_at": now_iso(), "year": year,
                   "output_root": str(output_root), "status": status,
                   "code_hashes": code_hashes,
                   **extra}
        waiter_record.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str)
            + chr(10), encoding="utf-8")
    _write_waiter("WAITING")

    # ---- pilot gate: strict release conditions only ----
    ready, why = pilot_ready()
    if not ready:
        if not args.wait_for_pilot:
            _write_waiter("BLOCKED",
                          reason="EXTENSION_BLOCKED_PILOT_INCOMPLETE")
            print("EXTENSION_BLOCKED_PILOT_INCOMPLETE:", why)
            return 3
        log(f"waiting for pilot completion ({why}); poll 60s, timeout 12h")
        deadline = time.time() + 12 * 3600.0
        try:
            while time.time() < deadline:
                time.sleep(60)
                ready, why = pilot_ready()
                if ready:
                    break
        except Exception as error:
            _write_waiter("BLOCKED", reason=f"waiter exception: {error!r}")
            print("EXTENSION_BLOCKED_PILOT_INCOMPLETE: waiter exception:",
                  repr(error))
            return 3
        if not ready:
            _write_waiter("BLOCKED",
                          reason="EXTENSION_BLOCKED_PILOT_INCOMPLETE")
            print("EXTENSION_BLOCKED_PILOT_INCOMPLETE:", why)
            return 3
    log(f"pilot gate passed ({why})")
    if args.stagger_minutes:
        log(f"stagger sleep {args.stagger_minutes:.0f} min "
            "(heavy-phase spacing)")
        time.sleep(args.stagger_minutes * 60.0)

    # only NOW does this run create anything
    output_root.mkdir(parents=True, exist_ok=True)
    m5b.set_run_context(bundle_base=output_root)
    _write_waiter("RUNNING")
    record: dict = {"started_at": now_iso()}
    log(f"extension chain for {year} (scope {scope})")

    # ---- bundle (build only when absent; verify-only otherwise) ------------
    if not m5b.m2_bundle_present(year):
        record["bundle"] = "REBUILD_REQUIRED"
        rc = subprocess.run(
            [sys.executable, "-u", "data2/scripts/build_year_references.py",
             "--years", str(year), "--output-root", str(output_root)],
            cwd=str(REPO)).returncode
        if rc != 0:
            print("FAIL_EXTENSION_BUNDLE")
            return 3
    else:
        record["bundle"] = "VERIFIED_PRESENT"
    m5b.load_year_m2_bundle(year)
    log(f"{year}: M2 bundle ok")

    # ---- headroom ----------------------------------------------------------
    if run(year, scope, output_root, "--phase", "headroom",
           "--years", str(year)) != 0:
        print("FAIL_EXTENSION_HEADROOM")
        return 3
    record["headroom"] = "PASS"

    # ---- ladder probe (skip when already present) ---------------------------
    ladder_file = output_root / f"LADDER_PROBE_{year}.json"
    if ladder_file.is_file():
        log(f"{year}: ladder probe reused")
        record["ladder"] = "REUSED"
    else:
        if run(year, scope, output_root, "--phase", "ladder",
               "--years", str(year)) != 0:
            print("FAIL_EXTENSION_LADDER")
            return 3
        record["ladder"] = "PASS"
    evaluation_e = json.loads(
        ladder_file.read_text(encoding="utf-8"))["evaluation_E"]
    log(f"{year}: evaluation_E={evaluation_e}")

    # ---- sentinel -----------------------------------------------------------
    if run(year, scope, output_root, "--phase", "sentinel",
           "--years", str(year)) != 0:
        print("FAIL_EXTENSION_SENTINEL")
        return 3
    sentinel = json.loads((output_root / "M1_DETERMINISM_SENTINEL.json")
                          .read_text(encoding="utf-8"))
    record["sentinel"] = sentinel.get("status")
    log(f"{year}: sentinel {record['sentinel']}")

    # ---- floor ---------------------------------------------------------------
    if run(year, scope, output_root, "--phase", "floor",
           "--years", str(year)) != 0:
        print("FAIL_EXTENSION_FLOOR")
        return 3
    floor = json.loads((output_root / "M5B_FLOOR_QUANTIFICATION.json")
                       .read_text(encoding="utf-8"))
    decision = floor.get("decision", {}).get("decision")
    record["floor"] = decision
    log(f"{year}: floor decision {decision}")
    if decision == "BLOCK_M5B_NONDETERMINISM":
        build_manifest(year, scope, output_root, record)
        _write_waiter("BLOCKED", reason="BLOCK_M5B_NONDETERMINISM")
        print("BLOCK_M5B_NONDETERMINISM")
        return 3

    # ---- fit ----------------------------------------------------------------
    if run(year, scope, output_root, "--phase", "fit", "--years",
           str(year), "--n", *n_args) != 0:
        print("FAIL_EXTENSION_FIT")
        return 3
    record["fit"] = "PASS"

    # ---- eval ----------------------------------------------------------------
    if run(year, scope, output_root, "--phase", "eval", "--years",
           str(year), "--n", *n_args, "--reuse-fit-comparison") != 0:
        print("FAIL_EXTENSION_EVAL")
        return 3
    summary = json.loads((output_root / "EVAL_SUMMARY.json")
                         .read_text(encoding="utf-8"))
    record["eval"] = summary.get("decision", {})
    record["finished_at"] = now_iso()
    build_manifest(year, scope, output_root, record)
    _write_waiter("COMPLETE")
    print("EXTENSION_YEAR_COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
