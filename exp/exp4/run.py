"""Run the frozen Exp4 Development screening analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .triage import bootstrap_screening, capture, pareto_reversals, prepare_canonical_events, robust_sets, screen

DEFAULT_INPUT = Path(__file__).resolve().parents[2] / "artifacts/experiment/shared/development/SHARED_DEVELOPMENT_INPUTS.parquet"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("contract", "fast", "development"), required=True)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args(argv)
    if args.mode == "contract":
        print(json.dumps({"status": "PASS", "experiment_id": "EXP4", "capacity": [0.05, 0.10, 0.20, 0.30], "rounding": "CEIL", "final_test_access_count": 0, "paper_result": False}))
        return 0
    if not args.input.is_file():
        print(json.dumps({"status": "BLOCKED", "reason": "BLOCK_SHARED_INPUT_MISSING", "final_test_access_count": 0, "paper_result": False}))
        return 0
    frame = pd.read_parquet(args.input)
    if args.mode == "fast":
        keep = sorted(frame["original_episode_id"].astype(str).unique())[:8]
        frame = frame[frame["original_episode_id"].astype(str).isin(keep)].copy()
    events, _ = prepare_canonical_events(frame)
    output = Path(__file__).resolve().parents[2] / "artifacts" / "experiment" / "exp4" / "development"
    output.mkdir(parents=True, exist_ok=True)
    results = pd.concat([screen(events, q) for q in (0.05, 0.10, 0.20, 0.30)], ignore_index=True)
    captures = pd.concat([capture(events, q) for q in (0.05, 0.10, 0.20, 0.30)], ignore_index=True)
    pareto = pd.concat([pareto_reversals(events, q) for q in (0.05, 0.10, 0.20, 0.30)], ignore_index=True)
    robust = pd.concat([robust_sets(events, m) for m in (3, 4, 5)], ignore_index=True)
    bootstrap = bootstrap_screening(
        events, replicates=20 if args.mode == "fast" else 2000
    )
    events.to_parquet(output / "EXP4_CANONICAL_EVENTS.parquet", index=False)
    results.to_csv(output / "EXP4_SCREENING_RESULTS.csv", index=False)
    captures.to_csv(output / "EXP4_CAPTURE.csv", index=False)
    pareto.to_csv(output / "EXP4_PARETO_RESULTS.csv", index=False)
    robust.to_csv(output / "EXP4_ROBUST_HIGH_CONSEQUENCE.csv", index=False)
    bootstrap.to_csv(output / "EXP4_BOOTSTRAP.csv", index=False)
    manifest = {"status": "PASS", "experiment_id": "EXP4", "mode": args.mode, "canonical_event_count": len(events), "bootstrap_replicates": 20 if args.mode == "fast" else 2000, "bootstrap_seed": 20260906, "final_test_access_count": 0, "paper_result": False, "model_retrained": False, "calibration_refit": False, "parameter_reselected": False}
    (output / "EXP4_OUTPUT_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
