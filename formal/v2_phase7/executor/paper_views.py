"""``PAPER_VIEWS``: read-only projections of the frozen stage checkpoints."""

from __future__ import annotations

from typing import Any, Mapping

from .. import constants as C
from . import stages as S
from .checkpoints import content_hash

PRIMARY_DESIGN = "STAGE_X_Q"
SENSITIVITY_DESIGN = "ONE_FACTOR_AT_A_TIME"
EXCLUDED_STATUS = "NOT_ACTIVATED_BY_PHASE6_FREEZE"

SECTION_5_5_AXES: tuple[dict[str, Any], ...] = (
    {
        "axis": "lambda",
        "nominal": C.NOMINAL_LAMBDA,
        "grid": [0.10, 0.25, 0.50, 1.00],
        "status": "FROZEN_SENSITIVITY_AXIS_DECLARED",
    },
    {
        "axis": "turnaround_lower_bound_q",
        "nominal": C.NOMINAL_TURNAROUND_Q20,
        "grid": [34.0, 41.0, 47.0],
        "quantiles": ["Q10", "Q20", "Q30"],
        "status": "FROZEN_SENSITIVITY_AXIS_DECLARED",
    },
    {
        "axis": "u_max",
        "nominal": C.NOMINAL_U_MAX,
        "grid": [
            C.U_MAX_BY_SPECIFICATION["Q80"],
            C.U_MAX_BY_SPECIFICATION["nominal"],
            C.U_MAX_BY_SPECIFICATION["Q95"],
        ],
        "quantiles": ["Q80", "Q90", "Q95"],
        "status": "FROZEN_SENSITIVITY_AXIS_DECLARED",
    },
)

EXCLUDED_FROM_FINAL_TEST_SCOPE: tuple[dict[str, str], ...] = (
    {"item": "similar_delay_5_10_15", "status": EXCLUDED_STATUS},
    {"item": "itinerary_threshold_30_60", "status": EXCLUDED_STATUS},
    {"item": "service_threshold_150_210", "status": EXCLUDED_STATUS},
    {
        "item": "fixed_window_history",
        "status": S.FIXED_WINDOW_SENSITIVITY_STATUS,
    },
)


def build_paper_views(
    attention_decisions: Mapping[str, Any],
    m4_comparisons: Mapping[str, Any],
    bootstrap: Mapping[str, Any],
    robustness: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "primary_design": PRIMARY_DESIGN,
        "scientific_recomputation_performed": False,
        "source_stages": [
            S.ATTENTION_DECISIONS,
            S.M4_COMPARISONS,
            S.BOOTSTRAP,
            S.ROBUSTNESS,
        ],
        "section_5_2": _section_5_2(attention_decisions, m4_comparisons),
        "section_5_4": _section_5_4(m4_comparisons, bootstrap),
        "information_value": _information_value(m4_comparisons, bootstrap),
        "section_5_5": _section_5_5(robustness),
        "excluded_from_final_test_scope": [
            dict(item) for item in EXCLUDED_FROM_FINAL_TEST_SCOPE
        ],
        "typed_scientific_states": list(C.TYPED_SCIENTIFIC_STATES),
        "no_total_loss_constructed": True,
    }


def _section_5_2(
    attention_decisions: Mapping[str, Any],
    m4_comparisons: Mapping[str, Any],
) -> dict[str, Any]:
    reference_variant = S.REFERENCE_VARIANT
    rows: list[dict[str, Any]] = []
    for q in C.Q_GRID:
        stage_rows: list[dict[str, Any]] = []
        for stage in S.ACTIONABLE_STAGE_I_STAGES:
            matching = [
                row
                for row in attention_decisions["rows"]
                if row["variant"] == reference_variant
                and row["stage"] == stage
                and abs(float(row["q"]) - float(q)) <= 1e-9
            ]
            if not matching:
                continue
            row = matching[0]
            stage_rows.append(row)
            rows.append(
                {
                    "q": float(row["q"]),
                    "stage": stage,
                    "k": int(row["k"]),
                    "cohort_size": int(row["cohort_size"]),
                    "canonical_stage_node_count": int(
                        row["canonical_stage_node_count"]
                    ),
                    "eligible_candidate_count": int(
                        row["eligible_candidate_count"]
                    ),
                    "abstaining_node_count": int(row["abstaining_node_count"]),
                    "selected_node_count": len(row["selected_node_ids"]),
                    "selected_stage_counts": dict(row["selected_stage_counts"]),
                    "selected_stage_class_counts": dict(
                        row["selected_stage_class_counts"]
                    ),
                }
            )
        rows.append(
            {
                "q": float(q),
                "stage": "OVERALL",
                "k": sum(int(row["k"]) for row in stage_rows),
                "cohort_size": sum(int(row["cohort_size"]) for row in stage_rows),
                "canonical_stage_node_count": sum(
                    int(row["canonical_stage_node_count"]) for row in stage_rows
                ),
                "eligible_candidate_count": sum(
                    int(row["eligible_candidate_count"]) for row in stage_rows
                ),
                "abstaining_node_count": sum(
                    int(row["abstaining_node_count"]) for row in stage_rows
                ),
                "selected_node_count": sum(
                    len(row["selected_node_ids"]) for row in stage_rows
                ),
                "selected_stage_counts": {},
                "selected_stage_class_counts": {},
                "aggregation": "PRE_TURN_OBJECTIVE_ROWS_NOT_A_POOLED_STAGE1_RANKING",
                "attention_aggregate": m4_comparisons["attention"]["aggregation"],
                "L_att_overall": (
                    m4_comparisons["attention"]["self_reference"].get("L_att")
                    if abs(float(q) - float(C.NOMINAL_Q)) <= 1e-9
                    else None
                ),
            }
        )
    return {
        "reference_variant": reference_variant,
        "reference_representation_id": C.REFERENCE_REPRESENTATION_ID,
        "stage1_actionable_stages": list(S.ACTIONABLE_STAGE_I_STAGES),
        "capacity_rule": "K_STAGE = ceil(q * N_STAGE); K_OVERALL = sum_g K_g",
        "q_grid": [float(value) for value in attention_decisions["q_grid"]],
        "nominal_q": float(attention_decisions["nominal_q"]),
        "q_is_primary_operating_axis": True,
        "q_is_sensitivity_axis": False,
        "pooled_stage1_ranking": False,
        "overall_rule": "OBJECTIVES_THEN_NORMALIZE",
        "rows": rows,
    }


def _section_5_4(
    m4_comparisons: Mapping[str, Any], bootstrap: Mapping[str, Any]
) -> dict[str, Any]:
    attention = m4_comparisons["attention"]
    recovery = m4_comparisons["recovery"]
    cross_state_attention = attention["comparators"]["HISTORY_MARGINAL"]
    cross_state_recovery = recovery["comparators"]["HISTORY_MARGINAL"]
    comparators: list[dict[str, Any]] = []
    for variant in S.COMPARATOR_VARIANTS:
        attention_record = attention["comparators"][variant]
        recovery_record = recovery["comparators"][variant]
        attention_interval = bootstrap["comparators"][variant]["attention"]
        recovery_interval = bootstrap["comparators"][variant]["recovery"]
        comparators.append(
            {
                "comparator_id": variant,
                "attention": {
                    "L_att": attention_record.get("L_att"),
                    "typed_state": attention_record.get("typed_state"),
                    "overlap_count": attention_record.get("overlap_count"),
                    "entered_count": len(attention_record.get("entered", ()) or ()),
                    "displaced_count": len(
                        attention_record.get("displaced", ()) or ()
                    ),
                    "kendall_tau": attention_record.get("kendall_tau"),
                    "spearman_rho": attention_record.get("spearman_rho"),
                    "ci": attention_interval.get("ci"),
                    "ci_status": attention_interval.get("status"),
                    "aggregation": "OBJECTIVES_THEN_NORMALIZE",
                },
                "recovery": {
                    "L_rec": recovery_record.get("L_rec"),
                    "typed_state": recovery_record.get("typed_state"),
                    "A0": recovery_record.get("A0"),
                    "A5": recovery_record.get("A5"),
                    "activation_events": recovery_record.get("activation_events"),
                    "ci": recovery_interval.get("ci"),
                    "ci_status": recovery_interval.get("status"),
                },
            }
        )
    paired = bootstrap["marginal_uncertainty_increment"]
    return {
        "reference_id": m4_comparisons["reference_variant"],
        "reference_representation_id": C.REFERENCE_REPRESENTATION_ID,
        "fixed_cohort_id": m4_comparisons["cohort_id"],
        "fixed_cohort_size": int(m4_comparisons["cohort_size"]),
        "stage1_actionable_stages": list(S.ACTIONABLE_STAGE_I_STAGES),
        "stage2_comparisons_use_fixed_r_star": True,
        "losses_reported_separately": True,
        "loss_total_defined": False,
        "attention_stage_aggregation": m4_comparisons["attention"]["aggregation"],
        "CROSS_STATE_DEPENDENCE_L_ATT": cross_state_attention.get("L_att"),
        "CROSS_STATE_DEPENDENCE_L_REC": cross_state_recovery.get("L_rec"),
        "MARGINAL_UNCERTAINTY_INCREMENT_L_ATT": paired["attention"].get(
            "estimate"
        ),
        "MARGINAL_UNCERTAINTY_INCREMENT_L_ATT_CI_LOW": paired[
            "attention"].get("ci_low"),
        "MARGINAL_UNCERTAINTY_INCREMENT_L_ATT_CI_HIGH": paired[
            "attention"].get("ci_high"),
        "MARGINAL_UNCERTAINTY_INCREMENT_L_REC": paired["recovery"].get(
            "estimate"
        ),
        "MARGINAL_UNCERTAINTY_INCREMENT_L_REC_CI_LOW": paired[
            "recovery"].get("ci_low"),
        "MARGINAL_UNCERTAINTY_INCREMENT_L_REC_CI_HIGH": paired[
            "recovery"].get("ci_high"),
        "comparators": comparators,
    }


def _information_value(
    m4_comparisons: Mapping[str, Any], bootstrap: Mapping[str, Any]
) -> dict[str, Any]:
    paired = bootstrap["marginal_uncertainty_increment"]
    return {
        "components": list(S.COMPARATOR_VARIANTS),
        "cross_state_dependence": {
            "comparator": "HISTORY_MARGINAL",
            "reference": S.REFERENCE_VARIANT,
            "definition": "L_HISTORY_MARGINAL - L_HISTORY_JOINT",
            "CROSS_STATE_DEPENDENCE_L_ATT": m4_comparisons["attention"]
            ["comparators"]["HISTORY_MARGINAL"].get("L_att"),
            "CROSS_STATE_DEPENDENCE_L_REC": m4_comparisons["recovery"]
            ["comparators"]["HISTORY_MARGINAL"].get("L_rec"),
        },
        "marginal_uncertainty_increment": {
            "definition": paired["definition"],
            "paired": bool(paired["paired"]),
            "attention": dict(paired["attention"]),
            "recovery": dict(paired["recovery"]),
            "MARGINAL_UNCERTAINTY_INCREMENT_L_ATT": paired["attention"]
            .get("estimate"),
            "MARGINAL_UNCERTAINTY_INCREMENT_L_ATT_CI_LOW": paired[
                "attention"].get("ci_low"),
            "MARGINAL_UNCERTAINTY_INCREMENT_L_ATT_CI_HIGH": paired[
                "attention"].get("ci_high"),
            "MARGINAL_UNCERTAINTY_INCREMENT_L_REC": paired["recovery"]
            .get("estimate"),
            "MARGINAL_UNCERTAINTY_INCREMENT_L_REC_CI_LOW": paired[
                "recovery"].get("ci_low"),
            "MARGINAL_UNCERTAINTY_INCREMENT_L_REC_CI_HIGH": paired[
                "recovery"].get("ci_high"),
        },
        "no_ambiguous_marginal_labels": True,
    }


def _section_5_5(robustness: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "design": SENSITIVITY_DESIGN,
        "nominal_base": {
            "q": C.NOMINAL_Q,
            "lambda": C.NOMINAL_LAMBDA,
            "turnaround_q20_minutes": C.NOMINAL_TURNAROUND_Q20,
            "u_max_minutes": C.NOMINAL_U_MAX,
            "history_capacity": 16,
            "m_cs": 0.90,
        },
        "axes": [dict(axis) for axis in SECTION_5_5_AXES],
        "one_factor_at_a_time": True,
        "crossed_with_q_grid": False,
        "fixed_window_history_status": S.FIXED_WINDOW_SENSITIVITY_STATUS,
        "sensitivity_results_status": "EXECUTED",
        "source_stage": S.ROBUSTNESS,
        "source_payload_hash": content_hash(robustness),
        "nominal_reference_id": robustness.get("nominal_reference_id"),
        "fixed_r_star": bool(robustness.get("fixed_r_star")),
        "stage1_rerun": bool(robustness.get("stage1_rerun")),
        "row_count": int(robustness.get("row_count", 0)),
        "results": [dict(row) for row in robustness.get("rows", ())],
    }


__all__ = [
    "EXCLUDED_FROM_FINAL_TEST_SCOPE",
    "PRIMARY_DESIGN",
    "SECTION_5_5_AXES",
    "build_paper_views",
]
