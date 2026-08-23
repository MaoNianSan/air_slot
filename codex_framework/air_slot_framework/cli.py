"""Development-only CLI for the AIR SLOT framework contracts."""

from __future__ import annotations

import argparse
import json

from .experiments import (
    EXP1_VARIANTS,
    EXP2_VARIANTS,
    EXP3_VARIANTS,
    EXP4_VARIANTS,
    ExperimentStage,
    build_experiment_manifest,
    development_protocol_report,
)
from .workflow import (
    write_artifact_manifest,
    write_contract_audit,
    write_development_manifest,
    write_experiment_readiness,
    write_validation_report,
)


def smoke_report() -> dict[str, object]:
    manifests = tuple(
        build_experiment_manifest(
            stage=stage,
            variant=variant,
            source_artifact={"artifact": "synthetic_smoke", "stage": stage.value},
            split="DEVELOPMENT_SYNTHETIC",
            seed=0,
            provenance=("CLI_SMOKE",),
        )
        for stage, variants in (
            (ExperimentStage.EXP1, (EXP1_VARIANTS[0],)),
            (ExperimentStage.EXP2, (EXP2_VARIANTS[0],)),
            (ExperimentStage.EXP3, (EXP3_VARIANTS[0],)),
            (ExperimentStage.EXP4, (EXP4_VARIANTS[0],)),
        )
        for variant in variants
    )
    return development_protocol_report(manifests)


def main() -> None:
    parser = argparse.ArgumentParser(description="AIR SLOT development contract CLI")
    parser.add_argument("command", choices=("smoke", "workflow"))
    parser.add_argument("--output", default="codex_framework", help="development artifact directory")
    args = parser.parse_args()
    if args.command == "smoke":
        print(json.dumps(smoke_report(), sort_keys=True))
    elif args.command == "workflow":
        from pathlib import Path

        output = Path(args.output)
        paths = (
            write_development_manifest(output / "workflow_manifest.json"),
            write_artifact_manifest(output / "artifact_manifest.json"),
            write_contract_audit(output / "contract_audit.json"),
            write_experiment_readiness(output / "experiment_readiness.json"),
            write_validation_report(output / "validation_report.json"),
        )
        print(json.dumps({"status": "DEVELOPMENT_WORKFLOW_READY", "formal_execution": False, "paths": [str(p) for p in paths]}, sort_keys=True))


if __name__ == "__main__":
    main()
