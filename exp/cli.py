"""Unified CONTRACT_FAST/REAL_DATA_FAST/MIDDLE/FULL experiment CLI.

``smoke-all`` is source-free CONTRACT_FAST. ``real-fast-all`` binds the same
frozen Data2 Development cohort across Exp1--Exp4 and never accesses Final
Test or paper_full.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from exp.common.context import real_fast_context
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


def _write_results(results, output: Path) -> dict:
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
    tier = results[0].tier if results else "UNKNOWN"
    statuses = {item.support_status.value for item in results}
    summary = {
        "status": (
            "PASS" if tier == "CONTRACT_FAST" else
            "REAL_FAST_ALL_PASS" if statuses == {"SUPPORTED"} else
            "REAL_FAST_PARTIAL_SHARED_GATES_REMAIN"
        ),
        "tier": tier,
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
        command.add_argument("--tier", choices=("fast", "real-fast", "middle", "full"), default="fast")
        command.add_argument("--dataset", default="data2_2019")
        command.add_argument("--split", default="DEVELOPMENT")
        command.add_argument("--seed", type=int, default=0)
        command.add_argument("--output", type=Path, default=Path("artifacts") / "fast" / name)
        if name == "exp1":
            command.add_argument("--include-sensitivity", action="store_true")

    smoke_all = sub.add_parser("smoke-all")
    smoke_all.add_argument("--output", type=Path, default=Path("artifacts") / "fast")
    real_fast_all = sub.add_parser("real-fast-all")
    real_fast_all.add_argument("--seed", type=int, default=0)
    real_fast_all.add_argument("--output", type=Path, default=Path("artifacts") / "real_fast")
    real_fast_all.add_argument("--include-sensitivity", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "smoke-all":
        summary = {}
        for name, runner_type in RUNNERS.items():
            results = runner_type().execute_fast(
                dataset="data2_2019",
                split="DEVELOPMENT",
                seed=0,
            )
            summary[name] = _write_results(results, args.output / name)
        print(json.dumps({"status": "PASS", "tier": "CONTRACT_FAST", "experiments": summary}, sort_keys=True))
        return 0

    if args.command == "real-fast-all":
        context = real_fast_context(seed=args.seed)
        summary = {}
        for name, runner_type in RUNNERS.items():
            runner = runner_type()
            kwargs = {"context": context}
            if name == "exp1":
                kwargs["include_sensitivity"] = args.include_sensitivity
            summary[name] = _write_results(runner.execute_real_fast(**kwargs), args.output / name)
        print(json.dumps({
            "status": "REAL_FAST_ALL_PASS" if all(
                item["status"] == "REAL_FAST_ALL_PASS" for item in summary.values()
            ) else "REAL_FAST_PARTIAL_SHARED_GATES_REMAIN",
            "tier": "REAL_DATA_FAST",
            "cohort_hash": context.lineage["cohort_hash"],
            "experiments": summary,
        }, sort_keys=True))
        return 0

    if args.tier not in {"fast", "real-fast"}:
        raise SystemExit("FULL/MIDDLE execution requires an explicitly bound protocol context")
    runner = RUNNERS[args.command]()
    if args.tier == "fast":
        kwargs = {"dataset": args.dataset, "split": args.split, "seed": args.seed}
        if args.command == "exp1":
            kwargs["include_sensitivity"] = args.include_sensitivity
        results = runner.execute_fast(**kwargs)
    else:
        if args.dataset.lower() not in {"data2", "data2_2019"} or args.split.upper() != "DEVELOPMENT":
            raise SystemExit("REAL_DATA_FAST_REQUIRES_DATA2_DEVELOPMENT")
        kwargs = {"context": real_fast_context(seed=args.seed)}
        if args.command == "exp1":
            kwargs["include_sensitivity"] = args.include_sensitivity
        results = runner.execute_real_fast(**kwargs)
    print(json.dumps(_write_results(results, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
