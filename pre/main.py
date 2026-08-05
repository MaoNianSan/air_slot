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
from src.core.contracts import (
    CONTRACT_ID,
    RESEARCH_CODE_REVISION,
    SCHEMA_VERSION,
    frozen_config_hash,
)
from src.core.pipeline import (
    build_core,
    core_readiness_existing,
    core_report_existing,
    core_validate_existing,
)
from src.pipeline_config import SUPPORTED_MODES, load_config
from src.progress import VALID_PROGRESS_LEVELS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Air Slot PRE Core V2 pipeline")
    parser.add_argument(
        "command",
        choices=["build", "validate", "readiness", "report", "inspect-config"],
    )
    parser.add_argument("--mode", choices=SUPPORTED_MODES, required=True)
    parser.add_argument("--config", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--n-jobs", type=int, default=None)
    parser.add_argument(
        "--progress",
        choices=sorted(VALID_PROGRESS_LEVELS),
        default=None,
    )
    return parser


def _configure_runtime(args: argparse.Namespace) -> tuple[dict, object]:
    cfg = load_config(args.config, mode=args.mode)
    requested = resolve_requested_n_jobs(
        args.n_jobs, cfg.get("runtime", {}).get("state_workers", 1)
    )
    plan = resolve_parallel_plan(
        requested, task_count=10_000, prefer_outer_parallelism=True
    )
    cfg.setdefault("runtime", {}).update(
        parallel_metadata(
            plan,
            task_seed_digest=task_seed_hash(
                20260726,
                "pre",
                args.mode,
                "state_partitions",
                ["CACHE_PARTITIONS"],
            ),
        )
    )
    cfg["runtime"]["state_workers"] = plan.outer_workers
    cfg["runtime"]["rebuild_cache"] = bool(args.rebuild_cache)
    if args.progress is not None:
        cfg["runtime"]["progress_level"] = args.progress
    return cfg, plan


def main() -> int:
    args = build_parser().parse_args()
    cfg, plan = _configure_runtime(args)
    output = args.output_dir
    if args.command == "inspect-config":
        print(
            json.dumps(
                {
                    "contract_id": CONTRACT_ID,
                    "schema_version": SCHEMA_VERSION,
                    "research_code_revision": RESEARCH_CODE_REVISION,
                    "mode": cfg["mode"],
                    "frozen_config_hash": frozen_config_hash(cfg),
                },
                indent=2,
            )
        )
        return 0
    if args.command == "build":
        with thread_limit_environment(plan):
            result = build_core(cfg, output_override=output)
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
    if args.command == "validate":
        print(json.dumps(core_validate_existing(cfg, output), indent=2, default=str))
        return 0
    if args.command == "readiness":
        print(json.dumps(core_readiness_existing(cfg, output), indent=2, default=str))
        return 0
    if args.command == "report":
        print(core_report_existing(cfg, output))
        return 0
    return 2


if __name__ == "__main__":
    with contextlib.suppress(BrokenPipeError):
        raise SystemExit(main())
