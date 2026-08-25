"""Official Exp2 full-Development execution entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from exp.common.full_development_inputs import materialize as materialize_inputs
from exp.common.full_development_scenarios import materialize as materialize_scenarios
from exp.common.official_execution import (
    load_json,
    load_official_frozen_binding,
    repository_root,
    require_active_path,
    require_development_safety,
    require_files,
)
from exp.exp2.global_development import run as run_global_development
from exp.reporting.output_contract import (
    validate_artifacts,
    write_from_global_metrics,
)
from model.common.errors import ContractError


INPUT_ROOT = Path("artifacts/experiment/full_development_inputs_v1")
SCENARIO_ROOT = Path("artifacts/experiments/exp2/full_development_scenarios_v1")
OUTPUT_ROOT = Path("artifacts/experiments/exp2/full_development_v1")


def _validate_existing(root: Path, output_root: Path) -> dict:
    manifest_path = output_root / "EXP2_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json"
    required = (
        manifest_path,
        output_root / "EXP2_FULL_DEVELOPMENT_METRICS.json",
        output_root / "M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet",
        output_root / "EXP2_FULL_DEVELOPMENT_TABLE.csv",
        output_root / "EXP2_FULL_DEVELOPMENT_INTERPRETATION.md",
    )
    require_files(required, code="EXP2_OFFICIAL_OUTPUT_MISSING")
    manifest = load_json(manifest_path)
    require_development_safety(manifest, label="EXP2_OFFICIAL")
    if manifest.get("dataset") != "DATA2" or manifest.get("split") != "DEVELOPMENT":
        raise ContractError("EXP2_OFFICIAL_DATA_BOUNDARY_INVALID")
    if manifest.get("episode_count") != 128 or manifest.get("node_count") != 1769:
        raise ContractError("EXP2_OFFICIAL_COHORT_CARDINALITY_INVALID")
    return {
        "status": "EXP2_OFFICIAL_READY",
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
        "episode_count": 128,
        "node_count": 1769,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Exp2 on the frozen Data2 Development cohort.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--finalize-output", action="store_true")
    parser.add_argument("--skip-scenarios", action="store_true")
    parser.add_argument("--scenario-count", type=int, default=250)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--scenario-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = repository_root()
    frozen = load_official_frozen_binding(root)
    input_root = require_active_path((args.input_root or root / INPUT_ROOT), root)
    scenario_root = require_active_path((args.scenario_root or root / SCENARIO_ROOT), root)
    output_root = require_active_path((args.output_root or root / OUTPUT_ROOT), root)
    if args.scenario_count <= 0:
        raise ContractError("EXP2_OFFICIAL_SCENARIO_COUNT_INVALID")

    if args.check:
        if (output_root / "exp2_summary.json").is_file():
            output_contract_state = validate_artifacts("EXP2", output_root)
        else:
            output_contract_state = "NOT_RUN"
        print(json.dumps({
            "status": "EXP2_OFFICIAL_PREFLIGHT_PASS",
            "scenario_count": args.scenario_count,
            "frozen_hashes": frozen.as_dict(),
            "output_contract": output_contract_state,
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
        }, sort_keys=True))
        return 0
    if args.resume and (output_root / "EXP2_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json").is_file():
        print(json.dumps(_validate_existing(root, output_root), sort_keys=True))
        return 0
    if args.finalize_output:
        state = _validate_existing(root, output_root)
        write_from_global_metrics(
            experiment_id="EXP2", output_root=output_root,
            metrics_path=output_root / "EXP2_FULL_DEVELOPMENT_METRICS.json",
            frozen_hashes=frozen.as_dict(), root=root,
            scenario_count=args.scenario_count,
        )
        state["output_contract"] = validate_artifacts("EXP2", output_root)
        print(json.dumps(state, sort_keys=True))
        return 0

    if args.skip_scenarios:
        require_files(
            (
                scenario_root / "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIOS.parquet",
                scenario_root / "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json",
            ),
            code="EXP2_OFFICIAL_SCENARIOS_MISSING",
        )
    else:
        materialize_inputs(root=root, output_root=input_root)
        materialize_scenarios(
            root=root, input_root=input_root, output_root=scenario_root,
            scenario_count=args.scenario_count,
        )
    run_global_development(
        root=root, scenario_root=scenario_root, input_root=input_root,
        output_root=output_root,
    )
    write_from_global_metrics(
        experiment_id="EXP2", output_root=output_root,
        metrics_path=output_root / "EXP2_FULL_DEVELOPMENT_METRICS.json",
        frozen_hashes=frozen.as_dict(), root=root,
        scenario_count=args.scenario_count,
    )
    print(json.dumps(_validate_existing(root, output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
