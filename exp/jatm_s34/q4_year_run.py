"""Run one year of the frozen six-year Q4 extension across E1-E4."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import traceback

from .e4_run import N_GRID, run as run_e4
from .e1_information_gain import run_bounded_annual as run_e1
from .e2_e3_exact import run_bounded_annual as run_e2_e3
from .q4_bridge import iter_q4_bridges, load_frozen_q4_cohort
from .q4_cohort import select_q4_cohort
from model.common.identity import content_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _valid_summary(path: Path, *, year: int, split: str,
                   cohort_hash: str, section: str) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        recorded = payload.pop("artifact_hash")
        if content_id(payload) != recorded:
            return None
        if payload.get("year") != year or payload.get("split") != split:
            return None
        observed_cohort = (payload.get("evaluation_cohort_hash") if section == "E1"
                           else (payload.get("input_contract") or {}).get("evaluation_cohort_hash"))
        if observed_cohort != cohort_hash:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def run_year(*, repo: Path, results_root: Path, frozen_e4_root: Path,
             bundle_root: Path, year: int, n_grid: tuple[int, ...] = N_GRID,
             bootstrap_replicates: int = 2000) -> dict:
    repo = Path(repo).resolve()
    results_root = Path(results_root).resolve()
    cohort_dir = results_root / "cohorts" / str(year) / "cohort"
    year_root = results_root / str(year)
    manifest_path = year_root / "Q4_YEAR_MANIFEST.json"
    year_root.mkdir(parents=True, exist_ok=True)
    previous = {}
    if manifest_path.is_file():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    manifest = {
        "schema_version": "JATM_S34_Q4_YEAR_RUN_V1",
        "year": int(year), "split": "test", "status": "RUNNING",
        "updated_at": _now(), "n": 4096, "n_grid": list(n_grid),
        # Rebuild completion state from hash-validated artifacts on every
        # resume. Prior orchestrator manifests may have marked a failed E4 as
        # complete, so their stage list is not authoritative.
        "completed_stages": [],
        "final_test_access_count": 0,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _mark(stage: str) -> None:
        manifest["current_stage"] = stage
        manifest["updated_at"] = _now()
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"year": int(year), "stage": stage, "utc": _now()},
                         separators=(",", ":")), flush=True)
    try:
        if (cohort_dir / "Q4_COHORT_MANIFEST.json").is_file():
            _ranked, cohort = load_frozen_q4_cohort(cohort_dir, year=year)
            for relative, expected_hash in cohort["source_hashes"].items():
                source_path = repo / relative
                if not source_path.is_file() or _sha256(source_path) != expected_hash:
                    raise RuntimeError(f"Q4_FROZEN_SOURCE_HASH_MISMATCH:{relative}")
        else:
            cohort = select_q4_cohort(
                root=repo, year=year, output_dir=cohort_dir, n=4096
            )
        cohort_hash = cohort["selected_ids_sha256"]
        manifest["cohort"] = {
            "selected_episode_count": cohort["selected_episode_count"],
            "eligible_episode_count": cohort["eligible_episode_count"],
            "selected_ids_sha256": cohort["selected_ids_sha256"],
            "source_hashes": cohort["source_hashes"],
            "q4_raw_rows_read": cohort["q4_raw_rows_read"],
            "september_context_rows_read": cohort["september_context_rows_read"],
        }
        manifest["final_test_access_ledger"] = {
            "raw_q4_ontime_source_rows_read": int(cohort["final_test_access_count"]),
            "selected_q4_episode_evaluations": {},
        }
        manifest["completed_stages"] = ["COHORT_FROZEN"]
        manifest["updated_at"] = _now()
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        def bridge_factory(**kwargs):
            return iter_q4_bridges(
                cohort_dir=cohort_dir,
                output_root=year_root / "bridge_materialization",
                **kwargs,
            )

        e1_path = year_root / "E1" / "E1_SUMMARY.json"
        e1 = _valid_summary(e1_path, year=year, split="test",
                            cohort_hash=cohort_hash, section="E1")
        if e1 is None:
            _mark("E1_RUNNING")
            e1 = run_e1(
            output_root=year_root / "E1",
            year=year,
            n=4096,
            bridge_factory=bridge_factory,
            evaluation_split="test",
            final_test_access_count=4096,
            bootstrap_replicates=bootstrap_replicates,
            evaluation_cohort_hash=cohort_hash,
            )
        if e1.get("status") != "TEST_COMPLETE":
            raise RuntimeError(f"Q4_E1_NOT_COMPLETE:{year}:{e1.get('status')}")
        manifest["E1"] = {"status": e1["status"], "artifact_hash": e1["artifact_hash"],
                           "node_count": e1["node_count"]}
        manifest["final_test_access_ledger"]["selected_q4_episode_evaluations"]["E1"] = 4096
        manifest["completed_stages"].append("E1")
        manifest["updated_at"] = _now()
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        _mark("E2_E3_RUNNING")
        e2_path = year_root / "E2_E3" / "E2_E3_SUMMARY.json"
        e2_e3 = _valid_summary(e2_path, year=year, split="test",
                               cohort_hash=cohort_hash, section="E2_E3")
        if e2_e3 is None:
            _mark("E2_E3_RUNNING")
            e2_e3 = run_e2_e3(
            output_root=year_root / "E2_E3",
            year=year,
            n=4096,
            bridge_factory=bridge_factory,
            evaluation_split="test",
            final_test_access_count=8192,
            bootstrap_replicates=bootstrap_replicates,
            evaluation_cohort_hash=cohort_hash,
            )
        if e2_e3.get("status") != "TEST_COMPLETE":
            raise RuntimeError(
                f"Q4_E2_E3_NOT_COMPLETE:{year}:{e2_e3.get('status')}"
            )
        manifest["E2_E3"] = {
            "status": e2_e3["status"],
            "artifact_hash": e2_e3["artifact_hash"],
            "node_count": e2_e3["node_count"],
            "first_pass_episode_accesses": 4096,
            "second_pass_episode_accesses": 4096,
        }
        manifest["final_test_access_ledger"]["selected_q4_episode_evaluations"]["E2_E3_first_pass"] = 4096
        manifest["final_test_access_ledger"]["selected_q4_episode_evaluations"]["E2_E3_second_pass"] = 4096
        manifest["completed_stages"].append("E2_E3")
        manifest["updated_at"] = _now()
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        e4_manifest_path = year_root / "E4" / "E4_DEVELOPMENT_MANIFEST.json"
        e4 = None
        try:
            saved_e4 = json.loads(e4_manifest_path.read_text(encoding="utf-8"))
            if (saved_e4.get("status") == "TEST_COMPLETE"
                    and saved_e4.get("q4_cohort_hashes", {}).get(str(year)) == cohort_hash):
                e4 = saved_e4
        except (OSError, json.JSONDecodeError):
            pass
        if e4 is None:
            _mark("E4_RUNNING")
            e4 = run_e4(
            repo=repo,
            output_root=year_root / "E4",
            bundle_root=bundle_root,
            years=(year,),
            n_grid=n_grid,
            q4_cohort_root=results_root / "cohorts",
            frozen_e4_root=frozen_e4_root,
            )
        manifest["E4"] = {
            "status": e4["status"],
            "manifest": str(year_root / "E4" / "E4_DEVELOPMENT_MANIFEST.json"),
            "access_count": int(e4.get("test_access_count", 0)),
            "access_count_unit": "selected_q4_episode_model_evaluations",
        }
        e4_access_count = int(e4.get("test_access_count", 0))
        if e4_access_count:
            manifest["final_test_access_ledger"]["selected_q4_episode_evaluations"]["E4"] = e4_access_count
        e4_cohort_hash = (e4.get("q4_cohort_hashes") or {}).get(str(year))
        expected_e4_access_count = 4096 * len(n_grid)
        if (e4.get("status") != "TEST_COMPLETE"
                or e4_access_count != expected_e4_access_count
                or e4_cohort_hash != cohort_hash):
            manifest["updated_at"] = _now()
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            raise RuntimeError(
                f"Q4_E4_NOT_COMPLETE:{year}:status={e4.get('status')}:"
                f"access={e4_access_count}/{expected_e4_access_count}:"
                f"cohort_hash_match={e4_cohort_hash == cohort_hash}"
            )
        manifest["final_test_access_count"] = sum(
            manifest["final_test_access_ledger"]["selected_q4_episode_evaluations"].values()
        )
        manifest["final_test_access_count_unit"] = "selected_q4_episode_evaluations"
        manifest["completed_stages"].append("E4")
        manifest["current_stage"] = "COMPLETE"
        manifest["status"] = "TEST_COMPLETE"
        manifest["updated_at"] = _now()
    except Exception as error:
        manifest["status"] = "ENGINEERING_INCOMPLETE"
        manifest["final_test_access_count"] = sum(
            (manifest.get("final_test_access_ledger") or {}).get(
                "selected_q4_episode_evaluations", {}
            ).values()
        )
        manifest["final_test_access_count_unit"] = "selected_q4_episode_evaluations"
        manifest["error"] = f"{type(error).__name__}: {error}"
        manifest["traceback"] = traceback.format_exc()
        manifest["updated_at"] = _now()
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--frozen-e4-root", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True, choices=range(2017, 2023))
    parser.add_argument("--n", type=int, nargs="+", default=list(N_GRID))
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    args = parser.parse_args()
    result = run_year(
        repo=args.repo_root,
        results_root=args.results_root,
        frozen_e4_root=args.frozen_e4_root,
        bundle_root=args.bundle_root,
        year=args.year,
        n_grid=tuple(args.n),
        bootstrap_replicates=args.bootstrap_replicates,
    )
    print(json.dumps({"year": args.year, "status": result["status"],
                      "completed_stages": result.get("completed_stages")}, separators=(",", ":")))
    return 0 if result["status"] == "TEST_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
