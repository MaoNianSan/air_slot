"""Thin CLI for the Phase-7 runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .errors import TypedBlocker
from .gate_a import run_gate_a
from .gate_b import execute_gate_b
from .gate_b0 import DEFAULT_NODE_LIMIT, run_gate_b0_binding_audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--gate-a", action="store_true", help="run Phase-7 Gate A")
    mode.add_argument(
        "--gate-b0",
        action="store_true",
        help="run the Gate B.0 executor binding audit (pre-open only)",
    )
    mode.add_argument("--gate-b", action="store_true", help="run Phase-7 Gate B")
    parser.add_argument("--release", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--fixture-root", type=Path)
    parser.add_argument("--node-limit", type=int, default=DEFAULT_NODE_LIMIT)
    parser.add_argument(
        "--unbound-executor",
        action="store_true",
        help="validate a release without binding the scientific executor",
    )
    args = parser.parse_args(argv)

    if args.gate_b0:
        report = run_gate_b0_binding_audit(
            output_root=args.output_root,
            fixture_root=args.fixture_root,
            node_limit=args.node_limit,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report.get("status") == "PASS" else 2

    if args.gate_b:
        if args.release is None:
            raise SystemExit("--release is required with --gate-b")
        try:
            result = execute_gate_b(
                release_path=args.release,
                use_production_executor=not args.unbound_executor,
            )
        except TypedBlocker as error:
            print(json.dumps({"status": "TYPED_BLOCKER", "blocker": error.code}))
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    result = run_gate_a(output_root=args.output_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "READY_FOR_GATE_B" else 2


__all__ = ["main"]
