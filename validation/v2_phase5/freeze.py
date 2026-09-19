"""Phase 5 draft scientific freeze (instruction section 15, draft only).

The Phase 5 deliverable is a *draft*: ``status = DRAFT_NOT_ACTIVATED`` and
``freeze_commit = PENDING``. Nothing here activates the freeze, opens Final Test,
or claims a formal freeze. Phase 6 owns activation.

The draft records the instruction's section-15 checklist, the Phase-5 rulings,
the V4 -> V5 CU supersession, the Train-support numbers, the Development family
artifacts, and the explicit statement that no new Final-Test run happened.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from model.M3.stage1 import (
    ATTENTION_CAPACITY_GRID,
    NOMINAL_ATTENTION_CAPACITY,
    STAGE_I_TIE_BREAK,
)
from model.M3.stage2 import LAMBDA_GRID, LAMBDA_NOMINAL
from model.M3.support import (
    FLOOR_TO_MINUTES,
    HEADROOM_QUANTILE_NOMINAL,
    HEADROOM_QUANTILE_SENSITIVITY,
    QUANTILE_RULE,
    TURNAROUND_QUANTILE_NOMINAL,
    TURNAROUND_QUANTILE_SENSITIVITY,
)
from model.M2.comparison_support import NOMINAL_COMPARISON_SUPPORT_RULE
from model.common.decision_contracts import (
    NOMINAL_COMMON_SUPPORT_MASS,
    PREDEFINED_COMMON_SUPPORT_SENSITIVITY,
)
from model.common.identity import content_id

from .common import (
    DEVELOPMENT_EPISODES,
    DEVELOPMENT_NODE_COUNT,
    CORRECTED_TURNAROUND_REFERENCE_PATH,
    INSTRUCTION_PATH,
    PROJECT_ROOT,
    SCENARIO_COUNT,
    SUPERSEDED_TURNAROUND_REFERENCE_PATH,
    Authorities,
    file_hash,
    read_json,
    write_json,
)


DRAFT_NAME = "v2_scientific_freeze_draft.json"
DRAFT_SUMMARY_NAME = "V2_SCIENTIFIC_FREEZE_SUMMARY.md"
DRAFT_STATUS = "DRAFT_NOT_ACTIVATED"
FREEZE_COMMIT = "PENDING"
REGISTRY_PATH = PROJECT_ROOT / "registries" / "m2_data2_formal_cu_v5.json"

SEVEN_CONSEQUENCE_DEFINITIONS: Mapping[str, str] = {
    "F_continuity": "max(0, T_IB - turnaround_reference)",
    "F_execution": "D_OB",
    "F_propagation": "D_TO * expected_downstream_exposure",
    "P_time": "N_pax * D_TO",
    "P_itinerary": "N_pax * s_conn * I[D_TO > 45]",
    "P_service": "N_pax * I[D_TO >= 180]",
    "R_operating": "D_TX",
}

SPLIT_DEFINITIONS: Mapping[str, Any] = {
    "train": {
        "window": "2019-01-01..2019-06-30",
        "role": "parameter fitting and Train-derived support only",
    },
    "calibration": {
        "window": "2019-07-01..2019-07-31",
        "role": "M1 calibration only",
    },
    "development": {
        "window": "2019-08-01..2019-09-30",
        "episodes": DEVELOPMENT_EPISODES,
        "decision_nodes": DEVELOPMENT_NODE_COUNT,
        "role": "Section-4 Development comparisons",
    },
    "final_test": {
        "window": "2019-10-01 onward",
        "role": "sealed; Phase 7 only",
        "new_access_requested": False,
        "final_test_access_count_this_round": 1,
    },
}

CANONICAL_NODE_RULE = (
    "Rolling decision nodes are rebuilt from the rolling PRE environment; the "
    "published PRE state at the frozen M1 cache position is the cross-artifact "
    "identity authority, and the node's information cutoff may never exceed its "
    "decision time."
)

PRIORITY_SIGNALS: Mapping[str, Any] = {
    "P_C": {
        "role": "UNIQUE_CONSEQUENCE_BASED_PRIORITY_AUTHORITY",
        "definition": "P^C = Phi_C(C^CU)",
        "aggregation": (
            "manuscript fixed domain-balanced mapping: equal weight within the F "
            "and P domains, equal weight across the three domains"
        ),
        "authority": "manuscript section 4 consequence priority",
    },
    "P_D": {
        "role": "PARALLEL_DELAY_COMPARATOR",
        "definition": "P^D = E[D^{+,TO} | Omega^CS]",
        "estimator": "(1 / m^CS) * sum_{s in Omega^CS} w_s * D^{+,TO}_s",
        "authority": "manuscript section 4 eq:empirical_delay_score (lines 336-344)",
        "deviating_legacy_implementation": (
            "exp/shared/recovery_priority.py::summarize_delay_score "
            "(weight sum without m^CS renormalisation, all-or-nothing scenario "
            "support) - recorded deviation, not paper-primary"
        ),
    },
    "shared_selector": {
        "stage1_selector": True,
        "shared_candidate_queue": True,
        "signals_never_mixed": True,
        "a00_recommendation_forbidden": True,
    },
}

STAGE2_TRANSITION = (
    "A proposed recovery action shifts the node's successor departure time by u "
    "minutes inside PRE/TURN stages only; the post-action state is mapped through "
    "the same M2 consequence service. TAXI/COMP stages admit the singleton action "
    "set {0} and return NOT_ACTIONABLE; no action-specific percentage reduction is "
    "ever applied."
)

STAGE2_OBJECTIVE = (
    "J(u) = sum_s w_s * Phi_C(C^CU(s, u)) + lambda * u / U_max, with ties broken "
    "towards the smaller u; the recoverable value is V = J(0) - J(u*)."
)

M4_ATTENTION_LOSS = (
    "L_att = [A*(H*) - A*(H^(r))] / A*(H*), reported with overlap, "
    "entered/displaced nodes, coverage and Kendall/Spearman statistics"
)

M4_RECOVERY_LOSS = (
    "L_rec = sum_i [J_i(u_i^*(r)) - J_i(u_i^*)] / sum_i V_i^* on the fixed cohort "
    "R_g* = H_g^{C,*} intersect StageIISupported; a zero denominator returns "
    "UNDEFINED_ZERO_RECOVERABLE_VALUE, and no L_total is ever constructed"
)

BOOTSTRAP_SPEC = {
    "B": 2000,
    "resampling_unit": "episode_id",
    "paired": True,
    "interval": "percentile_95",
    "shared_plan_and_seed_across_related_metrics": True,
}


def _registry_payload() -> Mapping[str, Any]:
    return read_json(REGISTRY_PATH)


def _sensitivity_block(train_support: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "m_cs": {
            "nominal": NOMINAL_COMMON_SUPPORT_MASS,
            "grid": list(PREDEFINED_COMMON_SUPPORT_SENSITIVITY),
            "status": "NO_MANUSCRIPT_PREDEFINED_SENSITIVITY_VALUES",
        },
        "attention_capacity_q": {
            "nominal": NOMINAL_ATTENTION_CAPACITY,
            "grid": list(ATTENTION_CAPACITY_GRID),
        },
        "stage2_effort_lambda": {
            "nominal": LAMBDA_NOMINAL,
            "grid": list(LAMBDA_GRID),
        },
        "turnaround_lower_bound_quantile": {
            "nominal": TURNAROUND_QUANTILE_NOMINAL,
            "grid": list(TURNAROUND_QUANTILE_SENSITIVITY),
        },
        "headroom_quantile": {
            "nominal": HEADROOM_QUANTILE_NOMINAL,
            "grid": list(HEADROOM_QUANTILE_SENSITIVITY),
        },
        "materialized_train_quantiles": train_support.get("turnaround", {}).get(
            "quantile_minutes"
        ),
        "materialized_u_max": train_support.get("u_max", {}),
    }

def _reference_cells(payload: Mapping[str, Any]) -> dict[str, float]:
    cells = payload.get("cells") or payload.get("airport_cells") or ()
    resolved: dict[str, float] = {}
    for cell in cells:
        airport = str(cell.get("airport_id") or cell.get("airport"))
        value = cell.get("value_minutes", cell.get("value"))
        if value is None:
            raise ValueError(
                f"TURNAROUND_REFERENCE_CELL_WITHOUT_VALUE:{airport}"
            )
        resolved[airport] = float(value)
    return resolved


def _turnaround_reference_precheck(
    *,
    registry: Mapping[str, Any],
    authorities: Authorities,
    train_support: Mapping[str, Any],
) -> dict[str, Any]:
    """Record the 2026-09-19 turnaround-reference freeze precheck.

    The precheck found that the superseded reference ``sha256:7c6ac016...``
    was not stale metadata: it resolved the M2 node-reference bundle at
    decision time. The V2 chain now binds the corrected Data Gate A2
    reference, and the Stage-II lower-tail support stays a separate object.
    """
    lineage = dict(authorities.audit.get("reference_lineage") or {})
    active = dict(
        (registry.get("reference_artifacts") or {}).get("turnaround") or {}
    )
    scale = dict(
        (registry.get("train_scale_artifact") or {}).get("F_continuity") or {}
    )
    quantiles = dict(
        (train_support.get("turnaround") or {}).get("quantile_minutes") or {}
    )
    corrected = read_json(CORRECTED_TURNAROUND_REFERENCE_PATH)
    superseded = read_json(SUPERSEDED_TURNAROUND_REFERENCE_PATH)
    corrected_cells = _reference_cells(corrected)
    superseded_cells = _reference_cells(superseded)
    shared = sorted(set(corrected_cells) & set(superseded_cells))
    deltas = [
        abs(corrected_cells[key] - superseded_cells[key]) for key in shared
    ]
    corrected_global = float(corrected.get("global_value_minutes", 0.0))
    superseded_global = float(superseded.get("global_value_minutes", 0.0))
    return {
        "round": "FREEZE_PRECHECK_20260919",
        "owner": "M2_NODE_REFERENCE_BUNDLE",
        "audit_finding": "SUPERSEDED_REFERENCE_WAS_ACTIVE_NOT_STALE_METADATA",
        "active_call_path": [
            "exp.exp2.development_inputs._reference_payloads",
            "model.M2.context.load_data2_reference_bundle",
            "validation.v2_phase5.common.build_node_binding",
            "model.M2.consequence_service.M2ConsequenceService",
            "F_continuity = max(0, R_IB - turnaround_reference)",
        ],
        "active_reference": {
            "reference_id": active.get("reference_id")
            or lineage.get("turnaround_reference_id"),
            "manifest_freeze_id": active.get("manifest_freeze_id")
            or lineage.get("turnaround_reference_hash"),
            "artifact_hash": active.get("artifact_hash")
            or lineage.get("turnaround_artifact_hash"),
            "path": active.get("path")
            or lineage.get("turnaround_reference_path"),
            "file_hash": lineage.get("turnaround_reference_file_hash"),
            "global_value_minutes": corrected.get("global_value_minutes"),
            "global_sample_count": corrected.get("global_sample_count"),
            "cells_count": corrected.get("cells_count"),
            "semantic_correction": active.get("semantic_correction")
            or corrected.get("semantic_correction"),
            "status": lineage.get(
                "turnaround_reference_status", "CORRECTED_A2_ACTIVE"
            ),
        },
        "superseded_reference": {
            "reference_id": active.get("superseded_reference_id")
            or lineage.get("legacy_turnaround_reference_id"),
            "manifest_freeze_id": active.get("superseded_manifest_freeze_id")
            or lineage.get("legacy_turnaround_reference_hash"),
            "artifact_hash": lineage.get("legacy_turnaround_artifact_hash"),
            "path": active.get("superseded_path")
            or lineage.get("superseded_turnaround_reference_path"),
            "file_hash": lineage.get(
                "superseded_turnaround_reference_file_hash"
            ),
            "global_value_minutes": superseded.get("global_value_minutes"),
            "global_sample_count": superseded.get("global_sample_count"),
            "status": "SUPERSEDED_PROVENANCE_ONLY",
        },
        "reference_delta": {
            "shared_cells": len(shared),
            "changed_cells": sum(1 for delta in deltas if delta > 0.0),
            "max_abs_delta_minutes": max(deltas) if deltas else None,
            "mean_abs_delta_minutes": (
                sum(deltas) / len(deltas) if deltas else None
            ),
            "global_median_delta_minutes": corrected_global - superseded_global,
        },
        "semantics": {
            "node_reference_quantity": (
                "AIRPORT_LEVEL_POSITIVE_TRAIN_MEDIAN_TURNAROUND_REFERENCE "
                "(DATA2_TURNAROUND_REFERENCE@1.0.0, statistic MEDIAN, "
                "global fallback)"
            ),
            "stage2_lower_tail_quantity": "T^{turn,lb} = Q20(T^{turn} | Train)",
            "same_quantity": False,
            "stage2_nominal_minutes": quantiles.get("q20"),
            "scalar_substitution_rejected": True,
            "scalar_substitution_reason": (
                "Replacing the airport-conditioned median reference with the "
                "scalar Q20 bound would redefine F_continuity = "
                "max(0, R_IB - turnaround_reference) and therefore change "
                "the frozen consequence definition."
            ),
        },
        "f_continuity_train_scale_correction": {
            "active_scale_minutes": scale.get("median"),
            "active_positive_n": scale.get("positive_n"),
            "active_population_rows": scale.get("population_rows"),
            "active_artifact_path": scale.get("path"),
            "active_artifact_hash": scale.get("artifact_hash"),
            "superseded_scale_minutes": (
                (scale.get("superseded_scale") or {}).get("median")
            ),
            "reason": "F_continuity reads the corrected node reference",
            "scale_rule_unchanged": "Median_Train(q_k | q_k > 0)",
        },
        "m1_retrained_this_round": False,
        "new_final_test_access_this_round": False,
    }


def build_freeze_draft(
    *,
    authorities: Authorities,
    train_support: Mapping[str, Any],
    family_a: Mapping[str, Any],
    family_b: Mapping[str, Any],
    h8_result: Mapping[str, Any],
    output_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Compose the section-15 draft freeze from the Phase 5 evidence."""

    registry = _registry_payload()
    h16 = authorities.h16_manifest
    phase_dir = Path(output_root) / "artifacts" / "diagnostics" / "v2_phase5_development"
    evidence = {
        "train_support": {
            "path": str(
                phase_dir / "TRAIN_TURNAROUND_HEADROOM_SUMMARY.json"
            ),
            "hash": file_hash(phase_dir / "TRAIN_TURNAROUND_HEADROOM_SUMMARY.json"),
        },
        "family_a": {
            "path": str(phase_dir / "FAMILY_A_STATE_FAMILIES.json"),
            "hash": file_hash(phase_dir / "FAMILY_A_STATE_FAMILIES.json"),
            "artifact_hash": family_a.get("artifact_hash"),
        },
        "family_b": {
            "path": str(phase_dir / "FAMILY_B_REPRESENTATION_FAMILIES.json"),
            "hash": file_hash(phase_dir / "FAMILY_B_REPRESENTATION_FAMILIES.json"),
            "artifact_hash": family_b.get("artifact_hash"),
        },
        "reference_binding_audit": {
            "path": str(phase_dir / "REFERENCE_BINDING_AUDIT.json"),
            "hash": file_hash(phase_dir / "REFERENCE_BINDING_AUDIT.json"),
        },
        "cu_registry_v5": {
            "path": str(REGISTRY_PATH),
            "hash": file_hash(REGISTRY_PATH),
            "registry_hash": registry.get("registry_hash"),
        },
        "instruction": {
            "path": str(INSTRUCTION_PATH),
            "hash": file_hash(INSTRUCTION_PATH),
            "role": "single engineering instruction (rev2)",
        },
        "h8_sensitivity": {
            "manifest_path": h8_result.get("manifest_path"),
            "checkpoint_hash": h8_result.get("manifest", {}).get("checkpoint_hash"),
            "matched_audit_status": h8_result.get("matched_audit", {}).get("status"),
        },
    }
    draft: dict[str, Any] = {
        "schema_version": "V2_SCIENTIFIC_FREEZE_DRAFT_V1",
        "artifact_kind": "SCIENTIFIC_FREEZE_DRAFT",
        "status": DRAFT_STATUS,
        "freeze_commit": FREEZE_COMMIT,
        "activation_owner": "PHASE_6_SCIENTIFIC_FREEZE",
        "activation_requirements": [
            "explicit human release of Phase 6",
            "freeze_commit resolved to the activation commit",
            "status moved from DRAFT_NOT_ACTIVATED to an activated freeze state",
        ],
        "not_a_formal_freeze": True,
        "final_test_access_count": 1,
        "new_final_test_execution": False,
        "new_final_test_statement": (
            "No new Final-Test run was executed in Phase 0-5. The single recorded "
            "Final-Test access predates this work; old Final-Test outputs are not "
            "reusable under the V5 consequence and V2 representation definitions."
        ),
        "split_definitions": dict(SPLIT_DEFINITIONS),
        "canonical_node_rule": CANONICAL_NODE_RULE,
        "common_support_rule": {
            "owner": "M2_COMPARISON_SUPPORT",
            "pre_ownership": "EVIDENCE_AND_DATA_SUPPORT_ONLY",
            "rule_id": NOMINAL_COMPARISON_SUPPORT_RULE,
            "nominal_threshold": NOMINAL_COMMON_SUPPORT_MASS,
            "estimand": "COMMON_SUPPORT_CONDITIONAL",
            "predefined_sensitivity": list(PREDEFINED_COMMON_SUPPORT_SENSITIVITY),
            "sensitivity_status": "NO_MANUSCRIPT_PREDEFINED_SENSITIVITY_VALUES",
            "missing_vs_unsupported_vs_zero": "STRICTLY_DISTINCT",
            "below_threshold_policy": "TYPED_ABSTAIN_NO_ZERO_FILL",
        },
        "primary_m1_model": {
            "model_id": "HISTORY_H16_PRIMARY",
            "model_version": h16.get("model_version"),
            "hidden_size": h16.get("hidden_size"),
            "history_mode": h16.get("history_mode"),
            "training_seed": h16.get("training_seed"),
            "epochs": h16.get("epochs"),
            "optimizer": h16.get("optimizer"),
            "learning_rate": h16.get("learning_rate"),
            "weight_decay": h16.get("weight_decay"),
            "batch_size": h16.get("batch_size"),
            "checkpoint_hash": h16.get("checkpoint_hash"),
            "manifest_hash": authorities.audit.get("h16_manifest_hash"),
            "training_cohort_hash": h16.get("training_cohort_hash"),
            "history_primary_is_h16": True,
            "lower_capacity_sensitivity": {
                "model_id": "HISTORY_H8_SENSITIVITY",
                "hidden_size": h8_result.get("manifest", {}).get("hidden_size"),
                "role": "PREDEFINED_SENSITIVITY_ONLY",
                "matched_contract_status": h8_result.get("matched_audit", {}).get(
                    "status"
                ),
            },
        },
        "calibration": {
            "calibration_id": h16.get("calibration_hash"),
            "calibration_cohort_hash": h16.get("calibration_cohort_hash"),
            "variant_specific": True,
            "reused_h32_temperature": False,
        },
        "reference_representation": {
            "representation_id": "HISTORY_H16:JOINT",
            "temporal": "HISTORY",
            "uncertainty": "JOINT",
            "point_rule": "FROZEN_WEIGHTED_JOINT_MEDOID",
            "marginal_rule": "DETERMINISTIC_COORDINATE_PERMUTATION",
            "marginal_identity_note": (
                "NOT_A_CLAIM_OF_PHYSICAL_INDEPENDENCE"
            ),
            "realized_milestones": "COLLAPSE_TO_WEIGHT_ONE_POINT",
        },
        "scenario_count": SCENARIO_COUNT,
        "consequence_definitions": {
            "version": "M2_DATA2_FORMAL_CU_V5",
            "native_formulas": dict(SEVEN_CONSEQUENCE_DEFINITIONS),
            "cu_mapping": "C_k^CU = q_k / c_k^CU",
            "aggregation_rule": registry.get("aggregation_rule"),
            "support_rule": registry.get("support_rule"),
            "semantic_channels": registry.get("semantic_channels"),
        },
        "cu_references": {
            "registry_id": registry.get("registry_id"),
            "registry_hash": registry.get("registry_hash"),
            "scientific_status": registry.get("scientific_status"),
            "implementation_status": registry.get("implementation_status"),
            "numeric_scale_adoption": registry.get("numeric_scale_adoption"),
            "train_scale_artifact": registry.get("train_scale_artifact"),
            "assumption_scale_artifact": registry.get("assumption_scale_artifact"),
            "reference_artifacts": registry.get("reference_artifacts"),
            "fit_year": registry.get("fit_year"),
            "fit_months": registry.get("fit_months"),
        },
        "turnaround_reference_precheck": _turnaround_reference_precheck(
            registry=registry,
            authorities=authorities,
            train_support=train_support,
        ),
        "priority_signals": dict(PRIORITY_SIGNALS),
        "stage1_attention": {
            "capacity_rule": "K = ceil(q * N)",
            "nominal_q": NOMINAL_ATTENTION_CAPACITY,
            "q_grid": list(ATTENTION_CAPACITY_GRID),
            "tie_break": STAGE_I_TIE_BREAK,
            "a00_never_recommended": True,
            "stage1_operates_on": "COMMON_SUPPORT_NODES_ONLY",
        },
        "stage2_recovery": {
            "actionable_stages": ["PRE", "TURN"],
            "non_actionable_stages": {
                "TAXI": {"action_set": [0], "status": "NOT_ACTIONABLE"},
                "COMP": {"action_set": [0], "status": "NOT_ACTIONABLE"},
            },
            "transition": STAGE2_TRANSITION,
            "turnaround_lower_bound": {
                "definition": "T^{turn,lb} = Q20(T^{turn} | Train)",
                "nominal_quantile": TURNAROUND_QUANTILE_NOMINAL,
                "sensitivity_quantiles": list(TURNAROUND_QUANTILE_SENSITIVITY),
                "quantile_rule": QUANTILE_RULE,
            },
            "u_max": {
                "definition": "U_max = floor5(Q90(H^{+,fact} | Train))",
                "nominal_quantile": HEADROOM_QUANTILE_NOMINAL,
                "sensitivity_quantiles": list(HEADROOM_QUANTILE_SENSITIVITY),
                "floor_to_minutes": FLOOR_TO_MINUTES,
                "nominal_minutes": train_support.get("u_max", {}).get(
                    "nominal_minutes"
                ),
            },
            "action_step_minutes": FLOOR_TO_MINUTES,
            "objective": STAGE2_OBJECTIVE,
            "lambda": {
                "nominal": LAMBDA_NOMINAL,
                "grid": list(LAMBDA_GRID),
                "tie_break": "SMALLER_U",
            },
        },
        "stage2_solver": {
            "formal_path": "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID",
            "parity_backend": "PYOMO_HIGHS",
            "parity_scope": "REPRESENTATIVE_PRE_TURN_CASES_ONLY",
            "long_term_deviation": False,
            "instruction_reference": "instruction rev2 section 11",
        },
        "m4_evaluation": {
            "common_basis_only": True,
            "L_att": M4_ATTENTION_LOSS,
            "L_rec": M4_RECOVERY_LOSS,
            "zero_denominator_status": "UNDEFINED_ZERO_RECOVERABLE_VALUE",
            "fixed_stage2_cohort": (
                "R_g* = H_g^{C,*} intersect StageIISupported"
            ),
            "L_total_constructed": False,
            "monetary_branch": "SECONDARY_INTERPRETATION_ONLY",
        },
        "bootstrap": dict(BOOTSTRAP_SPEC),
        "predefined_sensitivity": _sensitivity_block(train_support),
        "v4_to_v5_supersession": {
            "superseded_registry": registry.get("numeric_scale_adoption", {}).get(
                "previous_registry"
            ),
            "adopted_registry": registry.get("registry_id"),
            "principal_components": "FIVE_TRAIN_POSITIVE_MEDIANS_RETAINED_FROM_V4",
            "event_components": {
                "P_itinerary": {
                    "scale": registry.get("assumption_scale_artifact", {})
                    .get("P_itinerary", {})
                    .get("scale"),
                    "status": "ASSUMPTION_EVENT_NORMALIZATION",
                    "empirical_train_positive_median": False,
                },
                "P_service": {
                    "scale": registry.get("assumption_scale_artifact", {})
                    .get("P_service", {})
                    .get("scale"),
                    "status": "ASSUMPTION_EVENT_NORMALIZATION",
                    "empirical_train_positive_median": False,
                },
            },
            "passenger_formula": (
                "P_itinerary = N_pax * s_conn * I[D_TO > 45] "
                "(DB1B continuation share retained)"
            ),
            "legacy_reference_retained": ["T-100 expected pax", "DB1B connection share"],
        },
        "train_support": {
            "rotation_count": train_support.get("rotation_count"),
            "population_gates": train_support.get("population_gates"),
            "turnaround_quantile_minutes": train_support.get("turnaround", {}).get(
                "quantile_minutes"
            ),
            "u_max_nominal_minutes": train_support.get("u_max", {}).get(
                "nominal_minutes"
            ),
            "action_grid_size": train_support.get("action_grid", {}).get(
                "nominal_size"
            ),
            "artifact_hash": train_support.get("artifact_hash"),
        },
        "development_families": {
            "family_a": {
                "artifact_hash": family_a.get("artifact_hash"),
                "models": sorted(family_a.get("models", {})),
                "selection_use": family_a.get("selection_use"),
                "directional_claims": family_a.get("directional_claims"),
            },
            "family_b": {
                "artifact_hash": family_b.get("artifact_hash"),
                "representations": sorted(family_b.get("representations", {})),
                "selection_use": family_b.get("selection_use"),
                "directional_claims": family_b.get("directional_claims"),
                "variogram_rows_representation_specific": True,
            },
        },
        "rulings_this_round": [
            {
                "id": "R1",
                "ruling": (
                    "P_itinerary = N_pax * s_conn * I[D_TO > 45]; the DB1B "
                    "historical continuation share stays in the formula."
                ),
                "authority": "manuscript body (corrected in the review copy)",
            },
            {
                "id": "R2",
                "ruling": (
                    "CU normalization = five principal positive Train medians plus "
                    "two assumption-grounded event components with scale 1.0."
                ),
                "authority": "owner decision; registry M2_DATA2_FORMAL_CU_V5",
            },
            {
                "id": "R3",
                "ruling": (
                    "Stage-II formal path is exact enumeration; Pyomo+HiGHS is a "
                    "parity backend only."
                ),
                "authority": "instruction rev2 section 11",
            },
            {
                "id": "R4",
                "ruling": (
                    "P^C is the unique consequence-based priority authority; P^D is "
                    "the parallel delay comparator; both share one Stage-I selector."
                ),
                "authority": "instruction rev2 sections 5/7/8",
            },
            {
                "id": "R5",
                "ruling": (
                    "common support m^CS >= 0.90 nominal belongs to M2; PRE owns "
                    "evidence/data support only."
                ),
                "authority": "instruction rev2 sections 5/12",
            },
            {
                "id": "R6",
                "ruling": (
                    "m^CS sensitivity stays empty because the current manuscript "
                    "body predefines no numeric sensitivity values."
                ),
                "authority": "manuscript body; appendix grid is not authoritative",
            },
            {
                "id": "R7",
                "ruling": (
                    "The superseded turnaround reference sha256:7c6ac016 was an "
                    "active M2 node-reference input, not stale metadata. The V2 "
                    "chain binds the corrected Data Gate A2 reference "
                    "(sha256:aa241b90) and keeps the superseded artifact as "
                    "provenance only."
                ),
                "authority": (
                    "freeze-precheck audit 2026-09-19; registry "
                    "M2_DATA2_FORMAL_CU_V5"
                ),
            },
            {
                "id": "R8",
                "ruling": (
                    "The M2 node reference stays the airport-conditioned empirical "
                    "Train median with global fallback; T^{turn,lb} = Q20 = 41 "
                    "minutes stays a separate Stage-II lower-tail support. "
                    "Substituting the scalar Q20 bound into the node reference "
                    "was rejected because it would redefine F_continuity."
                ),
                "authority": (
                    "DATA2_TURNAROUND_REFERENCE@1.0.0 statistic MEDIAN; "
                    "instruction rev2 sections 7/11"
                ),
            },
        ],
        "open_items": [
            {
                "id": "O1",
                "item": "manuscript appendix CU section is not yet synchronised",
                "status": "HUMAN_DECISION_REQUIRED",
            },
            {
                "id": "O2",
                "item": (
                    "m^CS predefined sensitivity values absent from the manuscript "
                    "body"
                ),
                "status": "OPEN_MANUSCRIPT_ITEM",
            },
            {
                "id": "O3",
                "item": (
                    "instruction rev2 contains 14 mechanically truncated "
                    "'\\rightarrow' escapes ('ightarrow') inherited from the source "
                    "attachment; text is unambiguously recoverable but the authority "
                    "document was left byte-identical in Phase 0-5"
                ),
                "status": "OPEN_DOCUMENTATION_ITEM",
            },
            {
                "id": "O4",
                "item": (
                    "four PGV->CLT Development nodes have no admissible reference "
                    "binding and stay typed UNSUPPORTED_REFERENCE"
                ),
                "status": "RECORDED_NOT_ZERO_FILLED",
            },
        ],
        "evidence_artifacts": evidence,
        "final_test_path_touched": False,
    }
    draft["artifact_hash"] = content_id(draft)
    output_root = Path(output_root)
    registry_dir = output_root / "registries"
    registry_dir.mkdir(parents=True, exist_ok=True)
    draft_path = registry_dir / DRAFT_NAME
    write_json(draft_path, draft)
    summary_path = output_root / "docs" / DRAFT_SUMMARY_NAME
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(render_freeze_summary(draft), encoding="utf-8")
    return {
        "draft_path": str(draft_path),
        "draft_hash": file_hash(draft_path),
        "summary_path": str(summary_path),
        "summary_hash": file_hash(summary_path),
        "artifact_hash": draft["artifact_hash"],
        "status": draft["status"],
        "freeze_commit": draft["freeze_commit"],
    }


def render_freeze_summary(draft: Mapping[str, Any]) -> str:
    """Render the human-readable freeze summary (draft, never a formal freeze)."""

    lines: list[str] = [
        "# AirSlot V2 - Scientific Freeze Summary (DRAFT)",
        "",
        f"- status: `{draft['status']}`",
        f"- freeze_commit: `{draft['freeze_commit']}`",
        f"- draft artifact hash: `{draft['artifact_hash']}`",
        "- activation owner: `PHASE_6_SCIENTIFIC_FREEZE` (not executed)",
        "- new Final Test executed this round: `NO` "
        f"(`FINAL_TEST_ACCESS_COUNT={draft['final_test_access_count']}` unchanged)",
        "",
        "This document is a **draft only**. It does not activate the scientific",
        "freeze, does not authorise Final Test, and must not be cited as a formal",
        "freeze.",
        "",
        "## 1. Split definitions",
        "",
    ]
    for name, block in draft["split_definitions"].items():
        details = ", ".join(
            f"{key}={value}" for key, value in block.items() if key != "role"
        )
        lines.append(f"- `{name}`: {details} ({block.get('role')})")
    lines += [
        "",
        "## 2. Canonical node rule",
        "",
        draft["canonical_node_rule"],
        "",
        "## 3. Common support rule",
        "",
    ]
    support = draft["common_support_rule"]
    lines += [
        f"- owner: `{support['owner']}`; PRE: `{support['pre_ownership']}`",
        f"- rule id: `{support['rule_id']}`",
        f"- nominal threshold: `{support['nominal_threshold']}`",
        f"- predefined sensitivity: `{support['predefined_sensitivity']}` "
        f"({support['sensitivity_status']})",
        f"- missing / unsupported / zero: `{support['missing_vs_unsupported_vs_zero']}`",
        f"- below threshold: `{support['below_threshold_policy']}`",
        "",
        "## 4. Primary M1 model and calibration",
        "",
    ]
    model = draft["primary_m1_model"]
    lines += [
        f"- model: `{model['model_id']}` (`{model['model_version']}`)",
        f"- hidden size: `{model['hidden_size']}`; history mode: `{model['history_mode']}`",
        f"- seed `{model['training_seed']}`, epochs `{model['epochs']}`, "
        f"optimizer `{model['optimizer']}`, lr `{model['learning_rate']}`, "
        f"weight decay `{model['weight_decay']}`, batch `{model['batch_size']}`",
        f"- checkpoint hash: `{model['checkpoint_hash']}`",
        f"- History primary is H16: `{model['history_primary_is_h16']}`",
        f"- lower-capacity sensitivity: "
        f"`{model['lower_capacity_sensitivity']['model_id']}` "
        f"(hidden `{model['lower_capacity_sensitivity']['hidden_size']}`, "
        f"matched contract `{model['lower_capacity_sensitivity']['matched_contract_status']}`)",
        f"- calibration id: `{draft['calibration']['calibration_id']}`",
        "",
        "## 5. Reference representation and scenario count",
        "",
    ]
    reference = draft["reference_representation"]
    lines += [
        f"- representation: `{reference['representation_id']}` "
        f"(temporal `{reference['temporal']}`, uncertainty `{reference['uncertainty']}`)",
        f"- Point rule: `{reference['point_rule']}`",
        f"- Marginal rule: `{reference['marginal_rule']}` "
        f"(`{reference['marginal_identity_note']}`)",
        f"- realized milestones: `{reference['realized_milestones']}`",
        f"- scenario count: `{draft['scenario_count']}`",
        "",
        "## 6. Seven consequence definitions (V5)",
        "",
    ]
    for component, formula in draft["consequence_definitions"][
        "native_formulas"
    ].items():
        lines.append(f"- `{component} = {formula}`")
    cu = draft["cu_references"]
    lines += [
        "",
        f"CU registry: `{cu['registry_id']}` `{cu['registry_hash']}` "
        f"(scientific `{cu['scientific_status']}`, implementation `{cu['implementation_status']}`).",
        "",
        f"Scale adoption: `{cu['numeric_scale_adoption']['decision']}`; principal "
        f"scale source `{cu['numeric_scale_adoption']['principal_scale_source']}`; "
        f"event scale source `{cu['numeric_scale_adoption']['event_scale_source']}`.",
        "",
        "## 7. Priority signals",
        "",
        f"- `P^C` ({draft['priority_signals']['P_C']['role']}): "
        f"`{draft['priority_signals']['P_C']['definition']}`",
        f"- `P^D` ({draft['priority_signals']['P_D']['role']}): "
        f"`{draft['priority_signals']['P_D']['definition']}` -> "
        f"`{draft['priority_signals']['P_D']['estimator']}`",
        f"- `P^D` authority: {draft['priority_signals']['P_D']['authority']}",
        f"- legacy deviation recorded: "
        f"{draft['priority_signals']['P_D']['deviating_legacy_implementation']}",
        f"- shared Stage-I selector: "
        f"`{draft['priority_signals']['shared_selector']['stage1_selector']}`; "
        f"A00 recommendation forbidden: "
        f"`{draft['priority_signals']['shared_selector']['a00_recommendation_forbidden']}`",
        "",
        "## 8. Stage I attention allocation",
        "",
    ]
    stage1 = draft["stage1_attention"]
    lines += [
        f"- `{stage1['capacity_rule']}` with `q0={stage1['nominal_q']}` and grid "
        f"`{stage1['q_grid']}`",
        f"- tie break: `{stage1['tie_break']}`",
        f"- operates on `{stage1['stage1_operates_on']}`",
        f"- A00 never recommended: `{stage1['a00_never_recommended']}`",
        "",
        "## 9. Stage II recovery and solver",
        "",
    ]
    stage2 = draft["stage2_recovery"]
    lines += [
        f"- actionable stages: `{stage2['actionable_stages']}`; non-actionable: "
        f"`{sorted(stage2['non_actionable_stages'])}` -> `NOT_ACTIONABLE`",
        f"- transition: {stage2['transition']}",
        f"- turnaround lower bound: `{stage2['turnaround_lower_bound']['definition']}` "
        f"(sensitivity `{stage2['turnaround_lower_bound']['sensitivity_quantiles']}`)",
        f"- headroom: `{stage2['u_max']['definition']}` nominal "
        f"`{stage2['u_max']['nominal_minutes']}` minutes, sensitivity "
        f"`{stage2['u_max']['sensitivity_quantiles']}`",
        f"- action step: `{stage2['action_step_minutes']}` minutes",
        f"- objective: {stage2['objective']}",
        f"- lambda nominal `{stage2['lambda']['nominal']}`, grid "
        f"`{stage2['lambda']['grid']}`, tie break `{stage2['lambda']['tie_break']}`",
        "",
        f"Solver: formal path `{draft['stage2_solver']['formal_path']}`; "
        f"`{draft['stage2_solver']['parity_backend']}` is a "
        f"`{draft['stage2_solver']['parity_scope']}` parity backend; recorded as a "
        f"long-term deviation: `{draft['stage2_solver']['long_term_deviation']}`.",
        "",
        "## 10. M4 common-basis evaluation",
        "",
    ]
    m4 = draft["m4_evaluation"]
    lines += [
        f"- `{m4['L_att']}`",
        f"- `{m4['L_rec']}`",
        f"- fixed Stage-II cohort: `{m4['fixed_stage2_cohort']}`",
        f"- zero denominator: `{m4['zero_denominator_status']}`",
        f"- `L_total` constructed: `{m4['L_total_constructed']}`",
        f"- monetary branch: `{m4['monetary_branch']}`",
        "",
        "## 11. Bootstrap",
        "",
    ]
    bootstrap = draft["bootstrap"]
    lines += [
        f"- B = `{bootstrap['B']}`, unit `{bootstrap['resampling_unit']}`, paired "
        f"`{bootstrap['paired']}`, interval `{bootstrap['interval']}`, shared plan "
        f"`{bootstrap['shared_plan_and_seed_across_related_metrics']}`",
        "",
        "## 12. Predefined sensitivity list",
        "",
    ]
    sensitivity = draft["predefined_sensitivity"]
    lines += [
        f"- `m^CS`: nominal `{sensitivity['m_cs']['nominal']}`, grid "
        f"`{sensitivity['m_cs']['grid']}` ({sensitivity['m_cs']['status']})",
        f"- `q`: nominal `{sensitivity['attention_capacity_q']['nominal']}`, grid "
        f"`{sensitivity['attention_capacity_q']['grid']}`",
        f"- `lambda`: nominal `{sensitivity['stage2_effort_lambda']['nominal']}`, "
        f"grid `{sensitivity['stage2_effort_lambda']['grid']}`",
        f"- turnaround quantile: nominal "
        f"`{sensitivity['turnaround_lower_bound_quantile']['nominal']}`, grid "
        f"`{sensitivity['turnaround_lower_bound_quantile']['grid']}`",
        f"- headroom quantile: nominal `{sensitivity['headroom_quantile']['nominal']}`, "
        f"grid `{sensitivity['headroom_quantile']['grid']}`",
        "",
        "## 13. V4 -> V5 CU supersession",
        "",
    ]
    supersession = draft["v4_to_v5_supersession"]
    lines += [
        f"- superseded: `{supersession['superseded_registry']}`; adopted: "
        f"`{supersession['adopted_registry']}`",
        f"- principal components: `{supersession['principal_components']}`",
        f"- `P_itinerary` scale `{supersession['event_components']['P_itinerary']['scale']}` "
        f"(`{supersession['event_components']['P_itinerary']['status']}`, empirical "
        f"median `{supersession['event_components']['P_itinerary']['empirical_train_positive_median']}`)",
        f"- `P_service` scale `{supersession['event_components']['P_service']['scale']}` "
        f"(`{supersession['event_components']['P_service']['status']}`, empirical "
        f"median `{supersession['event_components']['P_service']['empirical_train_positive_median']}`)",
        f"- passenger formula: {supersession['passenger_formula']}",
        f"- legacy references retained: `{supersession['legacy_reference_retained']}`",
        "",
        "## 14. Phase 5 Train support and Development families",
        "",
    ]
    train = draft["train_support"]
    lines += [
        f"- Train rotations: `{train['rotation_count']}` (population gates "
        f"`{train['population_gates']['sample_count_match']}` / median match "
        f"`{train['population_gates']['median_match']}`)",
        f"- turnaround quantiles (minutes): `{train['turnaround_quantile_minutes']}`",
        f"- `U_max`: `{train['u_max_nominal_minutes']}` minutes; action grid size "
        f"`{train['action_grid_size']}`",
        f"- Family A artifact hash: `{draft['development_families']['family_a']['artifact_hash']}`",
        f"- Family B artifact hash: `{draft['development_families']['family_b']['artifact_hash']}`",
        "",
        "## 15. Rulings recorded this round",
        "",
    ]
    for ruling in draft["rulings_this_round"]:
        lines.append(
            f"- `{ruling['id']}`: {ruling['ruling']} (authority: {ruling['authority']})"
        )
    lines += ["", "## 16. Open items", ""]
    for item in draft["open_items"]:
        lines.append(f"- `{item['id']}` [{item['status']}]: {item['item']}")
    lines += [
        "",
        "## 17. Freeze commit",
        "",
        f"`freeze_commit = {draft['freeze_commit']}`. Phase 5 records the pending",
        "value only; resolving it is a Phase 6 action and requires explicit human",
        "release.",
        "",
        "## 18. Turnaround reference freeze-precheck (2026-09-19)",
        "",
    ]
    precheck = draft["turnaround_reference_precheck"]
    active_reference = precheck["active_reference"]
    superseded_reference = precheck["superseded_reference"]
    delta = precheck["reference_delta"]
    semantics = precheck["semantics"]
    scale_correction = precheck["f_continuity_train_scale_correction"]
    mean_delta = delta["mean_abs_delta_minutes"]
    mean_delta_text = f"{mean_delta:.2f}" if mean_delta is not None else "NA"
    lines += [
        f"- audit finding: `{precheck['audit_finding']}` (owner "
        f"`{precheck['owner']}`)",
        f"- active node reference: `{active_reference['reference_id']}` ("
        f"`{active_reference['semantic_correction']}`, global median "
        f"{active_reference['global_value_minutes']} minutes, "
        f"{active_reference['cells_count']} cells)",
        f"- superseded node reference: `{superseded_reference['reference_id']}` -> "
        f"`{superseded_reference['status']}` (global median "
        f"{superseded_reference['global_value_minutes']} minutes)",
        f"- reference delta over {delta['shared_cells']} shared cells: "
        f"{delta['changed_cells']} changed, max {delta['max_abs_delta_minutes']} "
        f"minutes, mean {mean_delta_text} minutes",
        f"- node reference quantity: {semantics['node_reference_quantity']}",
        f"- Stage-II quantity: `{semantics['stage2_lower_tail_quantity']}` nominal "
        f"{semantics['stage2_nominal_minutes']} minutes; same quantity: "
        f"`{semantics['same_quantity']}`",
        f"- scalar substitution rejected: `{semantics['scalar_substitution_rejected']}`",
        f"- `F_continuity` Train scale corrected: "
        f"{scale_correction['superseded_scale_minutes']} -> "
        f"{scale_correction['active_scale_minutes']} minutes (positive n "
        f"{scale_correction['active_positive_n']}, population "
        f"{scale_correction['active_population_rows']}), scale rule "
        f"`{scale_correction['scale_rule_unchanged']}`",
        f"- M1 retrained this round: `{precheck['m1_retrained_this_round']}`; new "
        f"Final-Test access: `{precheck['new_final_test_access_this_round']}`",
        "- this precheck leaves the draft `DRAFT_NOT_ACTIVATED` with "
        "`freeze_commit = PENDING`",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "BOOTSTRAP_SPEC",
    "DRAFT_NAME",
    "DRAFT_STATUS",
    "DRAFT_SUMMARY_NAME",
    "FREEZE_COMMIT",
    "SEVEN_CONSEQUENCE_DEFINITIONS",
    "build_freeze_draft",
    "render_freeze_summary",
]
