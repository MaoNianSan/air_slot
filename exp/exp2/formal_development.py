"""Development-only Exp2 execution record under the frozen M1 binding.

This entry point never trains, changes model artifacts, accesses Final Test, or
falls back to historical V1 outputs. It records every requested variant and
stops metric generation when the exact current artifact gates are unresolved.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import yaml

from model.M1.cache import M1DevelopmentBaseCache
from model.common.identity import content_id

from .variants import (
    EXP2A_JOINT,
    EXP2A_MARGINAL,
    EXP2A_POINT,
    EXP2B_3CHANNEL,
    EXP2B_7COMP,
    EXP2B_SCALAR,
)


VARIANTS = (
    EXP2A_POINT,
    EXP2A_MARGINAL,
    EXP2A_JOINT,
    EXP2B_SCALAR,
    EXP2B_3CHANNEL,
    EXP2B_7COMP,
)
EXP2A = frozenset((EXP2A_POINT, EXP2A_MARGINAL, EXP2A_JOINT))
M2_COMPONENTS = (
    "F_continuity",
    "F_execution",
    "F_propagation",
    "P_time",
    "P_itinerary",
    "P_service",
    "R_operating",
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        raise RuntimeError(f"EXP2_FORMAL_OUTPUT_EXISTS_WITH_DIFFERENT_CONTENT:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _artifact(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "artifact_hash": content_id(payload)}


def _metric(reason: str) -> dict[str, Any]:
    return {"value": None, "support_status": "NOT_RUN", "reason": reason}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _load_inputs(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    paths = {
        "m1_binding": root / "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json",
        "m1_freeze": root / "artifacts/diagnostics/m1_v2_final_development_freeze/M1_V2_FINAL_FREEZE_MANIFEST.json",
        "m1_checkpoint": root / "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt",
        "m1_cache": root / "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz",
        "m1_cache_manifest": root / "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json",
        "exp1_full_manifest": root / "artifacts/experiment/exp1_full_development/EXP1_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json",
        "exp2_cohort": root / "artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT_CURRENT_STAGE_V2.json",
        "m1_current_stage_refreeze": root / "artifacts/diagnostics/m1_v2_development_current_stage_refreeze/M1_V2_CURRENT_STAGE_COHORT_REFREEZE_MANIFEST.json",
        "m2_registry": root / "registries/m2_data2_formal_cu_v1.json",
        "m2_design": root / "registries/m2_v2_design.json",
        "m3_design": root / "registries/m3_v2_action_response_design.json",
        "m4_design": root / "registries/m4_v2_monetary_mapping_design.json",
        "m4_policy": root / "artifacts/experiment/exp2/DATA2_DEV_PILOT_M4_RISK_POLICY.json",
    }
    _require(all(path.is_file() for path in paths.values()), "EXP2_FORMAL_INPUT_ARTIFACT_MISSING")
    return {
        name: (path, {} if path.suffix == ".pt" or path.suffix == ".npz" else _load_json(path))
        for name, path in paths.items()
    }


def _validate_fixed_contract(root: Path, inputs: dict[str, tuple[Path, dict[str, Any]]]) -> dict[str, Any]:
    binding = inputs["m1_binding"][1]
    freeze = inputs["m1_freeze"][1]
    cache_manifest = inputs["m1_cache_manifest"][1]
    exp1 = inputs["exp1_full_manifest"][1]
    cohort = inputs["exp2_cohort"][1]
    refreeze = inputs["m1_current_stage_refreeze"][1]
    foundation = yaml.safe_load(
        (root / "configs/scientific/foundation.yaml").read_text(encoding="utf-8")
    )
    parameters = foundation["parameters"]

    _require(binding["status"] == "BOUND_FROZEN_M1_V2", "EXP2_M1_BINDING_NOT_FROZEN")
    _require(binding["model_id"] == "M1_V2_GRU_H32", "EXP2_M1_MODEL_NOT_H32")
    _require(_file_hash(inputs["m1_checkpoint"][0]) == binding["checkpoint"]["sha256"], "EXP2_M1_CHECKPOINT_HASH_MISMATCH")
    _require(freeze["status"] == "M1_V2_FINAL_DEVELOPMENT_FREEZE_READY", "EXP2_M1_FREEZE_NOT_READY")
    _require(exp1["split"] == "DEVELOPMENT", "EXP2_EXP1_SOURCE_NOT_DEVELOPMENT")
    _require(exp1["m1_model_id"] == "M1_V2_GRU_H32", "EXP2_EXP1_SOURCE_MODEL_MISMATCH")
    _require(cohort["dataset_id"] == "DATA2" and cohort["split"] == "DEVELOPMENT", "EXP2_COHORT_NOT_DEVELOPMENT")
    _require(
        refreeze["status"] == "NEW_DEVELOPMENT_COHORT_REFROZEN",
        "EXP2_M1_CURRENT_STAGE_REFREEZE_STATUS_INVALID",
    )
    _require(refreeze["next_gate"] == "M1_POSITIVE_TAIL_DECISION_REQUIRED", "EXP2_M1_CURRENT_STAGE_NEXT_GATE_INVALID")
    _require(refreeze["new_cohort"]["cohort_hash"] == cohort["cohort_hash"], "EXP2_M1_CURRENT_STAGE_COHORT_HASH_MISMATCH")
    _require(refreeze["new_cohort"]["node_count"] == len(cohort["node_ids"]), "EXP2_M1_CURRENT_STAGE_NODE_COUNT_MISMATCH")
    _require(refreeze["stage_audit"]["changed_node_count"] == 3, "EXP2_M1_CURRENT_STAGE_STAGE_AUDIT_INVALID")
    _require(refreeze["feature_compatibility"]["status"] == "PASS_FROZEN_M1_FEATURE_TENSOR_COMPATIBILITY", "EXP2_M1_CURRENT_STAGE_FEATURE_COMPATIBILITY_INVALID")
    _require(refreeze["m1_artifact_validity"]["status"] == "PASS_FROZEN_M1_ARTIFACT_VALID_FOR_CURRENT_STAGE_INPUTS", "EXP2_M1_CURRENT_STAGE_M1_VALIDITY_INVALID")
    for payload in (binding, exp1, cohort, refreeze):
        safety = payload.get("safety", payload)
        _require(safety.get("FINAL_TEST_ACCESS_COUNT", payload.get("FINAL_TEST_ACCESS_COUNT")) == 0, "EXP2_INPUT_FINAL_TEST_ACCESS_NONZERO")
        _require(safety.get("PAPER_FULL_RUN", payload.get("PAPER_FULL_RUN")) is False, "EXP2_INPUT_PAPER_FULL_TRUE")
    _require(exp1["safety"]["FULL"] is False, "EXP2_EXP1_SOURCE_FULL_TRUE")

    cache = M1DevelopmentBaseCache.load(
        inputs["m1_cache"][0],
        inputs["m1_cache_manifest"][0],
        expected_cache_key=cache_manifest["cache_key"],
    )
    cache_nodes = {row.decision_node_id for row in cache.partition("development")}
    cohort_nodes = set(cohort["node_ids"])
    _require(None not in cache_nodes, "EXP2_M1_CACHE_NODE_ID_MISSING")
    support = binding["frozen_contracts"]["support"]
    return {
        "m1_checkpoint_sha256": binding["checkpoint"]["sha256"],
        "feature_schema_hash": binding["frozen_contracts"]["feature_schema_hash"],
        "cache_hash": binding["frozen_contracts"]["cache_hash"],
        "support_hash": binding["frozen_contracts"]["support_hash"],
        "support": support,
        "loss_version": binding["frozen_contracts"]["loss_version"],
        "m1_cache_development_node_count": len(cache_nodes),
        "exp2_cohort_node_count": len(cohort_nodes),
        "m1_cache_exp2_cohort_intersection_count": len(cache_nodes & cohort_nodes),
        "m1_cache_exp2_cohort_missing_node_count": len(cohort_nodes - cache_nodes),
        "m1_current_stage_refreeze_status": refreeze["status"],
        "m1_current_stage_cohort_hash": cohort["cohort_hash"],
        "m1_current_stage_node_count": len(cohort["node_ids"]),
        "m1_current_stage_changed_node_count": refreeze["stage_audit"]["changed_node_count"],
        "m1_current_stage_distribution": refreeze["stage_audit"],
        "m1_current_stage_feature_compatibility": refreeze["feature_compatibility"]["status"],
        "m1_current_stage_artifact_validity": refreeze["m1_artifact_validity"]["status"],
        "m1_positive_tail_policy": parameters["m1_v2_positive_tail_policy"]["value"],
    }


def _gates(inputs: dict[str, tuple[Path, dict[str, Any]]], fixed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    m2_registry = inputs["m2_registry"][1]
    m2_design = inputs["m2_design"][1]
    m3_design = inputs["m3_design"][1]
    m4_design = inputs["m4_design"][1]
    m4_policy = inputs["m4_policy"][1]
    covered = tuple(m2_registry["formal_scope"])
    missing = tuple(component for component in M2_COMPONENTS if component not in covered)
    return {
        "M1_COHORT_BINDING": {
            "status": "PASS_CURRENT_STAGE_COHORT_REFROZEN",
            "reason": "NEW_COHORT_BINDS_CURRENT_APPROVED_DECLARED_EVENT_TIME_REPLAY_STAGE_POLICY",
            "current_stage_refreeze_status": fixed["m1_current_stage_refreeze_status"],
            "current_stage_cohort_hash": fixed["m1_current_stage_cohort_hash"],
            "current_stage_node_count": fixed["m1_current_stage_node_count"],
            "changed_node_count_from_historical_parent": fixed["m1_current_stage_changed_node_count"],
            "stage_distribution": fixed["m1_current_stage_distribution"],
            "feature_compatibility": fixed["m1_current_stage_feature_compatibility"],
            "m1_artifact_validity": fixed["m1_current_stage_artifact_validity"],
            "historical_parent_preserved": True,
            "cache_development_nodes": fixed["m1_cache_development_node_count"],
            "exp2_cohort_nodes": fixed["exp2_cohort_node_count"],
            "intersection_nodes": fixed["m1_cache_exp2_cohort_intersection_count"],
        },
        "M1_SCENARIOS": {
            "status": "BLOCKED_M1_V2_SCENARIO_ARTIFACT_NOT_MATERIALIZED",
            "reason": "NO_CONTENT_ADDRESSED_JOINT_SCENARIO_ARTIFACT_FOR_THE_CURRENT_STAGE_REFROZEN_DEVELOPMENT_COHORT",
        },
        "M1_POSITIVE_TAIL": {
            "status": "BLOCKED_M1_POSITIVE_TAIL_UNRESOLVED",
            "policy": fixed["m1_positive_tail_policy"],
            "reason": "ANCESTRAL_SAMPLING_CANNOT_SILENTLY_CLAMP_OR_EXTRAPOLATE_ABOVE_THE_FROZEN_POSITIVE_QUANTILE_GRID",
        },
        "M2_SEVEN_COMPONENT": {
            "status": "BLOCKED_M2_SEVEN_COMPONENT_CU_ARTIFACT_NOT_MATERIALIZED",
            "formal_cu_components": covered,
            "required_components": M2_COMPONENTS,
            "uncovered_components": missing,
            "v2_formal_aggregate_status": m2_design["formal_aggregate_status"],
        },
        "M3_NON_A00": {
            "status": "BLOCKED_M3_NON_A00_RESPONSE_RULES_NOT_EXECUTABLE",
            "non_a00_v2_execution_enabled": m3_design["non_a00_v2_execution_enabled"],
        },
        "M4_MAPPING": {
            "status": "BLOCKED_M4_MAPPING_NOT_FROZEN",
            "production_mapping_enabled": m4_design["production_mapping_enabled"],
            "policy_status": m4_policy["status"],
            "monetary_mapping_status": m4_policy["monetary_mapping_status"],
        },
    }


def _variant_metrics(gates: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    m1_reason = ";".join((gates["M1_COHORT_BINDING"]["status"], gates["M1_SCENARIOS"]["status"], gates["M1_POSITIVE_TAIL"]["status"]))
    downstream_reason = ";".join((gates["M2_SEVEN_COMPONENT"]["status"], gates["M3_NON_A00"]["status"], gates["M4_MAPPING"]["status"]))
    records: dict[str, dict[str, Any]] = {}
    for variant in VARIANTS:
        if variant in EXP2A:
            records[variant] = {
                "family": "EXP2A",
                "reference_variant": EXP2A_JOINT,
                "execution_status": "BLOCKED_BEFORE_METRIC_GENERATION",
                "state_metrics": {
                    metric: _metric(m1_reason)
                    for metric in ("STATE_CRPS", "STATE_BRIER", "STATE_CALIBRATION", "STATE_COVERAGE", "STATE_VARIOGRAM_SCORE")
                },
                "decision_metrics": {
                    metric: _metric(downstream_reason)
                    for metric in ("DECISION_ACTION_DISAGREEMENT", "DECISION_RANKING_CHANGE", "DECISION_RISK_DIFFERENCE", "DECISION_CVAR_DIFFERENCE")
                },
            }
        else:
            records[variant] = {
                "family": "EXP2B",
                "reference_variant": EXP2B_7COMP,
                "execution_status": "BLOCKED_BEFORE_METRIC_GENERATION",
                "state_metrics": "NOT_APPLICABLE_TO_EXP2B",
                "decision_metrics": {
                    metric: _metric(downstream_reason)
                    for metric in ("DECISION_ACTION_DISAGREEMENT", "DECISION_RANKING_CHANGE", "DECISION_RISK_DIFFERENCE", "DECISION_CVAR_DIFFERENCE")
                },
            }
    return records


def run_formal_development(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/experiment/exp2_formal_development").resolve()
    inputs = _load_inputs(root)
    fixed = _validate_fixed_contract(root, inputs)
    gates = _gates(inputs, fixed)
    metrics = _artifact({
        "schema_version": "EXP2_FORMAL_VARIANT_METRICS_V1",
        "status": "COMPLETE_WITH_GATED_NOT_RUN_RESULTS",
        "support_policy": "ABSTAIN_NOT_RUN_NO_ZERO_FILL_NO_SILENT_RENORMALIZATION",
        "variants": _variant_metrics(gates),
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    })
    metric_path = output_root / "EXP2_FORMAL_VARIANT_METRICS.json"
    _write_json(metric_path, metrics)

    lineage = _artifact({
        "schema_version": "EXP2_FORMAL_ARTIFACT_LINEAGE_V1",
        "status": "BOUND_WITH_UNRESOLVED_UPSTREAM_GATES",
        "inputs": {
            name: {"path": _relative(path, root), "sha256": _file_hash(path)}
            for name, (path, _) in inputs.items()
        },
        "fixed_contract": fixed,
        "cohort": {
            "cohort_hash": inputs["exp2_cohort"][1]["cohort_hash"],
            "episode_count": len(inputs["exp2_cohort"][1]["episode_ids"]),
            "node_count": len(inputs["exp2_cohort"][1]["node_ids"]),
            "split": "DEVELOPMENT",
        },
        "gates": gates,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "FULL": False,
    })
    lineage_path = output_root / "EXP2_FORMAL_ARTIFACT_LINEAGE.json"
    _write_json(lineage_path, lineage)

    manifest = _artifact({
        "schema_version": "EXP2_FORMAL_EXECUTION_MANIFEST_V1",
        "status": "EXP2_FORMAL_EXECUTION_COMPLETE",
        "execution_scope": "DEVELOPMENT_COHORT_NON_FULL",
        "dataset": "DATA2",
        "split": "DEVELOPMENT",
        "variants": list(VARIANTS),
        "fixed_contract": fixed,
        "m1_binding": {
            "model_id": "M1_V2_GRU_H32",
            "checkpoint_sha256": fixed["m1_checkpoint_sha256"],
            "model_modified": False,
        },
        "exp1_modified": False,
        "metrics_status": metrics["status"],
        "gated_metric_count": 6,
        "outputs": {
            "variant_metrics": _relative(metric_path, root),
            "lineage": _relative(lineage_path, root),
        },
        "safety": {
            "M1_TRAINING_RUNS_THIS_EXECUTION": 0,
            "TUNING_RUNS_THIS_EXECUTION": 0,
            "FINAL_TEST_ACCESS_COUNT": 0,
            "FULL": False,
            "PAPER_FULL_RUN": False,
        },
    })
    manifest_path = output_root / "EXP2_FORMAL_EXECUTION_MANIFEST.json"
    _write_json(manifest_path, manifest)
    return {"manifest": manifest_path, "metrics": metric_path, "lineage": lineage_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record Development-only Exp2 execution gates.")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    run_formal_development(root=root, output_root=args.output_root)
    print("EXP2_FORMAL_EXECUTION_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
