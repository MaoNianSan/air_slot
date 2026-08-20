"""Freeze the declared Exp2 M4 policy while retaining unresolved tail/mapping gates."""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

from model.M4.residual_risk import (
    M1_POSITIVE_TAIL_DECISION_REQUIRED,
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


def _write_json(path: Path, payload: dict) -> None:
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) == payload:
            return
        raise RuntimeError("EXP2_M4_POLICY_ARTIFACT_EXISTS_WITH_DIFFERENT_CONTENT")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


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
        tail_support_state=TailSupportState.UNRESOLVED,
        tail_reference=(
            "configs/scientific/foundation.yaml:m1_v2_positive_tail_policy",
            M1_POSITIVE_TAIL_DECISION_REQUIRED,
        ),
        provenance=(
            "configs/scientific/foundation.yaml:m4_lambda=0.25",
            "configs/scientific/foundation.yaml:m4_alpha=0.90",
            "CURRENT_MANUSCRIPT_PRINCIPAL_EMPIRICAL_SPECIFICATION",
        ),
    )
    payload = {
        "schema_version": M4_POLICY_SCHEMA_VERSION,
        "status": "FROZEN_POLICY_TAIL_EXECUTION_BLOCKED",
        "policy_id": M4_POLICY_ID,
        "policy_version": "M4_RESIDUAL_RISK_V2",
        "source_reference": M4_POLICY_SOURCE_REFERENCE,
        "policy": policy.model_dump(mode="json"),
        "m4_execution_status": M1_POSITIVE_TAIL_DECISION_REQUIRED,
        "monetary_mapping_status": "MONETARY_MAPPING_BLOCKED",
        "monetary_mapping_reference": "registries/m4_v2_monetary_mapping_design.json",
        "manuscript_experiment_interpretation_note": (
            "Exp2 remains a constructed internal paired-sensitivity lane until a complete "
            "seven-component monetary mapping is independently frozen."
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
