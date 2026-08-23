"""Promote the fixed 1.0*CU baseline into the paper's Exp2 internal-loss lane.

The Exp2 protocol calls this quantity ``CONSTRUCTED_INTERNAL_LOSS_UNIT``;
the separate RMB interface remains constructed and non-real-currency.  This
module creates only frozen, content-addressed preparation artifacts.  It does
not execute Exp2 or upgrade M3 scenario responses to empirical support.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id
from exp.exp2.artifacts.artifact_schema import (
    ArtifactSupportStatus,
    Exp2MonetaryMappingBundle,
    Exp2RiskPolicyBundle,
)

from .cu_rmb_exp_continuation_workflow import materialize as materialize_v1


SAFETY = {
    "M1_TRAINING_RUNS": 0,
    "TUNING_RUNS": 0,
    "EXP2_RUNS": 0,
    "EXP3_RUNS": 0,
    "EXP4_RUNS": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "FULL": False,
    "PAPER_FULL_RUN": False,
}


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"CU_RMB_WORKFLOW_V2_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(rendered, encoding="utf-8")
    temp.replace(path)


def _mapping_bundle() -> Exp2MonetaryMappingBundle:
    payload = {
        "mapping_id": "M4_EXP2_CONSTRUCTED_INTERNAL_LOSS_UNIT_V1",
        "schema_version": "AIR_SLOT_EXP2_SCIENTIFIC_ARTIFACT_V1",
        "component_ids": tuple(CONSEQUENCE_COMPONENTS),
        "mapping_function_reference": {
            component: "LINEAR_SCALE:1.0*CU_k"
            for component in CONSEQUENCE_COMPONENTS
        },
        "source_reference": {
            component: (
                "M2_FORMAL_FREEZE:M2_DATA2_FORMAL_CU_V1",
                "M4_RMB_MAPPING_FREEZE_CANDIDATE_20260823",
                "CONSTRUCTED_INTERNAL_LOSS_UNIT_SCOPE",
            )
            for component in CONSEQUENCE_COMPONENTS
        },
        "version": "M4_CONSTRUCTED_INTERNAL_LOSS_UNIT_V1",
        "support_status": ArtifactSupportStatus.FROZEN,
        "interpretation": "CONSTRUCTED_INTERNAL_LOSS_UNIT",
    }
    provisional = Exp2MonetaryMappingBundle.model_construct(hash="sha256:" + "0" * 64, **payload)
    hash_payload = provisional.model_dump(mode="json", exclude={"hash"})
    hashed = {**hash_payload, "hash": content_id(hash_payload)}
    return Exp2MonetaryMappingBundle.model_validate(hashed)


def _risk_policy_bundle() -> Exp2RiskPolicyBundle:
    payload = {
        "policy_id": "M4_EXP2_RESIDUAL_RISK_POLICY_V2",
        "tail_policy": "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS",
        "CVaR_policy": "EXPECTED_LOSS_PLUS_CVAR_ALPHA_0.90",
        "parameters": {
            "alpha": 0.90,
            "expected_loss_coefficient": 0.75,
            "cvar_coefficient": 0.25,
        },
        "version": "M4_RESIDUAL_RISK_V2",
        "support_status": ArtifactSupportStatus.FROZEN,
    }
    provisional = Exp2RiskPolicyBundle.model_construct(hash="sha256:" + "0" * 64, **payload)
    hash_payload = provisional.model_dump(mode="json", exclude={"hash"})
    hashed = {**hash_payload, "hash": content_id(hash_payload)}
    return Exp2RiskPolicyBundle.model_validate(hashed)


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/cu_rmb_exp_continuation_workflow_v2").resolve()
    # Reuse the already validated literature, M2, RMB, and readiness bindings.
    materialize_v1(root=root, output_root=output_root)
    mapping = _mapping_bundle()
    policy = _risk_policy_bundle()
    mapping_path = output_root / "EXP2_M4_CONSTRUCTED_INTERNAL_LOSS_MAPPING_BUNDLE.json"
    policy_path = output_root / "EXP2_M4_RISK_POLICY_BUNDLE.json"
    _write(mapping_path, mapping.model_dump(mode="json"))
    _write(policy_path, policy.model_dump(mode="json"))

    m4 = {
        "schema_version": "M4_FORMAL_INTERNAL_LOSS_READINESS_V2",
        "status": "FORMAL_CONSTRUCTED_INTERNAL_LOSS_BUNDLE_READY",
        "mapping_status": mapping.support_status.value,
        "risk_policy_status": policy.support_status.value,
        "interpretation": mapping.interpretation,
        "rmb_interface_status": "CONSTRUCTED_RMB_BASELINE_RETAINED_SEPARATELY",
        "authoritative_ranking_allowed": False,
        "reason": "M4 bundle is frozen for conditional representation sensitivity; M3 scenario responses remain non-causal and non-authoritative.",
        "mapping_bundle": str(mapping_path.resolve()),
        "risk_policy_bundle": str(policy_path.resolve()),
        "safety": dict(SAFETY),
    }
    m4["artifact_hash"] = content_id(m4)
    m4_path = output_root / "M4_FORMAL_INTERNAL_LOSS_READINESS_V2.json"
    _write(m4_path, m4)

    exp2 = {
        "schema_version": "EXP2_EXECUTION_READINESS_AFTER_CU_RMB_V2",
        "status": "BLOCKED_M3_NON_A00_CONDITIONAL_RESPONSE_GATE",
        "preparation_status": "READY",
        "m4_mapping_gate": "CLOSED_FOR_CONSTRUCTED_INTERNAL_LOSS_SENSITIVITY",
        "reason_codes": [
            "M3_NON_A00_RESPONSES_REMAIN_SCENARIO_ASSUMPTIONS",
            "FORMAL_AUTHORITATIVE_RANKING_FORBIDDEN",
            "TAIL_AWARE_SCALAR_METRICS_REMAIN_GATED",
        ],
        "mapping_bundle": str(mapping_path.resolve()),
        "risk_policy_bundle": str(policy_path.resolve()),
        "safety": dict(SAFETY),
    }
    exp2["artifact_hash"] = content_id(exp2)
    exp2_path = output_root / "EXP2_EXECUTION_READINESS_V2.json"
    _write(exp2_path, exp2)

    exp3 = {
        "schema_version": "EXP3_EXECUTION_READINESS_AFTER_CU_RMB_V2",
        "status": "BLOCKED_M3_FORMAL_COHORT",
        "preparation_status": "READY",
        "m4_mapping_gate": "READY_CONDITIONAL_INTERNAL_LOSS",
        "reason_codes": [
            "BLOCKED_M3_NON_A00_RESPONSE_RULES_NOT_EXECUTABLE",
            "EXP3_FORMAL_COHORT_BLOCKED",
        ],
        "safety": dict(SAFETY),
    }
    exp3["artifact_hash"] = content_id(exp3)
    exp3_path = output_root / "EXP3_EXECUTION_READINESS_V2.json"
    _write(exp3_path, exp3)

    exp4 = {
        "schema_version": "EXP4_EXECUTION_READINESS_AFTER_CU_RMB_V2",
        "status": "BLOCKED_PREDICTIVE_ARTIFACTS",
        "preparation_status": "READY",
        "m4_mapping_gate": "READY_CONDITIONAL_INTERNAL_LOSS",
        "reason_codes": [
            "BLOCKED_CURRENT_M1_PREDICTIVE_ARTIFACT_GATES",
            "DATA1_TYPED_GENERALIZATION_ARTIFACT_NOT_MATERIALIZED",
        ],
        "safety": dict(SAFETY),
    }
    exp4["artifact_hash"] = content_id(exp4)
    exp4_path = output_root / "EXP4_EXECUTION_READINESS_V2.json"
    _write(exp4_path, exp4)

    report = {
        "schema_version": "AIR_SLOT_CU_RMB_EXP_CONTINUATION_WORKFLOW_V2",
        "status": "PAPER_ALIGNED_M4_CLOSED_M3_BLOCKED",
        "chain": "E -> S -> C -> CU -> RMB -> risk -> decision",
        "m4_transition": "TEST_ONLY_RMB_INTERFACE_TO_FROZEN_CONSTRUCTED_INTERNAL_LOSS_BUNDLE",
        "rmb_baseline": "RMB_k = 1.0 * CU_k",
        "scientific_boundary": {
            "real_currency_claim": False,
            "monetary_ground_truth_claim": False,
            "causal_action_effect_claim": False,
            "authoritative_ranking_allowed": False,
        },
        "next_automatic_action": "NONE_BEFORE_M3_FORMAL_SUPPORT_OR_EXPLICIT_CONDITIONAL_EXECUTION_AUTHORIZATION",
        "artifacts": {
            "mapping": str(mapping_path.resolve()),
            "risk_policy": str(policy_path.resolve()),
            "m4_readiness": str(m4_path.resolve()),
            "exp2_readiness": str(exp2_path.resolve()),
            "exp3_readiness": str(exp3_path.resolve()),
            "exp4_readiness": str(exp4_path.resolve()),
        },
        "safety": dict(SAFETY),
    }
    report["artifact_hash"] = content_id(report)
    report_path = output_root / "AIR_SLOT_CU_RMB_EXP_CONTINUATION_WORKFLOW_REPORT_V2.json"
    _write(report_path, report)
    manifest = {
        "schema_version": "AIR_SLOT_CU_RMB_EXP_CONTINUATION_WORKFLOW_MANIFEST_V2",
        "status": report["status"],
        "report": str(report_path.resolve()),
        "report_hash": report["artifact_hash"],
        "safety": dict(SAFETY),
    }
    manifest_path = output_root / "AIR_SLOT_CU_RMB_EXP_CONTINUATION_WORKFLOW_MANIFEST_V2.json"
    _write(manifest_path, manifest)
    return {
        "mapping": mapping_path,
        "risk_policy": policy_path,
        "m4_readiness": m4_path,
        "exp2_readiness": exp2_path,
        "exp3_readiness": exp3_path,
        "exp4_readiness": exp4_path,
        "report": report_path,
        "manifest": manifest_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Close M4 internal-loss readiness without executing experiments.")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[1], output_root=args.output_root)
    print("AIR_SLOT_CU_RMB_EXP_CONTINUATION_WORKFLOW_V2_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
