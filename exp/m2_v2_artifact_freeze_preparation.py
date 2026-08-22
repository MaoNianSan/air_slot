"""Prepare the gated M2 V2 seven-component artifact freeze.

This module writes contracts and readiness metadata only.  It does not read
raw Data2 rows, materialize M2 consequences, run Exp2/Exp3, or create paper
results.  The existing V1 five-component CU registry is recorded as
provenance and is never relabelled as the V2 seven-component artifact.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id


COMPONENTS = tuple(CONSEQUENCE_COMPONENTS)
_FIVE_COMPONENTS = (
    "F_continuity",
    "F_execution",
    "F_propagation",
    "P_time",
    "R_operating",
)
_CHANNELS = {
    "Flight": ("F_continuity", "F_execution", "F_propagation"),
    "Passenger": ("P_time", "P_itinerary", "P_service"),
    "Resource": ("R_operating",),
}
_SAFETY = {
    "M1_TRAINING_RUNS_THIS_PREPARATION": 0,
    "TUNING_RUNS_THIS_PREPARATION": 0,
    "EXP2_RUNS_THIS_PREPARATION": 0,
    "EXP3_RUNS_THIS_PREPARATION": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
        raise RuntimeError(f"M2_V2_FREEZE_OUTPUT_CONFLICT:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _inputs(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    paths = {
        "m1_binding": root / "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json",
        "m1_freeze": root / "artifacts/diagnostics/m1_v2_final_development_freeze/M1_V2_FINAL_FREEZE_MANIFEST.json",
        "m1_checkpoint": root / "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt",
        "m2_design": root / "registries/m2_v2_design.json",
        "m2_registry_v1": root / "registries/m2_data2_formal_cu_v1.json",
        "m2_registry_manifest_v1": root / "artifacts/diagnostics/v5_development_freeze/M2_DATA2_FORMAL_CU_V1_MANIFEST.json",
        "m2_freeze_closure_v1": root / "artifacts/diagnostics/v5_development_freeze/M2_FORMAL_FREEZE_CLOSURE.json",
        "pre_ownership": root / "artifacts/diagnostics/v5_development_freeze/PRE_OWNERSHIP_GATE_V2.json",
        "exp2_lineage": root / "artifacts/experiment/exp2_formal_development/EXP2_FORMAL_ARTIFACT_LINEAGE.json",
        "exp3_manifest": root / "artifacts/diagnostics/exp3_formal_execution_preparation/EXP3_FORMAL_EXECUTION_MANIFEST.json",
        "data2_usage": root / "data2/DATA_USAGE.md",
    }
    _require(all(path.is_file() for path in paths.values()), "M2_V2_FREEZE_INPUT_MISSING")
    loaded: dict[str, tuple[Path, dict[str, Any]]] = {}
    for name, path in paths.items():
        loaded[name] = (
            path,
            {} if path.suffix == ".pt" else (_load_json(path) if path.suffix == ".json" else {}),
        )
    return loaded


def _validate_inputs(inputs: dict[str, tuple[Path, dict[str, Any]]]) -> dict[str, Any]:
    binding = inputs["m1_binding"][1]
    freeze = inputs["m1_freeze"][1]
    design = inputs["m2_design"][1]
    registry = inputs["m2_registry_v1"][1]
    registry_manifest = inputs["m2_registry_manifest_v1"][1]
    pre_gate = inputs["pre_ownership"][1]
    exp2_lineage = inputs["exp2_lineage"][1]
    exp3_manifest = inputs["exp3_manifest"][1]

    _require(binding["status"] == "BOUND_FROZEN_M1_V2", "M2_V2_M1_BINDING_NOT_FROZEN")
    _require(binding["model_id"] == "M1_V2_GRU_H32", "M2_V2_M1_MODEL_NOT_H32")
    _require(binding["hidden_size"] == 32, "M2_V2_M1_HIDDEN_SIZE_NOT_32")
    _require(_file_hash(inputs["m1_checkpoint"][0]) == binding["checkpoint"]["sha256"], "M2_V2_M1_CHECKPOINT_HASH_MISMATCH")
    _require(freeze["status"] == "M1_V2_FINAL_DEVELOPMENT_FREEZE_READY", "M2_V2_M1_FREEZE_NOT_READY")
    _require(freeze["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0, "M2_V2_M1_FINAL_TEST_NONZERO")
    _require(freeze["safety"]["PAPER_FULL_RUN"] is False, "M2_V2_M1_PAPER_FULL_TRUE")

    _require(tuple(design["component_order"]) == COMPONENTS, "M2_V2_COMPONENT_ORDER_MISMATCH")
    _require(design["design_status"] == "FROZEN", "M2_V2_DESIGN_NOT_FROZEN")
    _require(design["formal_aggregate_status"] == "FORMAL_AGGREGATE_UNRESOLVED", "M2_V2_AGGREGATE_STATUS_CHANGED")
    _require(design["cu_normalization_registry_id"] == "M2_DATA2_FORMAL_CU_V2_PENDING", "M2_V2_CU_REGISTRY_ID_CHANGED")
    _require(design["monetary_mapping_layer"] == "M4_ONLY", "M2_V2_MONEY_MAPPING_OWNER_INVALID")
    _require(tuple(registry["formal_scope"]) == _FIVE_COMPONENTS, "M2_V1_FORMAL_SCOPE_CHANGED")
    _require(tuple(registry["outside_principal_scope"]) == ("P_itinerary", "P_service"), "M2_V1_OUTSIDE_SCOPE_CHANGED")
    _require(registry["final_test_access_count"] == 0, "M2_V1_FINAL_TEST_NONZERO")
    _require(registry["paper_full_run"] is False, "M2_V1_PAPER_FULL_TRUE")
    _require(registry_manifest["final_test_access_count"] == 0, "M2_V1_MANIFEST_FINAL_TEST_NONZERO")
    _require(registry_manifest["paper_full_run"] is False, "M2_V1_MANIFEST_PAPER_FULL_TRUE")
    _require(pre_gate["PRE_OWNERSHIP_GATE"] == "PASS", "M2_V2_PRE_OWNERSHIP_GATE_NOT_PASS")
    _require(exp2_lineage["status"] == "BOUND_WITH_UNRESOLVED_UPSTREAM_GATES", "M2_V2_EXP2_LINEAGE_STATUS_INVALID")
    _require(exp3_manifest["status"] == "EXP3_FORMAL_EXECUTION_READY", "M2_V2_EXP3_PREPARATION_NOT_READY")
    for payload in (exp2_lineage, exp3_manifest):
        safety = payload.get("safety", payload)
        _require(safety.get("FINAL_TEST_ACCESS_COUNT", payload.get("FINAL_TEST_ACCESS_COUNT")) == 0, "M2_V2_UPSTREAM_FINAL_TEST_NONZERO")
        _require(safety.get("PAPER_FULL_RUN", payload.get("PAPER_FULL_RUN")) is False, "M2_V2_UPSTREAM_PAPER_FULL_TRUE")
        _require(safety.get("FULL", payload.get("FULL")) is False, "M2_V2_UPSTREAM_FULL_TRUE")

    return {
        "m1_model_id": binding["model_id"],
        "m1_checkpoint_sha256": binding["checkpoint"]["sha256"],
        "feature_schema_hash": binding["frozen_contracts"]["feature_schema_hash"],
        "cache_hash": binding["frozen_contracts"]["cache_hash"],
        "support_hash": binding["frozen_contracts"]["support_hash"],
        "support": binding["frozen_contracts"]["support"],
        "loss_version": binding["frozen_contracts"]["loss_version"],
        "m2_design_id": design["design_id"],
        "m2_design_version": design["version"],
        "m2_v1_registry_id": registry["registry_id"],
        "m2_v1_registry_hash": registry["registry_hash"],
        "m2_v1_formal_scope": _FIVE_COMPONENTS,
        "m2_v2_scope_status": design["formal_aggregate_status"],
        "m2_v2_cu_registry_id": design["cu_normalization_registry_id"],
        "pre_ownership_gate": pre_gate["PRE_OWNERSHIP_GATE"],
        "exp2_shared_gates": exp2_lineage["gates"],
    }


_FORMULAS = {
    "F_continuity": {
        "aspect": "Flight",
        "native_unit": "minutes",
        "formula": "max(0, r_ib_minutes - turnaround_reference(connection_airport))",
        "driver": "turnaround_compression",
        "source_type": "HYBRID",
        "critical_inputs": ["r_ib_minutes", "turnaround_reference"],
    },
    "F_execution": {
        "aspect": "Flight",
        "native_unit": "minutes",
        "formula": "d_ob_minutes",
        "driver": "additional_off_block_wait",
        "source_type": "SCENARIO_ASSUMPTION",
        "critical_inputs": ["d_ob_minutes"],
    },
    "F_propagation": {
        "aspect": "Flight",
        "native_unit": "exposure_minutes",
        "formula": "d_to_minutes * expected_downstream_exposure(origin)",
        "driver": "takeoff_delay_x_expected_downstream_exposure",
        "source_type": "HYBRID",
        "critical_inputs": ["d_to_minutes", "expected_downstream_exposure"],
    },
    "P_time": {
        "aspect": "Passenger",
        "native_unit": "passenger_minutes",
        "formula": "passenger_exposure(origin,destination) * d_to_minutes",
        "driver": "passenger_exposure_x_delay",
        "source_type": "HYBRID",
        "critical_inputs": ["d_to_minutes", "passenger_exposure"],
    },
    "P_itinerary": {
        "aspect": "Passenger",
        "native_unit": "events",
        "formula": "itinerary_disruption_events",
        "driver": "supported_itinerary_disruption_events",
        "source_type": "DATA",
        "critical_inputs": ["itinerary_disruption_events"],
    },
    "P_service": {
        "aspect": "Passenger",
        "native_unit": "threshold_events",
        "formula": "service_policy_threshold_events(d_ob_minutes)",
        "driver": "service_policy_threshold_events",
        "source_type": "OPERATIONAL_RULE",
        "critical_inputs": ["d_ob_minutes", "service_policy_reference"],
    },
    "R_operating": {
        "aspect": "Resource",
        "native_unit": "excess_taxi_minutes",
        "formula": "max(0, d_tx_minutes - taxi_reference(origin))",
        "driver": "excess_taxi",
        "source_type": "SCENARIO_ASSUMPTION",
        "critical_inputs": ["d_tx_minutes"],
    },
}


def _typed_output_contract() -> dict[str, Any]:
    component_rows = []
    for component in COMPONENTS:
        formula = dict(_FORMULAS[component])
        if component in {"P_itinerary", "P_service"}:
            support = "ABSTAIN_UNSUPPORTED_CURRENT_DATA2_CONTRACT"
            value_policy = "native_quantity=null;cu_quantity=null;reason_code_required"
        else:
            support = "BOUND_TO_TYPED_M2_V2_CONTEXT_AND_M1_SCENARIO"
            value_policy = "value_allowed_only_when_parent_support_and_reference_lineage_are_valid"
        component_rows.append({
            "component_id": component,
            **formula,
            "support_contract": support,
            "value_policy": value_policy,
            "required_lineage": ("source", "formula", "support", "provenance", "native_artifact_id", "cu_artifact_id"),
        })
    return _artifact({
        "schema_version": "M2_V2_TYPED_OUTPUT_ARTIFACT_CONTRACT_V1",
        "status": "READY_SCHEMA_ONLY_NO_MATERIALIZED_VALUES",
        "component_order": COMPONENTS,
        "component_rows": tuple(component_rows),
        "channel_contract": {
            channel: {
                "component_ids": components,
                "aggregation": "SUM_ONLY_OVER_COMPONENTS_WITH_EXPLICIT_SUPPORT",
                "missing_component_policy": "ABSTAIN_NO_DROP_RENORM_ZERO",
                "value_status": "NOT_RUN_UNTIL_COMPONENT_ARTIFACT_IS_BOUND",
            }
            for channel, components in _CHANNELS.items()
        },
        "scalar_aggregation": {
            "component_ids": COMPONENTS,
            "aggregation_rule": "SUM_OVER_SEVEN_ONLY_IF_ALL_NATIVE_AND_CU_FROZEN",
            "status": "BLOCKED_M2_V2_FORMAL_AGGREGATE_UNRESOLVED",
            "value": None,
            "sortable": False,
            "monetary_mapping": "M4_ONLY",
        },
        "action_effect_policy": "M2_OUTPUT_IS_BASELINE_C0_CU_ACTION_EFFECT_IS_NOT_NATIVE_CONSEQUENCE",
        "no_monetary_overclaim": True,
        "no_unsupported_cu_mapping": True,
        "no_synthetic_values": True,
        "no_zero_fill": True,
    })


def _lineage_schema() -> dict[str, Any]:
    return _artifact({
        "schema_version": "M2_V2_LINEAGE_SCHEMA_V1",
        "status": "READY_FOR_TYPED_ARTIFACT_BINDING",
        "required_identity_fields": (
            "episode_id", "decision_node_id", "scenario_id", "scenario_weight",
            "m1_model_id", "m1_checkpoint_sha256", "m1_scenario_seed_key",
            "pre_lineage", "reference_lineage", "component_id", "native_artifact_id",
            "cu_artifact_id", "cu_registry_id", "cu_registry_hash",
        ),
        "required_semantic_fields": (
            "source", "formula", "native_unit", "support_state", "evidence_class",
            "source_type", "reference_source", "reference_lineage", "confidence",
            "provenance", "reason_code",
        ),
        "aggregation_fields": (
            "channel_id", "included_component_ids", "channel_support_status",
            "scalar_aggregation_rule_id", "scalar_support_status", "sortable",
        ),
        "invariants": (
            "COMPONENT_ORDER_IS_EXACTLY_SEVEN",
            "SCENARIO_ID_AND_WEIGHT_PRESERVED_FROM_M1",
            "PRE_INFORMATION_CUTOFF_IS_NOT_FUTURE",
            "NATIVE_FORMULA_IS_DECLARED_AND_VERSIONED",
            "ABSTAIN_REQUIRES_NULL_VALUE_AND_REASON_CODE",
            "CU_VALUE_REQUIRES_FROZEN_REGISTRY_AND_SCALE_LINEAGE",
            "V1_FIVE_COMPONENT_REGISTRY_IS_NOT_RELABELLED_AS_V2",
            "P_ITINERARY_AND_P_SERVICE_ARE_NOT_ZERO_FILLED",
            "CHANNEL_OR_SCALAR_AGGREGATE_CANNOT_DROP_OR_RENORMALIZE_MISSING_COMPONENTS",
            "M2_DOES_NOT_CREATE_MONETARY_MAPPING",
            "NO_MISSING_LINEAGE_FIELDS",
        ),
        "safety": dict(_SAFETY),
    })


def _validation_report(fixed: dict[str, Any], typed: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "SEVEN_COMPONENT_ONTOLOGY": {"status": "PASS", "detail": "exact component order is bound to current ontology"},
        "TYPED_COMPONENT_CHANNEL_SCALAR_SCHEMA": {"status": "PASS", "detail": "native, CU, channel and scalar fields are explicit"},
        "M2_PRE_OWNERSHIP": {"status": "PASS", "detail": "PRE_OWNERSHIP_GATE_V2=PASS"},
        "NO_MONETARY_OVERCLAIM": {"status": "PASS", "detail": "monetary_mapping_layer=M4_ONLY"},
        "NO_UNSUPPORTED_CU_MAPPING": {"status": "PASS", "detail": "V2 pending CU registry cannot emit values"},
        "NO_MISSING_LINEAGE": {"status": "PASS", "detail": "required source/formula/support/provenance fields are mandatory"},
        "P_ITINERARY_P_SERVICE": {"status": "BLOCKED", "detail": "current contracts require explicit ABSTAIN; no zero fill"},
        "M2_V2_CU_REGISTRY": {"status": "BLOCKED", "detail": "M2_DATA2_FORMAL_CU_V2_PENDING"},
        "M2_V2_FORMAL_AGGREGATE": {"status": "BLOCKED", "detail": "FORMAL_AGGREGATE_UNRESOLVED"},
        "EXP2_EXP3_EXECUTION": {"status": "NOT_RUN", "detail": "preparation only"},
    }
    return _artifact({
        "schema_version": "M2_V2_FREEZE_VALIDATION_REPORT_V1",
        "status": "READY_WITH_FORMAL_AGGREGATE_BLOCKED",
        "preparation_status": "READY",
        "freeze_status": "BLOCKED_M2_V2_VALUES_NOT_MATERIALIZED",
        "checks": checks,
        "fixed_contract": fixed,
        "typed_output_artifact_status": typed["status"],
        "unsupported_value_policy": "ABSTAIN_NULL_WITH_REASON_NO_ZERO_FILL_NO_SYNTHETIC_METRICS",
        "safety": dict(_SAFETY),
    })


def _readiness(fixed: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    gates = fixed["exp2_shared_gates"]
    blockers = tuple(item["status"] for item in gates.values() if str(item["status"]).startswith("BLOCKED_"))
    return _artifact({
        "schema_version": "M2_V2_ARTIFACT_FREEZE_READINESS_V1",
        "status": "M2_V2_ARTIFACT_FREEZE_READY",
        "preparation_status": "READY",
        "artifact_status": "BLOCKED_M2_V2_FORMAL_VALUES_AND_AGGREGATE",
        "seven_component_representation": "READY",
        "typed_output_contract": "READY_SCHEMA_ONLY",
        "lineage_contract": "READY",
        "validation_contract": validation["status"],
        "shared_upstream_blockers": blockers,
        "execution_policy": "DO_NOT_RUN_EXP2_OR_EXP3_UNTIL_M2_V2_ARTIFACT_AND_CU_LINEAGE_ARE_BOUND",
        "safety": dict(_SAFETY),
    })


def prepare_artifact_freeze(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/m2_v2_artifact_freeze_preparation").resolve()
    inputs = _inputs(root)
    fixed = _validate_inputs(inputs)
    typed = _typed_output_contract()
    typed_path = output_root / "M2_V2_TYPED_OUTPUT_ARTIFACT_CONTRACT.json"
    _write(typed_path, typed)
    lineage = _lineage_schema()
    lineage_path = output_root / "M2_V2_LINEAGE_SCHEMA.json"
    _write(lineage_path, lineage)
    validation = _validation_report(fixed, typed)
    validation_path = output_root / "M2_V2_FREEZE_VALIDATION_REPORT.json"
    _write(validation_path, validation)
    readiness = _readiness(fixed, validation)
    readiness_path = output_root / "M2_V2_ARTIFACT_FREEZE_READINESS_REPORT.json"
    _write(readiness_path, readiness)
    manifest = _artifact({
        "schema_version": "M2_V2_ARTIFACT_FREEZE_MANIFEST_V1",
        "status": "M2_V2_ARTIFACT_FREEZE_READY",
        "freeze_scope": "M2_V2_SEVEN_COMPONENT_INTERFACE_AND_LINEAGE_PREPARATION",
        "m1_binding": {
            "model_id": fixed["m1_model_id"],
            "checkpoint_sha256": fixed["m1_checkpoint_sha256"],
            "modified": False,
        },
        "component_order": COMPONENTS,
        "channels": {channel: components for channel, components in _CHANNELS.items()},
        "fixed_contract": {
            key: fixed[key]
            for key in (
                "feature_schema_hash", "cache_hash", "support_hash", "support",
                "loss_version", "m2_design_id", "m2_design_version",
            )
        },
        "existing_v1_registry": {
            "registry_id": fixed["m2_v1_registry_id"],
            "registry_hash": fixed["m2_v1_registry_hash"],
            "formal_scope": fixed["m2_v1_formal_scope"],
            "reuse_policy": "PROVENANCE_ONLY_NOT_V2_RELABELLED",
        },
        "outputs": {
            "typed_output_contract": _relative(typed_path, root),
            "lineage_schema": _relative(lineage_path, root),
            "validation_report": _relative(validation_path, root),
            "readiness_report": _relative(readiness_path, root),
        },
        "inputs": {
            name: {"path": _relative(path, root), "sha256": _file_hash(path)}
            for name, (path, _) in inputs.items()
        },
        "provenance": {
            "source": "M2_V2_DESIGN_AND_CURRENT_TYPED_M2_IMPLEMENTATION",
            "formula_source": "model/M2/drivers.py_and_registries/m2_v2_design.json",
            "pre_ownership": "BOUND_EXISTING_PRE_OWNERSHIP_GATE_V2",
            "monetary_mapping_owner": "M4_ONLY",
        },
        "safety": dict(_SAFETY),
    })
    manifest_path = output_root / "M2_V2_ARTIFACT_FREEZE_MANIFEST.json"
    _write(manifest_path, manifest)
    return {
        "manifest": manifest_path,
        "typed_output_contract": typed_path,
        "lineage_schema": lineage_path,
        "validation_report": validation_path,
        "readiness": readiness_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the gated M2 V2 seven-component artifact freeze.")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    prepare_artifact_freeze(root=Path(__file__).resolve().parents[1], output_root=args.output_root)
    print("M2_V2_ARTIFACT_FREEZE_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
