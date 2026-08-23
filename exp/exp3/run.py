"""Official Exp3 full-Development execution entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from exp.common.official_execution import (
    load_json,
    load_official_frozen_binding,
    repository_root,
    require_active_path,
    require_development_safety,
    require_files,
)
from exp.exp3.global_development import run as run_global_development
from model.common.errors import ContractError


EXP2_ROOT = Path("artifacts/experiments/exp2/full_development_v1")
INPUT_ROOT = Path("artifacts/experiment/full_development_inputs_v1")
OUTPUT_ROOT = Path("artifacts/experiments/exp3/full_development_v1")


def _validate_existing(root: Path, output_root: Path) -> dict:
    manifest_path = output_root / "EXP3_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json"
    required = (
        manifest_path,
        output_root / "EXP3_FULL_DEVELOPMENT_METRICS.json",
        output_root / "EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet",
        output_root / "EXP3_FULL_DEVELOPMENT_TABLE.csv",
        output_root / "EXP3_FULL_DEVELOPMENT_INTERPRETATION.md",
    )
    require_files(required, code="EXP3_OFFICIAL_OUTPUT_MISSING")
    manifest = load_json(manifest_path)
    require_development_safety(manifest, label="EXP3_OFFICIAL")
    if manifest.get("dataset") != "DATA2" or manifest.get("split") != "DEVELOPMENT":
        raise ContractError("EXP3_OFFICIAL_DATA_BOUNDARY_INVALID")
    if (manifest.get("episode_count"), manifest.get("node_count"), manifest.get("action_count")) != (128, 1769, 23):
        raise ContractError("EXP3_OFFICIAL_CARDINALITY_INVALID")
    if manifest.get("safety", {}).get("AUTHORITATIVE_RANKING") is not False:
        raise ContractError("EXP3_OFFICIAL_AUTHORITATIVE_RANKING_FORBIDDEN")
    return {
        "status": "EXP3_OFFICIAL_READY",
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
        "episode_count": 128, "node_count": 1769, "action_count": 23,
        "formal_decision_status": "NOT_RUN",
        "FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Exp3 on the frozen Data2 Development cohort.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--response-scenario-limit", type=int)
    parser.add_argument("--exp2-root", type=Path)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = repository_root()
    frozen = load_official_frozen_binding(root)
    exp2_root = require_active_path((args.exp2_root or root / EXP2_ROOT), root)
    input_root = require_active_path((args.input_root or root / INPUT_ROOT), root)
    output_root = require_active_path((args.output_root or root / OUTPUT_ROOT), root)
    if args.check:
        print(json.dumps({
            "status": "EXP3_OFFICIAL_PREFLIGHT_PASS",
            "frozen_hashes": frozen.as_dict(),
            "formal_authoritative_ranking": "NOT_RUN",
            "FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False,
        }, sort_keys=True))
        return 0
    if args.resume and (output_root / "EXP3_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json").is_file():
        print(json.dumps(_validate_existing(root, output_root), sort_keys=True))
        return 0
    run_global_development(
        root=root, exp2_root=exp2_root, input_root=input_root,
        output_root=output_root,
        response_scenario_limit=args.response_scenario_limit,
    )
    print(json.dumps(_validate_existing(root, output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
