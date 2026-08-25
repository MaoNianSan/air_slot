"""Audit Exp4 predictive baseline and cross-data capabilities without fitting."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import yaml

from model.common.identity import content_id


SAFETY = {
    "M1_TRAINING_RUNS_THIS_AUDIT": 0,
    "TUNING_RUNS_THIS_AUDIT": 0,
    "EXP4_RUNS_THIS_AUDIT": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"EXP4_CAPABILITY_AUDIT_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _fitted_lightgbm_registered(root: Path) -> bool:
    fitted_names = [
        path.name.lower() for path in (root / "artifacts").rglob("*") if path.is_file()
    ]
    return any(
        "lightgbm" in name and name.endswith((".pkl", ".joblib", ".txt"))
        for name in fitted_names
    )


def _random_forest_artifact_found(root: Path) -> bool:
    return any(
        ("random_forest" in name or "randomforest" in name)
        and path.suffix.lower() in {".pt", ".pkl", ".joblib", ".json"}
        for path, name in (
            (path, path.name.lower())
            for path in (root / "artifacts").rglob("*") if path.is_file()
        )
    )


def _profile(registry: dict[str, Any], dataset_id: str) -> dict[str, Any]:
    matches = [row for row in registry["profiles"] if row["dataset_instance_id"] == dataset_id]
    if len(matches) != 1:
        raise RuntimeError(f"EXP4_CAPABILITY_PROFILE_MISSING:{dataset_id}")
    return matches[0]


def audit(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/exp4_predictive_capability_audit_v1").resolve()
    capability_path = root / "registries/dataset_capabilities.yaml"
    fast_path = root / "model/M1/fast_path.py"
    diagnostics_path = root / "model/M1/development_training.py"
    scenario_manifest = root / "artifacts/experiment/m1_v2_current_stage_scenarios_v4/M1_V2_CURRENT_STAGE_TYPED_JOINT_SCENARIO_MANIFEST.json"
    for path in (capability_path, fast_path, diagnostics_path, scenario_manifest):
        if not path.is_file():
            raise RuntimeError(f"EXP4_CAPABILITY_AUDIT_INPUT_MISSING:{path}")

    registry = yaml.safe_load(capability_path.read_text(encoding="utf-8"))
    data1, data2 = _profile(registry, "data1_2019"), _profile(registry, "data2_2019")
    data1_caps = {row["scientific_object"]: row for row in data1["capabilities"]}
    data2_caps = {row["scientific_object"]: row for row in data2["capabilities"]}
    fitted_names = [
        path.name.lower() for path in (root / "artifacts").rglob("*") if path.is_file()
    ]
    historical_found = any("historical" in name and "baseline" in name for name in fitted_names)
    rf_found = _random_forest_artifact_found(root)
    lightgbm_registered = _fitted_lightgbm_registered(root)

    payload = {
        "schema_version": "EXP4_PREDICTIVE_CAPABILITY_AUDIT_V1",
        "status": "EXP4_PREDICTIVE_ARTIFACTS_BLOCKED_CAPABILITIES_AUDITED",
        "baseline_capabilities": {
            "HISTORICAL": {
                "implementation_or_fitted_artifact_found": historical_found,
                "status": "BLOCKED_NO_CURRENT_V2_HISTORICAL_BASELINE_ARTIFACT",
            },
            "LIGHTGBM_FAST": {
                "implementation_found": True,
                "train_frozen_fitted_artifact_registered": lightgbm_registered,
                "status": "BLOCKED_M1_FAST_V2_FITTED_ARTIFACT_NOT_REGISTERED",
            },
            "RANDOM_FOREST": {
                "implementation_or_fitted_artifact_found": rf_found,
                "status": "BLOCKED_NO_CURRENT_V2_RANDOM_FOREST_IMPLEMENTATION_OR_ARTIFACT",
            },
            "STATE_AWARE_FULL": {
                "node_conditional_scenario_artifact_found": True,
                "formal_exp4_lead_grid_artifact_found": False,
                "status": "BLOCKED_FROZEN_CHECKPOINT_WITHOUT_BOUND_PREDICTIVE_ARTIFACT",
            },
        },
        "data_environment_capabilities": {
            "data2_2019": {
                "role": "PRIMARY_DEVELOPMENT_EVALUATION_ENVIRONMENT",
                "realized_events": data2_caps["realized_events"],
                "status": "SUPPORTED_FOR_OBSERVED_OUTCOME_EVALUATION_AFTER_BASELINE_ARTIFACTS_EXIST",
            },
            "data1_2019": {
                "role": "TRAJECTORY_RICH_APPLICABILITY_ENVIRONMENT",
                "trajectory": data1_caps["trajectory"],
                "schedule": data1_caps["schedule"],
                "action_response_history": data1_caps["action_response_history"],
                "status": "DEGRADED_BUT_VALID_FOR_TYPED_APPLICABILITY_NOT_ISOMORPHIC_EXTERNAL_VALIDATION",
                "pooling_with_data2": "FORBIDDEN",
                "silent_schedule_proxy": "FORBIDDEN",
            },
        },
        "next_automatic_actions": [
            "IMPLEMENT_VERSIONED_HISTORICAL_AND_RANDOM_FOREST_BASELINES_ON_TRAIN_ONLY",
            "REGISTER_TRAIN_FROZEN_LIGHTGBM_FAST_ARTIFACT",
            "MATERIALIZE_STATE_AWARE_EXP4_LEAD_GRID_PREDICTIONS_FROM_FROZEN_CHECKPOINT",
            "MATERIALIZE_TYPED_DATA1_APPLICABILITY_DENOMINATORS_WITH_UNSUPPORTED_FIELDS_ABSTAIN",
        ],
        "inputs": {
            "dataset_capabilities": {"path": "registries/dataset_capabilities.yaml", "sha256": _hash(capability_path)},
            "fast_path": {"path": "model/M1/fast_path.py", "sha256": _hash(fast_path)},
            "development_training": {"path": "model/M1/development_training.py", "sha256": _hash(diagnostics_path)},
            "m1_scenario_manifest": {"path": scenario_manifest.relative_to(root).as_posix(), "sha256": _hash(scenario_manifest)},
        },
        "safety": SAFETY,
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "EXP4_PREDICTIVE_CAPABILITY_AUDIT.json"
    _write(artifact_path, payload)
    manifest = {
        "schema_version": "EXP4_PREDICTIVE_CAPABILITY_AUDIT_MANIFEST_V1",
        "status": payload["status"],
        "artifact": str(artifact_path.resolve()),
        "artifact_hash": payload["artifact_hash"],
        "baseline_statuses": {key: value["status"] for key, value in payload["baseline_capabilities"].items()},
        "data1_status": payload["data_environment_capabilities"]["data1_2019"]["status"],
        "safety": SAFETY,
    }
    manifest_path = output_root / "EXP4_PREDICTIVE_CAPABILITY_AUDIT_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    audit(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    print("EXP4_PREDICTIVE_CAPABILITIES_AUDITED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
