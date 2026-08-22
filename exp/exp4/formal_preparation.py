"""Development-only preparation for the gated Exp4 formal execution."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import yaml

from model.common.identity import content_id

from .protocol import EVALUATION_LEAD_MINUTES, PredictiveBaseline


FORMAL_BASELINES = tuple(item.value for item in PredictiveBaseline)
_SAFETY = {
    "M1_TRAINING_RUNS_THIS_PREPARATION": 0,
    "TUNING_RUNS_THIS_PREPARATION": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "FULL": False,
    "PAPER_FULL_RUN": False,
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _artifact(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "artifact_hash": content_id(payload)}


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        raise RuntimeError(f"EXP4_FORMAL_PREPARATION_OUTPUT_CONFLICT:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _inputs(root: Path) -> dict[str, tuple[Path, Any]]:
    paths = {
        "m1_binding": root / "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json",
        "m1_freeze": root / "artifacts/diagnostics/m1_v2_final_development_freeze/M1_V2_FINAL_FREEZE_MANIFEST.json",
        "m1_checkpoint": root / "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt",
        "exp2_lineage": root / "artifacts/experiment/exp2_formal_development/EXP2_FORMAL_ARTIFACT_LINEAGE.json",
        "data1_usage": root / "data1/DATA_USAGE.md",
        "data2_usage": root / "data2/DATA_USAGE.md",
        "dataset_capabilities": root / "registries/dataset_capabilities.yaml",
        "source_adapter_registry": root / "registries/source_adapter_registry.yaml",
    }
    _require(all(path.is_file() for path in paths.values()), "EXP4_FORMAL_PREPARATION_INPUT_MISSING")
    loaded: dict[str, tuple[Path, Any]] = {}
    for name, path in paths.items():
        if path.suffix == ".json":
            value: Any = _load_json(path)
        elif path.suffix == ".yaml":
            value = _load_yaml(path)
        elif path.suffix == ".pt":
            value = {}
        else:
            value = path.read_text(encoding="utf-8")
        loaded[name] = (path, value)
    return loaded


def _input_safety(payload: dict[str, Any]) -> None:
    safety = payload.get("safety", payload)
    _require(
        safety.get("FINAL_TEST_ACCESS_COUNT", payload.get("FINAL_TEST_ACCESS_COUNT")) == 0,
        "EXP4_INPUT_FINAL_TEST_ACCESS_NONZERO",
    )
    _require(
        safety.get("PAPER_FULL_RUN", payload.get("PAPER_FULL_RUN")) is False,
        "EXP4_INPUT_PAPER_FULL_TRUE",
    )
    _require(safety.get("FULL", payload.get("FULL")) is False, "EXP4_INPUT_FULL_TRUE")


def _profile(capabilities: dict[str, Any], dataset_id: str) -> dict[str, Any]:
    matches = [item for item in capabilities["profiles"] if item["dataset_instance_id"] == dataset_id]
    _require(len(matches) == 1, f"EXP4_DATASET_PROFILE_MISSING:{dataset_id}")
    return matches[0]


def _validate(inputs: dict[str, tuple[Path, Any]]) -> dict[str, Any]:
    binding = inputs["m1_binding"][1]
    freeze = inputs["m1_freeze"][1]
    exp2_lineage = inputs["exp2_lineage"][1]
    checkpoint = inputs["m1_checkpoint"][0]

    _require(binding["status"] == "BOUND_FROZEN_M1_V2", "EXP4_M1_BINDING_NOT_FROZEN")
    _require(binding["model_id"] == "M1_V2_GRU_H32", "EXP4_M1_MODEL_NOT_H32")
    _require(binding["hidden_size"] == 32, "EXP4_M1_HIDDEN_SIZE_NOT_32")
    _require(_file_hash(checkpoint) == binding["checkpoint"]["sha256"], "EXP4_M1_CHECKPOINT_HASH_MISMATCH")
    _require(freeze["status"] == "M1_V2_FINAL_DEVELOPMENT_FREEZE_READY", "EXP4_M1_FREEZE_NOT_READY")
    _require(freeze["selected_model"]["model_id"] == binding["model_id"], "EXP4_M1_FREEZE_MODEL_MISMATCH")
    _require(
        freeze["selected_model"]["checkpoint_sha256"] == binding["checkpoint"]["sha256"],
        "EXP4_M1_FREEZE_CHECKPOINT_MISMATCH",
    )
    _require(exp2_lineage["status"] == "BOUND_WITH_UNRESOLVED_UPSTREAM_GATES", "EXP4_CURRENT_GATE_SOURCE_INVALID")
    for payload in (binding, freeze, exp2_lineage):
        _input_safety(payload)

    binding_contract = binding["frozen_contracts"]
    freeze_contract = freeze["fixed_contracts"]
    _require(binding_contract["feature_schema_hash"] == freeze_contract["feature_schema_hash"], "EXP4_FEATURE_HASH_MISMATCH")
    _require(binding_contract["cache_hash"] == freeze_contract["cache_hash"], "EXP4_CACHE_HASH_MISMATCH")
    _require(binding_contract["support_hash"] == freeze_contract["support_hash"], "EXP4_SUPPORT_HASH_MISMATCH")
    _require(binding_contract["loss_version"] == freeze_contract["loss_version"], "EXP4_LOSS_VERSION_MISMATCH")
    _require(binding_contract["support"]["T_IB"] == 360, "EXP4_T_IB_SUPPORT_MISMATCH")
    _require(binding_contract["support"]["D_OB"] == 210, "EXP4_D_OB_SUPPORT_MISMATCH")
    _require(binding_contract["support"]["D_TX"] == 60, "EXP4_D_TX_SUPPORT_MISMATCH")
    _require(freeze_contract["support"]["T_IB_REMAINING_HAZARD"] == 360, "EXP4_FREEZE_T_IB_SUPPORT_MISMATCH")
    _require(binding["data_boundary"]["final_test"] == "LOCKED_NOT_ACCESSED", "EXP4_FINAL_TEST_BOUNDARY_INVALID")

    capabilities = inputs["dataset_capabilities"][1]
    data1_profile = _profile(capabilities, "data1_2019")
    data2_profile = _profile(capabilities, "data2_2019")
    _require(data1_profile["cross_dataset_reference_overlay"] is False, "EXP4_DATA1_OVERLAY_ENABLED")
    _require(data2_profile["cross_dataset_reference_overlay"] is False, "EXP4_DATA2_OVERLAY_ENABLED")
    _require("primary experimental dataset" in inputs["data2_usage"][1], "EXP4_DATA2_PRIMARY_BINDING_MISSING")
    _require("trajectory-rich applicability dataset" in inputs["data1_usage"][1], "EXP4_DATA1_GENERALIZATION_BINDING_MISSING")

    return {
        "m1_model_id": binding["model_id"],
        "m1_hidden_size": binding["hidden_size"],
        "m1_checkpoint_sha256": binding["checkpoint"]["sha256"],
        "feature_schema_hash": binding_contract["feature_schema_hash"],
        "cache_hash": binding_contract["cache_hash"],
        "support_hash": binding_contract["support_hash"],
        "support": binding_contract["support"],
        "loss_version": binding_contract["loss_version"],
        "data2": {
            "dataset_instance_id": "data2_2019",
            "role": "PRIMARY_DEVELOPMENT_EVALUATION_ENVIRONMENT",
            "split": "DEVELOPMENT",
            "profile": data2_profile["dataset_profile"],
            "cross_dataset_reference_overlay": False,
        },
        "data1": {
            "dataset_instance_id": "data1_2019",
            "role": "GENERALIZATION_ENVIRONMENT_ONLY",
            "profile": data1_profile["dataset_profile"],
            "cross_dataset_reference_overlay": False,
            "pooling": "FORBIDDEN",
            "substitution_for_data2": "FORBIDDEN",
        },
        "evaluation_lead_minutes": EVALUATION_LEAD_MINUTES,
        "m1_model_horizon_minutes": (0, 15, 60),
    }


def _baseline_contracts() -> dict[str, dict[str, Any]]:
    common = {
        "evaluation_lead_minutes": EVALUATION_LEAD_MINUTES,
        "cohort_policy": "SAME_FROZEN_DATA2_DEVELOPMENT_COHORT_PER_BASELINE",
        "information_policy": "PRE_CUTOFF_INPUTS_ONLY_NO_FUTURE_INFORMATION",
        "distribution_output": "REQUIRED_FOR_CRPS_AND_MARGINAL_CALIBRATION",
        "result_policy": "NOT_RUN_UNTIL_EXACT_VERSIONED_ARTIFACT_IS_BOUND",
        "zero_fill": False,
        "synthetic_metrics": False,
        "final_test": "FORBIDDEN",
        "full_run": False,
        "paper_full_run": False,
    }
    contracts = {
        PredictiveBaseline.HISTORICAL.value: {
            **common,
            "status": "BLOCKED_NO_CURRENT_V2_HISTORICAL_BASELINE_ARTIFACT",
            "model_path": "HISTORICAL_REFERENCE",
            "reason": "CURRENT_BASELINE_AUDIT_AND_M1_DIAGNOSTICS_REPORT_NO_EXECUTABLE_CURRENT_V2_IMPLEMENTATION",
            "fallback_to_legacy_v1": "FORBIDDEN",
        },
        PredictiveBaseline.LIGHTGBM_FAST.value: {
            **common,
            "status": "BLOCKED_M1_FAST_V2_FITTED_ARTIFACT_NOT_REGISTERED",
            "model_path": "FAST_CURRENT_LOCAL_R_FAST_PLUS_STATIC",
            "reason": "IMPLEMENTATION_EXISTS_BUT_PREDICT_DISTRIBUTIONS_ABSTAINS_UNTIL_TRAIN_FROZEN_ARTIFACT_IS_REGISTERED",
            "state_aware_equivalence_claim": "FORBIDDEN_UNTIL_TYPED_PARITY_ARTIFACT",
        },
        PredictiveBaseline.RANDOM_FOREST.value: {
            **common,
            "status": "BLOCKED_NO_CURRENT_V2_RANDOM_FOREST_IMPLEMENTATION_OR_ARTIFACT",
            "model_path": "RANDOM_FOREST_REFERENCE",
            "reason": "M1_DEVELOPMENT_DIAGNOSTICS_RECORDS_NO_EXISTING_IMPLEMENTATION",
            "fallback_to_different_baseline": "FORBIDDEN",
        },
        PredictiveBaseline.STATE_AWARE_FULL.value: {
            **common,
            "status": "BLOCKED_FROZEN_CHECKPOINT_WITHOUT_BOUND_PREDICTIVE_ARTIFACT",
            "model_path": "STATE_AWARE_GRU_H32",
            "model_id": "M1_V2_GRU_H32",
            "checkpoint_binding": "FROZEN_HASH_VERIFIED",
            "reason": "CURRENT_COHORT_IDENTITY_SCENARIO_AND_POSITIVE_TAIL_GATES_REMAIN_UNRESOLVED",
            "full_name_semantics": "STATE_AWARE_PATH_LABEL_ONLY_NOT_PAPER_FULL_OR_FULL_EXECUTION",
        },
    }
    _require(tuple(contracts) == FORMAL_BASELINES, "EXP4_BASELINE_SET_MISMATCH")
    return contracts


def _lineage_schema() -> dict[str, Any]:
    return _artifact({
        "schema_version": "EXP4_FORMAL_LINEAGE_SCHEMA_V1",
        "status": "READY_FOR_FROZEN_INPUT_BINDING",
        "required_identity_fields": (
            "dataset_instance_id", "dataset_role", "baseline_id", "baseline_contract_hash",
            "episode_id", "decision_node_id", "decision_time_utc", "information_cutoff_utc",
            "prediction_horizon_minutes", "target_id", "cohort_hash", "split",
            "m1_model_id", "m1_checkpoint_sha256", "feature_schema_hash", "cache_hash",
            "support_hash", "loss_version",
        ),
        "distribution_fields": (
            "joint_distribution_artifact_hash", "marginal_distribution_artifact_hash",
            "calibration_artifact_hash", "history_lineage_hash", "target_support_status",
        ),
        "portability_fields": (
            "data2_support", "data1_support", "support_transition", "data1_metric_denominator",
            "data2_metric_denominator", "cross_dataset_reference_overlay",
        ),
        "required_invariants": (
            "DATA2_IS_PRIMARY_AND_DATA1_IS_GENERALIZATION_ONLY",
            "NO_DATA1_DATA2_POOLING_OR_SILENT_SUBSTITUTION",
            "PREDICTION_HORIZON_IS_ONE_OF_FORMAL_EXP4_GRID",
            "INFORMATION_CUTOFF_NOT_AFTER_DECISION_TIME",
            "NO_FUTURE_INFORMATION",
            "UNAVAILABLE_BASELINE_OR_TARGET_IS_NOT_RUN_NOT_ZERO",
            "NO_SYNTHETIC_METRICS_OR_LEGACY_V1_FALLBACK",
            "FINAL_TEST_ACCESS_COUNT_IS_ZERO",
        ),
        "safety": dict(_SAFETY),
    })


def _readiness(gates: dict[str, Any], baseline_contracts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    blockers = tuple(item["status"] for item in gates.values() if str(item["status"]).startswith("BLOCKED_"))
    return _artifact({
        "schema_version": "EXP4_FORMAL_EXECUTION_READINESS_V1",
        "status": "EXP4_FORMAL_EXECUTION_READY",
        "preparation_status": "READY",
        "execution_status": "BLOCKED_CURRENT_ARTIFACT_AND_BASELINE_GATES",
        "data_environment_readiness": {
            "data2_2019": {
                "role": "PRIMARY_DEVELOPMENT_EVALUATION_ENVIRONMENT",
                "status": "BLOCKED_CURRENT_M1_PREDICTIVE_ARTIFACT_GATES",
            },
            "data1_2019": {
                "role": "GENERALIZATION_ENVIRONMENT_ONLY",
                "status": "BLOCKED_TYPED_DATA1_EVALUATION_ARTIFACT_NOT_MATERIALIZED",
                "pooling": "FORBIDDEN",
            },
        },
        "baseline_readiness": {
            baseline: {
                "status": contract["status"],
                "metrics": "NOT_RUN_NO_SYNTHETIC_OR_ZERO_FILLED_VALUES",
            }
            for baseline, contract in baseline_contracts.items()
        },
        "shared_blockers": blockers,
        "evaluation_contract": {
            "metrics": ("MAE_MINUTES", "CRPS", "BRIER", "CALIBRATION_GAP"),
            "aggregation": "TARGET_AND_HORIZON_SPECIFIC_WITH_EXPLICIT_EPISODE_DENOMINATORS",
            "cross_dataset_comparison": "WITHIN_ENVIRONMENT_BASELINE_PATTERN_AND_SUPPORT_TRANSITIONS_ONLY",
            "lead_minutes": EVALUATION_LEAD_MINUTES,
            "selection_or_ranking": "NOT_PART_OF_THIS_PREPARATION",
        },
        "safety": dict(_SAFETY),
    })


def prepare_formal_execution(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/exp4_formal_execution_preparation").resolve()
    inputs = _inputs(root)
    fixed = _validate(inputs)
    gates = inputs["exp2_lineage"][1]["gates"]
    baseline_contracts = _artifact({
        "schema_version": "EXP4_FORMAL_BASELINE_CONTRACTS_V1",
        "status": "READY_WITH_BLOCKED_EXECUTABLE_ARTIFACTS",
        "baselines": _baseline_contracts(),
        "fixed_m1_contract": fixed,
        "safety": dict(_SAFETY),
    })
    baseline_contracts_path = output_root / "EXP4_FORMAL_BASELINE_CONTRACTS.json"
    _write(baseline_contracts_path, baseline_contracts)
    schema = _lineage_schema()
    schema_path = output_root / "EXP4_FORMAL_LINEAGE_SCHEMA.json"
    _write(schema_path, schema)
    readiness = _readiness(gates, baseline_contracts["baselines"])
    readiness_path = output_root / "EXP4_FORMAL_EXECUTION_READINESS_REPORT.json"
    _write(readiness_path, readiness)
    manifest = _artifact({
        "schema_version": "EXP4_FORMAL_EXECUTION_MANIFEST_V1",
        "status": "EXP4_FORMAL_EXECUTION_READY",
        "execution_scope": "DEVELOPMENT_PREPARATION_NON_FULL",
        "m1_binding": {
            "model_id": fixed["m1_model_id"],
            "hidden_size": fixed["m1_hidden_size"],
            "checkpoint_sha256": fixed["m1_checkpoint_sha256"],
            "model_modified": False,
        },
        "datasets": {"primary": fixed["data2"], "generalization": fixed["data1"]},
        "baselines": FORMAL_BASELINES,
        "evaluation_lead_minutes": EVALUATION_LEAD_MINUTES,
        "m1_model_horizon_minutes": fixed["m1_model_horizon_minutes"],
        "lead_time_policy": "FORMAL_EXP4_GRID_IS_DISTINCT_FROM_M1_MODEL_HORIZON_NO_IMPLICIT_INTERPOLATION",
        "fixed_contract": {
            key: fixed[key]
            for key in ("feature_schema_hash", "cache_hash", "support_hash", "support", "loss_version")
        },
        "inputs": {
            name: {"path": _relative(path, root), "sha256": _file_hash(path)}
            for name, (path, _) in inputs.items()
        },
        "shared_gates_source": _relative(inputs["exp2_lineage"][0], root),
        "outputs": {
            "baseline_contracts": _relative(baseline_contracts_path, root),
            "lineage_schema": _relative(schema_path, root),
            "execution_readiness_report": _relative(readiness_path, root),
        },
        "safety": dict(_SAFETY),
    })
    manifest_path = output_root / "EXP4_FORMAL_EXECUTION_MANIFEST.json"
    _write(manifest_path, manifest)
    return {
        "manifest": manifest_path,
        "baseline_contracts": baseline_contracts_path,
        "lineage_schema": schema_path,
        "readiness": readiness_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the gated Exp4 Development execution contract.")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    prepare_formal_execution(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    print("EXP4_FORMAL_EXECUTION_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
