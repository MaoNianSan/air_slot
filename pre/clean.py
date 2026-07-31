from __future__ import annotations

import argparse
import json
import sys as _sys
from pathlib import Path
from typing import Any

_sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from clean_common import (
    CleanBoundaryError,
    inventory_target,
    find_run_states,
    count_residuals,
    validate_target,
    find_active_workers,
    stop_verified_workers,
    execute_clean,
)


SUPPORTED_MODES = ('fast', 'diagnostic', 'adapt_full', 'full', 'precision')
MODULE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_ROOT.parent.resolve()
OUTPUT_ROOT = (MODULE_ROOT / "output").resolve()
DATA_ROOT = (PROJECT_ROOT / "data").resolve()
PRE_CACHE_ROOT = (PROJECT_ROOT / "pre" / "cache").resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Safely clean {MODULE_ROOT.name} runtime output")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--mode", choices=SUPPORTED_MODES)
    selection.add_argument("--all-output", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--stop-owned-processes",
        action="store_true",
        help="Gracefully stop only a process whose module, mode, and run_id ownership all match",
    )
    return parser


def clean_selection(
    *,
    mode: str | None,
    all_output: bool,
    dry_run: bool,
    stop_owned_processes: bool = False,
) -> dict[str, Any]:
    return execute_clean(
        module_root=MODULE_ROOT,
        output_root=OUTPUT_ROOT,
        project_root=PROJECT_ROOT,
        data_root=DATA_ROOT,
        pre_cache_root=PRE_CACHE_ROOT,
        supported_modes=SUPPORTED_MODES,
        mode=mode,
        all_output=all_output,
        dry_run=dry_run,
        stop_owned_processes=stop_owned_processes,
    )


def _validate_target(target: Path, *, allow_output_root: bool) -> Path:
    return validate_target(
        target,
        output_root=OUTPUT_ROOT,
        project_root=PROJECT_ROOT,
        data_root=DATA_ROOT,
        pre_cache_root=PRE_CACHE_ROOT,
        allow_output_root=allow_output_root,
    )


def _inventory(target: Path, *, remove_root: bool) -> dict[str, int]:
    return inventory_target(target, remove_root=remove_root)


def _run_states(target: Path, all_output: bool) -> list[Path]:
    return find_run_states(target, all_output)


def _active_workers(target: Path, all_output: bool) -> list[dict[str, Any]]:
    return find_active_workers(target, all_output, MODULE_ROOT)


def _stop_verified_workers(workers: list[dict[str, Any]]) -> None:
    stop_verified_workers(workers, MODULE_ROOT)


def _residual_counts(target: Path) -> dict[str, int]:
    return count_residuals(target)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = clean_selection(
            mode=args.mode,
            all_output=args.all_output,
            dry_run=args.dry_run,
            stop_owned_processes=args.stop_owned_processes,
        )
    except Exception as exc:
        print(json.dumps({
            "module": MODULE_ROOT.name,
            "selected_mode": getattr(args, "mode", None) or "ALL_OUTPUT",
            "resolved_output_path": None,
            "files_removed": 0,
            "directories_removed": 0,
            "bytes_removed": 0,
            "cache_preserved": True,
            "data_preserved": True,
            "active_worker_count": None,
            "status": "CLEAN_FAILED",
            "error": f"{type(exc).__name__}:{exc}",
        }, indent=2), flush=True)
        return 1
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
