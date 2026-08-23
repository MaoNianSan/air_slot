"""Official Exp4 Development execution entry point."""

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
from exp.exp4.global_development import run as run_global_development
from model.common.errors import ContractError


INPUT_ROOT = Path("artifacts/experiment/full_development_inputs_v1")
OUTPUT_ROOT = Path("artifacts/experiments/exp4/full_development_v1")


def _validate_existing(root: Path, output_root: Path) -> dict:
    manifest_path = output_root / "EXP4_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json"
    required = (
        manifest_path,
        output_root / "EXP4_FULL_DEVELOPMENT_METRICS.json",
        output_root / "EXP4_FULL_DEVELOPMENT_TABLE.csv",
        output_root / "EXP4_FULL_DEVELOPMENT_INTERPRETATION.md",
        output_root / "EXP4_DATA1_BOUNDED_ACCEPTANCE.json",
    )
    require_files(required, code="EXP4_OFFICIAL_OUTPUT_MISSING")
    manifest = load_json(manifest_path)
    require_development_safety(manifest, label="EXP4_OFFICIAL")
    if manifest.get("data2_role") != "MAIN_EVALUATION":
        raise ContractError("EXP4_OFFICIAL_DATA2_ROLE_INVALID")
    if manifest.get("data1_role") != "BOUNDED_GENERALIZATION_SMOKE_ONLY":
        raise ContractError("EXP4_OFFICIAL_DATA1_ROLE_INVALID")
    if manifest.get("data1_data2_pooling") is not False:
        raise ContractError("EXP4_OFFICIAL_DATASET_POOLING_FORBIDDEN")
    if (manifest.get("episode_count"), manifest.get("node_count")) != (128, 1769):
        raise ContractError("EXP4_OFFICIAL_CARDINALITY_INVALID")
    if tuple(manifest.get("baselines", ())) != (
        "HISTORICAL", "LIGHTGBM", "RANDOM_FOREST", "STATE_AWARE_H32"
    ):
        raise ContractError("EXP4_OFFICIAL_BASELINE_SET_INVALID")
    return {
        "status": "EXP4_OFFICIAL_READY",
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
        "data2": "MAIN_DEVELOPMENT_EVALUATION",
        "data1": "BOUNDED_SMOKE_PASS",
        "FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Exp4 Data2 baselines and Data1 bounded smoke.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = repository_root()
    frozen = load_official_frozen_binding(root)
    input_root = require_active_path((args.input_root or root / INPUT_ROOT), root)
    output_root = require_active_path((args.output_root or root / OUTPUT_ROOT), root)
    if args.check:
        print(json.dumps({
            "status": "EXP4_OFFICIAL_PREFLIGHT_PASS",
            "frozen_hashes": frozen.as_dict(),
            "data2_role": "MAIN_DEVELOPMENT_EVALUATION",
            "data1_role": "BOUNDED_GENERALIZATION_SMOKE_ONLY",
            "FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False,
        }, sort_keys=True))
        return 0
    if args.resume and (output_root / "EXP4_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json").is_file():
        print(json.dumps(_validate_existing(root, output_root), sort_keys=True))
        return 0
    run_global_development(root=root, input_root=input_root, output_root=output_root)
    print(json.dumps(_validate_existing(root, output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
