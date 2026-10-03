# -*- coding: utf-8 -*-
"""Autonomous M5-b pilot runner (state machine, resumable, typed stops).

    python -u data2/scripts/run_m5b_autonomous.py \
        --mode pilot --years 2019 2020 \
        --n 128 256 512 1024 2048 4096 \
        --bootstrap 2000 --bootstrap-seed 20260906

Non-interactive: never waits for confirmation inside the authorized scope.
Idempotent: every state verifies its recorded outputs (paths + hashes) before
executing; completed states are reused.  Every stop is a typed status.
Final-Test (Oct-Dec) data is never read; the input manifest rejects any path
containing final_test/test/october/november/december (case-insensitive).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (str(_REPO_ROOT), str(Path(__file__).resolve().parent)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import consequence_stability_metrics as m5b  # noqa: E402

REPO = _REPO_ROOT
STUDY_ROOT = m5b.STUDY_ROOT
BATTERY = REPO / "data2" / "scripts" / "consequence_stability_battery.py"
BUILDER = REPO / "data2" / "scripts" / "build_year_references.py"
PRE_ROOT = m5b.PRE_ROOT
N_GRID = (128, 256, 512, 1024, 2048, 4096)
PILOT_YEARS = (2019, 2020)
AUDIT_YEARS = (2017, 2018, 2019, 2020, 2021, 2022)
PROTOCOL_BOOTSTRAP_REPLICATES = 2000
PROTOCOL_BOOTSTRAP_SEED = 20260906

STATE_FILE = STUDY_ROOT / "AUTORUN_STATE.json"
REPORT_FILE = STUDY_ROOT / "AUTORUN_REPORT.md"
LOG_FILE = STUDY_ROOT / "AUTORUN.log"
LOCK_FILE = STUDY_ROOT / "AUTORUN.lock"
AUDIT_JSON = STUDY_ROOT / "PRE_STATE_MATERIALIZATION_AUDIT_V2.json"
AUDIT_MD = STUDY_ROOT / "PRE_STATE_MATERIALIZATION_AUDIT_V2.md"
SENTINEL_JSON = STUDY_ROOT / "M1_DETERMINISM_SENTINEL.json"
FLOOR_JSON = STUDY_ROOT / "M5B_FLOOR_QUANTIFICATION.json"
SMOKE_JSON = STUDY_ROOT / "M5B_SMOKE.json"
EVAL_SUMMARY = STUDY_ROOT / "EVAL_SUMMARY.json"

PILOT_STATES = [
    "PREFLIGHT", "REUSE_ARTIFACT_AUDIT", "PROTOCOL_GATE",
    "DETERMINISM_SENTINEL", "M2_REFERENCE_GATE", "LADDER_PROBE",
    "DETERMINISM_FLOOR_QUANTIFICATION", "EVAL_SMOKE_GATE",
    "FIT_SIZE_STABILITY", "EVAL_SIZE_STABILITY", "PILOT_REPORT", "HARD_STOP",
]
AUDIT_STATES = ["PREFLIGHT", "REUSE_ARTIFACT_AUDIT", "PROTOCOL_GATE",
                "PRE_METRICS", "CONSEQUENCE_INTERFACE_AUDIT", "HARD_STOP"]

BLOCKING_PREFIXES = ("BLOCKED_", "FAIL_", "N_GRID_", "BLOCK_M5B")
SUCCESS_STATUSES = {"M5B_PILOT_COMPLETE_HARD_STOP",
                    "PRE_STATE_MATERIALIZATION_COMPLETE_CONSEQUENCE_SIDE_PENDING"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(message: str) -> None:
    print(f"[{now_iso()}] [autorun] {message}", flush=True)


def append_log(**fields: object) -> None:
    fields.setdefault("timestamp", now_iso())
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(fields, ensure_ascii=False, default=str) + "\n")


def file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json_atomic(path: Path, payload: object) -> str:
    return m5b.write_json_atomic(Path(path), payload)


def reject_unsafe_path(path: Path) -> bool:
    text = str(path).lower()
    return any(token in text for token in
               ("final_test", "test", "october", "november", "december"))


class TypedStop(SystemExit):
    def __init__(self, status: str, detail: str = "") -> None:
        super().__init__(status)
        self.status = status
        self.detail = detail


def is_blocking(status: str) -> bool:
    return status.startswith(BLOCKING_PREFIXES)


# --------------------------------------------------------------------------- #
# state file + lock
# --------------------------------------------------------------------------- #

def load_or_initialize_state(mode: str, args: argparse.Namespace) -> dict:
    if STATE_FILE.is_file():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if state.get("mode") != mode or state.get("years") != list(args.years):
                raise TypedStop(
                    "BLOCKED_AUTORUN_STATE_CORRUPT",
                    f"mode/years mismatch: {state.get('mode')}/{state.get('years')}")
            return state
        except json.JSONDecodeError as error:
            raise TypedStop("BLOCKED_AUTORUN_STATE_CORRUPT", str(error))
    state = {
        "schema_version": "M5B_AUTORUN_STATE_V1",
        "run_id": f"m5b-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "started_at": now_iso(), "updated_at": now_iso(),
        "repo_root": str(REPO), "git_head": None, "git_branch": None,
        "mode": mode, "years": list(args.years), "n_grid": list(args.n),
        "bootstrap": args.bootstrap, "bootstrap_seed": args.bootstrap_seed,
        "current_state": None, "completed_states": [], "failed_state": None,
        "status": "INIT", "input_manifest_hash": None,
        "outputs_manifest_hash": None, "final_test_access_count": 0,
        "model_retrained": False, "model_recalibrated": False,
        "consequence_side_executed": False, "next_action": None,
        "state_outputs": {}, "commands": [],
    }
    write_json_atomic(STATE_FILE, state)
    return state


def _output_paths(entry: object) -> list[str]:
    """Flatten a state_outputs entry (str | list | year-keyed dict) to paths."""

    if entry is None:
        return []
    if isinstance(entry, str):
        return [entry]
    if isinstance(entry, dict):
        paths: list[str] = []
        for value in entry.values():
            paths.extend(_output_paths(value))
        return paths
    if isinstance(entry, (list, tuple)):
        paths = []
        for value in entry:
            paths.extend(_output_paths(value))
        return paths
    return []


def _record_output_hashes(state: dict) -> None:
    hashes: dict[str, dict[str, str | None]] = {}
    for name, entry in state.get("state_outputs", {}).items():
        hashes[name] = {
            path: (file_hash(Path(path)) if Path(path).is_file() else None)
            for path in _output_paths(entry)
        }
    state["state_output_hashes"] = hashes


def write_state(state: dict) -> None:
    state["updated_at"] = now_iso()
    _record_output_hashes(state)
    state["outputs_manifest_hash"] = m5b.sha256_json(
        state.get("state_output_hashes", {}))
    write_json_atomic(STATE_FILE, state)


def verify_completed_state_outputs(state: dict) -> None:
    """Resume gate: every recorded output of a completed state must still be
    present and hash-identical; otherwise the state file is corrupt."""

    recorded = state.get("state_output_hashes") or {}
    problems: list[str] = []
    for name, entries in recorded.items():
        for path, expected in entries.items():
            if not Path(path).is_file():
                problems.append(f"{name}:missing:{path}")
            elif expected is not None and file_hash(Path(path)) != expected:
                problems.append(f"{name}:hash_changed:{path}")
    if problems:
        raise TypedStop("BLOCKED_AUTORUN_STATE_CORRUPT",
                        "; ".join(problems[:5]))


def acquire_single_run_lock() -> None:
    STUDY_ROOT.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.is_file():
        try:
            payload = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {"pid": None}
        pid = payload.get("pid")
        alive = False
        if pid:
            try:
                os.kill(pid, 0)
                alive = True
            except OSError:
                alive = False
        if alive:
            raise TypedStop(
                "BLOCKED_AUTORUN_ALREADY_RUNNING",
                f"pid={pid} since {payload.get('acquired_at')}")
        raise TypedStop(
            "BLOCKED_AUTORUN_STALE_LOCK",
            f"stale lock preserved at {LOCK_FILE} (pid={pid}); "
            "rerun with --recover-stale-lock to take over")
    write_json_atomic(LOCK_FILE, {
        "pid": os.getpid(), "acquired_at": now_iso(), "host": os.uname().nodename
        if hasattr(os, "uname") else "windows"})


def release_single_run_lock() -> None:
    if LOCK_FILE.is_file():
        try:
            LOCK_FILE.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# subprocess execution with captured provenance
# --------------------------------------------------------------------------- #

def _typed_token_from_output(output: str) -> str | None:
    """Extract a typed status token from a child's failure output, if any."""

    pattern = re.compile(
        r"\b(BLOCK_M5B_[A-Z_]+|BLOCKED_[A-Z_]+|FAIL_[A-Z_]+|N_GRID_[A-Z_]+)\b")
    matches = pattern.findall(output or "")
    return matches[-1] if matches else None


HEARTBEAT_SECONDS = 60.0


def run_command(state: dict, label: str, command: list[str]) -> dict:
    started = time.perf_counter()
    started_at = now_iso()
    log(f"RUN {label}: {' '.join(command)}")
    child = subprocess.Popen(
        [sys.executable, "-u", *command], cwd=str(REPO),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    state["current_subprocess"] = {
        "pid": child.pid, "label": label, "command": command,
        "started_at": started_at,
    }
    state["heartbeat_at"] = now_iso()
    write_state(state)
    append_log(state=state.get("current_state"), event="child_started",
               status="RUNNING", command=[sys.executable, "-u", *command],
               return_code=None, output_paths=[], input_hashes={},
               timestamp=now_iso(), child_pid=child.pid)
    while True:
        try:
            stdout, stderr = child.communicate(timeout=HEARTBEAT_SECONDS)
            break
        except subprocess.TimeoutExpired:
            # live heartbeat while the child runs (state file stays current)
            state["heartbeat_at"] = now_iso()
            write_state(state)
            append_log(state=state.get("current_state"), event="heartbeat",
                       status="RUNNING", command=[], return_code=None,
                       output_paths=[], input_hashes={}, timestamp=now_iso(),
                       child_pid=child.pid,
                       elapsed_seconds=round(time.perf_counter() - started, 1))
    state.pop("current_subprocess", None)
    record = {
        "label": label, "command": [sys.executable, "-u", *command],
        "return_code": child.returncode,
        "stdout_tail": (stdout or "")[-4000:],
        "stderr_tail": (stderr or "")[-4000:],
        "seconds": round(time.perf_counter() - started, 1),
        "started_at": started_at,
        "command_hash": m5b.sha256_json(command),
    }
    state.setdefault("commands", []).append(record)
    # persist immediately so the executed-command table survives a typed stop
    # that re-reads the state file from disk
    write_state(state)
    append_log(state=state.get("current_state"), event="command", status=(
        "OK" if child.returncode == 0 else "FAIL"), command=record["command"],
        return_code=child.returncode,
        output_paths=[], input_hashes={}, timestamp=now_iso())
    if child.returncode != 0:
        tail = (stderr or stdout or "")[-2000:]
        token = _typed_token_from_output(f"{stdout}\n{stderr}")
        if token is not None:
            raise TypedStop(token, f"child {label}: {tail[-600:]}")
        raise RuntimeError(f"COMMAND_FAILED:{label}:rc={child.returncode}:{tail}")
    return record


def battery_command(state: dict, label: str, *args: str) -> dict:
    return run_command(state, label, ["data2/scripts/consequence_stability_battery.py", *args])


# --------------------------------------------------------------------------- #
# states
# --------------------------------------------------------------------------- #

def collect_repository_provenance(state: dict) -> None:
    provenance = m5b.git_provenance()
    state["git_head"] = provenance["git_head"]
    state["git_branch"] = provenance["git_branch"]


def build_input_manifest_without_test_paths(state: dict) -> str:
    entries: dict[str, str] = {}
    candidates: list[Path] = [STUDY_ROOT / m5b.V1_PROTOCOL_NAME]
    for year in state["years"]:
        root = STUDY_ROOT / str(year)
        candidates += [
            root / "HASH_SELECTED_COHORT_RECORDS_N4096.jsonl",
            root / "HASH_RANKED_POOL_SUMMARY.json",
            root / "COHORT_SIZE_STABILITY_PRE.json",
            PRE_ROOT / str(year) / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN.json",
            PRE_ROOT / str(year) / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN.json",
        ]
        for n in state["n_grid"]:
            candidates.append(root / f"N{n}" / "MATERIALIZE_SUMMARY.json")
    candidates += [BATTERY, BUILDER, Path(__file__).resolve(),
                   REPO / "data2" / "scripts" / "consequence_stability_metrics.py"]
    candidates += sorted((REPO / "configs").rglob("*.yaml"))
    for path in candidates:
        if path.is_file() and not reject_unsafe_path(path):
            entries[str(path.relative_to(REPO))] = file_hash(path)
    return m5b.sha256_json(entries)


def state_complete(state: dict, name: str, outputs: list[Path]) -> bool:
    recorded = state.get("state_outputs", {}).get(name)
    if recorded is None:
        return False
    for path in outputs:
        if not Path(path).is_file():
            return False
    return True


def run_preflight(state: dict, args: argparse.Namespace) -> None:
    if not (REPO / "AGENTS.md").is_file() or not (
            REPO / "REPOSITORY_AUTHORITY.md").is_file():
        raise TypedStop("BLOCKED_PRECHECK", "authority docs missing")
    collect_repository_provenance(state)
    dirty = subprocess.run(["git", "status", "--short"], cwd=str(REPO),
                           capture_output=True, text=True).stdout
    state["pre_existing_dirty_files"] = dirty.strip().splitlines()
    # process scan: no forbidden writer may be active while we run
    try:
        scan = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | "
             "Where-Object { $_.CommandLine -match 'final_test|jatm_section5|"
             "cohort_size_study' } | Select-Object -ExpandProperty CommandLine"],
            capture_output=True, text=True, timeout=60)
        active = [line for line in (scan.stdout or "").splitlines()
                  if line.strip() and "Get-CimInstance" not in line
                  and "run_m5b_autonomous" not in line]
        if active:
            raise TypedStop("BLOCKED_PRECHECK",
                            f"forbidden writer active: {active[:3]}")
        state["process_scan"] = "CLEAN" if scan.returncode == 0 else "UNAVAILABLE"
    except TypedStop:
        raise
    except Exception as error:  # scan failure must not block the run
        state["process_scan"] = f"UNAVAILABLE:{error}"
    missing = []
    for year in AUDIT_YEARS if state["mode"] == "audit" else state["years"]:
        root = STUDY_ROOT / str(year)
        if not (root / "HASH_SELECTED_COHORT_RECORDS_N4096.jsonl").is_file():
            missing.append(str(root))
        for n in state["n_grid"]:
            if not (root / f"N{n}" / "MATERIALIZE_SUMMARY.json").is_file():
                missing.append(f"{root}/N{n}")
    if missing:
        raise TypedStop("BLOCKED_MISSING_PRECOMPUTED_ARTIFACT",
                        f"missing={missing[:6]}")
    state["input_manifest_hash"] = build_input_manifest_without_test_paths(state)
    append_log(state="PREFLIGHT", event="complete", status="OK",
               command=[], return_code=0,
               output_paths=[], input_hashes={}, timestamp=now_iso())


def audit_pre_materialization(state: dict) -> None:
    """13 frozen invariants per (year, N); writes AUDIT_V2 json+md."""

    if state_complete(state, "REUSE_ARTIFACT_AUDIT", [AUDIT_JSON, AUDIT_MD]):
        log("REUSE_ARTIFACT_AUDIT: reused")
        return
    years = AUDIT_YEARS  # the materialization spans 2017-2022 (plan Phase 1)
    grid = list(state["n_grid"])
    problems: list[str] = []
    per_year: dict[str, object] = {}
    seed_contracts: set[str] = set()
    for year in years:
        root = STUDY_ROOT / str(year)
        pool_path = root / "HASH_RANKED_POOL_SUMMARY.json"
        pool = json.loads(pool_path.read_text(encoding="utf-8"))
        seed_contracts.add(json.dumps(pool.get("seed_contract"), sort_keys=True))
        ranked: dict[str, list[tuple[str, str]]] = {
            "train": [], "calibration": [], "development": []}
        with (root / "HASH_SELECTED_COHORT_RECORDS_N4096.jsonl").open(
                encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                ranked[row["split"]].append((str(row["rank"]),
                                             str(row["episode"]["episode_id"])))
        for split, records in ranked.items():
            records.sort()
            ids = [episode_id for _rank, episode_id in records]
            if len(set(ids)) != len(ids):
                problems.append(f"{year}:{split}:duplicate_episode_ids")
            ranks = [rank for rank, _episode_id in records]
            if len(set(ranks)) != len(ranks):
                problems.append(f"{year}:{split}:duplicate_ranks")
            ranked[split] = records
        year_report: dict[str, object] = {"pool": pool.get("pool_sizes"),
                                          "n_levels": {}}
        for n in grid:
            n_dir = root / f"N{n}"
            summary_path = n_dir / "MATERIALIZE_SUMMARY.json"
            if not summary_path.is_file():
                problems.append(f"{year}:N{n}:MATERIALIZE_SUMMARY_missing")
                continue
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            size_vector = summary.get("size_vector", {})
            checks = {
                "materialized_episodes_eq_n":
                    int(summary.get("materialized_episodes", -1)) == int(n),
                "train_eq_n": int(size_vector.get("TRAIN", -1)) == int(n),
                "calibration_eq_n_half":
                    int(size_vector.get("CALIBRATION", -1)) == int(n) // 2,
                "development_eq_n": int(size_vector.get("DEVELOPMENT", -1)) == int(n),
                "nodes_eq_prestates":
                    int(summary.get("development_nodes", -1))
                    == int(summary.get("prestates", -2)),
                "final_test_access_zero":
                    int(summary.get("weather_audit", {})
                        .get("final_test_access_count", -1)) == 0,
                "year_agrees": int(summary.get("year", -1)) == int(year),
                "n_agrees": int(summary.get("n", -1)) == int(n),
                "states_file_present": (n_dir / "PRE_DEVELOPMENT_STATES.jsonl").is_file(),
            }
            if n < grid[-1]:
                bigger = grid[grid.index(n) + 1]
                smaller_ids = _states_episode_ids(n_dir)
                bigger_ids = _states_episode_ids(root / f"N{bigger}")
                checks["nested_in_next"] = smaller_ids.issubset(bigger_ids)
            failed = [name for name, ok in checks.items() if not ok]
            if failed:
                problems.append(f"{year}:N{n}:{','.join(failed)}")
            year_report["n_levels"][str(n)] = {
                "checks": checks,
                "development_nodes": summary.get("development_nodes"),
            }
        if len(seed_contracts) > 1:
            problems.append(f"{year}:seed_contract_differs")
        per_year[str(year)] = year_report
    status = "PASS_PRE_STATE_AUDIT" if not problems else "FAIL_PRE_STATE_AUDIT"
    payload = {
        "schema_version": "M5B_PRE_STATE_AUDIT_V2",
        "status": status, "problems": problems, "per_year": per_year,
        "seed_contracts": sorted(seed_contracts),
        "git_head": state.get("git_head"), "git_branch": state.get("git_branch"),
        "final_test_access_count": 0,
        "analysis_layer": "PRE_OBSERVABLE_ONLY",
    }
    payload["artifact_hash"] = m5b.sha256_json(
        {k: v for k, v in payload.items() if k != "artifact_hash"})
    write_json_atomic(AUDIT_JSON, payload)
    AUDIT_MD.write_text(
        "# M5-b PRE-state materialization audit V2\n\n"
        f"- status: **{status}**\n- problems: {len(problems)}\n\n"
        + "\n".join(f"- {problem}" for problem in problems[:80]) + "\n",
        encoding="utf-8")
    state["state_outputs"]["REUSE_ARTIFACT_AUDIT"] = str(AUDIT_JSON)
    append_log(state="REUSE_ARTIFACT_AUDIT", event="complete", status=status,
               command=[], return_code=0,
               output_paths=[str(AUDIT_JSON), str(AUDIT_MD)],
               input_hashes={}, timestamp=now_iso())
    if problems:
        raise TypedStop("FAIL_PRE_STATE_AUDIT", f"{len(problems)} problems")


def _states_episode_ids(n_dir: Path, _cache: dict = {}) -> set[str]:
    if n_dir in _cache:
        return _cache[n_dir]
    ids: set[str] = set()
    path = n_dir / "PRE_DEVELOPMENT_STATES.jsonl"
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            node = row.get("decision_node") or {}
            episode_id = node.get("episode_id")
            if episode_id:
                ids.add(str(episode_id))
    _cache[n_dir] = ids
    return ids


def freeze_or_verify_protocol(state: dict) -> None:
    protocol = m5b.create_or_verify_protocol_v2(STUDY_ROOT)
    if state["mode"] == "pilot":
        if sorted(int(y) for y in state["years"]) != sorted(
                int(y) for y in protocol["pilot"]["years"]):
            raise TypedStop(
                "BLOCKED_PROTOCOL_SCOPE",
                f"years={state['years']} vs protocol={protocol['pilot']['years']}")
        if [int(n) for n in state["n_grid"]] != [int(n) for n in protocol["n_grid"]]:
            raise TypedStop("BLOCKED_PROTOCOL_SCOPE", "n grid mismatch")
        if (int(state["bootstrap"]) != PROTOCOL_BOOTSTRAP_REPLICATES
                or int(state["bootstrap_seed"]) != PROTOCOL_BOOTSTRAP_SEED):
            raise TypedStop("BLOCKED_PROTOCOL_SCOPE", "bootstrap contract mismatch")
    state["protocol_hash"] = protocol["protocol_hash"]
    append_log(state="PROTOCOL_GATE", event="complete", status="OK",
               command=[], return_code=0, output_paths=[m5b.V2_PROTOCOL_NAME],
               input_hashes={}, timestamp=now_iso())


def run_determinism_sentinel(state: dict) -> None:
    outputs = [SENTINEL_JSON]
    if state_complete(state, "DETERMINISM_SENTINEL", outputs):
        log("DETERMINISM_SENTINEL: reused")
    else:
        battery_command(state, "sentinel", "--phase", "sentinel",
                        "--years", "2019")
        state["state_outputs"]["DETERMINISM_SENTINEL"] = str(SENTINEL_JSON)
        state["model_retrained"] = True
    sentinel = json.loads(SENTINEL_JSON.read_text(encoding="utf-8"))
    state["sentinel_status"] = sentinel.get("status")
    state["nondeterminism_detected"] = any(
        verdict.get("nondeterminism_detected")
        for verdict in sentinel.get("verdicts", {}).values())


def reuse_or_build_year_references(state: dict) -> None:
    for year in state["years"]:
        if not m5b.m2_bundle_present(year):
            log(f"M2 bundle {year} missing; running build_year_references")
            run_command(state, f"build_year_references_{year}",
                        ["data2/scripts/build_year_references.py",
                         "--years", str(year)])
        else:
            log(f"M2 bundle {year} present; verify-only (no rebuild)")
        m5b.load_year_m2_bundle(year)
    battery_command(state, "headroom", "--phase", "headroom",
                    "--years", *[str(y) for y in state["years"]])
    for year in state["years"]:
        summary_path = STUDY_ROOT / str(year) / "M2_TRAIN_HEADROOM_SUMMARY.json"
        if not summary_path.is_file():
            raise TypedStop("BLOCKED_M2_REFERENCE",
                            f"headroom summary missing: {summary_path}")
        state["state_outputs"].setdefault("M2_REFERENCE_GATE", {})[str(year)] = str(summary_path)


def run_ladder_probe(state: dict) -> None:
    outputs = [STUDY_ROOT / f"LADDER_PROBE_{year}.json" for year in state["years"]]
    if state_complete(state, "LADDER_PROBE", outputs):
        log("LADDER_PROBE: reused")
        return
    battery_command(state, "ladder", "--phase", "ladder",
                    "--years", *[str(y) for y in state["years"]])
    state["state_outputs"]["LADDER_PROBE"] = [str(path) for path in outputs]


def run_determinism_floor_quantification(state: dict) -> None:
    if state_complete(state, "DETERMINISM_FLOOR_QUANTIFICATION", [FLOOR_JSON]):
        log("DETERMINISM_FLOOR_QUANTIFICATION: reused")
    else:
        # floor scope = the protocol's sentinel settings (2019 only)
        sentinel = json.loads(SENTINEL_JSON.read_text(encoding="utf-8"))
        sentinel_years = sorted({key.split("_")[0]
                                 for key in sentinel.get("verdicts", {})})
        if not sentinel_years:
            raise TypedStop("BLOCK_M5B_SENTINEL_MISSING", str(SENTINEL_JSON))
        battery_command(state, "floor", "--phase", "floor",
                        "--years", *sentinel_years)
        state["state_outputs"]["DETERMINISM_FLOOR_QUANTIFICATION"] = str(FLOOR_JSON)
        state["model_retrained"] = True
    payload = json.loads(FLOOR_JSON.read_text(encoding="utf-8"))
    decision = payload.get("decision", {})
    if decision.get("decision") == "BLOCK_M5B_NONDETERMINISM":
        raise TypedStop("BLOCK_M5B_NONDETERMINISM",
                        f"blocked_metrics={decision.get('blocked_metrics')}")


def run_eval_smoke_gate(state: dict) -> None:
    if state_complete(state, "EVAL_SMOKE_GATE", [SMOKE_JSON]):
        log("EVAL_SMOKE_GATE: reused")
        return
    battery_command(state, "smoke", "--phase", "smoke", "--years",
                    *[str(y) for y in state["years"]])
    payload = json.loads(SMOKE_JSON.read_text(encoding="utf-8"))
    if payload.get("status") != "PASS":
        raise TypedStop("FAIL_EVAL_SMOKE", str(payload.get("failures"))[:400])
    state["state_outputs"]["EVAL_SMOKE_GATE"] = str(SMOKE_JSON)


def run_fit_size_stability(state: dict) -> None:
    missing = []
    for year in state["years"]:
        for n in state["n_grid"]:
            checkpoint = STUDY_ROOT / str(year) / f"N{n}" / "M1_N.pt"
            record = STUDY_ROOT / str(year) / f"N{n}" / "M1_N_HASHES.json"
            if not (checkpoint.is_file() and record.is_file()):
                missing.append(f"{year}/N{n}")
    if not missing:
        log("FIT_SIZE_STABILITY: reused (all checkpoints cached)")
        state["state_outputs"]["FIT_SIZE_STABILITY"] = str(STUDY_ROOT / str(state["years"][0]) / f"N{state['n_grid'][0]}" / "M1_N_HASHES.json")
        state["model_retrained"] = True
        return
    battery_command(state, "fit", "--phase", "fit",
                    "--years", *[str(y) for y in state["years"]],
                    "--n", *[str(n) for n in state["n_grid"]])
    state["state_outputs"]["FIT_SIZE_STABILITY"] = str(STUDY_ROOT / str(state["years"][0]) / f"N{state['n_grid'][0]}" / "M1_N_HASHES.json")
    state["model_retrained"] = True


def run_eval_size_stability(state: dict) -> None:
    if state_complete(state, "EVAL_SIZE_STABILITY", [EVAL_SUMMARY]):
        log("EVAL_SIZE_STABILITY: reused")
    else:
        battery_command(state, "eval", "--phase", "eval",
                        "--years", *[str(y) for y in state["years"]],
                        "--n", *[str(n) for n in state["n_grid"]],
                        "--reuse-fit-comparison")
        state["state_outputs"]["EVAL_SIZE_STABILITY"] = str(EVAL_SUMMARY)
        state["consequence_side_executed"] = True
        state["model_recalibrated"] = True


def apply_stability_decision_tree(state: dict) -> str:
    payload = json.loads(EVAL_SUMMARY.read_text(encoding="utf-8"))
    decision = payload.get("decision", {})
    status = decision.get("status", "FAIL_EVAL_SIZE_STABILITY")
    state["decision"] = decision
    return status


# --------------------------------------------------------------------------- #
# audit-mode helpers
# --------------------------------------------------------------------------- #

def run_or_reuse_pre_metrics(state: dict) -> None:
    missing = [str(year) for year in state["years"]
               if not (STUDY_ROOT / str(year) / "COHORT_SIZE_STABILITY_PRE.json").is_file()]
    if missing:
        run_command(state, "pre_metrics",
                    ["data2/scripts/cohort_size_metrics.py",
                     "--years", *[str(y) for y in state["years"]]])
    else:
        log("PRE_METRICS: reused existing PRE-observable reports")


def audit_consequence_interfaces_without_execution(state: dict) -> None:
    interfaces = {
        "M1_train": str(BATTERY), "M1_calibration": str(BATTERY),
        "M2_reference_builder": str(BUILDER),
        "Stage_I": "model/M3/stage1.py",
        "Stage_II": "model/M3/stage2.py (enumerate_recovery_decision)",
        "M4_loss": "model/M4/evaluation.py",
        "battery_eval_implemented": True,
        "m2_bundles_present": {str(y): m5b.m2_bundle_present(y)
                               for y in state["years"]},
    }
    state["consequence_interfaces"] = interfaces
    append_log(state="CONSEQUENCE_INTERFACE_AUDIT", event="complete",
               status="OK", command=[], return_code=0, output_paths=[],
               input_hashes={}, timestamp=now_iso())


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #

def build_report(state: dict, final_status: str) -> None:
    executed = "\n".join(
        f"| {record['label']} | `{' '.join(record['command'][2:])}` | "
        f"{record['return_code']} | {record['seconds']}s |"
        for record in state.get("commands", [])) or "| - | - | - | - |"
    not_executed = [
        "cohort_size_study.py --collect/--materialize (PRE reuse contract)",
        "exp/jatm_section5/run_development.py (Section-5 driver out of contract)",
        "Section-4 rerun", "Final-Test evaluation (Oct-Dec, forbidden)",
        "8192 rescan (needs human confirmation)",
    ]
    lines = [
        "# M5-b Pilot Autonomous Run Report",
        "",
        f"- final status: **{final_status}**",
        f"- run_id: {state.get('run_id')}",
        f"- mode: {state.get('mode')}  years: {state.get('years')}  "
        f"n_grid: {state.get('n_grid')}",
        f"- git: {state.get('git_branch')} @ {state.get('git_head')}",
        f"- protocol hash: {state.get('protocol_hash')}",
        f"- input manifest: {state.get('input_manifest_hash')}",
        f"- model_retrained: {state.get('model_retrained')}  "
        f"model_recalibrated: {state.get('model_recalibrated')}",
        f"- consequence_side_executed: {state.get('consequence_side_executed')}",
        f"- final_test_access_count: 0",
        "",
        "## COMMANDS_EXECUTED",
        "",
        "| label | command | rc | seconds |",
        "|---|---|---|---|",
        executed,
        "",
        "## COMMANDS_NOT_EXECUTED_BY_CONTRACT",
        "",
        *[f"- {item}" for item in not_executed],
        "",
    ]
    sentinel = state.get("sentinel_status")
    if sentinel:
        lines += [f"## Determinism sentinel", "",
                  f"- digest detection status: **{sentinel}** "
                  f"(decision deferred to the frozen floor rule)", ""]
    if FLOOR_JSON.is_file():
        floor = json.loads(FLOOR_JSON.read_text(encoding="utf-8"))
        decision = floor.get("decision", {})
        lines += ["## Nondeterminism floor (per-metric vs protocol threshold)", "",
                  f"- decision: **{decision.get('decision')}**",
                  f"- quantified sentinel settings: "
                  f"{floor.get('sentinel_settings_quantified')}",
                  f"- years not quantified (no protocol setting): "
                  f"{decision.get('years_not_quantified_no_protocol_setting')}",
                  "",
                  "| metric instance | floor (max over settings) | band | band half-width | "
                  "threshold (0.1 x half-width) | setting | verdict |",
                  "|---|---|---|---|---|---|---|",
                  ]
        for name, record in sorted(decision.get("floors", {}).items()):
            lines.append(
                f"| {name} | {record.get('floor'):.6g} | {record.get('band')} | "
                f"{record.get('band_half_width'):.6g} | "
                f"{record.get('threshold'):.6g} | {record.get('setting')} | "
                f"{'BLOCK' if record.get('same_order_as_band') else 'within floor'} |")
        lines += ["", f"- blocked metrics: {decision.get('blocked_metrics')}", ""]
    if EVAL_SUMMARY.is_file():
        summary = json.loads(EVAL_SUMMARY.read_text(encoding="utf-8"))
        lines += ["## Stability decision", "",
                  f"```json",
                  json.dumps(summary.get("decision"), indent=2),
                  "```", ""]
        for year, year_summary in summary.get("years", {}).items():
            lines += [f"### {year}", ""]
            for stage in ("fit", "eval"):
                lines += [f"- {stage}: `{json.dumps(year_summary.get(stage))}`"]
            lines.append("")
    lines += [
        "## Next human decision",
        "",
        next_action_for(state, final_status),
        "",
    ]
    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")


def next_action_for(state: dict, final_status: str) -> str:
    if final_status == "M5B_PILOT_COMPLETE_HARD_STOP":
        return ("Pilot scope completed. Human decisions pending: review "
                "stability table; decide whether to extend the battery to "
                "2017/2018/2021/2022 or to freeze a cohort-size contract "
                "(COMMON_N_STAR) — both require explicit authorization.")
    if final_status == "BLOCK_M5B_NONDETERMINISM":
        return ("Training nondeterminism floor reached band order. Decide: "
                "authorize battery-side determinism controls (single-thread "
                "torch / deterministic algorithms), then quarantine sentinel "
                "passes and rerun the floor state.")
    if final_status == "N_GRID_UPPER_BOUND_REACHED":
        return ("2048-vs-4096 failed a binding metric (or the ladder capped "
                "the grid). Decide whether to authorize 8192 (human "
                "confirmation required by the protocol).")
    return f"Address typed status {final_status}; see AUTORUN.log and state file."


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", required=True, choices=["audit", "pilot"])
    parser.add_argument("--years", type=int, nargs="*", default=list(PILOT_YEARS))
    parser.add_argument("--n", type=int, nargs="*", default=list(N_GRID))
    parser.add_argument("--bootstrap", type=int,
                        default=PROTOCOL_BOOTSTRAP_REPLICATES)
    parser.add_argument("--bootstrap-seed", type=int,
                        default=PROTOCOL_BOOTSTRAP_SEED)
    parser.add_argument("--recover-stale-lock", action="store_true")
    args = parser.parse_args()
    if args.mode == "pilot" and sorted(args.years) != list(PILOT_YEARS):
        # pilot scope is frozen to 2019/2020; no silent expansion to other years
        print("BLOCKED_PROTOCOL_SCOPE")
        return 3
    if args.recover_stale_lock and LOCK_FILE.is_file():
        LOCK_FILE.rename(LOCK_FILE.with_suffix(
            f".stale.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"))
    try:
        acquire_single_run_lock()
    except TypedStop as stop:
        log(f"{stop.status}: {stop.detail}")
        append_log(state="INIT", event="lock", status=stop.status, command=[],
                   return_code=3, output_paths=[], input_hashes={},
                   timestamp=now_iso())
        print(stop.status)
        return 3
    try:
        return _run(args)
    except TypedStop as stop:
        log(f"{stop.status}: {stop.detail}")
        _finish(None, stop.status, stop.detail, args)
        print(stop.status)
        return 3
    except m5b.M5BBlockedError as error:
        log(f"{error.status}: {error}")
        _finish(None, error.status, str(error), args)
        print(error.status)
        return 3
    except Exception as error:  # unexpected -> typed failure, never silent
        log(f"FAIL_AUTORUN_UNEXPECTED: {error!r}")
        _finish(None, "FAIL_AUTORUN_UNEXPECTED", repr(error), args)
        print("FAIL_AUTORUN_UNEXPECTED")
        return 3
    finally:
        release_single_run_lock()


def _run(args: argparse.Namespace) -> int:
    state = load_or_initialize_state(args.mode, args)
    verify_completed_state_outputs(state)
    state["status"] = "RUNNING"
    state["failed_state"] = None
    # a stale detail/next_action from an earlier failed run must never be
    # displayed as the CURRENT error; history stays in AUTORUN.log only
    state.pop("status_detail", None)
    state["next_action"] = None
    state["heartbeat_at"] = now_iso()
    state["stage_index"] = 0
    write_state(state)
    states = AUDIT_STATES if args.mode == "audit" else PILOT_STATES
    completed = set(state.get("completed_states", []))
    for name in states:
        if name in completed or name == "HARD_STOP":
            continue
        state["current_state"] = name
        state["stage_index"] = states.index(name) + 1
        state["stage_total"] = len(states)
        state["stage_started_at"] = now_iso()
        state["heartbeat_at"] = now_iso()
        freeze_stage_code(name, state)
        write_state(state)
        log(f"STATE {name}")
        try:
            if name == "PREFLIGHT":
                run_preflight(state, args)
            elif name == "REUSE_ARTIFACT_AUDIT":
                audit_pre_materialization(state)
            elif name == "PROTOCOL_GATE":
                freeze_or_verify_protocol(state)
            elif name == "DETERMINISM_SENTINEL":
                run_determinism_sentinel(state)
            elif name == "M2_REFERENCE_GATE":
                reuse_or_build_year_references(state)
            elif name == "LADDER_PROBE":
                run_ladder_probe(state)
            elif name == "DETERMINISM_FLOOR_QUANTIFICATION":
                run_determinism_floor_quantification(state)
            elif name == "EVAL_SMOKE_GATE":
                run_eval_smoke_gate(state)
            elif name == "FIT_SIZE_STABILITY":
                run_fit_size_stability(state)
            elif name == "EVAL_SIZE_STABILITY":
                run_eval_size_stability(state)
            elif name == "PILOT_REPORT":
                pass  # report is written at finish
            elif name == "PRE_METRICS":
                run_or_reuse_pre_metrics(state)
            elif name == "CONSEQUENCE_INTERFACE_AUDIT":
                audit_consequence_interfaces_without_execution(state)
        except m5b.M5BBlockedError as error:
            _finish(state, error.status, str(error), args)
            print(error.status)
            return 3
        verify_stage_code_frozen(name, state)
        completed.add(name)
        state["completed_states"] = sorted(completed)
        write_state(state)
        _record_gate_provenance(name)
    if args.mode == "audit":
        final_status = "PRE_STATE_MATERIALIZATION_COMPLETE_CONSEQUENCE_SIDE_PENDING"
    else:
        final_status = apply_stability_decision_tree(state)
        if is_blocking(final_status):
            _finish(state, final_status, str(state.get("decision")), args)
            print(final_status)
            return 3
    state["current_state"] = "HARD_STOP"
    state["completed_states"] = sorted(set(state["completed_states"]) | {
        "PILOT_REPORT", "HARD_STOP"})
    write_state(state)
    _finish(state, final_status, "", args)
    print(final_status)
    return 0


def freeze_stage_code(name: str, state: dict) -> None:
    """Freeze the code/dependency hashes at stage start (user rule: no code
    edits to a stage once it has started)."""

    state["stage_code_freeze"] = {
        "stage": name, "frozen_at": now_iso(),
        "source_script_hashes": m5b.source_script_hashes(),
        "protocol_hash": state.get("protocol_hash"),
        "conductor_hashes": {
            "run_m5b_autonomous.py": file_hash(Path(__file__).resolve()),
        },
    }


def verify_stage_code_frozen(name: str, state: dict) -> None:
    """Stage-completion gate: every frozen hash must be unchanged."""

    frozen = state.get("stage_code_freeze") or {}
    if frozen.get("stage") != name:
        return
    current = m5b.source_script_hashes()
    drift = [key for key, value in frozen.get("source_script_hashes", {}).items()
             if current.get(key) != value]
    conductor = frozen.get("conductor_hashes", {}).get("run_m5b_autonomous.py")
    conductor_now = file_hash(Path(__file__).resolve())
    if conductor is not None and conductor != conductor_now:
        drift.append("run_m5b_autonomous.py")
    if drift:
        raise TypedStop(
            "BLOCKED_CODE_FROZEN_VIOLATION",
            f"stage {name}: code changed while the stage ran: {sorted(drift)}")


def _record_gate_provenance(name: str) -> None:
    """Append the gate's provenance record (code/protocol/hashes/state)."""

    try:
        subprocess.run(
            [sys.executable, "data2/scripts/record_gate_provenance.py", name],
            cwd=str(REPO), capture_output=True, text=True, timeout=900,
            check=False)
    except Exception as error:  # recording must never break the pipeline
        log(f"WARN gate provenance recording failed for {name}: {error!r}")


def _finish(state: dict | None, status: str, detail: str,
            args: argparse.Namespace) -> None:
    if state is None:
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            state = {"run_id": "unknown", "mode": args.mode}
    state["status"] = status
    state["failed_state"] = state.get("current_state") if is_blocking(status) else None
    state["next_action"] = next_action_for(state, status)
    state.pop("current_subprocess", None)
    state["heartbeat_at"] = now_iso()
    if detail:
        state["status_detail"] = detail[:2000]
    else:
        state.pop("status_detail", None)
    write_state(state)
    build_report(state, status)
    append_log(state=state.get("current_state"), event="finish", status=status,
               command=[], return_code=(0 if status in SUCCESS_STATUSES else 3),
               output_paths=[str(REPORT_FILE)], input_hashes={},
               timestamp=now_iso())


if __name__ == "__main__":
    sys.exit(main())
