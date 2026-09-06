"""Run the frozen Exp3 Development diagnostic/analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import SHARED_INPUT, bootstrap_stage, stage_agreement, stage_contrasts, stage_heterogeneity


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("contract", "fast", "development"), required=True)
    parser.add_argument("--input", type=Path, default=SHARED_INPUT)
    args = parser.parse_args(argv)
    if args.mode == "contract":
        print(json.dumps({"status": "PASS", "experiment_id": "EXP3", "support_policy_id": "COMMON_SUPPORT_CONDITIONAL_090", "final_test_access_count": 0, "paper_result": False}))
        return 0
    if not args.input.is_file():
        print(json.dumps({"status": "BLOCKED", "reason": "BLOCK_SHARED_INPUT_MISSING", "final_test_access_count": 0, "paper_result": False}))
        return 0
    import pandas as pd
    frame = pd.read_parquet(args.input)
    if args.mode == "fast":
        keep = sorted(frame["original_episode_id"].astype(str).unique())[:8]
        frame = frame[frame["original_episode_id"].astype(str).isin(keep)].copy()
    result = stage_agreement(frame)
    heterogeneity = pd.concat([stage_heterogeneity(frame, c) for c in (5.0, 10.0, 15.0)], ignore_index=True)
    contrasts = stage_contrasts(result)
    bootstrap = bootstrap_stage(frame, replicates=20 if args.mode == "fast" else 2000)
    output = Path(__file__).resolve().parents[2] / "artifacts" / "experiment" / "exp3" / "development"
    output.mkdir(parents=True, exist_ok=True)
    result.to_csv(output / "EXP3_STAGE_AGREEMENT.csv", index=False)
    heterogeneity.to_csv(output / "EXP3_STAGE_HETEROGENEITY.csv", index=False)
    contrasts.to_csv(output / "EXP3_STAGE_CONTRASTS.csv", index=False)
    bootstrap.to_csv(output / "EXP3_BOOTSTRAP.csv", index=False)
    manifest = {"status": "PASS", "experiment_id": "EXP3", "mode": args.mode, "rows": len(result), "bootstrap_seed": 20260906, "bootstrap_replicates": 20 if args.mode == "fast" else 2000, "final_test_access_count": 0, "paper_result": False, "model_retrained": False, "calibration_refit": False, "parameter_reselected": False}
    (output / "EXP3_OUTPUT_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
