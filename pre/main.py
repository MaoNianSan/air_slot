from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from downstream_common import (
    parallel_metadata,
    resolve_parallel_plan,
    resolve_requested_n_jobs,
    task_seed_hash,
    thread_limit_environment,
)
from run_profiles import resolve_profile
from src.pipeline import (
    build_all,
    build_core,
    core_readiness_existing,
    core_report_existing,
    core_validate_existing,
    load_config,
    migrate_legacy_profile,
    readiness_existing,
    repair_contract,
    run_inventory,
    validate_existing,
)
from src.progress import VALID_PROGRESS_LEVELS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Air Slot PRE preprocessing pipeline")
    modes = ["fast", "diagnostic", "acceptance_23d", "adapt_full", "middle", "full"]
    parser.add_argument(
        "command",
        choices=[
            "inventory",
            "build",
            "validate",
            "readiness",
            "migrate-profile",
            "all",
            *modes,
            "report",
            "repair",
            "core-build",
            "core-validate",
            "core-readiness",
            "core-report",
        ],
    )
    parser.add_argument("mode_arg", nargs="?", choices=modes, default=None)
    parser.add_argument("--mode", choices=modes, default=None)
    parser.add_argument("--config", default=None, help="Optional YAML override merged onto config/default.yaml")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Isolated output directory; default mode output semantics are unchanged",
    )
    parser.add_argument("--rebuild-cache", action="store_true", help="Discard and rebuild reusable state/flow cache")
    parser.add_argument("--smoke-subset", action="store_true", default=False)
    parser.add_argument("--from-mode", choices=["adapt_full"], default="adapt_full")
    parser.add_argument("--n-jobs", type=int, default=None, help="Runtime CPU budget; default 1, -1 uses all but one logical CPU")
    parser.add_argument(
        "--progress",
        choices=sorted(VALID_PROGRESS_LEVELS),
        default=None,
        help="Terminal progress detail",
    )
    parser.add_argument(
        "--progress-level",
        choices=sorted(VALID_PROGRESS_LEVELS),
        default=None,
        help="Terminal progress detail; overrides runtime.progress_level in YAML",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    selected_mode = args.mode_arg or args.mode
    executable_modes = {"fast", "diagnostic", "acceptance_23d", "adapt_full", "middle", "full"}
    if args.command not in executable_modes and selected_mode is None:
        parser.error("an explicit mode is required for this command")
    requested_mode = args.command if args.command in executable_modes else selected_mode
    profile = resolve_profile(str(requested_mode), smoke_subset=args.smoke_subset)
    output_dir = args.output_dir
    if args.smoke_subset and output_dir is None:
        output_dir = ROOT / "output" / profile.output_id
    core_commands = {"core-build", "core-validate", "core-readiness", "core-report"}
    cfg = load_config(
        args.config,
        mode=profile.profile_id,
        output_dir=None if args.command in core_commands else output_dir,
    )
    cfg["profile_contract"] = {
        "requested_token": profile.requested_token,
        "profile_id": profile.profile_id,
        "run_profile": profile.run_profile,
        "acceptance_profile": profile.acceptance_profile,
        "compute_profile": profile.compute_profile,
        "legacy_token": profile.legacy_token,
        "smoke_subset": profile.smoke_subset,
        "output_id": profile.output_id,
    }
    if args.smoke_subset:
        cfg.setdefault("runtime", {})["adapt_manifest_path"] = "../data/manifests/middle_smoke_manifest.csv"
        cfg["runtime"]["smoke_subset"] = True
    requested_n_jobs = resolve_requested_n_jobs(
        args.n_jobs,
        cfg.get("runtime", {}).get("state_workers", 1),
    )
    plan = resolve_parallel_plan(requested_n_jobs, task_count=10_000, prefer_outer_parallelism=True)
    runtime_parallel = parallel_metadata(
        plan,
        task_seed_digest=task_seed_hash(20260726, "pre", profile.output_id, "state_partitions", ["CACHE_PARTITIONS"]),
    )
    cfg.setdefault("runtime", {}).update(runtime_parallel)
    cfg["runtime"]["state_workers"] = plan.outer_workers
    cfg["runtime"]["rebuild_cache"] = bool(args.rebuild_cache)
    requested_progress = args.progress if args.progress is not None else args.progress_level
    if requested_progress is not None:
        cfg["runtime"]["progress_level"] = requested_progress
    if args.command == "inventory":
        raw_inventory, coverage = run_inventory(cfg)
        print(json.dumps({
            "status": "PASS",
            "raw_files": len(raw_inventory),
            "state_vector_hours": len(coverage),
            "output_root": str(cfg["output_root"]),
        }, indent=2, default=str))
        return 0
    if args.command == "migrate-profile":
        result = migrate_legacy_profile(cfg, source_mode=args.from_mode)
        print(json.dumps(result, indent=2, default=str))
        return 0
    if args.command == "core-build":
        with thread_limit_environment(plan):
            result = build_core(cfg, output_override=output_dir)
        print(
            json.dumps(
                {
                    "status": result.validation["status"],
                    "publication_status": result.publication_status,
                    "output_root": str(result.output_root),
                    "core_data_hash": result.manifest["core_data_hash"],
                    "readiness": result.readiness,
                },
                indent=2,
                default=str,
            )
        )
        return 0
    if args.command == "core-validate":
        print(json.dumps(core_validate_existing(cfg, output_dir), indent=2, default=str))
        return 0
    if args.command == "core-readiness":
        print(json.dumps(core_readiness_existing(cfg, output_dir), indent=2, default=str))
        return 0
    if args.command == "core-report":
        print(core_report_existing(cfg, output_dir))
        return 0
    if args.command in {"build", "all", *executable_modes}:
        try:
            with thread_limit_environment(plan):
                result = build_all(cfg)
        except Exception as exc:
            output = Path(cfg["output_root"])
            output.mkdir(parents=True, exist_ok=True)
            failure = {
                "mode": profile.output_id,
                "status": "INCOMPLETE",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            (output / "run_state.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
            (output / "artifact_registry.json").write_text(
                json.dumps({**failure, "artifacts": []}, indent=2), encoding="utf-8"
            )
            raise
        print(json.dumps({
            "status": "PASS",
            "formal_eligible": result.manifest["formal_eligible"],
            "output_root": str(result.output_root),
            "validation": result.validation,
            "readiness": result.readiness,
        }, indent=2, default=str))
        return 0
    if args.command == "validate":
        print(json.dumps(validate_existing(cfg), indent=2, default=str))
        return 0
    if args.command == "repair":
        print(json.dumps(repair_contract(cfg), indent=2, default=str))
        return 0
    if args.command == "readiness":
        _, _, summary = readiness_existing(cfg)
        print(json.dumps(summary, indent=2, default=str))
        return 0
    if args.command == "report":
        summary = Path(cfg["output_root"]) / "run_summary.json"
        if not summary.exists():
            raise FileNotFoundError(f"missing frozen run summary: {summary}")
        print(summary.read_text(encoding="utf-8"))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
