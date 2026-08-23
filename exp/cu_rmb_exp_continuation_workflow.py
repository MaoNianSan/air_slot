"""Continue the paper-aligned C -> CU -> RMB -> risk readiness workflow.

This module binds already-approved M2 CU semantics and the explicit RMB=1
candidate without running experiments or promoting unsupported passenger
components.  It writes versioned decision/readiness artifacts only.
"""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from model.M2.freeze import M2Data2FormalCuRegistry
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id
from model.common.rmb_mapping import RMBMappingRegistry


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

M2_REGISTRY = Path("registries/m2_data2_formal_cu_v1.json")
M2_ARTIFACT = Path(
    "artifacts/experiment/m2_v2_current_stage_consequences_v1/"
    "M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCES.json"
)
M2_MANIFEST = Path(
    "artifacts/experiment/m2_v2_current_stage_consequences_v1/"
    "M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCE_MANIFEST.json"
)
RMB_REGISTRY = Path("registries/m4_cu_rmb_mapping_candidate_v1.json")
RMB_CANDIDATE = Path(
    "artifacts/diagnostics/m4_rmb_mapping_freeze_candidate_v1/"
    "M4_RMB_MAPPING_FREEZE_CANDIDATE.json"
)
M4_POLICY = Path("artifacts/experiment/exp2/DATA2_DEV_PILOT_M4_RISK_POLICY.json")
EXP2_MANIFEST = Path(
    "artifacts/experiment/exp2_formal_development_v9/EXP2_FORMAL_EXECUTION_MANIFEST.json"
)
EXP3_READINESS = Path(
    "artifacts/diagnostics/exp3_formal_execution_preparation_v10/"
    "EXP3_FORMAL_EXECUTION_READINESS_REPORT.json"
)
EXP4_READINESS = Path(
    "artifacts/diagnostics/exp4_formal_execution_preparation_v10/"
    "EXP4_FORMAL_EXECUTION_READINESS_REPORT.json"
)

LITERATURE_REFERENCES = [
    {
        "id": "AIRLINE_RECOVERY_REVIEW_HASSAN_2021",
        "citation": "Hassan, Santos, Vink (2021), Computers and Operations Research 127:105137",
        "doi": "10.1016/j.cor.2020.105137",
        "use": "heterogeneous aircraft, crew, passenger, and integrated recovery consequences",
    },
    {
        "id": "AIRLINE_DISRUPTION_REVIEW_SU_2021",
        "citation": "Su et al. (2021), Engineering 7(4):435-447",
        "doi": "10.1016/j.eng.2020.08.021",
        "use": "disruption-management objectives and operational constraints",
    },
    {
        "id": "INTEGRATED_RECOVERY_HU_2016",
        "citation": "Hu, Song, Zhao, Xu (2016), Transportation Research Part E 87:97-112",
        "doi": "10.1016/j.tre.2016.01.002",
        "use": "integrated aircraft/passenger recovery and consequence mechanisms",
    },
    {
        "id": "MCDA_VIKOR_TOPSIS_OPRICOVIC_2004",
        "citation": "Opricovic and Tzeng (2004), European Journal of Operational Research 156(2):445-455",
        "doi": "10.1016/S0377-2217(03)00020-1",
        "use": "transparent normalization and aggregation choices in multi-criteria decision support",
    },
]


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"CU_RMB_WORKFLOW_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(rendered, encoding="utf-8")
    temp.replace(path)


def _check_safety(payload: Any, label: str) -> None:
    if not isinstance(payload, dict):
        return
    safety = payload.get("safety", payload)
    if safety.get("FINAL_TEST_ACCESS_COUNT", 0) != 0:
        raise RuntimeError(f"CU_RMB_WORKFLOW_FINAL_TEST_NONZERO:{label}")
    if safety.get("FULL", False) is not False or safety.get("PAPER_FULL_RUN", False) is not False:
        raise RuntimeError(f"CU_RMB_WORKFLOW_UNSAFE_SCOPE:{label}")
    for key, value in safety.items():
        if key.endswith("RUNS") and isinstance(value, (int, float)) and value != 0:
            raise RuntimeError(f"CU_RMB_WORKFLOW_EXECUTION_NONZERO:{label}:{key}")


def _literature_options() -> list[dict[str, Any]]:
    return [
        {
            "option_id": "TRAIN_POSITIVE_MEDIAN",
            "formula": "CU_k = q_k / median_train_positive(q_k)",
            "assumption": "component-wise positive Train-period median is a robust, frozen reference scale",
            "advantage": "transparent, unitless, resistant to heterogeneous native units, and already approved in M2_FORMAL_FREEZE",
            "limitation": "not an observed monetary valuation and sensitive to the chosen training reference period",
            "compatibility": "SELECTED_PRINCIPAL",
            "provenance": ["M2_FORMAL_FREEZE", "M2_DATA2_FORMAL_CU_V1"],
        },
        {
            "option_id": "ROBUST_QUANTILE_SCALE",
            "formula": "CU_k = q_k / Q_p(train_positive(q_k))",
            "assumption": "a fixed upper quantile is a stable reference scale",
            "advantage": "less sensitive to extreme values than a maximum",
            "limitation": "introduces an additional percentile decision and is not the approved M2 contract",
            "compatibility": "NOT_SELECTED_ALTERNATIVE",
            "provenance": ["OR_METHOD_MCDA", "SCIENTIFIC_DECISION_NOT_FROZEN"],
        },
        {
            "option_id": "MIN_MAX",
            "formula": "CU_k = (q_k - min_k) / (max_k - min_k)",
            "assumption": "training extrema define a meaningful common interval",
            "advantage": "bounded [0,1] representation",
            "limitation": "unstable under tails and requires a zero/reference policy; conflicts with explicit tail and no-winsorization rules",
            "compatibility": "REJECTED",
            "provenance": ["MCDA_NORMALIZATION_OPTION", "TAIL_POLICY_CONFLICT"],
        },
        {
            "option_id": "Z_SCORE",
            "formula": "CU_k = (q_k - mean_k) / sd_k",
            "assumption": "signed deviations around a mean are meaningful for all components",
            "advantage": "standard statistical scaling",
            "limitation": "allows negative consequence units and is not aligned with nonnegative operational burden",
            "compatibility": "REJECTED",
            "provenance": ["MCDA_NORMALIZATION_OPTION", "NONNEGATIVE_CONSEQUENCE_CONTRACT"],
        },
        {
            "option_id": "RAW_HETEROGENEOUS_SUM",
            "formula": "CU = sum_k q_k",
            "assumption": "native units are commensurate",
            "advantage": "minimal implementation",
            "limitation": "invalid across minutes, passenger-minutes, and exposure-minutes",
            "compatibility": "REJECTED",
            "provenance": ["M2_FORMAL_FREEZE", "HETEROGENEOUS_UNITS"],
        },
    ]


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/cu_rmb_exp_continuation_workflow_v1").resolve()
    paths = {name: root / value for name, value in {
        "m2_registry": M2_REGISTRY,
        "m2_artifact": M2_ARTIFACT,
        "m2_manifest": M2_MANIFEST,
        "rmb_registry": RMB_REGISTRY,
        "rmb_candidate": RMB_CANDIDATE,
        "m4_policy": M4_POLICY,
        "exp2_manifest": EXP2_MANIFEST,
        "exp3_readiness": EXP3_READINESS,
        "exp4_readiness": EXP4_READINESS,
    }.items()}
    if not all(path.is_file() for path in paths.values()):
        missing = [name for name, path in paths.items() if not path.is_file()]
        raise RuntimeError("CU_RMB_WORKFLOW_INPUT_MISSING:" + ",".join(missing))
    loaded = {name: _load(path) for name, path in paths.items()}
    for name, payload in loaded.items():
        _check_safety(payload, name)

    m2_registry = M2Data2FormalCuRegistry.model_validate(loaded["m2_registry"])
    rmb_registry = RMBMappingRegistry.model_validate(loaded["rmb_registry"])
    if tuple(m2_registry.formal_scope) != (
        "F_continuity", "F_execution", "F_propagation", "P_time", "R_operating"
    ):
        raise RuntimeError("CU_RMB_WORKFLOW_M2_FORMAL_SCOPE_CHANGED")
    if tuple(m2_registry.outside_principal_scope) != ("P_itinerary", "P_service"):
        raise RuntimeError("CU_RMB_WORKFLOW_ABSTAIN_SCOPE_CHANGED")
    if rmb_registry.status.value != "TEST_ONLY" or not rmb_registry.executable:
        raise RuntimeError("CU_RMB_WORKFLOW_RMB_CANDIDATE_INVALID")
    if rmb_registry.authoritative:
        raise RuntimeError("CU_RMB_WORKFLOW_RMB_CANDIDATE_MUST_NOT_BE_AUTHORITATIVE")

    literature = {
        "schema_version": "CU_TRANSFORMATION_LITERATURE_REVIEW_V1",
        "status": "REVIEW_COMPLETED_WITH_TRANSPARENT_OPTION_SELECTION",
        "scope": "OR_DECISION_SUPPORT_AND_AIRLINE_DISRUPTION_METHODOLOGY",
        "references": LITERATURE_REFERENCES,
        "options": _literature_options(),
        "selected_option": "TRAIN_POSITIVE_MEDIAN",
        "scientific_note": "The cited literature supports heterogeneous consequence mechanisms and explicit multi-criteria representation; it does not supply observed-currency coefficients for this study.",
        "safety": dict(SAFETY),
    }
    literature["artifact_hash"] = content_id(literature)
    literature_path = output_root / "CU_TRANSFORMATION_LITERATURE_REVIEW.json"
    _write(literature_path, literature)

    abstain = {
        "schema_version": "ABSTAIN_COMPONENT_SCIENTIFIC_DECISION_V1",
        "status": "ABSTAIN_POLICY_SELECTED",
        "principal_strategy": "A_KEEP_ABSTAIN_AND_EVALUATE_SUPPORTED_DIMENSIONS_ONLY",
        "secondary_strategy": "C_SCENARIO_SENSITIVITY_ONLY_WITH_SEPARATE_NON_PRINCIPAL_LABEL",
        "rejected_strategy": "B_EXPLICIT_PROXY_FOR_P_ITINERARY_P_SERVICE",
        "affected_components": ["P_itinerary", "P_service"],
        "justification": [
            "M2_FORMAL_FREEZE explicitly excludes both components from the principal Data2 scope",
            "Data2 has no observed itinerary/service outcomes or action logs for these dimensions",
            "proxy substitution would change the estimand and could be mistaken for supported evidence",
            "scenario sensitivity may be retained only as a separately labelled non-principal diagnostic",
        ],
        "paper_limitation_statement": "Principal results cover the supported five-component consequence basis; itinerary and service consequences remain unresolved and are not zero-filled, renormalized, or represented by an unsupported proxy.",
        "support_rule": "UNAVAILABLE_ABSTAIN_NO_DROP_RENORM_ZERO_PROXY",
        "safety": dict(SAFETY),
    }
    abstain["artifact_hash"] = content_id(abstain)
    abstain_path = output_root / "ABSTAIN_COMPONENT_SCIENTIFIC_DECISION.json"
    _write(abstain_path, abstain)

    m2_binding = {
        "schema_version": "M2_CU_FORMAL_BINDING_V2",
        "status": "M2_CU_FORMAL_BINDING_READY",
        "mapping": "CU_k = q_k / s_k_CU",
        "scale_rule": "POSITIVE_TRAIN_PERIOD_MEDIAN",
        "formal_scope": list(m2_registry.formal_scope),
        "outside_principal_scope": list(m2_registry.outside_principal_scope),
        "aggregation_rule": m2_registry.aggregation_rule,
        "support_rule": m2_registry.support_rule,
        "inputs": {
            "registry": {"path": M2_REGISTRY.as_posix(), "sha256": _hash(paths["m2_registry"])},
            "artifact": {"path": M2_ARTIFACT.as_posix(), "sha256": _hash(paths["m2_artifact"])},
            "manifest": {"path": M2_MANIFEST.as_posix(), "sha256": _hash(paths["m2_manifest"])},
        },
        "abstain_components": ["P_itinerary", "P_service"],
        "no_development_calibration": True,
        "safety": dict(SAFETY),
    }
    m2_binding["artifact_hash"] = content_id(m2_binding)
    m2_binding_path = output_root / "M2_CU_FORMAL_BINDING.json"
    _write(m2_binding_path, m2_binding)

    rmb_binding = {
        "schema_version": "M4_CU_RMB_INTERFACE_BINDING_V3",
        "status": "RMB_BASELINE_BOUND_TEST_ONLY",
        "chain": "C -> CU -> RMB -> risk",
        "c_to_cu": "CU_k = q_k / s_k_CU",
        "cu_to_rmb": "RMB_k = 1.0 * CU_k",
        "aggregation": "RMB = SUM_k RMB_k",
        "rmb_mapping_status": rmb_registry.status.value,
        "authoritative_ranking_allowed": False,
        "real_currency_claim": False,
        "monetary_ground_truth_claim": False,
        "inputs": {
            "m2_binding": {"path": m2_binding_path.as_posix(), "sha256": _hash(m2_binding_path)},
            "rmb_registry": {"path": RMB_REGISTRY.as_posix(), "sha256": _hash(paths["rmb_registry"])},
            "rmb_candidate": {"path": RMB_CANDIDATE.as_posix(), "sha256": _hash(paths["rmb_candidate"])},
        },
        "sensitivity_policy": "0.5x, 1.0x, 2.0x global and component-wise; no selection from Development outcomes",
        "safety": dict(SAFETY),
    }
    rmb_binding["artifact_hash"] = content_id(rmb_binding)
    rmb_binding_path = output_root / "M4_CU_RMB_INTERFACE_BINDING.json"
    _write(rmb_binding_path, rmb_binding)

    m4_readiness = {
        "schema_version": "M4_RISK_EVALUATION_READINESS_V2",
        "status": "SCENARIO_CONDITIONED_NON_AUTHORITATIVE_READY",
        "rmb_mapping": "TEST_ONLY_BASELINE_BOUND",
        "risk_evaluation": "callable_for_sensitivity_only",
        "authoritative_status": "BLOCKED_TEST_ONLY_MAPPING_AND_UNRESOLVED_TAIL_POLICY",
        "abstain_behavior": "any unsupported component causes ABSTAIN; no zero-fill or renormalization",
        "inputs": {
            "rmb_binding": {"path": rmb_binding_path.as_posix(), "sha256": _hash(rmb_binding_path)},
            "m4_policy": {"path": M4_POLICY.as_posix(), "sha256": _hash(paths["m4_policy"])},
        },
        "safety": dict(SAFETY),
    }
    m4_readiness["artifact_hash"] = content_id(m4_readiness)
    m4_readiness_path = output_root / "M4_RISK_EVALUATION_READINESS.json"
    _write(m4_readiness_path, m4_readiness)

    exp2_readiness = {
        "schema_version": "EXP2_EXECUTION_READINESS_AFTER_CU_RMB_V1",
        "status": "BLOCKED_UNSUPPORTED_MAPPING",
        "preparation_status": "READY",
        "reason_codes": [
            "TEST_ONLY_MAPPING_REJECTED_BY_FORMAL_EXP2_GATE",
            "P_ITINERARY_P_SERVICE_OUTSIDE_PRINCIPAL_SCOPE",
            "TAIL_AWARE_SCALAR_METRICS_REMAIN_GATED",
        ],
        "available_scope": "supported five-component representation diagnostics only",
        "source_manifest": {"path": EXP2_MANIFEST.as_posix(), "sha256": _hash(paths["exp2_manifest"])},
        "safety": dict(SAFETY),
    }
    exp2_readiness["artifact_hash"] = content_id(exp2_readiness)
    exp2_path = output_root / "EXP2_EXECUTION_READINESS.json"
    _write(exp2_path, exp2_readiness)

    exp3_readiness = {
        "schema_version": "EXP3_EXECUTION_READINESS_AFTER_CU_RMB_V1",
        "status": "BLOCKED_FORMAL_COHORT_AND_MAPPING",
        "preparation_status": "READY",
        "reason_codes": [
            "BLOCKED_M3_NON_A00_RESPONSE_RULES_NOT_EXECUTABLE",
            "BLOCKED_M4_MAPPING_NOT_AUTHORITATIVE",
            "EXP3_FORMAL_COHORT_BLOCKED",
        ],
        "source_readiness": {"path": EXP3_READINESS.as_posix(), "sha256": _hash(paths["exp3_readiness"])},
        "safety": dict(SAFETY),
    }
    exp3_readiness["artifact_hash"] = content_id(exp3_readiness)
    exp3_path = output_root / "EXP3_EXECUTION_READINESS.json"
    _write(exp3_path, exp3_readiness)

    exp4_readiness = {
        "schema_version": "EXP4_EXECUTION_READINESS_AFTER_CU_RMB_V1",
        "status": "BLOCKED_PREDICTIVE_ARTIFACTS_AND_MAPPING",
        "preparation_status": "READY",
        "reason_codes": [
            "BLOCKED_CURRENT_M1_PREDICTIVE_ARTIFACT_GATES",
            "BLOCKED_M4_MAPPING_NOT_AUTHORITATIVE",
            "DATA1_TYPED_GENERALIZATION_ARTIFACT_NOT_MATERIALIZED",
        ],
        "source_readiness": {"path": EXP4_READINESS.as_posix(), "sha256": _hash(paths["exp4_readiness"])},
        "safety": dict(SAFETY),
    }
    exp4_readiness["artifact_hash"] = content_id(exp4_readiness)
    exp4_path = output_root / "EXP4_EXECUTION_READINESS.json"
    _write(exp4_path, exp4_readiness)

    report = {
        "schema_version": "AIR_SLOT_CU_RMB_EXP_CONTINUATION_WORKFLOW_V1",
        "status": "PAPER_ALIGNED_READINESS_MATERIALIZED_WITH_UPSTREAM_BLOCKERS",
        "chain": "E -> S -> C -> CU -> RMB -> risk -> decision",
        "completed": [
            "literature-oriented CU option review",
            "approved M2 CU transformation binding",
            "ABSTAIN policy decision packet",
            "RMB baseline interface binding",
            "M4 sensitivity readiness",
            "Exp2/Exp3/Exp4 readiness propagation",
        ],
        "scientific_decisions": {
            "cu_transformation": "TRAIN_POSITIVE_MEDIAN",
            "abstain_principal": "KEEP_ABSTAIN",
            "abstain_secondary": "SCENARIO_SENSITIVITY_ONLY",
            "rmb_baseline": "RMB_k = 1.0 * CU_k",
        },
        "next_automatic_action": "NONE_BEFORE_FORMAL_M3_SUPPORT_AND_NON_TEST_M4_MAPPING",
        "safety": dict(SAFETY),
        "artifacts": {
            "literature_review": str(literature_path.resolve()),
            "abstain_decision": str(abstain_path.resolve()),
            "m2_binding": str(m2_binding_path.resolve()),
            "rmb_binding": str(rmb_binding_path.resolve()),
            "m4_readiness": str(m4_readiness_path.resolve()),
            "exp2_readiness": str(exp2_path.resolve()),
            "exp3_readiness": str(exp3_path.resolve()),
            "exp4_readiness": str(exp4_path.resolve()),
        },
    }
    report["artifact_hash"] = content_id(report)
    report_path = output_root / "AIR_SLOT_CU_RMB_EXP_CONTINUATION_WORKFLOW_REPORT.json"
    _write(report_path, report)
    manifest = {
        "schema_version": "AIR_SLOT_CU_RMB_EXP_CONTINUATION_WORKFLOW_MANIFEST_V1",
        "status": report["status"],
        "report": str(report_path.resolve()),
        "report_hash": report["artifact_hash"],
        "safety": dict(SAFETY),
    }
    manifest_path = output_root / "AIR_SLOT_CU_RMB_EXP_CONTINUATION_WORKFLOW_MANIFEST.json"
    _write(manifest_path, manifest)
    return {
        "report": report_path,
        "manifest": manifest_path,
        "literature": literature_path,
        "abstain": abstain_path,
        "m2_binding": m2_binding_path,
        "rmb_binding": rmb_binding_path,
        "m4_readiness": m4_readiness_path,
        "exp2_readiness": exp2_path,
        "exp3_readiness": exp3_path,
        "exp4_readiness": exp4_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize CU/RMB continuation readiness.")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[1], output_root=args.output_root)
    print("AIR_SLOT_CU_RMB_EXP_CONTINUATION_WORKFLOW_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
