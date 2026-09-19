"""Thin CLI for the Phase-7 runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .errors import TypedBlocker
from .gate_a import run_gate_a
from .gate_b import execute_gate_b


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--gate-a", action="store_true", help="run Phase-7 Gate A")
    mode.add_argument("--gate-b", action="store_true", help="run Phase-7 Gate B")
    parser.add_argument("--release", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)

    if args.gate_b:
        if args.release is None:
            raise SystemExit("--release is required with --gate-b")
        try:
            result = execute_gate_b(release_path=args.release)
        except TypedBlocker as error:
            print(json.dumps({"status": "TYPED_BLOCKER", "blocker": error.code}))
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    result = run_gate_a(output_root=args.output_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "READY_FOR_GATE_B" else 2


__all__ = ["main"]
