"""Unified FAST/MIDDLE/FULL experiment CLI.

The CLI is fixture-first. FAST validates source contracts and does not
discover raw data, access Final Test, or enable paper_full.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from exp.exp1.runner import Exp1Runner
from exp.exp2.runner import Exp2Runner
from exp.exp3.runner import Exp3Runner
from exp.exp4.runner import Exp4Runner


RUNNERS = {
    "exp1": Exp1Runner,
    "exp2": Exp2Runner,
    "exp3": Exp3Runner,
    "exp4": Exp4Runner,
}


def _write_fast_results(results, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    payloads = []
    for result in results:
        path = output / f"{result.experiment_id.lower()}_{result.variant_id.lower()}.json"
        path.write_text(
            result.model_dump_json(indent=2, by_alias=True) + "\n",
            encoding="utf-8",
        )
        payloads.append({
            "variant_id": result.variant_id,
            "support_status": result.support_status.value,
        })
    summary = {
        "status": "PASS",
        "tier": "FAST",
        "paper_result": False,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "results": payloads,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in RUNNERS:
        command = sub.add_parser(name)
        command.add_argument("--tier", choices=("fast", "middle", "full"), default="fast")
        command.add_argument("--dataset", default="data2_2019")
        command.add_argument("--split", default="DEVELOPMENT")
        command.add_argument("--seed", type=int, default=0)
        command.add_argument("--output", type=Path, default=Path("artifacts") / "fast" / name)

    smoke_all = sub.add_parser("smoke-all")
    smoke_all.add_argument("--output", type=Path, default=Path("artifacts") / "fast")
    args = parser.parse_args(argv)

    if args.command == "smoke-all":
        summary = {}
        for name, runner_type in RUNNERS.items():
            results = runner_type().execute_fast(
                dataset="data2_2019",
                split="DEVELOPMENT",
                seed=0,
            )
            summary[name] = _write_fast_results(results, args.output / name)
        print(json.dumps({"status": "PASS", "tier": "FAST", "experiments": summary}, sort_keys=True))
        return 0

    if args.tier != "fast":
        raise SystemExit("FULL/MIDDLE execution requires an explicitly bound protocol context")
    results = RUNNERS[args.command]().execute_fast(
        dataset=args.dataset,
        split=args.split,
        seed=args.seed,
    )
    print(json.dumps(_write_fast_results(results, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
