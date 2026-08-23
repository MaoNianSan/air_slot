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
        "exp2_cohort": root / "artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT_CURRENT_STAGE_V3.json",
        "m1_current_stage_refreeze": root / "artifacts/diagnostics/m1_v2_development_current_stage_refreeze_v3/M1_V2_CURRENT_STAGE_COHORT_REFREEZE_MANIFEST.json",
        "m1_positive_tail_freeze": root / "artifacts/diagnostics/m1_v2_positive_tail_policy_freeze_v2/M1_V2_POSITIVE_TAIL_POLICY_FREEZE_MANIFEST.json",
        "m1_scenario_manifest": root / "artifacts/experiment/m1_v2_current_stage_scenarios_v4/M1_V2_CURRENT_STAGE_TYPED_JOINT_SCENARIO_MANIFEST.json",
        "m1_scenarios": root / "artifacts/experiment/m1_v2_current_stage_scenarios_v4/M1_V2_CURRENT_STAGE_TYPED_JOINT_SCENARIOS.json",
        "m1_development_label_manifest": root / "artifacts/experiment/m1_v2_current_stage_development_labels_v1/M1_V2_CURRENT_STAGE_DEVELOPMENT_LABEL_MANIFEST.json",
        "m1_development_labels": root / "artifacts/experiment/m1_v2_current_stage_development_labels_v1/M1_V2_CURRENT_STAGE_DEVELOPMENT_LABELS.json",
        "tail_aware_brier_manifest": root / "artifacts/experiment/exp2a_tail_aware_brier_v1/EXP2A_TAIL_AWARE_BRIER_MANIFEST.json",
        "tail_aware_brier": root / "artifacts/experiment/exp2a_tail_aware_brier_v1/EXP2A_TAIL_AWARE_BRIER.json",
        "tail_aware_calibration_manifest": root / "artifacts/experiment/exp2a_tail_aware_calibration_v1/EXP2A_TAIL_AWARE_CALIBRATION_MANIFEST.json",
        "tail_aware_calibration": root / "artifacts/experiment/exp2a_tail_aware_calibration_v1/EXP2A_TAIL_AWARE_CALIBRATION.json",
        "m2_consequence_manifest": root / "artifacts/experiment/m2_v2_current_stage_consequences_v1/M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCE_MANIFEST.json",
        "m2_consequences": root / "artifacts/experiment/m2_v2_current_stage_consequences_v1/M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCES.json",
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
    tail_freeze = inputs["m1_positive_tail_freeze"][1]
    scenario_manifest = inputs["m1_scenario_manifest"][1]
    scenarios = inputs["m1_scenarios"][1]
    label_manifest = inputs["m1_development_label_manifest"][1]
    labels = inputs["m1_development_labels"][1]
    brier_manifest = inputs["tail_aware_brier_manifest"][1]
    brier = inputs["tail_aware_brier"][1]
    calibration_manifest = inputs["tail_aware_calibration_manifest"][1]
    calibration = inputs["tail_aware_calibration"][1]
    m2_consequence_manifest = inputs["m2_consequence_manifest"][1]
    m2_consequences = inputs["m2_consequences"][1]
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
    _require(refreeze["next_gate"] in ("M1_POSITIVE_TAIL_DECISION_REQUIRED", "M1_CURRENT_STAGE_JOINT_SCENARIO_ARTIFACT_REQUIRED"), "EXP2_M1_CURRENT_STAGE_NEXT_GATE_INVALID")
    _require(tail_freeze["status"] == "M1_POSITIVE_TAIL_POLICY_FROZEN", "EXP2_M1_POSITIVE_TAIL_FREEZE_NOT_BOUND")
    _require(tail_freeze["current_stage_cohort_hash"] == cohort["cohort_hash"], "EXP2_M1_POSITIVE_TAIL_COHORT_HASH_MISMATCH")
    _require(tail_freeze["feature_schema_hash"] == binding["frozen_contracts"]["feature_schema_hash"], "EXP2_M1_POSITIVE_TAIL_FEATURE_HASH_MISMATCH")
    _require(tail_freeze["support_hash"] == binding["frozen_contracts"]["support_hash"], "EXP2_M1_POSITIVE_TAIL_SUPPORT_HASH_MISMATCH")
    _require(tail_freeze["checkpoint_sha256"] == binding["checkpoint"]["sha256"], "EXP2_M1_POSITIVE_TAIL_CHECKPOINT_HASH_MISMATCH")
    _require(refreeze["new_cohort"]["cohort_hash"] == cohort["cohort_hash"], "EXP2_M1_CURRENT_STAGE_COHORT_HASH_MISMATCH")
    _require(refreeze["new_cohort"]["node_count"] == len(cohort["node_ids"]), "EXP2_M1_CURRENT_STAGE_NODE_COUNT_MISMATCH")
    _require(refreeze["stage_audit"]["changed_node_count"] == 3, "EXP2_M1_CURRENT_STAGE_STAGE_AUDIT_INVALID")
    _require(refreeze["feature_compatibility"]["status"] == "PASS_FROZEN_M1_FEATURE_TENSOR_COMPATIBILITY", "EXP2_M1_CURRENT_STAGE_FEATURE_COMPATIBILITY_INVALID")
    _require(refreeze["m1_artifact_validity"]["status"] == "PASS_FROZEN_M1_ARTIFACT_VALID_FOR_CURRENT_STAGE_INPUTS", "EXP2_M1_CURRENT_STAGE_M1_VALIDITY_INVALID")
    _require(scenario_manifest["status"] == "M1_CURRENT_STAGE_JOINT_SCENARIO_ARTIFACT_MATERIALIZED", "EXP2_M1_SCENARIO_MANIFEST_INVALID")
    _require(scenario_manifest["artifact_hash"] == scenarios["artifact_hash"], "EXP2_M1_SCENARIO_HASH_MISMATCH")
    _require(scenarios["cohort"]["cohort_hash"] == cohort["cohort_hash"], "EXP2_M1_SCENARIO_COHORT_MISMATCH")
    _require(scenarios["checkpoint"]["sha256"] == binding["checkpoint"]["sha256"], "EXP2_M1_SCENARIO_CHECKPOINT_MISMATCH")
    _require(scenarios["feature_schema_hash"] == binding["frozen_contracts"]["feature_schema_hash"], "EXP2_M1_SCENARIO_FEATURE_MISMATCH")
    _require(scenarios["support_hash"] == binding["frozen_contracts"]["support_hash"], "EXP2_M1_SCENARIO_SUPPORT_MISMATCH")
    _require(scenarios["node_count"] == len(cohort["node_ids"]) and scenarios["row_count"] == len(cohort["node_ids"]) * 250, "EXP2_M1_SCENARIO_CARDINALITY_INVALID")
    _require(label_manifest["status"] == "M1_CURRENT_STAGE_DEVELOPMENT_LABEL_ARTIFACT_MATERIALIZED", "EXP2_M1_DEVELOPMENT_LABEL_MANIFEST_INVALID")
    _require(label_manifest["artifact_hash"] == labels["artifact_hash"], "EXP2_M1_DEVELOPMENT_LABEL_HASH_MISMATCH")
    _require(labels["cohort_hash"] == cohort["cohort_hash"], "EXP2_M1_DEVELOPMENT_LABEL_COHORT_MISMATCH")
    _require(labels["node_count"] == len(cohort["node_ids"]) and labels["row_count"] == len(cohort["node_ids"]) * 3, "EXP2_M1_DEVELOPMENT_LABEL_CARDINALITY_INVALID")
    _require(labels["labels_are_model_inputs"] is False, "EXP2_M1_DEVELOPMENT_LABEL_INPUT_LEAKAGE")
    _require(brier_manifest["status"] == "EXP2A_TAIL_AWARE_BRIER_MATERIALIZED", "EXP2_TAIL_AWARE_BRIER_MANIFEST_INVALID")
    _require(brier_manifest["artifact_hash"] == brier["artifact_hash"], "EXP2_TAIL_AWARE_BRIER_HASH_MISMATCH")
    _require(brier_manifest["source_label_artifact_hash"] == labels["artifact_hash"], "EXP2_TAIL_AWARE_BRIER_LABEL_MISMATCH")
    _require(brier_manifest["source_scenario_artifact_hash"] == scenarios["artifact_hash"], "EXP2_TAIL_AWARE_BRIER_SCENARIO_MISMATCH")
    _require(set(brier_manifest["metrics"]) == set(EXP2A), "EXP2_TAIL_AWARE_BRIER_VARIANTS_INVALID")
    _require(calibration_manifest["status"] == "EXP2A_TAIL_AWARE_CALIBRATION_MATERIALIZED", "EXP2_TAIL_AWARE_CALIBRATION_MANIFEST_INVALID")
    _require(calibration_manifest["artifact_hash"] == calibration["artifact_hash"], "EXP2_TAIL_AWARE_CALIBRATION_HASH_MISMATCH")
    _require(calibration_manifest["source_brier_artifact_hash"] == brier["artifact_hash"], "EXP2_TAIL_AWARE_CALIBRATION_BRIER_MISMATCH")
    _require(calibration["source_scenario_artifact_hash"] == scenarios["artifact_hash"], "EXP2_TAIL_AWARE_CALIBRATION_SCENARIO_MISMATCH")
    _require(calibration["source_label_artifact_hash"] == labels["artifact_hash"], "EXP2_TAIL_AWARE_CALIBRATION_LABEL_MISMATCH")
    _require(calibration["development_bin_tuning"] is False, "EXP2_TAIL_AWARE_CALIBRATION_WAS_TUNED")
    _require(m2_consequence_manifest["status"] == "M2_V2_CONSEQUENCE_ARTIFACT_MATERIALIZED", "EXP2_M2_CONSEQUENCE_MANIFEST_INVALID")
    _require(m2_consequence_manifest["artifact_hash"] == m2_consequences["artifact_hash"], "EXP2_M2_CONSEQUENCE_HASH_MISMATCH")
    _require(m2_consequences["source_m1_artifact_hash"] == scenarios["artifact_hash"], "EXP2_M2_SOURCE_M1_HASH_MISMATCH")
    _require(m2_consequences["row_count"] == scenarios["row_count"] and m2_consequences["node_count"] == scenarios["node_count"], "EXP2_M2_CONSEQUENCE_CARDINALITY_INVALID")
    _require(m2_consequences["seven_component_status_counts"] == {"ABSTAIN": scenarios["row_count"]}, "EXP2_M2_SEVEN_COMPONENT_STATUS_INVALID")
    for payload in (binding, exp1, cohort, refreeze, tail_freeze, scenario_manifest, scenarios, label_manifest, labels, brier_manifest, brier, calibration_manifest, calibration, m2_consequence_manifest, m2_consequences):
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
        "m1_current_stage_labels_materialized": True,
        "m1_development_label_artifact_hash": labels["artifact_hash"],
        "m1_development_label_row_count": labels["row_count"],
        "m1_development_label_status_counts": labels["status_counts"],
        "tail_aware_brier_artifact_hash": brier["artifact_hash"],
        "tail_aware_brier_metrics": brier_manifest["metrics"],
        "tail_aware_calibration_artifact_hash": calibration["artifact_hash"],
        "tail_aware_calibration_metrics": calibration_manifest["variant_metrics"],
        "m1_positive_tail_policy": parameters["m1_v2_positive_tail_policy"]["value"],
        "m1_positive_tail_freeze_manifest_hash": tail_freeze["artifact_hash"],
        "m1_positive_tail_representation": tail_freeze["representation"],
        "m1_target_support_manifest": tail_freeze["target_support_manifest"],
        "m1_scenario_artifact_hash": scenarios["artifact_hash"],
        "m1_scenario_count_per_node": scenarios["scenario_count_per_node"],
        "m1_scenario_row_count": scenarios["row_count"],
        "m2_consequence_artifact_hash": m2_consequences["artifact_hash"],
        "m2_consequence_row_count": m2_consequences["row_count"],
        "m2_formal_five_component_status_counts": m2_consequences["formal_five_component_status_counts"],
        "m2_seven_component_status_counts": m2_consequences["seven_component_status_counts"],
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
            "status": "PASS_M1_V2_TYPED_JOINT_SCENARIO_ARTIFACT_MATERIALIZED",
            "reason": "CONTENT_ADDRESSED_TAIL_AWARE_JOINT_SCENARIOS_BOUND_TO_CURRENT_STAGE_DEVELOPMENT_COHORT",
            "artifact_hash": fixed["m1_scenario_artifact_hash"],
            "scenario_count_per_node": fixed["m1_scenario_count_per_node"],
            "row_count": fixed["m1_scenario_row_count"],
        },
        "M1_DEVELOPMENT_LABELS": {
            "status": "PASS_CURRENT_STAGE_DEVELOPMENT_LABEL_ARTIFACT_MATERIALIZED",
            "reason": "EXP2A_PROPER_SCORES_REQUIRE_POST_OUTCOME_DEVELOPMENT_LABELS_BOUND_TO_THE_NEW_COHORT",
            "artifact_hash": fixed["m1_development_label_artifact_hash"],
            "row_count": fixed["m1_development_label_row_count"],
            "status_counts": fixed["m1_development_label_status_counts"],
            "labels_are_model_inputs": False,
            "final_test": "FORBIDDEN",
        },
        "M1_TAIL_AWARE_PROPER_SCORES": {
            "status": "BLOCKED_STANDARD_SCALAR_CRPS_AND_VARIOGRAM_UNDEFINED_FOR_EXPLICIT_TAIL_CLASS",
            "reason": "OVERFLOW_TAIL_HAS_OBSERVABLE_CLASS_BUT_NO_SCALAR_MAGNITUDE_AND_MUST_NOT_BE_DROPPED_OR_EXTRAPOLATED",
            "manuscript_implementation_mismatch": True,
            "allowed_without_new_tail_assumption": ["THRESHOLD_EVENT_BRIER_WHEN_EVENT_IS_IDENTIFIABLE_FROM_CLASS_BOUNDS"],
            "forbidden_workarounds": ["DROP_TAIL_DRAWS", "ZERO_FILL", "QMAX_SUBSTITUTION", "SCALAR_EXTRAPOLATION"],
        },
        "M1_TAIL_AWARE_BRIER": {
            "status": "PASS_THRESHOLD_EVENT_BRIER_MATERIALIZED",
            "artifact_hash": fixed["tail_aware_brier_artifact_hash"],
            "event": "D_TO_GT_30_MINUTES",
            "aggregation": "EPISODE_BALANCED_MEAN_OF_NODE_BRIERS",
            "variant_metrics": fixed["tail_aware_brier_metrics"],
            "abstention_policy": "UNRESOLVED_INTERVAL_OR_MISSING_OBSERVED_LABEL_ABSTAIN",
        },
        "M1_TAIL_AWARE_CALIBRATION": {
            "status": "PASS_THRESHOLD_EVENT_CALIBRATION_MATERIALIZED",
            "artifact_hash": fixed["tail_aware_calibration_artifact_hash"],
            "event": "D_TO_GT_30_MINUTES",
            "contract": "EPISODE_BALANCED_FIXED_EQUAL_WIDTH_TEN_BIN",
            "development_bin_tuning": False,
            "variant_metrics": fixed["tail_aware_calibration_metrics"],
        },
        "M1_POSITIVE_TAIL": {
            "status": "PASS_M1_POSITIVE_TAIL_POLICY_FROZEN",
            "policy": fixed["m1_positive_tail_policy"],
            "representation": fixed["m1_positive_tail_representation"],
            "target_support_manifest": fixed["m1_target_support_manifest"],
            "reason": "FINITE_SUPPORT_BINS_AND_EXPLICIT_TAIL_CLASS_PRESERVE_OBSERVABILITY_WITHOUT_SCALAR_EXTRAPOLATION",
        },
        "M2_SEVEN_COMPONENT": {
            "status": "PASS_M2_TYPED_SEVEN_COMPONENT_VECTOR_MATERIALIZED_WITH_ABSTENTION",
            "artifact_hash": fixed["m2_consequence_artifact_hash"],
            "row_count": fixed["m2_consequence_row_count"],
            "formal_cu_components": covered,
            "required_components": M2_COMPONENTS,
            "uncovered_components": missing,
            "v2_formal_aggregate_status": m2_design["formal_aggregate_status"],
            "formal_five_component_status_counts": fixed["m2_formal_five_component_status_counts"],
            "seven_component_status_counts": fixed["m2_seven_component_status_counts"],
            "representation_readiness": {
                "EXP2B_7COMP": "READY_TYPED_VECTOR_WITH_EXPLICIT_ABSTAIN",
                "EXP2B_3CHANNEL": "BLOCKED_PASSENGER_CHANNEL_INCOMPLETE",
                "EXP2B_SCALAR": "BLOCKED_SEVEN_COMPONENT_AGGREGATE_UNRESOLVED",
            },
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
    m1_reason = ";".join((
        gates["M1_COHORT_BINDING"]["status"],
        gates["M1_SCENARIOS"]["status"],
        gates["M1_POSITIVE_TAIL"]["status"],
        gates["M1_DEVELOPMENT_LABELS"]["status"],
    ))
    tail_reason = gates["M1_TAIL_AWARE_PROPER_SCORES"]["status"]
    downstream_reason = ";".join((gates["M2_SEVEN_COMPONENT"]["status"], gates["M3_NON_A00"]["status"], gates["M4_MAPPING"]["status"]))
    records: dict[str, dict[str, Any]] = {}
    for variant in VARIANTS:
        if variant in EXP2A:
            brier = gates["M1_TAIL_AWARE_BRIER"]["variant_metrics"][variant]
            calibration = gates["M1_TAIL_AWARE_CALIBRATION"]["variant_metrics"][variant]
            records[variant] = {
                "family": "EXP2A",
                "reference_variant": EXP2A_JOINT,
                "execution_status": "PARTIAL_TAIL_AWARE_BRIER_AND_CALIBRATION_COMPLETE_OTHER_STATE_AND_DECISION_METRICS_BLOCKED",
                "state_metrics": {
                    "STATE_CRPS": _metric(tail_reason),
                    "STATE_VARIOGRAM_SCORE": _metric(tail_reason),
                    "STATE_BRIER": {
                        "value": brier["episode_balanced_brier"],
                        "support_status": brier["support_status"],
                        "event": "D_TO_GT_30_MINUTES",
                        "supported_node_count": brier["supported_node_count"],
                        "abstain_node_count": brier["abstain_node_count"],
                        "supported_episode_count": brier["supported_episode_count"],
                    },
                    "STATE_CALIBRATION": {
                        "value": calibration["episode_balanced_fixed_bin_calibration_gap"],
                        "support_status": calibration["support_status"],
                        "event": "D_TO_GT_30_MINUTES",
                        "contract": "EPISODE_BALANCED_FIXED_EQUAL_WIDTH_TEN_BIN",
                        "supported_node_count": calibration["supported_node_count"],
                        "supported_episode_count": calibration["supported_episode_count"],
                    },
                    "STATE_COVERAGE": _metric(f"{m1_reason};TAIL_AWARE_INTERVAL_COVERAGE_IMPLEMENTATION_REQUIRED"),
                },
                "decision_metrics": {
                    metric: _metric(downstream_reason)
                    for metric in ("DECISION_ACTION_DISAGREEMENT", "DECISION_RANKING_CHANGE", "DECISION_RISK_DIFFERENCE", "DECISION_CVAR_DIFFERENCE")
                },
            }
        else:
            representation_status = gates["M2_SEVEN_COMPONENT"]["representation_readiness"][variant]
            records[variant] = {
                "family": "EXP2B",
                "reference_variant": EXP2B_7COMP,
                "execution_status": representation_status,
                "state_metrics": "NOT_APPLICABLE_TO_EXP2B",
                "decision_metrics": {
                    metric: _metric(downstream_reason)
                    for metric in ("DECISION_ACTION_DISAGREEMENT", "DECISION_RANKING_CHANGE", "DECISION_RISK_DIFFERENCE", "DECISION_CVAR_DIFFERENCE")
                },
            }
    return records


def run_formal_development(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/experiment/exp2_formal_development_v9").resolve()
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
