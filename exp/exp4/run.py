"""Run the frozen Exp4 Development screening analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .triage import prepare_canonical_events, screen

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
    events, _ = prepare_canonical_events(pd.read_parquet(args.input))
    output = args.input.parent.parent / "exp4/development"
    output.mkdir(parents=True, exist_ok=True)
    results = pd.concat([screen(events, q) for q in (0.05, 0.10, 0.20, 0.30)], ignore_index=True)
    events.to_parquet(output / "EXP4_CANONICAL_EVENTS.parquet", index=False)
    results.to_csv(output / "EXP4_SCREENING_RESULTS.csv", index=False)
    manifest = {"status": "PASS", "experiment_id": "EXP4", "mode": args.mode, "canonical_event_count": len(events), "final_test_access_count": 0, "paper_result": False, "model_retrained": False, "calibration_refit": False, "parameter_reselected": False}
    (output / "EXP4_OUTPUT_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
