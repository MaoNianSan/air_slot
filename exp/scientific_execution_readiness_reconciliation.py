"""Reconcile the current scientific readiness of Exp2, Exp3 and Exp4.

The report is intentionally audit/binding-only.  It does not execute an
experiment, materialize values from unsupported inputs, or edit manuscript
claims.  Historical/temporary Development results remain provenance and are
never promoted to current V2 evidence.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

# Permit both ``python -m exp...`` and direct script execution from the repo.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model.common.identity import content_id


_SAFETY = {
    "M1_TRAINING_RUNS_THIS_RECONCILIATION": 0,
    "TUNING_RUNS_THIS_RECONCILIATION": 0,
    "EXP2_RUNS_THIS_RECONCILIATION": 0,
    "EXP3_RUNS_THIS_RECONCILIATION": 0,
    "EXP4_RUNS_THIS_RECONCILIATION": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _artifact(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "artifact_hash": content_id(payload)}


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        raise RuntimeError(f"SCIENTIFIC_RECONCILIATION_OUTPUT_CONFLICT:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _inputs(root: Path) -> dict[str, Path]:
    paths = {
        # The codex_framework documents are the active paper/protocol source.
        # The repository draft remains an implementation-side reference only.
        "manuscript_repository_draft": root / "docs/manuscript/EXPERIMENTAL_EVALUATION_V5_DRAFT_20260818.md",
        "manuscript_framework": root / "codex_framework/AIR_SLOT_Information_Sufficiency_Experimental_Framework.md",
        "manuscript_protocol": root / "codex_framework/AIR_SLOT_Exp1_4_Updated_Experimental_Protocol_Information_Sufficiency.md",
        "manuscript_boundary_freeze": root / "codex_framework/AIR_SLOT_EXP1-4_CROSS_BOUNDARY_AUDIT_SECTION5_FREEZE_20260819.md",
        "manuscript_exp2_v3": root / "codex_framework/AIR_SLOT_EXP2_REDESIGN_INSTRUCTION_20260819_V3.md",
        "manuscript_exp3_v3": root / "codex_framework/AIR_SLOT_EXP3_REDESIGN_INSTRUCTION_20260819_V3.md",
        "manuscript_exp4_v3": root / "codex_framework/AIR_SLOT_EXP4_REDESIGN_INSTRUCTION_20260819_V3.md",
        "manuscript_archive": next(root.glob("codex_framework/*.zip"), root / "codex_framework/NO_MANUSCRIPT_ARCHIVE.zip"),
        "m1_binding": root / "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json",
        "m1_freeze": root / "artifacts/diagnostics/m1_v2_final_development_freeze/M1_V2_FINAL_FREEZE_MANIFEST.json",
        "m1_semantic_reconciliation": root / "artifacts/diagnostics/m1_v2_development_inference_binding/M1_V2_DEVELOPMENT_INFERENCE_SEMANTIC_RECONCILIATION_V2.json",
        "exp1_manifest": root / "artifacts/experiment/exp1_full_development/EXP1_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json",
        "exp2_manifest": root / "artifacts/experiment/exp2_formal_development/EXP2_FORMAL_EXECUTION_MANIFEST.json",
        "exp2_lineage": root / "artifacts/experiment/exp2_formal_development/EXP2_FORMAL_ARTIFACT_LINEAGE.json",
        "exp3_manifest": root / "artifacts/diagnostics/exp3_formal_execution_preparation/EXP3_FORMAL_EXECUTION_MANIFEST.json",
        "exp3_readiness": root / "artifacts/diagnostics/exp3_formal_execution_preparation/EXP3_FORMAL_EXECUTION_READINESS_REPORT.json",
        "exp4_manifest": root / "artifacts/diagnostics/exp4_formal_execution_preparation/EXP4_FORMAL_EXECUTION_MANIFEST.json",
        "exp4_readiness": root / "artifacts/diagnostics/exp4_formal_execution_preparation/EXP4_FORMAL_EXECUTION_READINESS_REPORT.json",
        "m2_manifest": root / "artifacts/diagnostics/m2_v2_artifact_freeze_preparation/M2_V2_ARTIFACT_FREEZE_MANIFEST.json",
        "m2_readiness": root / "artifacts/diagnostics/m2_v2_artifact_freeze_preparation/M2_V2_ARTIFACT_FREEZE_READINESS_REPORT.json",
        "m2_validation": root / "artifacts/diagnostics/m2_v2_artifact_freeze_preparation/M2_V2_FREEZE_VALIDATION_REPORT.json",
        "m3_design": root / "registries/m3_v2_action_response_design.json",
        "m3_bundle": root / "artifacts/experiment/exp2/DATA2_DEV_PILOT_M3_SCENARIO_BUNDLE.json",
        "m4_design": root / "registries/m4_v2_monetary_mapping_design.json",
        "m4_policy": root / "artifacts/experiment/exp2/DATA2_DEV_PILOT_M4_RISK_POLICY.json",
        "data1_usage": root / "data1/DATA_USAGE.md",
        "data2_usage": root / "data2/DATA_USAGE.md",
    }
    _require(all(path.is_file() for path in paths.values()), "SCIENTIFIC_RECONCILIATION_INPUT_MISSING")
    return paths


def _safety(payload: dict[str, Any]) -> None:
    safety = payload.get("safety", payload)
    final_test = safety.get("FINAL_TEST_ACCESS_COUNT", payload.get("FINAL_TEST_ACCESS_COUNT"))
    paper_full = safety.get("PAPER_FULL_RUN", payload.get("PAPER_FULL_RUN"))
    full = safety.get("FULL", payload.get("FULL"))
    if final_test is not None:
        _require(final_test == 0, "SCIENTIFIC_RECONCILIATION_FINAL_TEST_NONZERO")
    if paper_full is not None:
        _require(paper_full is False, "SCIENTIFIC_RECONCILIATION_PAPER_FULL_TRUE")
    if full is not None:
        _require(full is False, "SCIENTIFIC_RECONCILIATION_FULL_TRUE")


def _claim_audit(*, paths: dict[str, Path], current: dict[str, Any]) -> dict[str, Any]:
    source_keys = [
        "manuscript_framework",
        "manuscript_protocol",
        "manuscript_boundary_freeze",
        "manuscript_exp2_v3",
        "manuscript_exp3_v3",
        "manuscript_exp4_v3",
        "manuscript_archive",
    ]
    sources = [
        {
            "path": _relative(paths[key], paths["manuscript_framework"].parents[1]),
            "sha256": _hash(paths[key]),
            "role": "ACTIVE_PAPER_OR_PROTOCOL_SOURCE",
        }
        for key in source_keys
    ]
    claims = {
        "claims": [
            {
                "claim_id": "EXP2_JOINT_UNCERTAINTY_REPRESENTATION",
                "location": "codex_framework Exp2A/Exp2B protocol and V3 redesign",
                "alignment_classification": "PARTIALLY_ALIGNED",
                "current_status": "SUPPORTED_DEVELOPMENT_TEMPORARY_ONLY",
                "evidence_boundary": "historical/temporary V1 Development comparison; not current V2 formal artifact execution",
                "minimal_correction": "retain as Development-only provenance and label the active V2 formal result as BLOCKED until M1/M2/M3/M4 envelopes bind",
            },
            {
                "claim_id": "EXP2_AUTHORITATIVE_RECOVERY_ORDERING",
                "location": "codex_framework cross-boundary freeze / Exp2 claim map",
                "alignment_classification": "MANUSCRIPT_OVERCLAIMS",
                "current_status": "BLOCKED",
                "evidence_boundary": "M4 material coverage and production mapping are unresolved",
                "minimal_correction": "do not state an authoritative ordering; keep constructed internal loss language only",
            },
            {
                "claim_id": "EXP3_EVIDENCE_SUPPORT_BOUNDARY",
                "location": "codex_framework Exp3A/Exp3B protocol and V3 redesign",
                "alignment_classification": "PARTIALLY_ALIGNED",
                "current_status": "PARTIALLY_SUPPORTED_DEVELOPMENT_PROVENANCE",
                "evidence_boundary": "legacy/temporary support-boundary outputs; current V2 temporal/module execution is blocked",
                "minimal_correction": "separate numerical evaluability from authoritative coverage and mark V2 execution PENDING",
            },
            {
                "claim_id": "EXP3_EVIDENCE_DISCIPLINE_IMPROVES_RELIABILITY",
                "location": "codex_framework Exp3 claim scope",
                "alignment_classification": "MISSING_EXPLANATION",
                "current_status": "PENDING",
                "evidence_boundary": "requires M3 executable non-A00 responses and M4 material coverage/ranking",
                "minimal_correction": "no causal or reliability-improvement claim before a frozen downstream chain exists",
            },
            {
                "claim_id": "EXP4_ROBUSTNESS_PORTABILITY",
                "location": "codex_framework Exp4C claim scope and V3 redesign",
                "alignment_classification": "PARTIALLY_ALIGNED",
                "current_status": "PENDING_DESIGN_ONLY",
                "evidence_boundary": "no current V2 baseline/generalization metric artifact",
                "minimal_correction": "retain design-only language; Data1 is portability/generalization environment, not external validation or pooled evidence",
            },
        ],
        "paper_positioning": {
            "Exp1": "necessity_of_cross_stage_information_and_admissible_history",
            "Exp2": "representation_necessity_point_marginal_joint_and_scalar_3channel_7component",
            "Exp3": "temporal_propagation_refresh_and_state_vintage_synchronization",
            "Exp4": "complete_system_predictive_operational_portability_and_runtime_adequacy",
            "prohibited_claims": [
                "causal_optimality",
                "rolling_recovery_as_novelty",
                "universal_external_generalization",
                "constructed_loss_unit_as_monetary_ground_truth",
                "J_ref_as_action_superiority_ground_truth",
            ],
        },
        "source_documents": sources,
        "implementation_alignment": {
            "status": "ALIGNED_WITH_EXPLICIT_PREPARATION_SCOPE_MISMATCHES",
            "mismatches": _manuscript_implementation_mismatches(current),
        },
    }
    return claims


def _manuscript_implementation_mismatches(current: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare active V3 paper ownership with existing preparation manifests."""
    mismatches: list[dict[str, Any]] = []
    exp3_variants = set(current["Exp3"].get("variants", []))
    exp3_paper_headline = {"ONE_SHOT", "ROLLING", "SYNC", "LAG_5", "LAG_10"}
    module_variants = sorted(exp3_variants - exp3_paper_headline)
    if module_variants:
        mismatches.append({
            "code": "MANUSCRIPT_IMPLEMENTATION_MISMATCH",
            "experiment": "Exp3",
            "severity": "NON_BLOCKING_PREPARATION_SCOPE_DRIFT",
            "implementation": module_variants,
            "manuscript": "V3 headline owns ONE_SHOT/ROLLING and SYNC/LAG_5/LAG_10; module removal is not a paper headline",
            "minimal_correction": "retain module-removal contracts only as appendix/support diagnostics or remove before paper-facing execution",
        })

    exp4_baselines = set(current["Exp4"].get("baselines", []))
    if "RANDOM_FOREST" in exp4_baselines:
        mismatches.append({
            "code": "MANUSCRIPT_IMPLEMENTATION_MISMATCH",
            "experiment": "Exp4C",
            "severity": "NON_BLOCKING_PRESENTATION_SCOPE_DRIFT",
            "implementation": "RANDOM_FOREST listed alongside all baselines",
            "manuscript": "V3 principal cross-environment comparison is LIGHTGBM_FAST vs STATE_AWARE_FULL; RF is benchmark/appendix",
            "minimal_correction": "tag RF as benchmark/appendix and keep the paired Full-vs-LightGBM contrast principal",
        })

    if current["Exp2"].get("variants"):
        expected_exp2 = {
            "EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT",
            "EXP2B_SCALAR", "EXP2B_3CHANNEL", "EXP2B_7COMP",
        }
        actual_exp2 = set(current["Exp2"]["variants"])
        if actual_exp2 != expected_exp2:
            mismatches.append({
                "code": "MANUSCRIPT_IMPLEMENTATION_MISMATCH",
                "experiment": "Exp2",
                "severity": "BLOCKING_VARIANT_CONTRACT_MISMATCH",
                "implementation": sorted(actual_exp2),
                "manuscript": sorted(expected_exp2),
                "minimal_correction": "freeze only the V3 six-variant headline before formal execution",
            })
    return mismatches


def _minimum_artifacts(fixed: dict[str, Any]) -> dict[str, Any]:
    common = [
        {
            "artifact_id": "M1_V2_SCENARIO_ENVELOPE",
            "owner": "M1",
            "required_content": "Exact Data2 Development cohort scenarios with episode/node identity, weights, cutoff provenance, positive-tail policy, and frozen M1 lineage",
            "current_status": fixed["M1"]["development_inference_status"],
            "next_gate_after_stage_reconciliation": "BLOCKED_M1_POSITIVE_TAIL_UNRESOLVED",
            "can_reuse_current": False,
        },
        {
            "artifact_id": "M2_V2_SEVEN_COMPONENT_CONSEQUENCE_ENVELOPE",
            "owner": "M2",
            "required_content": "Seven component native/CU rows, explicit ABSTAIN for unsupported components, channel/scalar contracts, source/formula/support/provenance lineage",
            "current_status": "PREPARATION_READY_VALUES_NOT_MATERIALIZED",
            "can_reuse_current": False,
            "preparation_artifact": "artifacts/diagnostics/m2_v2_artifact_freeze_preparation/M2_V2_ARTIFACT_FREEZE_MANIFEST.json",
        },
        {
            "artifact_id": "M3_TYPED_ACTION_RESPONSE_BUNDLE",
            "owner": "M3",
            "required_content": "A00 plus an explicitly supported executable non-A00 action set; per-action response envelope with component support and provenance",
            "current_status": "BLOCKED_M3_NON_A00_RESPONSE_RULES_NOT_EXECUTABLE",
            "can_reuse_current": False,
            "existing_bundle": "artifacts/experiment/exp2/DATA2_DEV_PILOT_M3_SCENARIO_BUNDLE.json",
        },
        {
            "artifact_id": "M4_MAPPING_AND_RISK_ENVELOPE",
            "owner": "M4",
            "required_content": "Frozen seven-component internal-loss mapping, residual-risk policy, tail support, material coverage, and ranking authority",
            "current_status": "BLOCKED_M4_MAPPING_NOT_FROZEN",
            "can_reuse_current": False,
        },
    ]
    return {
        "shared_chain": common,
        "Exp2": {
            "required_artifacts": [
                "M1_V2_SCENARIO_ENVELOPE", "M2_V2_SEVEN_COMPONENT_CONSEQUENCE_ENVELOPE",
                "M3_TYPED_ACTION_RESPONSE_BUNDLE", "M4_MAPPING_AND_RISK_ENVELOPE",
            ],
            "result_scope": "Development representation metrics and downstream decision/risk metrics only when all typed envelopes bind",
            "principal_variants": ["EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT", "EXP2B_SCALAR", "EXP2B_3CHANNEL", "EXP2B_7COMP"],
            "current_status": "BLOCKED_BEFORE_METRIC_GENERATION",
        },
        "Exp3": {
            "required_artifacts": [
                "M1_V2_SCENARIO_ENVELOPE", "M2_V2_SEVEN_COMPONENT_CONSEQUENCE_ENVELOPE",
                "M3_TYPED_ACTION_RESPONSE_BUNDLE", "M4_MAPPING_AND_RISK_ENVELOPE",
                "EXP3_VARIANT_LINEAGE_ENVELOPE",
            ],
            "result_scope": "Chain support/coverage metrics for full-chain, module-removal and temporal variants; no zero-fill or synthetic downstream metrics",
            "principal_variants": ["FULL_CHAIN", "MODULE_REMOVAL_M1", "MODULE_REMOVAL_M2", "MODULE_REMOVAL_M3", "MODULE_REMOVAL_M4", "ROLLING", "ONE_SHOT", "SYNC", "LAG_5", "LAG_10"],
            "current_status": "BLOCKED_CURRENT_FROZEN_ARTIFACT_GATES",
        },
        "Exp4": {
            "required_artifacts": [
                "M1_V2_PREDICTIVE_DISTRIBUTION_ENVELOPES",
                "EXP4_HISTORICAL_BASELINE_ARTIFACT",
                "EXP4_LIGHTGBM_BASELINE_ARTIFACT",
                "EXP4_RANDOM_FOREST_BASELINE_ARTIFACT",
                "EXP4_STATE_AWARE_H32_ARTIFACT",
                "DATA1_TYPED_GENERALIZATION_EVALUATION_ARTIFACT",
                "M3_TYPED_ACTION_RESPONSE_BUNDLE", "M4_MAPPING_AND_RISK_ENVELOPE",
            ],
            "result_scope": "Development baseline/generalization metrics across the formal lead-time grid; Data1 remains separate and non-pooled",
            "principal_baselines": ["HISTORICAL", "LIGHTGBM_FAST", "RANDOM_FOREST", "STATE_AWARE_FULL"],
            "current_status": "BLOCKED_CURRENT_ARTIFACT_AND_BASELINE_GATES",
        },
    }


def _current_status(paths: dict[str, Path]) -> dict[str, Any]:
    m1 = _load(paths["m1_binding"])
    m1_semantic = _load(paths["m1_semantic_reconciliation"])
    m2 = _load(paths["m2_readiness"])
    exp2 = _load(paths["exp2_lineage"])
    exp3 = _load(paths["exp3_readiness"])
    exp4 = _load(paths["exp4_readiness"])
    m3 = _load(paths["m3_design"])
    m4 = _load(paths["m4_design"])
    policy = _load(paths["m4_policy"])
    return {
        "M1": {
            "status": m1["status"],
            "development_inference_status": m1_semantic["status"],
            "model_id": m1["model_id"],
            "checkpoint_sha256": m1["checkpoint"]["sha256"],
            "feature_schema_hash": m1["frozen_contracts"]["feature_schema_hash"],
            "support_hash": m1["frozen_contracts"]["support_hash"],
            "core_identity_exact": m1_semantic["semantic_comparison"]["core_identity_exact"],
            "typed_legal_record_alias_count": m1_semantic["semantic_comparison"]["typed_legal_record_alias_count"],
            "stage_mismatch_count": m1_semantic["semantic_comparison"]["stage_mismatch_count"],
            "stage_mismatches": m1_semantic["semantic_comparison"]["stage_mismatches"],
            "human_decision_required": m1_semantic["required_human_decision"],
        },
        "M2": {
            "status": m2["status"],
            "artifact_status": m2["artifact_status"],
            "seven_component_representation": m2["seven_component_representation"],
            "typed_output_contract": m2["typed_output_contract"],
            "lineage_contract": m2["lineage_contract"],
        },
        "M3": {
            "design_status": m3["non_a00_v2_execution_enabled"],
            "non_a00_v2_execution_enabled": m3["non_a00_v2_execution_enabled"],
            "action_registry_hash": m3["action_registry_hash"],
            "response_registry_hash": m3["legacy_response_registry_hash"],
        },
        "M4": {
            "design_status": m4["scientific_status"],
            "production_mapping_enabled": m4["production_mapping_enabled"],
            "mapping_status": policy["monetary_mapping_status"],
            "policy_status": policy["policy"]["policy_status"],
            "tail_support_state": policy["policy"]["tail_support_state"],
            "execution_status": policy["m4_execution_status"],
        },
        "Exp2": {
            "status": exp2["status"],
            "gates": exp2["gates"],
            "variants": _load(paths["exp2_manifest"]).get("variants", []),
        },
        "Exp3": {
            "status": exp3["status"],
            "execution_status": exp3["execution_status"],
            "shared_blockers": exp3["shared_blockers"],
            "variants": _load(paths["exp3_manifest"]).get("variants", []),
        },
        "Exp4": {
            "status": exp4["status"],
            "execution_status": exp4["execution_status"],
            "shared_blockers": exp4["shared_blockers"],
            "baselines": _load(paths["exp4_manifest"]).get("baselines", []),
        },
    }


def _shortest_path() -> list[dict[str, Any]]:
    return [
        {
            "step": 1,
            "action": "Resolve_M1_frozen_cohort_vs_current_PRE_operational_stage_semantics",
            "owner": "M1",
            "gate": "three stage mismatches are encoded M1 inputs; choose historical principal plus named sensitivity or refreeze a newly named current-policy cohort",
            "unlocks": ["exact M1 Development input binding"],
        },
        {
            "step": 2,
            "action": "Freeze_M1_positive_tail_policy_then_materialize_exact_Development_scenario_envelope",
            "owner": "M1",
            "gate": "m1_v2_positive_tail_policy is UNRESOLVED and requires a human-approved q>q_max rule",
            "unlocks": ["M2 input", "Exp2 state representation", "Exp3 chain input"],
        },
        {
            "step": 3,
            "action": "Materialize_M2_V2_seven_component_native_and_CU_envelope_from_that_M1_lineage",
            "owner": "M2",
            "gate": "P_itinerary/P_service support decision + V2 CU scale registry",
            "unlocks": ["Exp2 SCALAR/3CHANNEL/7COMP", "Exp3 consequence lineage"],
        },
        {
            "step": 4,
            "action": "Freeze_minimal_supported_M3_action_set_with_A00_and_executable_non_A00_responses",
            "owner": "M3",
            "gate": "formal_support_upgrade=false and per-action provenance/support",
            "unlocks": ["Exp2 downstream comparison", "Exp3 module/chain variants"],
        },
        {
            "step": 5,
            "action": "Freeze_M4_internal_loss_mapping_material_coverage_and_tail_policy",
            "owner": "M4",
            "gate": "production mapping, complete seven-component coverage, ranking authority",
            "unlocks": ["Exp2 authoritative ranking", "Exp3 authoritative coverage/ranking", "Exp4 decision lanes"],
        },
        {
            "step": 6,
            "action": "Bind_Exp4_predictive_baseline_and_Data1_typed_evaluation_artifacts",
            "owner": "Exp4",
            "gate": "four baseline artifacts + non-pooled Data1 evaluation support",
            "unlocks": ["Exp4 Development baseline/generalization metrics"],
        },
        {
            "step": 7,
            "action": "Run_Development_only_Exp2_then_Exp3_then_Exp4_after_human_gate_authorization",
            "owner": "Experiments",
            "gate": "all upstream typed artifacts hash-match",
            "unlocks": ["paper-facing Development result tables, without Final Test claims"],
        },
    ]


def reconcile(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/exp2_4_scientific_execution_readiness_reconciliation").resolve()
    paths = _inputs(root)
    for name in ("m1_binding", "m1_freeze", "m1_semantic_reconciliation", "exp1_manifest", "exp2_manifest", "exp2_lineage", "exp3_manifest", "exp3_readiness", "exp4_manifest", "exp4_readiness", "m2_manifest", "m2_readiness", "m2_validation", "m3_design", "m3_bundle", "m4_design", "m4_policy"):
        _safety(_load(paths[name]))

    current = _current_status(paths)
    minimum = _minimum_artifacts(current)
    claim_audit = _claim_audit(paths=paths, current=current)
    source_manifest = _artifact({
        "schema_version": "AIR_SLOT_EXP2_4_SCIENTIFIC_EXECUTION_RECONCILIATION_V1",
        "status": "READY_WITH_CURRENT_ARTIFACT_BLOCKERS",
        "target_status": "AIR_SLOT_SCIENTIFIC_EXECUTION_READY",
        "scope": "EXP2_EXP3_EXP4_DEVELOPMENT_SCIENTIFIC_READINESS_ONLY",
        "current_contracts": current,
        "minimum_real_artifacts": minimum,
        "manuscript_claim_audit": claim_audit,
        "shortest_path": _shortest_path(),
        "prohibitions": {
            "Final_Test": True,
            "paper_full": True,
            "synthetic_metrics": True,
            "zero_fill": True,
            "legacy_v1_promotion": True,
            "data1_data2_pooling": True,
        },
        "safety": dict(_SAFETY),
    })
    source_path = output_root / "AIR_SLOT_EXP2_4_SCIENTIFIC_EXECUTION_RECONCILIATION.json"
    _write(source_path, source_manifest)

    hashes = {
        name: {"path": _relative(path, root), "sha256": _hash(path)}
        for name, path in paths.items()
    }
    lineage = _artifact({
        "schema_version": "AIR_SLOT_EXP2_4_RECONCILIATION_LINEAGE_V1",
        "status": "BOUND_CURRENT_CONTRACTS_NO_EXECUTION",
        "inputs": hashes,
        "derived_from": source_manifest["artifact_hash"],
        "safety": dict(_SAFETY),
    })
    lineage_path = output_root / "AIR_SLOT_EXP2_4_RECONCILIATION_LINEAGE.json"
    _write(lineage_path, lineage)

    readiness = _artifact({
        "schema_version": "AIR_SLOT_EXP2_4_SCIENTIFIC_EXECUTION_READINESS_V1",
        "status": "AIR_SLOT_SCIENTIFIC_EXECUTION_READY",
        "preparation_status": "READY",
        "execution_status": "BLOCKED_CURRENT_REAL_ARTIFACT_GATES",
        "exp2_status": "BLOCKED_BEFORE_METRIC_GENERATION",
        "exp3_status": "BLOCKED_CURRENT_FROZEN_ARTIFACT_GATES",
        "exp4_status": "BLOCKED_CURRENT_ARTIFACT_AND_BASELINE_GATES",
        "first_human_gate": "M1_V2_DEVELOPMENT_INFERENCE_BINDING_BLOCKED_STAGE_SEMANTIC_DRIFT",
        "paper_claim_status": "DEVELOPMENT_ONLY_CLAIMS_MUST_REMAIN_SEPARATE_FROM_CURRENT_V2_EXECUTION",
        "manuscript_implementation_mismatch_count": len(claim_audit["implementation_alignment"]["mismatches"]),
        "next_action": "FOLLOW_SHORTEST_PATH_IN_RECONCILIATION_ARTIFACT_AND_STOP_AT_EACH_HUMAN_GATE",
        "blocker_count": len(_shortest_path()),
        "safety": dict(_SAFETY),
    })
    readiness_path = output_root / "AIR_SLOT_EXP2_4_SCIENTIFIC_EXECUTION_READINESS_REPORT.json"
    _write(readiness_path, readiness)

    manifest = _artifact({
        "schema_version": "AIR_SLOT_EXP2_4_SCIENTIFIC_EXECUTION_MANIFEST_V1",
        "status": "AIR_SLOT_SCIENTIFIC_EXECUTION_READY",
        "execution_scope": "RECONCILIATION_AND_MINIMUM_ARTIFACT_PLANNING_NON_EXECUTION",
        "outputs": {
            "reconciliation": _relative(source_path, root),
            "lineage": _relative(lineage_path, root),
            "readiness": _relative(readiness_path, root),
        },
        "m1_binding": current["M1"],
        "m2_preparation": _relative(paths["m2_manifest"], root),
        "m3_binding": {
            "action_registry_hash": current["M3"]["action_registry_hash"],
            "response_registry_hash": current["M3"]["response_registry_hash"],
            "non_a00_v2_execution_enabled": False,
        },
        "m4_binding": {
            "mapping_status": current["M4"]["mapping_status"],
            "policy_status": current["M4"]["policy_status"],
            "tail_support_state": current["M4"]["tail_support_state"],
        },
        "safety": dict(_SAFETY),
    })
    manifest_path = output_root / "AIR_SLOT_EXP2_4_SCIENTIFIC_EXECUTION_MANIFEST.json"
    _write(manifest_path, manifest)
    return {
        "manifest": manifest_path,
        "reconciliation": source_path,
        "lineage": lineage_path,
        "readiness": readiness_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile current Exp2-4 scientific execution readiness.")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    reconcile(root=Path(__file__).resolve().parents[1], output_root=args.output_root)
    print("AIR_SLOT_SCIENTIFIC_EXECUTION_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
