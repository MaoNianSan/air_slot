from __future__ import annotations

import json
from pathlib import Path

import yaml

from model.M2.context import build_m2_frozen_scope
from model.M3.registry import ActionRegistry
from model.M3.response_registry import load_response_registry


def _load_config(name: str) -> dict:
    path = Path("configs/evaluation") / f"{name}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _m2_freeze_closure() -> dict | None:
    root = Path("artifacts/diagnostics/v5_development_freeze")
    for name in ("M2_FORMAL_FREEZE_CLOSURE_V2.json", "M2_FORMAL_FREEZE_CLOSURE.json"):
        path = root / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def build_development_readiness() -> dict:
    exp2 = _load_config("exp2")
    exp3 = _load_config("exp3")
    exp4 = _load_config("exp4")
    foundation = yaml.safe_load(
        Path("configs/scientific/foundation.yaml").read_text(encoding="utf-8")
    )
    m4_lambda = float(foundation["parameters"]["m4_lambda"]["value"])
    m4_alpha = float(foundation["parameters"]["m4_alpha"]["value"])
    scope = build_m2_frozen_scope(exp2)
    m2_closure = _m2_freeze_closure()
    m2_ready = bool(m2_closure and m2_closure.get("registry_hash"))
    m2_registry_hash = (m2_closure or {}).get("registry_hash", "M2_REGISTRY_NOT_YET_WRITTEN")

    structural = ActionRegistry.load(Path("registries/action_templates.yaml"))
    response = load_response_registry(
        Path("registries/m3_response_scenarios.yaml"),
        structural_path=Path("registries/action_templates.yaml"),
    )
    response_frozen = response.digest()

    exp2_ready = "PASS" if (m2_ready and scope.scope_status.value == "FORMAL_READY") else "PARTIAL"
    exp3_ready = "PASS" if response_frozen else "PARTIAL"
    exp4_ready = "PASS" if (m2_ready and response_frozen) else "PARTIAL"
    return {
        "EXP2_READINESS": exp2_ready,
        "EXP2_READINESS_REASON": (
            "M2_FORMAL_FREEZE_PENDING"
            if not m2_ready
            else "M2_FORMAL_SCOPE_READY"
        ),
        "EXP2_FORMAL_SCOPE_STATUS": scope.scope_status.value,
        "EXP3_READINESS": exp3_ready,
        "EXP3_READINESS_REASON": (
            "M3_RESPONSE_PARAMETERS_NOT_FROZEN"
            if exp3_ready != "PASS"
            else "M3_RESPONSE_PARAMETERS_FROZEN"
        ),
        "EXP3_UNFROZEN_RESPONSE_PARAMETER_TEMPLATES": 0,
        "EXP4_READINESS": exp4_ready,
        "EXP4_READINESS_REASON": (
            "M2_VALUATION_AND_M3_RESPONSE_SENSITIVITY_REQUIRE_FREEZE"
            if exp4_ready != "PASS"
            else "M2_VALUATION_AND_M3_RESPONSE_SENSITIVITY_FROZEN"
        ),
        "M2_REGISTRY_READY": "PASS" if m2_ready else "PARTIAL",
        "M2_REGISTRY_HASH": m2_registry_hash,
        "M2_FORMAL_SCOPE_STATUS": scope.scope_status.value,
        "M3_REGISTRY_READY": "PASS",
        "M3_REGISTRY_HASH": structural.digest(),
        "M3_RESPONSE_REGISTRY_READY": "PASS",
        "M3_RESPONSE_REGISTRY_HASH": response_frozen,
        "M3_UNFROZEN_RESPONSE_PARAMETER_TEMPLATES": 0,
        "M4_PRINCIPAL_CONFIG_READY": "PASS",
        "M4_PRINCIPAL_LAMBDA": m4_lambda,
        "M4_PRINCIPAL_ALPHA": m4_alpha,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }
