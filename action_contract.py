from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent
V3_CONTRACT_PATH = ROOT / "overall_run" / "config" / "m3_response_v3_expanded_provisional.yaml"
V2_CONTRACT_PATH = ROOT / "overall_run" / "config" / "scientific.yaml"


def _load_m3(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    m3 = payload.get("m3")
    if not isinstance(m3, dict):
        raise ValueError(f"M3_ACTION_CONTRACT_MISSING={path}")
    return m3


def load_action_contract(version: str) -> dict[str, Any]:
    path = V2_CONTRACT_PATH if "V2" in str(version) else V3_CONTRACT_PATH
    m3 = deepcopy(_load_m3(path))
    is_v3 = "V2" not in str(version)
    if is_v3:
        for key in ("scientific_approved", "publication_allowed"):
            if not isinstance(m3.get(key), bool):
                raise ValueError(f"M3_ACTION_CONTRACT_BOOLEAN_INVALID={key}")
    actions = m3.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError(f"M3_ACTION_CONTRACT_ACTIONS_INVALID={path}")
    ids = [str(item.get("id")) for item in actions]
    if is_v3:
        for item in actions:
            action_id = str(item.get("id"))
            for key in ("capacity_required", "provisional"):
                if not isinstance(item.get(key), bool):
                    raise ValueError(
                        f"M3_ACTION_CONTRACT_BOOLEAN_INVALID={action_id}.{key}"
                    )
    if len(ids) != len(set(ids)):
        raise ValueError("M3_ACTION_CONTRACT_DUPLICATE_ID")
    declared_count = int(m3.get("formal_action_count", len(ids)))
    if len(ids) != declared_count:
        raise ValueError("M3_ACTION_CONTRACT_COUNT_MISMATCH")
    stress_ids = {str(value) for value in m3.get("stress_test_action_ids", [])}
    if set(ids) & stress_ids:
        raise ValueError("M3_ACTION_CONTRACT_STRESS_ID_PRESENT")
    m3["formal_action_count"] = declared_count
    m3["action_ids"] = ids
    m3["stress_test_action_ids"] = sorted(stress_ids)
    return m3


def v3_pre_action_contract() -> dict[str, Any]:
    contract = load_action_contract("V3")
    specs = {
        str(item["id"]): {
            "capacity_required": item.get("capacity_required"),
            "window_type": item.get("window_type"),
            "typed_gates": list(item.get("typed_gates", [])),
        }
        for item in contract["actions"]
    }
    return {
        "action_library_version": contract["action_library_version"],
        "publication_allowed": contract["publication_allowed"],
        "formal_action_count": contract["formal_action_count"],
        "action_ids": list(contract["action_ids"]),
        "action_specs": specs,
    }
