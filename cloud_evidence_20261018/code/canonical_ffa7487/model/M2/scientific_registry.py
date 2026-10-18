"""Load and validate the active M2 scientific registries.

Two loader families exist:

- ``load_active_m2_cu_registry`` / ``load_active_passenger_consequence_design``
  keep the frozen V4 registry that the legacy Final-Test-era pipelines and
  their recorded artifacts are tied to. They are deliberately unchanged.
- ``load_active_v2_cu_registry`` / ``load_active_v2_passenger_consequence_design``
  load the V5 definition (five principal positive Train medians plus two
  assumption-grounded event normalizations) that the V2 paper chain uses.
  V5 supersedes V4 for the paper chain only; see
  ``registries/passenger_reference_supersession_v3.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from model.common.errors import ContractError
from model.M2.cu.registry import M2Data2FormalCuRegistry

ROOT = Path(__file__).resolve().parents[2]
PASSENGER_DESIGN_PATH = ROOT / "registries" / "m2_v4_passenger_consequence_design.json"
M2_CU_REGISTRY_PATH = ROOT / "registries" / "m2_data2_formal_cu_v4.json"

PASSENGER_DESIGN_V5_PATH = ROOT / "registries" / "m2_v5_passenger_consequence_design.json"
M2_CU_REGISTRY_V5_PATH = ROOT / "registries" / "m2_data2_formal_cu_v5.json"
V5_REGISTRY_ID = "M2_DATA2_FORMAL_CU_V5"
V5_DESIGN_ID = "M2_PASSENGER_CONSEQUENCE_REFERENCE_REFACTOR"
V5_DESIGN_VERSION = "5.0.0"


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


def load_active_v2_cu_registry(path: Path | None = None) -> M2Data2FormalCuRegistry:
    """Load the V5 CU registry used by the V2 paper chain.

    V5 keeps the V4 recomputed Train medians for the five principal consequence
    components and normalizes the two event components with the
    assumption-grounded one-native-event-unit scale (never an empirical median).
    """

    registry_path = path or M2_CU_REGISTRY_V5_PATH
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if payload.get("registry_id") != V5_REGISTRY_ID:
        raise ContractError("M2_V2_ACTIVE_REGISTRY_NOT_V5")
    registry = M2Data2FormalCuRegistry.model_validate(payload)
    if registry.registry_hash != registry.digest():
        raise ContractError("M2_REGISTRY_HASH_MISMATCH")
    return registry


def load_active_v2_passenger_consequence_design(path: Path | None = None) -> dict[str, Any]:
    """Load and validate the V5 passenger-consequence design (V2 chain)."""

    payload = json.loads(
        (path or PASSENGER_DESIGN_V5_PATH).read_text(encoding="utf-8")
    )
    if payload.get("design_id") != V5_DESIGN_ID:
        raise ContractError("M2_V5_PASSENGER_DESIGN_ID_MISMATCH")
    if payload.get("version") != V5_DESIGN_VERSION:
        raise ContractError("M2_V5_PASSENGER_DESIGN_VERSION_MISMATCH")
    if payload.get("fit_partition") != "TRAIN" or payload.get("fit_year") != 2019:
        raise ContractError("M2_V5_TRAIN_PERIOD_MISMATCH")
    if payload.get("fit_months") != [1, 2, 3, 4, 5, 6] or payload.get("db1b_quarters") != [1, 2]:
        raise ContractError("M2_V5_TRAIN_PERIOD_MISMATCH")
    itinerary = payload.get("components", {}).get("P_itinerary", {})
    if itinerary.get("itinerary_threshold_minutes") != 45.0:
        raise ContractError("M2_V5_ITINERARY_THRESHOLD_MISMATCH")
    if "connection_share" not in str(itinerary.get("formula", "")):
        raise ContractError("M2_V5_ITINERARY_CONNECTION_SHARE_MISSING")
    service = payload.get("components", {}).get("P_service", {})
    if service.get("service_threshold_minutes") != 180.0:
        raise ContractError("M2_V5_SERVICE_THRESHOLD_MISMATCH")
    if payload.get("cu_normalization_partition") != {
        "principal_components": [
            "F_continuity",
            "F_execution",
            "F_propagation",
            "P_time",
            "R_operating",
        ],
        "principal_rule": "POSITIVE_TRAIN_PERIOD_MEDIAN",
        "event_components": ["P_itinerary", "P_service"],
        "event_rule": "ASSUMPTION_EVENT_NORMALIZATION",
        "event_scale": 1.0,
    }:
        raise ContractError("M2_V5_CU_NORMALIZATION_PARTITION_MISMATCH")
    if payload.get("final_test_access_count") != 0 or payload.get("paper_full_run") is not False:
        raise ContractError("M2_V5_ACCESS_GUARD_VIOLATION")
    return payload


__all__ = [
    "load_active_m2_cu_registry",
    "load_active_passenger_consequence_design",
    "load_active_v2_cu_registry",
    "load_active_v2_passenger_consequence_design",
]

