"""Load the frozen model-owned M4 measurement and risk registries."""

from __future__ import annotations

import json
from pathlib import Path

from model.common.monetary_system import (
    MonetaryMappingFunction,
    MonetaryMappingParameter,
    MonetaryMappingRegistry,
    MonetaryMappingRule,
    MonetaryMappingStatus,
    MonetarySourceType,
)
from model.common.paths import project_path

PRINCIPAL_RMB_COMPONENTS = (
    "F_continuity",
    "F_execution",
    "F_propagation",
    "P_time",
    "P_itinerary",
    "P_service",
    "R_operating",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_active_rmb_mapping(
    path: Path | None = None,
) -> MonetaryMappingRegistry:
    payload = _read(path or project_path("registries", "m4_rmb_base_mapping_v2.json"))
    if payload["scientific_status"] != "FROZEN":
        raise ValueError("M4_RMB_BASE_MAPPING_NOT_FROZEN")
    if payload["implementation_status"] != "MATCH":
        raise ValueError("M4_RMB_BASE_MAPPING_IMPLEMENTATION_MISMATCH")
    if payload["measurement_system"] != "RMB" or payload["base_beta"] != 1.0:
        raise ValueError("M4_RMB_BASE_MAPPING_VALUE_MISMATCH")
    components = tuple(payload["component_ids"])
    if tuple(components) != PRINCIPAL_RMB_COMPONENTS:
        raise ValueError("M4_RMB_BASE_MAPPING_SCOPE_MISMATCH")
    freeze_id = payload["freeze_id"]
    rules = {}
    for component in components:
        rules[component] = MonetaryMappingRule.create(
            monetary_system_id="RMB",
            component_id=component,
            mapping_function=MonetaryMappingFunction.LINEAR_SCALE,
            parameter_version=payload["version"],
            source_type=MonetarySourceType.SCENARIO_ASSUMPTION,
            reference=(payload["claim_boundary"],),
            freeze_id=freeze_id,
            parameters=(
                MonetaryMappingParameter(
                    parameter_name="money_per_cu",
                    value=1.0,
                    unit="constructed_RMB_per_CU",
                    provenance=("ONE_CU_EQUALS_ONE_RMB_BASE_CONVENTION",),
                ),
            ),
            provenance=tuple(payload["provenance"]),
            rule_id=f"M4_RMB_BASE_{component}_V{payload['version'].split('.')[0]}",
        )
    registry = MonetaryMappingRegistry(
        monetary_system_id="RMB",
        registry_id=payload["registry_id"],
        registry_version=payload["version"],
        freeze_status=MonetaryMappingStatus.FROZEN,
        freeze_id=freeze_id,
        reference_period=payload["reference_period"],
        component_mappings=rules,
        provenance=tuple(payload["provenance"]),
    )
    return registry.model_copy(update={"registry_hash": registry.digest()})


def load_active_risk_policy_payload(path: Path | None = None) -> dict:
    payload = _read(path or project_path("registries", "m4_risk_policy_base_v1.json"))
    if payload["scientific_status"] != "FROZEN":
        raise ValueError("M4_RISK_POLICY_NOT_FROZEN")
    if payload["implementation_status"] != "MATCH":
        raise ValueError("M4_RISK_POLICY_IMPLEMENTATION_MISMATCH")
    if abs(payload["expected_loss_weight"] + payload["cvar_weight"] - 1.0) > 1e-12:
        raise ValueError("M4_RISK_POLICY_WEIGHTS_MUST_SUM_TO_ONE")
    if (
        payload["lambda"] != payload["cvar_weight"]
        or payload["expected_loss_weight"] != 1.0 - payload["lambda"]
        or payload["alpha"] != 0.90
    ):
        raise ValueError("M4_RISK_POLICY_VALUE_MISMATCH")
    return payload


__all__ = [
    "PRINCIPAL_RMB_COMPONENTS",
    "load_active_risk_policy_payload",
    "load_active_rmb_mapping",
]
