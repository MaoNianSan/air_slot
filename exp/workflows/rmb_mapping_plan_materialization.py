"""Materialize and verify the frozen Final Test RMB reporting registry."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


REGISTRY_PATH = Path("registries/m4_rmb_mapping_v1.json")
MAIN_COMPONENTS = (
    "F_continuity",
    "F_execution",
    "F_propagation",
    "P_time",
    "R_operating",
)
EVENT_COMPONENTS = ("P_itinerary", "P_service")


def _digest(payload: dict[str, Any]) -> str:
    canonical = {key: value for key, value in payload.items() if key != "registry_hash"}
    rendered = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(rendered.encode('utf-8')).hexdigest()}"


def registry_payload() -> dict[str, Any]:
    components = []
    for component in MAIN_COMPONENTS:
        components.append(
            {
                "component_id": component,
                "scope_status": "IN_MAIN_MONETARY_SCOPE",
                "mapping_function": "IDENTITY_LINEAR_CU_TO_RMB",
                "beta_k_rmb": {"LOW": 0.5, "BASE": 1.0, "HIGH": 2.0},
                "unit": "RMB_PER_CU",
                "source_type": "FROZEN_REPORTING_MEASUREMENT_MAPPING",
                "currency_conversion": False,
                "zero_fill_allowed": False,
            }
        )
    for component in EVENT_COMPONENTS:
        components.append(
            {
                "component_id": component,
                "scope_status": "NOT_IN_MAIN_MONETARY_SCOPE",
                "mapping_function": None,
                "beta_k_rmb": None,
                "unit": "EVENT_CU_ONLY",
                "source_type": "OPERATIONAL_CONSEQUENCE_ONLY",
                "currency_conversion": False,
                "zero_fill_allowed": False,
                "reason": "NOT_IN_MAIN_MONETARY_SCOPE",
            }
        )
    payload = {
        "schema_version": "M4_RMB_MAPPING_V1",
        "registry_id": "M4_RMB_MAPPING_V1_FINAL_TEST",
        "status": "FROZEN_FINAL_TEST_REPORTING_MAPPING",
        "monetary_system": "RMB",
        "scope": "FINAL_TEST_OUT_OF_TIME_2019_10_12",
        "claim_boundary": "RMB is the frozen reporting and measurement mapping for this Final Test comparison; it is not an EUR-to-RMB conversion or observed monetary ground truth.",
        "rmb_base_mapping": "1_CU_EQUALS_1_RMB",
        "main_monetary_components": list(MAIN_COMPONENTS),
        "excluded_operational_components": list(EVENT_COMPONENTS),
        "components": components,
        "valuation_sensitivity_bands": ["LOW", "BASE", "HIGH"],
        "currency_conversion": "PROHIBITED",
        "renormalization": "PROHIBITED",
        "unsupported_component_policy": "ABSTAIN_NO_ZERO_FILL_NO_IMPUTATION",
    }
    payload["registry_hash"] = _digest(payload)
    return payload


def materialize(*, root: Path) -> Path:
    target = root / REGISTRY_PATH
    payload = registry_payload()
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if target.is_file() and target.read_text(encoding="utf-8") != rendered:
        raise RuntimeError("RMB_MAPPING_REGISTRY_EXISTS_WITH_DIFFERENT_CONTENT")
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(target)
    verify(root=root)
    return target


def verify(*, root: Path) -> dict[str, Any]:
    path = root / REGISTRY_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("registry_hash") != _digest(payload):
        raise RuntimeError("RMB_MAPPING_REGISTRY_HASH_MISMATCH")
    if tuple(payload.get("main_monetary_components", ())) != MAIN_COMPONENTS:
        raise RuntimeError("RMB_MAPPING_MAIN_SCOPE_DRIFT")
    if tuple(payload.get("excluded_operational_components", ())) != EVENT_COMPONENTS:
        raise RuntimeError("RMB_MAPPING_EVENT_SCOPE_DRIFT")
    components = {item["component_id"]: item for item in payload.get("components", ())}
    for component in MAIN_COMPONENTS:
        beta = components[component]["beta_k_rmb"]
        if beta != {"LOW": 0.5, "BASE": 1.0, "HIGH": 2.0}:
            raise RuntimeError("RMB_MAPPING_BETA_DRIFT")
    for component in EVENT_COMPONENTS:
        if components[component]["beta_k_rmb"] is not None:
            raise RuntimeError("RMB_MAPPING_EVENT_ZERO_FILL")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not args.verify:
        materialize(root=root)
    payload = verify(root=root)
    print(json.dumps({"registry_hash": payload["registry_hash"], "registry": str(REGISTRY_PATH)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
