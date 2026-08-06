from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent
V3_CONTRACT_PATH = ROOT / "overall_run" / "config" / "m3_response_v3_expanded_provisional.yaml"
V2_CONTRACT_PATH = ROOT / "overall_run" / "config" / "scientific.yaml"
V4_CONTRACT_PATH = ROOT / "overall_run" / "config" / "m3_response_v4_atomic_subitem.yaml"

_VERSION_PATHS = {
    "V2": V2_CONTRACT_PATH,
    "M3_RESPONSE_V2_20260726": V2_CONTRACT_PATH,
    "overall-run-m3-response-v2": V2_CONTRACT_PATH,
    "V3": V3_CONTRACT_PATH,
    "M3_RESPONSE_V3_EXPANDED_PROVISIONAL": V3_CONTRACT_PATH,
    "overall-run-m3-response-v3-provisional": V3_CONTRACT_PATH,
    "V4": V4_CONTRACT_PATH,
    "M3_RESPONSE_V4_ATOMIC_SUBITEM": V4_CONTRACT_PATH,
    "overall-run-m3-response-v4-atomic-subitem": V4_CONTRACT_PATH,
}


def _load_m3(path: Path, key: str = "m3") -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    m3 = payload.get(key)
    if not isinstance(m3, dict):
        raise ValueError(f"M3_ACTION_CONTRACT_MISSING={path}")
    return m3


def load_action_contract(version: str) -> dict[str, Any]:
    token = str(version)
    path = _VERSION_PATHS.get(token)
    if path is None:
        raise ValueError(f"M3_CONTRACT_MISMATCH:unsupported={token}")
    m3 = deepcopy(_load_m3(path, "m3_legacy_v2" if path == V2_CONTRACT_PATH else "m3"))
    is_v4 = path == V4_CONTRACT_PATH
    is_v3 = path == V3_CONTRACT_PATH
    if is_v3:
        for key in ("scientific_approved", "publication_allowed"):
            if not isinstance(m3.get(key), bool):
                raise ValueError(f"M3_ACTION_CONTRACT_BOOLEAN_INVALID={key}")
    if is_v4:
        status = m3.get("status", {})
        for key in ("scientific_approved", "publication_allowed"):
            if not isinstance(status.get(key), bool):
                raise ValueError(f"M3_ACTION_CONTRACT_BOOLEAN_INVALID={key}")
    actions = m3.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError(f"M3_ACTION_CONTRACT_ACTIONS_INVALID={path}")
    id_key = "action_id" if is_v4 else "id"
    ids = [str(item.get(id_key)) for item in actions]
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
    declared_count = int(m3.get("action_count", m3.get("formal_action_count", len(ids))))
    if len(ids) != declared_count:
        raise ValueError("M3_ACTION_CONTRACT_COUNT_MISMATCH")
    stress_ids = {str(value) for value in m3.get("stress_test_action_ids", [])}
    if set(ids) & stress_ids:
        raise ValueError("M3_ACTION_CONTRACT_STRESS_ID_PRESENT")
    m3["formal_action_count"] = declared_count
    m3["action_ids"] = ids
    m3["stress_test_action_ids"] = sorted(stress_ids)
    if is_v4:
        if m3.get("identity", {}).get("name") != "M3_RESPONSE_V4_ATOMIC_SUBITEM":
            raise ValueError("M3_ACTION_CONTRACT_IDENTITY_MISMATCH")
        if m3.get("version", {}).get("action_library") != "M3_ATOMIC_ACTION_LIBRARY_V1":
            raise ValueError("M3_ACTION_CONTRACT_IDENTITY_MISMATCH")
        forbidden = ("PLUS", "WITH", "PACKAGE", "INTEGRATED", "BALANCED", "AGGRESSIVE")
        for item in actions:
            action_id = str(item.get("action_id"))
            text = str(item.get("action_name", "")).upper()
            if action_id in {"A51", "A52", "A53", "A54", "A55"}:
                raise ValueError(f"M3_ATOMIC_ACTION_REQUIRED={action_id}")
            if any(token in text for token in forbidden):
                raise ValueError(f"M3_ATOMIC_ACTION_REQUIRED={item.get('action_id')}")
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
