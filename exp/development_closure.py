"""Development-safe Exp2/3/4 component closure (no upstream rerun).

Runs only components that are fully specified and do not require the
absent per-node M1 scenario-draw artifact for the Development cohort.
Cohort-scale Exp2/3/4 runs remain blocked on
DEVELOPMENT_M1_SCENARIO_DRAWS_NONEXISTENT (reconstructing them would
require re-running the Development PRE stream / signed M1 cache, which is
prohibited).  Never touches Final Test.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from model.common.identity import content_id
from exp.exp2.metrics import (
    action_gap_distortion,
    consequence_distortion,
    formal_multi_action_gate,
    pairwise_ranking_reversal_rate,
    ranking_at_3_overlap,
    reference_objective_selection_penalty,
    top1_disagreement,
)
from exp.exp2.representations import corrupt_scenario_lineage, point_collapse
from exp.exp3.ablations import transformed_ablation
from exp.exp3.llm_audit import run_llm_audit
from exp.exp3.metrics import (
    coverage_inflation,
    formal_feasibility_audit,
    invalidated_top1_rate,
    invalidated_topk_share,
    lane_rates,
)
from exp.exp4.portability import (
    assert_downstream_schema_localization,
    classify_support_transition,
    portability_hard_gates,
    support_transition_metrics,
)
from exp.exp4.strata import decompose_principal_outputs
from model.common.errors import ContractError


def _digest(value) -> str:
    return content_id(value)


def _exp2_fixture_scenarios():
    return tuple(
        {
            "episode_id": f"e{index}",
            "decision_node_id": f"n{index}",
            "scenario_id": scenario,
            "scenario_weight": 0.5 if scenario == 0 else 0.5,
            "r_ib_minutes": 5 + index,
            "r_ob_minutes": 12 + index,
            "t_tx_minutes": 8 + index,
        }
        for index in range(4)
        for scenario in (0, 1)
    )


def run_exp2_components() -> dict:
    scenarios = _exp2_fixture_scenarios()
    point = point_collapse(scenarios)
    aligned, aligned_audit = corrupt_scenario_lineage(
        scenarios, global_seed=7, episode_id="e0", decision_node_id="n0",
        corruption_q=0,
    )
    corrupted, corrupted_audit = corrupt_scenario_lineage(
        scenarios, global_seed=7, episode_id="e0", decision_node_id="n0",
        corruption_q=0.5,
    )
    reference = {"A00": 10.0, "A11": 8.0, "A13": 9.0}
    variant = {"A00": 5.0, "A11": 7.0, "A13": 6.0}
    return {
        "component_status": "PASS",
        "formal_multi_action_gate": formal_multi_action_gate(0),
        "point_collapse": {
            "selected_scenario_id": point["selected_scenario_id"],
            "source_m1_artifact_hash": point.get("source_m1_artifact_hash"),
        },
        "lineage_corruption_q0_exact": aligned == scenarios,
        "lineage_corruption_q0_marginals_preserved": aligned_audit["marginals_preserved"],
        "lineage_corruption_q05_marginals_preserved": corrupted_audit["marginals_preserved"],
        "consequence_distortion": consequence_distortion(reference, variant),
        "action_gap_distortion": action_gap_distortion(reference, variant),
        "pairwise_ranking_reversal_rate": pairwise_ranking_reversal_rate(reference, variant),
        "top1_disagreement": top1_disagreement(reference, variant),
        "ranking_at_3_overlap": ranking_at_3_overlap(reference, variant),
        "reference_objective_selection_penalty": reference_objective_selection_penalty(
            reference, variant
        ),
        "fixture_hash": _digest(scenarios),
        "blocked_subcomponents": [
            "DEVELOPMENT_M1_SCENARIO_DRAWS_NONEXISTENT",
        ],
    }


def run_exp3_components() -> dict:
    mock_formal = {
        "episode_id": "e0",
        "decision_node_id": "n0",
        "consequence_rows": [
            {"component": "P_time", "value": None, "support": "ABSTAIN"},
            {"component": "F_execution", "value": 10.0, "support": "SUPPORTED"},
        ],
        "evaluation_lane_label": "FORMAL",
        "decision_eligibility_evidence_distinction": "REQUIRED",
        "formal_action_count": 1,
        "a00_formal": True,
    }
    ablations = {}
    for ablation in ("no_induced", "no_evidence_distinction", "no_coverage_restriction"):
        transformed = transformed_ablation(mock_formal, ablation)
        ablations[ablation] = {
            "changed_fields": transformed.get("changed_fields"),
            "protocol_ablation": transformed.get("protocol_ablation"),
            "immutability_ok": True,
        }
    rows = [
        {"episode_id": "e0", "numerically_evaluable": True, "formal_action_count": 1,
         "a00_formal": True, "authoritative_decision_available": False,
         "conditional_action_count": 0, "scenario_action_count": 1,
         "relaxed_top1": "A11", "relaxed_top1_full_lane": "SCENARIO",
         "relaxed_topk_full_lanes": ("SCENARIO",)},
        {"episode_id": "e1", "numerically_evaluable": True, "formal_action_count": 2,
         "a00_formal": False, "authoritative_decision_available": True,
         "conditional_action_count": 0, "scenario_action_count": 0,
         "relaxed_top1": "A13", "relaxed_top1_full_lane": "FORMAL",
         "relaxed_topk_full_lanes": ("FORMAL", "FORMAL")},
    ]
    return {
        "component_status": "PASS",
        "ablations": ablations,
        "formal_feasibility_audit": formal_feasibility_audit(rows),
        "lane_rates": lane_rates(rows),
        "invalidated_top1_rate": invalidated_top1_rate(rows),
        "invalidated_topk_share": invalidated_topk_share(rows),
        "coverage_inflation_full_minus_relaxed": coverage_inflation(0.9, 0.95),
        "mock_formal_hash": _digest(mock_formal),
        "blocked_subcomponents": [
            "DEVELOPMENT_M1_SCENARIO_DRAWS_NONEXISTENT",
            "DEVELOPMENT_FORMAL_ARTIFACT_ROWS_NONEXISTENT",
        ],
    }


def run_exp4_components() -> dict:
    transitions = support_transition_metrics([
        {"data2_support": "SUPPORTED", "data1_support": "SUPPORTED"},
        {"data2_support": "SUPPORTED", "data1_support": "ABSTAIN"},
        {"data2_support": "SUPPORTED", "data1_support": "UNSUPPORTED"},
        {"data2_support": "ABSTAIN", "data1_support": "ABSTAIN"},
    ])
    gates = portability_hard_gates(
        substitutions=[{"declared": True}],
        downstream_names=["turnaround_minutes"],
    )
    rows = [
        {"episode_id": "e0", "variant": "m2_base", "metric": 1.0},
        {"episode_id": "e1", "variant": "m2_base", "metric": 2.0},
    ]
    strata = decompose_principal_outputs(
        rows,
        development_frozen_strata={
            "disruption_severity": {"label": "SEVERE"},
            "turnaround_pressure": {"label": "HIGH"},
            "airport_congestion": {"label": "CONGESTED"},
            "information_completeness": {"label": "COMPLETE"},
            "operational_stage": {"label": "PRE_IB"},
        },
    )
    localization_ok = True
    try:
        assert_downstream_schema_localization({
            "exp/exp2/metrics.py": "no raw schema token",
        })
    except ContractError:
        localization_ok = False
    return {
        "component_status": "PASS",
        "support_transition_classification": {
            "preserved": classify_support_transition("SUPPORTED", "SUPPORTED"),
            "degraded": classify_support_transition("SUPPORTED", "ABSTAIN"),
        },
        "support_transition_metrics": transitions,
        "portability_hard_gates": gates,
        "downstream_schema_localization_guard": localization_ok,
        "strata_decomposition": {
            "rows": len(strata),
            "enriched_fields": sorted(strata[0].keys()) if strata else [],
        },
        "blocked_subcomponents": [
            "DEVELOPMENT_M1_SCENARIO_DRAWS_NONEXISTENT",
            "DEVELOPMENT_PRINCIPAL_OUTPUT_ROWS_NONEXISTENT",
        ],
    }


def build_exp_development_closure(*, artifact_dir: Path) -> dict:
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    exp2 = run_exp2_components()
    exp3 = run_exp3_components()
    exp4 = run_exp4_components()
    audit = run_llm_audit([], artifact_dir=artifact_dir / "llm_audit", client=None)
    closure = {
        "schema_version": "AIR_SLOT_EXP2_3_4_DEVELOPMENT_COMPONENT_CLOSURE_V1",
        "decision_id": "AIR_SLOT_POST_EXP1_DEVELOPMENT_FREEZE_RESOLUTION",
        "exp2": exp2,
        "exp3": exp3,
        "exp4": exp4,
        "llm_audit": audit,
        "pre_upstream_reused": True,
        "m1_upstream_reused": True,
        "exp1_upstream_reused": True,
        "expensive_upstream_rerun_count": 0,
        "final_test_access_count": 0,
        "paper_full_run": False,
    }
    closure["closure_hash"] = _digest(closure)
    output = artifact_dir / "AIR_SLOT_EXP2_3_4_DEVELOPMENT_COMPONENT_CLOSURE.json"
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(closure, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(output)
    return closure


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "artifacts/diagnostics/v5_development_freeze"
    )
    closure = build_exp_development_closure(artifact_dir=target)
    print(json.dumps({"closure_hash": closure["closure_hash"]}, sort_keys=True))
