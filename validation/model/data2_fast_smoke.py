"""Read-only Data2 FAST validation gate for the frozen model.

This is a validation boundary, not an experiment runner.  It refuses to
execute downstream inference when the registered frozen artifact is absent or
does not match the scientific contract.  In particular, a stale H8 checkpoint
with D_OB support 210 must not be presented as the frozen D_OB support 180
model.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from model.M1.pipeline import M1Pipeline
from model.M3.registry_layer.actions import ActionRegistry
from model.common.config import load_config_layers
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.paths import PROJECT_ROOT


OUT = PROJECT_ROOT / "artifacts" / "diagnostics" / "model_fast_smoke"
ARTIFACT = (
    PROJECT_ROOT
    / "artifacts"
    / "models"
    / "m1"
    / "M1_FROZEN_H8"
    / "DATA2_M1_V2_DEVELOPMENT_FAST.pt"
)


def _data_guard() -> dict[str, object]:
    status = subprocess.run(
        ["git", "status", "--short", "--", "data1", "data2"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    diff = subprocess.run(
        ["git", "diff", "--", "data1", "data2"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "status_short": status.stdout,
        "diff": diff.stdout,
        "data1_modified": bool(status.stdout or diff.stdout),
        "data2_modified": bool(status.stdout or diff.stdout),
    }


def _contract_gate() -> dict[str, object]:
    scientific = load_config_layers(PROJECT_ROOT / "configs").scientific
    expected = {
        "hidden_size": int(scientific.parameters["m1_hidden_size"].value),
        "d_ob_max_finite_minutes": int(
            scientific.parameters["m1_v2_d_ob_max_finite_minutes"].value
        ),
        "scenario_count": int(scientific.parameters["scenario_count"].value),
        "support": {
            "T_IB_REMAINING_HAZARD": int(
                scientific.parameters["m1_v2_t_ib_remaining_max_finite_minutes"].value
            ),
            "D_OB": int(
                scientific.parameters["m1_v2_d_ob_max_finite_minutes"].value
            ),
            "D_TX": int(
                scientific.parameters["m1_v2_d_tx_max_finite_minutes"].value
            ),
        },
    }
    result: dict[str, object] = {
        "expected": expected,
        "artifact": str(ARTIFACT),
        "artifact_exists": ARTIFACT.is_file(),
        "status": "PASS",
        "failures": [],
    }
    if not ARTIFACT.is_file():
        result["status"] = "FAIL"
        result["failures"] = ["M1_H8_PRIMARY_ARTIFACT_NOT_MATERIALIZED"]
        return result
    pipeline = M1Pipeline.load(ARTIFACT)
    actual = {
        "hidden_size": int(pipeline.model.hidden_size),
        "support": {
            name: int(contract.max_finite_minutes)
            for name, contract in pipeline.contracts.items()
        },
        "temperatures": pipeline.temperatures,
    }
    result["actual"] = actual
    failures: list[str] = []
    if actual["hidden_size"] != expected["hidden_size"]:
        failures.append("M1_H8_PRIMARY_HIDDEN_SIZE_MISMATCH")
    for name, value in expected["support"].items():
        if actual["support"].get(name) != value:
            failures.append(f"M1_H8_PRIMARY_SUPPORT_MISMATCH:{name}")
    if expected["scenario_count"] != 64:
        failures.append("FROZEN_SCENARIO_COUNT_NOT_64")
    result["failures"] = failures
    result["status"] = "PASS" if not failures else "FAIL"
    return result


def run(output: Path = OUT) -> dict[str, object]:
    guard = _data_guard()
    registry = ActionRegistry.load(PROJECT_ROOT / "registries" / "action_templates.yaml")
    contract = _contract_gate()
    failures = list(contract["failures"])
    if len(registry.templates) != 23:
        failures.append("M3_ACTION_TEMPLATE_COUNT_NOT_23")
    summary = {
        "schema_version": "AIR_SLOT_MODEL_FAST_SMOKE_SUMMARY_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_baseline": "MODEL_BASELINE_FROZEN",
        "data2_selector": {
            "dataset": "data2_2019",
            "scope": "DEVELOPMENT_ONLY",
            "episodes": 8,
            "seed": 20260902,
            "scenario_count": 64,
            "read_only": True,
        },
        "episodes": 0,
        "nodes": 0,
        "scenario_count": 64,
        "PRE": {"status": "NOT_RUN", "reason": "M1_PRIMARY_ARTIFACT_GATE"},
        "M1": {"status": contract["status"], "reason": contract["failures"]},
        "M2": {"status": "NOT_RUN", "ontology": list(CONSEQUENCE_COMPONENTS)},
        "M3": {
            "status": "PASS" if len(registry.templates) == 23 else "FAIL",
            "template_count": len(registry.templates),
        },
        "M4": {
            "status": "NOT_RUN",
            "reason": "M1_PRIMARY_ARTIFACT_GATE",
            "comparison_scope": "EXPLICIT_K_CMP_REQUIRED",
            "chi_sel": "UNIMPLEMENTED",
        },
        "warnings": [],
        "failures": failures,
        "data_guard": guard,
    }
    summary["status"] = "PASS" if not failures and not guard["data1_modified"] and not guard["data2_modified"] else "FAIL"
    manifest = {
        "schema_version": "AIR_SLOT_MODEL_FAST_SMOKE_MANIFEST_V1",
        "summary_status": summary["status"],
        "summary_path": str(output / "FAST_SMOKE_SUMMARY.json"),
        "frozen_contract_gate": contract,
        "data_guard": guard,
        "no_experiment_runner": True,
        "final_test_access_count": 0,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "FAST_SMOKE_SUMMARY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    (output / "FAST_SMOKE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
