"""Run the approved six-year Development chain with isolated yearly outputs.

The wrapper delegates M1/M2/M3/M4 computation to the existing consequence
stability battery.  It only supplies the versioned bundle root, yearly output
root, and checkpoint manifest; no Test path is accepted.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


YEARS = tuple(range(2017, 2023))
N_GRID = (128, 256, 512, 1024, 2048, 4096)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run_phase(
    *,
    repo: Path,
    phase: str,
    year: int,
    output_root: Path,
    bundle_root: Path,
    n_grid: tuple[int, ...],
) -> None:
    command = [
        sys.executable,
        "-u",
        "data2/scripts/consequence_stability_battery.py",
        "--phase",
        phase,
        "--years",
        str(year),
        "--output-root",
        str(output_root),
        "--bundle-base",
        str(bundle_root),
    ]
    if phase in {"fit", "eval"}:
        command.extend(["--n", *[str(value) for value in n_grid]])
    if phase == "eval":
        command.append("--reuse-fit-comparison")
    log_path = output_root / f"YEAR_{year}" / f"{phase}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        completed = subprocess.run(command, cwd=repo, stdout=handle, stderr=subprocess.STDOUT)
    if completed.returncode != 0:
        raise RuntimeError(f"E4_PHASE_FAILED:{year}:{phase}:{completed.returncode}")


def run(*, repo: Path, output_root: Path, bundle_root: Path, years: tuple[int, ...], n_grid: tuple[int, ...]) -> dict:
    output_root = output_root.resolve()
    bundle_root = bundle_root.resolve()
    if "final_test" in str(output_root).lower() or "final_test" in str(bundle_root).lower():
        raise RuntimeError("E4_FINAL_TEST_PATH_FORBIDDEN")
    output_root.mkdir(parents=True, exist_ok=True)
    records = []
    for year in years:
        year_out = output_root / f"YEAR_{year}"
        state_path = year_out / "E4_YEAR_STATE.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        previous = {}
        if state_path.is_file():
            try:
                previous = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                previous = {}
        resumable = (
            previous.get("bundle_root") == str(bundle_root)
            and tuple(previous.get("n_grid", ())) == n_grid
            and previous.get("status") != "DEVELOPMENT_COMPLETE"
        )
        completed = [phase for phase in (previous.get("completed_phases") or []) if phase in {"headroom", "fit", "ladder", "eval"}] if resumable else []
        state = {
            "schema_version": "JATM_S34_E4_YEAR_STATE_V1",
            "year": year,
            "status": "RUNNING",
            "updated_at": _now(),
            "bundle_root": str(bundle_root),
            "n_grid": list(n_grid),
            "resumed_from_checkpoint": bool(completed),
            "completed_phases": completed,
        }
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        phases = ["headroom", "fit", "ladder", "eval"]
        try:
            for phase in phases:
                if phase in completed:
                    continue
                _run_phase(repo=repo, phase=phase, year=year, output_root=output_root, bundle_root=bundle_root, n_grid=n_grid)
                completed.append(phase)
                state.update({"completed_phases": completed, "updated_at": _now()})
                state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            state.update({"status": "DEVELOPMENT_COMPLETE", "updated_at": _now()})
        except Exception as error:  # keep yearly checkpoint and continue next year
            state.update({"status": "ENGINEERING_INCOMPLETE", "error": f"{type(error).__name__}: {error}", "updated_at": _now()})
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        records.append(state)
    manifest = {
        "schema_version": "JATM_S34_E4_DEVELOPMENT_V1",
        "status": "DEVELOPMENT_COMPLETE" if all(item["status"] == "DEVELOPMENT_COMPLETE" for item in records) else "ENGINEERING_INCOMPLETE",
        "years": records,
        "year_local_rule": "Train Jan-Jun; Calibration Jul; Development Aug-Sep; Test Oct-Dec",
        "test_access_count": 0,
        "n_grid": list(n_grid),
        "updated_at": _now(),
    }
    (output_root / "E4_DEVELOPMENT_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--years", type=int, nargs="+", default=list(YEARS))
    parser.add_argument("--n", type=int, nargs="+", default=list(N_GRID))
    args = parser.parse_args()
    payload = run(
        repo=args.repo_root.resolve(),
        output_root=args.output_root,
        bundle_root=args.bundle_root,
        years=tuple(args.years),
        n_grid=tuple(args.n),
    )
    print(json.dumps({"status": payload["status"], "years": len(payload["years"])}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
