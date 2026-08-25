"""Freeze the declared Exp2 M4 policy while retaining unresolved tail/mapping gates."""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

from model.M4.residual_risk import (
    ResidualRiskPolicy,
    RiskPolicyStatus,
    TailSupportState,
)
from model.common.identity import content_id


M4_POLICY_FILENAME = "DATA2_DEV_PILOT_M4_RISK_POLICY.json"
M4_POLICY_SCHEMA_VERSION = "AIR_SLOT_EXP2_M4_POLICY_BINDING_V1"
M4_POLICY_FREEZE_ID = "EXP2_DATA2_DEVELOPMENT_PILOT_M4_POLICY_V1"
M4_POLICY_ID = "EXP2_DATA2_DEVELOPMENT_RESIDUAL_RISK_POLICY_V1"
M4_POLICY_SOURCE_REFERENCE = "configs/scientific/foundation.yaml:manuscript_principal_empirical_specification"
EUR_MAPPING_REGISTRY = "registries/m4_eur_mapping_assumption_grounded_v1.json"
MONETARY_MAPPING_STATUS_FROZEN = "FROZEN_ASSUMPTION_GROUNDED"
FIVE_ANCHOR_COMPONENTS = (
    "F_continuity", "F_execution", "F_propagation", "P_time", "R_operating",
)
PENDING_MONETARY_COMPONENTS = ("P_itinerary", "P_service")


def _write_json(path: Path, payload: dict) -> None:
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) == payload:
            return
        raise RuntimeError("EXP2_M4_POLICY_ARTIFACT_EXISTS_WITH_DIFFERENT_CONTENT")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _eur_mapping_anchor_state(root: Path) -> tuple[str, tuple[str, ...]]:
    """Registry hash + pending (HUMAN_DECISION_REQUIRED) components, D1 freeze."""
    payload = json.loads((root / EUR_MAPPING_REGISTRY).read_text(encoding="utf-8"))
    pending = tuple(
        rule["component_id"]
        for rule in payload["ops_components"]
        if rule["anchor_status"] == "HUMAN_DECISION_REQUIRED"
    )
    return str(payload["registry_hash"]), pending


def _eur_mapping_ranking_definition(root: Path, registry_hash: str) -> dict:
    payload = json.loads((root / EUR_MAPPING_REGISTRY).read_text(encoding="utf-8"))
    rates = {
        item["component_id"]: {
            band["band_id"]: band["per_cu_money"] for band in item["bands"]
        }
        for item in payload["ops_components"]
    }
    return {
        "subset": "5-ANCHOR SUBSET",
        "components": list(FIVE_ANCHOR_COMPONENTS),
        "units": "constructed_EUR",
        "registry": EUR_MAPPING_REGISTRY,
        "registry_hash": registry_hash,
        "base_rates_per_cu": {
            component: rates[component]["BASE"] for component in FIVE_ANCHOR_COMPONENTS
        },
        "sensitivity_bands": {"LOW": 0.5, "BASE": 1.0, "HIGH": 2.0},
        "semantics": "CONSTRUCTED_INTERNAL_LOSS_NOT_CAUSAL_NOT_REGRET_NOT_OPTIMAL",
        "top1_level": "ASSUMPTION_GROUNDED",
        "expost_level": "ASSUMPTION_GROUNDED",
        "formal_recommendation_level": "ASSUMPTION_GROUNDED",
        "excluded_components": list(PENDING_MONETARY_COMPONENTS),
        "excluded_reason": "MONETARY_ANCHOR_HUMAN_DECISION_REQUIRED_EVENT_COUNTS_ONLY_MONETARY_NOT_ANCHORED",
    }


def materialize_m4_policy(*, root: Path, output_path: Path | None = None) -> dict:
    foundation = yaml.safe_load(
        (root / "configs" / "scientific" / "foundation.yaml").read_text(encoding="utf-8")
    )
    parameters = foundation["parameters"]
    declared_lambda = float(parameters["m4_lambda"]["value"])
    declared_alpha = float(parameters["m4_alpha"]["value"])
    if (declared_lambda, declared_alpha) != (0.25, 0.90):
        raise RuntimeError("EXP2_M4_MANUSCRIPT_POLICY_PARAMETER_MISMATCH")
    policy = ResidualRiskPolicy.create(
        alpha=declared_alpha,
        expected_loss_coefficient=1.0 - declared_lambda,
        cvar_coefficient=declared_lambda,
        risk_metric_version="M4_RESIDUAL_RISK_V2",
        policy_status=RiskPolicyStatus.FROZEN,
        freeze_id=M4_POLICY_FREEZE_ID,
        tail_support_state=TailSupportState.FROZEN_ASSUMPTION_GROUNDED,
        tail_reference=(
            "configs/scientific/foundation.yaml:m1_v2_positive_tail_policy",
            "G_TAIL_T_A_MIXED_REPRESENTATION",
            "G_TAIL_T_B_TWCRPS_AND_MIXED_CRPS_CLOSED_FORM",
            "G_TAIL_T_C_GP_EXCESS_EXPECTATION_AND_LEV",
            "exp/exp2/tail_scores.py",
        ),
        provenance=(
            "configs/scientific/foundation.yaml:m4_lambda=0.25",
            "configs/scientific/foundation.yaml:m4_alpha=0.90",
            "CURRENT_MANUSCRIPT_PRINCIPAL_EMPIRICAL_SPECIFICATION",
        ),
    )
    mapping_hash, pending_anchors = _eur_mapping_anchor_state(root)
    payload = {
        "schema_version": M4_POLICY_SCHEMA_VERSION,
        "status": "FROZEN_POLICY_ASSUMPTION_GROUNDED_TAIL_READY",
        "policy_id": M4_POLICY_ID,
        "policy_version": "M4_RESIDUAL_RISK_V2",
        "source_reference": M4_POLICY_SOURCE_REFERENCE,
        "policy": policy.model_dump(mode="json"),
        "m4_execution_status": "M4_TAIL_ASSUMPTION_GROUNDED_READY",
        "monetary_mapping_status": MONETARY_MAPPING_STATUS_FROZEN,
        "monetary_mapping_reference": EUR_MAPPING_REGISTRY,
        "monetary_mapping_registry_hash": mapping_hash,
        "monetary_mapping_pending_anchor_components": pending_anchors,
        "m4_ranking_definition": _eur_mapping_ranking_definition(root, mapping_hash),
        "manuscript_experiment_interpretation_note": (
            "Tail scoring is ASSUMPTION_GROUNDED (T-BASE/T-PARAM dual track, "
            "exp/exp2/tail_scores.py); it is not empirical tail calibration. "
            "Monetary mapping is a constructed EUR scale anchored on EUROCONTROL "
            "EUR-per-minute literature (72 EUR/min network average; 0.30 EUR per "
            "passenger per delay minute) plus the EU261 EUR regulatory staircase "
            "(tau_comp=180; 150/210 sensitivity); claim statement: 'constructed "
            "scale anchored on EUROCONTROL EUR-basis values, not a currency "
            "conversion'. P_itinerary and P_service per-event anchors stay "
            "HUMAN_DECISION_REQUIRED until a literature value or a user-authorized "
            "assumption is provided. Exp2 remains an assumption-grounded internal "
            "paired-sensitivity lane; the mapping is not an empirical cost."
        ),
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }
    payload["artifact_hash"] = content_id(payload)
    target = output_path or root / "artifacts" / "experiment" / "exp2" / M4_POLICY_FILENAME
    _write_json(target, payload)
    return payload


__all__ = [
    "M4_POLICY_FILENAME",
    "M4_POLICY_SCHEMA_VERSION",
    "materialize_m4_policy",
]
