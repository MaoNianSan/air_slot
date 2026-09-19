"""``PAPER_VIEWS``: reporting views built only from frozen checkpoints.

The views are pure projections of the persisted atomic results:

* Section 5.2 primary design - the ``stage x q`` operating axis
  (``q in {0.05, 0.10, 0.20, 0.30}``), read from ``ATTENTION_DECISIONS``;
* Section 5.4 representation identification - the common-basis ``L_att`` and
  ``L_rec`` comparisons against ``HISTORY_JOINT`` on the fixed cohort ``R_g*``,
  read from ``M4_COMPARISONS``;
* Section 5.5 sensitivity scope - the nominal base specification and the frozen
  one-factor-at-a-time axes, read from the frozen constants.

No scientific quantity is recomputed here: the module never imports an M1, M2,
M3 or M4 service. Everything downstream of the immutable manifest is a view.
The fixed-window history sensitivity keeps the status
``NOT_AVAILABLE_NOT_FROZEN`` and no substitute model is trained for it.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .. import constants as C
from . import stages as S

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
    {
        "axis": "history_capacity",
        "nominal": 16,
        "grid": [8, 16],
        "levels": ["H8", "H16"],
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
) -> dict[str, Any]:
    """Build every paper-facing view from the persisted checkpoints."""

    return {
        "primary_design": PRIMARY_DESIGN,
        "scientific_recomputation_performed": False,
        "source_stages": [
            S.ATTENTION_DECISIONS,
            S.M4_COMPARISONS,
            S.BOOTSTRAP,
        ],
        "section_5_2": _section_5_2(attention_decisions),
        "section_5_4": _section_5_4(m4_comparisons, bootstrap),
        "section_5_5": _section_5_5(),
        "excluded_from_final_test_scope": [
            dict(item) for item in EXCLUDED_FROM_FINAL_TEST_SCOPE
        ],
        "typed_scientific_states": list(C.TYPED_SCIENTIFIC_STATES),
        "no_total_loss_constructed": True,
    }


def _section_5_2(attention_decisions: Mapping[str, Any]) -> dict[str, Any]:
    reference_variant = S.REFERENCE_VARIANT
    rows: list[dict[str, Any]] = []
    for row in attention_decisions["rows"]:
        if row["variant"] != reference_variant:
            continue
        rows.append(
            {
                "q": float(row["q"]),
                "k": int(row["k"]),
                "cohort_size": int(row["cohort_size"]),
                "abstaining_node_count": int(row["abstaining_node_count"]),
                "selected_node_count": len(row["selected_node_ids"]),
                "selected_stage_counts": dict(row["selected_stage_counts"]),
                "selected_stage_class_counts": dict(
                    row["selected_stage_class_counts"]
                ),
            }
        )
    rows.sort(key=lambda item: item["q"])
    return {
        "reference_variant": reference_variant,
        "reference_representation_id": C.REFERENCE_REPRESENTATION_ID,
        "capacity_rule": "K = ceil(q * N)",
        "q_grid": [float(value) for value in attention_decisions["q_grid"]],
        "nominal_q": float(attention_decisions["nominal_q"]),
        "q_is_primary_operating_axis": True,
        "q_is_sensitivity_axis": False,
        "rows": rows,
    }


def _section_5_4(
    m4_comparisons: Mapping[str, Any], bootstrap: Mapping[str, Any]
) -> dict[str, Any]:
    attention = m4_comparisons["attention"]
    recovery = m4_comparisons["recovery"]
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
                    "overlap_fraction_of_reference": attention_record.get(
                        "overlap_fraction_of_reference"
                    ),
                    "entered_count": len(attention_record.get("entered", ()) or ()),
                    "displaced_count": len(
                        attention_record.get("displaced", ()) or ()
                    ),
                    "kendall_tau": attention_record.get("kendall_tau"),
                    "spearman_rho": attention_record.get("spearman_rho"),
                    "ci": attention_interval.get("ci"),
                    "ci_status": attention_interval.get("status"),
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
    return {
        "reference_id": m4_comparisons["reference_variant"],
        "reference_representation_id": C.REFERENCE_REPRESENTATION_ID,
        "fixed_cohort_id": m4_comparisons["cohort_id"],
        "fixed_cohort_size": int(m4_comparisons["cohort_size"]),
        "stage2_comparisons_use_fixed_r_star": True,
        "losses_reported_separately": True,
        "loss_total_defined": False,
        "comparators": comparators,
    }


def _section_5_5() -> dict[str, Any]:
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
        "sensitivity_results_status": (
            "DECLARED_SCOPE_ONLY_NO_SENSITIVITY_RESULTS_IN_THIS_RUN"
        ),
    }


__all__ = [
    "EXCLUDED_FROM_FINAL_TEST_SCOPE",
    "PRIMARY_DESIGN",
    "SECTION_5_5_AXES",
    "build_paper_views",
]
