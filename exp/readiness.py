from __future__ import annotations

from pathlib import Path

import yaml

from model.M2.context import build_exp2_fixed_scope_pending
from model.M3.registry import ActionRegistry


def _load_config(name: str) -> dict:
    path = Path("configs/evaluation") / f"{name}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def build_development_readiness() -> dict:
    exp2 = _load_config("exp2")
    exp3 = _load_config("exp3")
    exp4 = _load_config("exp4")
    foundation = yaml.safe_load(
        Path("configs/scientific/foundation.yaml").read_text(encoding="utf-8")
    )
    m4_lambda = float(foundation["parameters"]["m4_lambda"]["value"])
    m4_alpha = float(foundation["parameters"]["m4_alpha"]["value"])
    scope = build_exp2_fixed_scope_pending(exp2)
    registry = ActionRegistry.load(Path("registries/action_templates.yaml"))
    unfrozen_m3 = sum(
        item.response_parameter_status.value == "NOT_FROZEN"
        for item in registry.templates
    )
    exp2_ready = "PASS" if scope.scope_status.value == "FORMAL_READY" else "PARTIAL"
    exp3_ready = "PASS" if unfrozen_m3 == 0 else "PARTIAL"
    exp4_ready = "PARTIAL"
    return {
        "EXP2_READINESS": exp2_ready,
        "EXP2_READINESS_REASON": (
            "M2_FORMAL_FREEZE_PENDING"
            if exp2_ready != "PASS"
            else "M2_FORMAL_SCOPE_READY"
        ),
        "EXP2_FORMAL_SCOPE_STATUS": scope.scope_status.value,
        "EXP3_READINESS": exp3_ready,
        "EXP3_READINESS_REASON": (
            "M3_RESPONSE_PARAMETERS_NOT_FROZEN"
            if exp3_ready != "PASS"
            else "M3_RESPONSE_PARAMETERS_FROZEN"
        ),
        "EXP3_UNFROZEN_RESPONSE_PARAMETER_TEMPLATES": unfrozen_m3,
        "EXP4_READINESS": exp4_ready,
        "EXP4_READINESS_REASON": "M2_VALUATION_AND_M3_RESPONSE_SENSITIVITY_REQUIRE_FREEZE",
        "M3_REGISTRY_READY": "PASS",
        "M3_REGISTRY_HASH": registry.digest(),
        "M3_UNFROZEN_RESPONSE_PARAMETER_TEMPLATES": unfrozen_m3,
        "M4_PRINCIPAL_CONFIG_READY": "PASS",
        "M4_PRINCIPAL_LAMBDA": m4_lambda,
        "M4_PRINCIPAL_ALPHA": m4_alpha,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }
