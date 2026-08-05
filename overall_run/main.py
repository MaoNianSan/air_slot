from __future__ import annotations

import argparse
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
from pre_contract_gate import DownstreamContractMismatch, require_m1_adapter
from src.config import load_config
from src.pipeline import (
    FullBlockedByFastAcceptance,
    mark_running_staging_incomplete,
    report_mode,
    run_experiment,
    run_precision,
    validate_mode,
)

def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Authoritative modular Air Slot M1-M4 pipeline")
    modes = ["fast", "diagnostic", "acceptance_23d", "adapt_full", "middle", "full", "precision"]
    command.add_argument("command", choices=[*modes, "validate", "report"])
    command.add_argument("mode", nargs="?", choices=modes, help=argparse.SUPPRESS)
    command.add_argument("--mode", choices=modes, default=None, dest="explicit_mode", help="Explicit mode for validate/report (preferred)")
    command.add_argument("--progress", choices=["quiet", "normal", "detail"], default="normal")
    command.add_argument("--config", type=Path, default=None, help="Optional final YAML override")
    command.add_argument("--pre-output", type=Path, default=None)
    command.add_argument(
        "--output-name",
        default=None,
        help="Isolated output directory name under overall_run/output",
    )
    command.add_argument("--override-fast-gate", action="store_true", default=False)
    command.add_argument("--smoke-subset", action="store_true", default=False)
    command.add_argument(
        "--resume-staging", "--resume", dest="resume_staging", type=Path, default=None,
        help="Resume from an explicit isolated failed staging directory",
    )
    command.add_argument("--n-jobs", type=int, default=None, help="Runtime CPU budget; default 1, -1 uses all but one logical CPU")
    return command


def main() -> int:
    args = parser().parse_args()
    try:
        require_m1_adapter()
    except DownstreamContractMismatch as exc:
        print(str(exc), file=sys.stderr)
        return 2
    executable_modes = {"fast", "diagnostic", "acceptance_23d", "adapt_full", "middle", "full", "precision"}
    # --mode flag takes precedence over positional mode for validate/report
    requested_mode = args.command if args.command in executable_modes else (args.explicit_mode or args.mode)
    mode = requested_mode
    if mode is None:
        parser().error(f"{args.command} requires --mode <mode>")
    cfg = None
    try:
        cfg = load_config(ROOT, mode=mode, override=args.config)
        if args.output_name:
            if cfg.mode_name != "fast":
                parser().error("--output-name is restricted to isolated fast development runs")
            cfg.profile_contract["output_id"] = str(args.output_name)
        if args.smoke_subset:
            if cfg.mode_name != "middle":
                parser().error("--smoke-subset is only valid for middle")
            cfg.profile_contract.update({"smoke_subset": True, "output_id": "middle_smoke"})
        requested_n_jobs = resolve_requested_n_jobs(args.n_jobs, cfg.compute.get("workers", 1))
        quantile_ids = [f"M1:Q{float(value):.3f}" for value in cfg.scientific["m1"]["quantiles"]]
        plan = resolve_parallel_plan(requested_n_jobs, len(quantile_ids), prefer_outer_parallelism=True)
        runtime_parallel = parallel_metadata(
            plan,
            task_seed_digest=task_seed_hash(
                int(cfg.compute.get("random_seed", 20260718)),
                "overall_run",
                requested_mode or mode,
                "m1_quantiles",
                quantile_ids,
            ),
        )
        cfg.merged.update(runtime_parallel)
        cfg.merged["workers"] = plan.inner_model_threads
        if args.command == "validate":
            result = validate_mode(cfg, cfg.profile_contract["output_id"], pre_output=args.pre_output, override_fast_gate=args.override_fast_gate)
        elif args.command == "report":
            result = report_mode(cfg, cfg.profile_contract["output_id"])
        elif args.command == "precision":
            with thread_limit_environment(plan):
                result_path = run_precision(cfg, args.progress, args.pre_output)
            result = json.loads((result_path / "run_summary.json").read_text(encoding="utf-8"))
        else:
            with thread_limit_environment(plan):
                result_path = run_experiment(
                    cfg,
                    cfg.mode_name,
                    args.progress,
                    args.pre_output or (
                        PROJECT / "pre" / "output" / cfg.profile_contract["output_id"]
                        if args.smoke_subset else None
                    ),
                    refit=True,
                    override_fast_gate=args.override_fast_gate,
                    output_name=cfg.profile_contract["output_id"],
                    resume_staging=args.resume_staging,
                )
            result = json.loads((result_path / "run_summary.json").read_text(encoding="utf-8"))
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except FullBlockedByFastAcceptance as exc:
        if cfg is not None:
            mark_running_staging_incomplete(cfg.root, exc)
        print("FULL_BLOCKED_BY_FAST_ACCEPTANCE")
        print(json.dumps({"blocking_reasons": exc.reasons}, ensure_ascii=False, indent=2))
        return 2
    except Exception as exc:
        if cfg is not None:
            mark_running_staging_incomplete(cfg.root, exc)
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        if args.progress == "detail":
            raise
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
