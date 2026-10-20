"""Run the approved six-year S34 E4 chain with isolated yearly outputs.

For a Q4 extension, this wrapper runs evaluation only and requires the frozen
E4 artifacts explicitly. It never refits or rebuilds prior stages.
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


def _completed_q4_model_evaluations(
    *, output_root: Path, year: int, n_grid: tuple[int, ...],
) -> dict[str, int]:
    """Count only completed, test-labelled per-model evaluation receipts."""

    completed: dict[str, int] = {}
    for n in n_grid:
        receipt_path = (
            output_root / str(year) / "passes" / f"fitN{n}" / "PASS_MANIFEST.json"
        )
        if not receipt_path.is_file():
            continue
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"E4_Q4_PASS_RECEIPT_UNREADABLE:{year}:N{n}"
            ) from error
        if (receipt.get("status") != "PASS"
                or receipt.get("split") != "test"
                or receipt.get("pass_id") != f"{year}_test_fitN{n}"
                or int(receipt.get("year", -1)) != year):
            raise RuntimeError(f"E4_Q4_PASS_RECEIPT_INVALID:{year}:N{n}")
        access_count = int(receipt.get("final_test_access_count", 0))
        case_count = int(receipt.get("case_count", 0))
        if access_count != 4096 or case_count != 4096:
            raise RuntimeError(
                f"E4_Q4_PASS_COHORT_COUNT_INVALID:{year}:N{n}:"
                f"access={access_count}:cases={case_count}"
            )
        completed[str(n)] = access_count
    return completed


def _run_phase(
    *,
    repo: Path,
    phase: str,
    year: int,
    output_root: Path,
    bundle_root: Path,
    n_grid: tuple[int, ...],
    q4_cohort_root: Path | None = None,
    frozen_e4_root: Path | None = None,
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
        "--scope-tag",
        f"YEAR_{year}",
        "--bundle-base",
        str(bundle_root),
    ]
    if phase in {"fit", "eval"}:
        command.extend(["--n", *[str(value) for value in n_grid]])
    if phase == "eval":
        command.append("--reuse-fit-comparison")
        if q4_cohort_root is not None:
            command.extend(["--q4-cohort-root", str(q4_cohort_root)])
            command.extend(["--frozen-e4-root", str(frozen_e4_root)])
    log_path = output_root / f"YEAR_{year}" / f"{phase}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        completed = subprocess.run(command, cwd=repo, stdout=handle, stderr=subprocess.STDOUT)
    if completed.returncode != 0:
        raise RuntimeError(f"E4_PHASE_FAILED:{year}:{phase}:{completed.returncode}")


def run(*, repo: Path, output_root: Path, bundle_root: Path,
        years: tuple[int, ...], n_grid: tuple[int, ...],
        q4_cohort_root: Path | None = None,
        frozen_e4_root: Path | None = None) -> dict:
    output_root = output_root.resolve()
    bundle_root = bundle_root.resolve()
    if q4_cohort_root is not None:
        q4_cohort_root = q4_cohort_root.resolve()
        if any(not (q4_cohort_root / str(year) / "cohort" / "Q4_COHORT_MANIFEST.json").is_file()
               for year in years):
            raise RuntimeError("E4_Q4_COHORT_MANIFEST_MISSING")
        if frozen_e4_root is None:
            raise RuntimeError("E4_Q4_FROZEN_E4_ROOT_REQUIRED")
        frozen_e4_root = frozen_e4_root.resolve()
        q4_cohort_hashes = {}
        for year in years:
            cohort_manifest_path = q4_cohort_root / str(year) / "cohort" / "Q4_COHORT_MANIFEST.json"
            q4_cohort_hashes[str(year)] = json.loads(cohort_manifest_path.read_text("utf-8")).get("selected_ids_sha256")
            year_root = frozen_e4_root / str(year)
            ladder = year_root / f"LADDER_PROBE_{year}.json"
            if not ladder.is_file():
                raise RuntimeError(f"E4_Q4_FROZEN_LADDER_MISSING:{year}")
            for n in n_grid:
                checkpoint = year_root / str(year) / f"N{n}" / "M1_N.pt"
                hashes = checkpoint.parent / "M1_N_HASHES.json"
                if not checkpoint.is_file() or not hashes.is_file():
                    raise RuntimeError(f"E4_Q4_FROZEN_MODEL_MISSING:{year}:N{n}")
                record = json.loads(hashes.read_text(encoding="utf-8"))
                from data2.scripts.consequence_stability_battery import _file_hash
                if record.get("checkpoint_hash") != _file_hash(checkpoint):
                    raise RuntimeError(f"E4_Q4_FROZEN_MODEL_HASH_MISMATCH:{year}:N{n}")
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
            and previous.get("q4_cohort_root") == (None if q4_cohort_root is None else str(q4_cohort_root))
            and previous.get("frozen_e4_root") == (None if frozen_e4_root is None else str(frozen_e4_root))
            and tuple(previous.get("n_grid", ())) == n_grid
            and previous.get("status") not in {"DEVELOPMENT_COMPLETE", "TEST_COMPLETE"}
        )
        completed = [phase for phase in (previous.get("completed_phases") or []) if phase in {"headroom", "fit", "ladder", "eval"}] if resumable else []
        state = {
            "schema_version": "JATM_S34_E4_YEAR_STATE_V1",
            "year": year,
            "status": "RUNNING",
            "updated_at": _now(),
            "bundle_root": str(bundle_root),
            "q4_cohort_root": None if q4_cohort_root is None else str(q4_cohort_root),
            "frozen_e4_root": None if frozen_e4_root is None else str(frozen_e4_root),
            "q4_cohort_hash": (None if q4_cohort_root is None
                               else q4_cohort_hashes[str(year)]),
            "split": "development" if q4_cohort_root is None else "test",
            "n_grid": list(n_grid),
            "resumed_from_checkpoint": bool(completed),
            "completed_phases": completed,
        }
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        phases = ["eval"] if q4_cohort_root is not None else ["headroom", "fit", "ladder", "eval"]
        try:
            for phase in phases:
                if phase in completed:
                    continue
                _run_phase(repo=repo, phase=phase, year=year, output_root=output_root,
                           bundle_root=bundle_root, n_grid=n_grid,
                           q4_cohort_root=q4_cohort_root,
                           frozen_e4_root=frozen_e4_root)
                if q4_cohort_root is not None and phase == "eval":
                    observed = _completed_q4_model_evaluations(
                        output_root=output_root, year=year, n_grid=n_grid,
                    )
                    if len(observed) != len(n_grid):
                        raise RuntimeError(
                            f"E4_Q4_EVALUATION_GRID_INCOMPLETE:{year}:"
                            f"{sorted(int(value) for value in observed)}"
                        )
                completed.append(phase)
                state.update({"completed_phases": completed, "updated_at": _now()})
                state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            eval_summary_path = output_root / f"YEAR_{year}" / "EVAL_SUMMARY.json"
            eval_decision = None
            if eval_summary_path.is_file():
                try:
                    eval_decision = (json.loads(eval_summary_path.read_text(encoding="utf-8")).get("decision") or {}).get("status")
                except (OSError, json.JSONDecodeError):
                    eval_decision = "UNREADABLE_EVAL_SUMMARY"
            if eval_decision == "M5B_PILOT_COMPLETE_HARD_STOP":
                state.update({
                    "status": "ENGINEERING_INCOMPLETE",
                    "completion_class": "PILOT_COMPLETE_HARD_STOP",
                    "eval_decision": eval_decision,
                    "updated_at": _now(),
                })
            else:
                state.update({"status": "DEVELOPMENT_COMPLETE" if q4_cohort_root is None else "TEST_COMPLETE",
                              "eval_decision": eval_decision, "updated_at": _now()})
            if eval_summary_path.is_file():
                try:
                    summary_payload = json.loads(eval_summary_path.read_text(encoding="utf-8"))
                    year_summary = (summary_payload.get("years") or {}).get(str(year), {})
                    observed = sorted(int(value) for value in (year_summary.get("eval") or {}).keys())
                    state["n_grid_coverage"] = {
                        "requested": list(n_grid),
                        "observed_eval": observed,
                        "evaluation_E": year_summary.get("evaluation_E"),
                        "full_default_grid_observed": observed == list(N_GRID),
                        "interpretation": "N128_PILOT_ONLY" if observed == [128] else "PARTIAL_OR_FULL_GRID",
                    }
                    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                except (OSError, json.JSONDecodeError):
                    state["n_grid_coverage"] = {"status": "UNREADABLE_EVAL_SUMMARY"}
        except Exception as error:  # keep yearly checkpoint and continue next year
            state.update({"status": "ENGINEERING_INCOMPLETE", "error": f"{type(error).__name__}: {error}", "updated_at": _now()})
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        records.append(state)
    manifest = {
        "schema_version": "JATM_S34_E4_DEVELOPMENT_V1" if q4_cohort_root is None else "JATM_S34_E4_TEST_V1",
        "status": ("DEVELOPMENT_COMPLETE" if q4_cohort_root is None else "TEST_COMPLETE")
            if all(item["status"] == ("DEVELOPMENT_COMPLETE" if q4_cohort_root is None else "TEST_COMPLETE") for item in records)
            else "ENGINEERING_INCOMPLETE",
        "years": records,
        "split": "development" if q4_cohort_root is None else "test",
        "year_local_rule": "Train Jan-Jun; Calibration Jul; Development Aug-Sep; Test Oct-Dec",
        "completed_test_model_evaluations": ({ } if q4_cohort_root is None else {
            str(year): _completed_q4_model_evaluations(
                output_root=output_root, year=year, n_grid=n_grid,
            ) for year in years
        }),
        "test_access_count": (0 if q4_cohort_root is None else sum(
            sum(_completed_q4_model_evaluations(
                output_root=output_root, year=year, n_grid=n_grid,
            ).values()) for year in years
        )),
        "test_access_count_unit": ("none" if q4_cohort_root is None
                                   else "selected_q4_episode_model_evaluations"),
        "n_grid": list(n_grid),
        "q4_cohort_hashes": ({} if q4_cohort_root is None else q4_cohort_hashes),
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
    parser.add_argument("--q4-cohort-root", type=Path, default=None)
    parser.add_argument("--frozen-e4-root", type=Path, default=None)
    args = parser.parse_args()
    payload = run(
        repo=args.repo_root.resolve(),
        output_root=args.output_root,
        bundle_root=args.bundle_root,
        years=tuple(args.years),
        n_grid=tuple(args.n),
        q4_cohort_root=args.q4_cohort_root,
        frozen_e4_root=args.frozen_e4_root,
    )
    print(json.dumps({"status": payload["status"], "years": len(payload["years"])}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
