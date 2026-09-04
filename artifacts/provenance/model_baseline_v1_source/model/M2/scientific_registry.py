"""Load and validate the active M2 V4 scientific registries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from model.common.errors import ContractError
from model.M2.freeze import M2Data2FormalCuRegistry

ROOT = Path(__file__).resolve().parents[2]
PASSENGER_DESIGN_PATH = ROOT / "registries" / "m2_v4_passenger_consequence_design.json"
M2_CU_REGISTRY_PATH = ROOT / "registries" / "m2_data2_formal_cu_v4.json"


def load_active_passenger_consequence_design(path: Path | None = None) -> dict[str, Any]:
    payload = json.loads((path or PASSENGER_DESIGN_PATH).read_text(encoding="utf-8"))
    if payload.get("design_id") != "M2_PASSENGER_CONSEQUENCE_REFERENCE_REFACTOR":
        raise ContractError("M2_V4_PASSENGER_DESIGN_ID_MISMATCH")
    if payload.get("version") != "4.0.0" or payload.get("status") != "FROZEN":
        raise ContractError("M2_V4_PASSENGER_DESIGN_NOT_FROZEN")
    if payload.get("fit_partition") != "TRAIN" or payload.get("fit_year") != 2019:
        raise ContractError("M2_V4_TRAIN_PERIOD_MISMATCH")
    if payload.get("fit_months") != [1, 2, 3, 4, 5, 6] or payload.get("db1b_quarters") != [1, 2]:
        raise ContractError("M2_V4_TRAIN_PERIOD_MISMATCH")
    if payload.get("components", {}).get("P_itinerary", {}).get("itinerary_threshold_minutes") != 45.0:
        raise ContractError("M2_V4_ITINERARY_THRESHOLD_MISMATCH")
    if payload.get("components", {}).get("P_service", {}).get("service_threshold_minutes") != 180.0:
        raise ContractError("M2_V4_SERVICE_THRESHOLD_MISMATCH")
    if payload.get("rmb_mapping_registry") != "M4_RMB_BASE_MAPPING_V2":
        raise ContractError("M2_V4_RMB_REGISTRY_MISMATCH")
    return payload


def load_active_m2_cu_registry(path: Path | None = None) -> M2Data2FormalCuRegistry:
    registry_path = path or M2_CU_REGISTRY_PATH
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if payload.get("registry_id") != "M2_DATA2_FORMAL_CU_V4":
        raise ContractError("M2_ACTIVE_REGISTRY_NOT_V4")
    registry = M2Data2FormalCuRegistry.model_validate(payload)
    if registry.registry_hash != registry.digest():
        raise ContractError("M2_REGISTRY_HASH_MISMATCH")
    return registry


__all__ = ["load_active_m2_cu_registry", "load_active_passenger_consequence_design"]
