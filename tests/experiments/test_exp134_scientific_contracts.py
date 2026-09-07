import pandas as pd
import numpy as np
import pytest

from exp.exp2.bootstrap import run_bootstrap
from exp.exp2.informativeness import informativeness_table
from exp.exp3.analysis import (
    _heterogeneity,
    bootstrap_stage,
    bootstrap_stage_fast,
    evaluate_stages,
    stage_agreement,
    stage_heterogeneity,
)
from exp.exp4.triage import evaluate_screening, prepare_canonical_events, robust_sets
from exp.shared.analytical import scores
from exp.shared.resampling import expand_draw


def _rows():
    base = {
        "episode_id": "e1",
        "original_episode_id": "e1",
        "decision_node_id": "n1",
        "decision_time": "2019-08-01T00:00:00+00:00",
        "operational_stage": "PRE_IB",
        "delay_to_mean": 10.0,
        "support_primary": True,
        "conditional_aggregate_complete": True,
        "F_continuity_native": 1.0,
        "F_execution_native": 2.0,
        "F_propagation_native": 3.0,
        "P_time_native": 4.0,
        "P_itinerary_native": 5.0,
        "P_service_native": 6.0,
        "R_operating_native": 7.0,
        "score_F": 2.0,
        "score_P": 5.0,
        "score_R": 7.0,
        "score_C": 14.0 / 3.0,
        "delay_to_mean_cs": 10.0,
        "common_support_mass": 1.0,
        "final_test_access_count": 0,
        "Z_F_continuity_cs": 1.0,
        "Z_F_execution_cs": 2.0,
        "Z_F_propagation_cs": 3.0,
        "Z_P_time_cs": 4.0,
        "Z_P_itinerary_cs": 5.0,
        "Z_P_service_cs": 6.0,
        "Z_R_operating_cs": 7.0,
    }
    second = {**base, "episode_id": "e2", "original_episode_id": "e2", "decision_node_id": "n2", "delay_to_mean": 10.0, "decision_time": "2019-08-01T00:05:00+00:00"}
    return pd.DataFrame([base, second])


def test_exp2b_component_population_is_not_seven_component_complete_case():
    frame = _rows()
    frame.loc[1, "P_service_native"] = float("nan")
    result = informativeness_table(frame)
    row = result[result.quantity_id == "F_continuity"].iloc[0]
    assert row.n_nodes == 2


def test_exp2b_bootstrap_uses_independent_population_universe():
    frame = _rows()
    frame = frame.assign(
        F_continuity_native=frame.F_continuity_native,
        F_continuity_status="SUPPORTED_CONDITIONAL",
        P_service_native=frame.P_service_native,
        P_service_status="SUPPORTED_CONDITIONAL",
        **{
            f"Z_{component}": frame[f"Z_{component}_cs"]
            for component in (
                "F_continuity", "F_execution", "F_propagation", "P_time",
                "P_itinerary", "P_service", "R_operating",
            )
        },
    )
    info = pd.concat([frame, frame.iloc[[0]].assign(
        episode_id="e3", original_episode_id="e3", decision_node_id="n3"
    )], ignore_index=True)
    draws = run_bootstrap(
        frame.iloc[[0]],
        replicates=1,
        seed=20260906,
        caliper=5.0,
        informativeness_frame=info,
        plan=np.asarray([["e3", "e1", "e3"]], dtype=object),
    )
    assert draws[0]["informativeness"]
    assert draws[0]["informativeness_n_nodes"]["F_continuity"] == 3


def test_exp2_reference_and_optimized_bootstrap_match_on_fixed_draw():
    frame = pd.concat([
        _rows(),
        _rows().iloc[[0]].assign(
            episode_id="e3", original_episode_id="e3", decision_node_id="n3",
            delay_to_mean=12.0, score_C=8.0,
        ),
    ], ignore_index=True).assign(
        **{
            f"Z_{component}": _rows()[f"Z_{component}_cs"]
            for component in (
                "F_continuity", "F_execution", "F_propagation", "P_time",
                "P_itinerary", "P_service", "R_operating",
            )
        },
        **{
            f"{component}_status": "SUPPORTED_CONDITIONAL"
            for component in (
                "F_continuity", "F_execution", "F_propagation", "P_time",
                "P_itinerary", "P_service", "R_operating",
            )
        },
    )
    draw = np.asarray([["e1", "e1", "e2"]], dtype=object)
    reference = run_bootstrap(
        frame,
        replicates=1,
        seed=20260906,
        caliper=5.0,
        informativeness_frame=frame,
        plan=draw,
        reference=True,
    )[0]
    optimized = run_bootstrap(
        frame,
        replicates=1,
        seed=20260906,
        caliper=5.0,
        informativeness_frame=frame,
        plan=draw,
    )[0]
    assert optimized["informativeness_n_nodes"] == reference["informativeness_n_nodes"]
    for section in ("priority", "informativeness", "similar_delay", "robustness"):
        assert optimized[section].keys() == reference[section].keys()
        for key, expected in reference[section].items():
            actual = optimized[section][key]
            if isinstance(expected, float):
                assert actual == pytest.approx(expected)
            else:
                assert actual == expected


def test_exp3_primary_support_and_percentile_gap():
    frame = _rows()
    frame.loc[1, "support_primary"] = False
    assert stage_agreement(frame).iloc[0].n_nodes == 1
    assert stage_heterogeneity(_rows()).iloc[0].median_consequence_priority_percentile_gap == 0


def test_exp3_same_delay_heterogeneity_uses_percentile_gap():
    frame = pd.concat([
        _rows().iloc[[0]].assign(
            episode_id="e1", original_episode_id="e1", decision_node_id="n1",
            score_C=1.0, Z_F_continuity_cs=1.0, Z_F_execution_cs=1.0,
            Z_F_propagation_cs=1.0, Z_P_time_cs=1.0, Z_P_itinerary_cs=1.0,
            Z_P_service_cs=1.0, Z_R_operating_cs=1.0,
        ),
        _rows().iloc[[0]].assign(
            episode_id="e2", original_episode_id="e2", decision_node_id="n2",
            score_C=2.0, Z_F_continuity_cs=2.0, Z_F_execution_cs=2.0,
            Z_F_propagation_cs=2.0, Z_P_time_cs=2.0, Z_P_itinerary_cs=2.0,
            Z_P_service_cs=2.0, Z_R_operating_cs=2.0,
        ),
        _rows().iloc[[0]].assign(
            episode_id="e3", original_episode_id="e3", decision_node_id="n3",
            score_C=100.0, Z_F_continuity_cs=100.0, Z_F_execution_cs=100.0,
            Z_F_propagation_cs=100.0, Z_P_time_cs=100.0, Z_P_itinerary_cs=100.0,
            Z_P_service_cs=100.0, Z_R_operating_cs=100.0,
        ),
    ], ignore_index=True)
    result = _heterogeneity(scores(frame), caliper=5.0, reference=True)
    assert result["median_consequence_priority_percentile_gap"] == pytest.approx(1 / 3)
    assert result["median_consequence_priority_percentile_gap"] != 98.0


def test_exp4_canonical_before_support_and_stage_local_robust_sets():
    frame = _rows()
    frame.loc[0, "support_primary"] = False
    canonical, _ = prepare_canonical_events(frame)
    assert canonical.iloc[0].canonical_event_status == "EXCLUDE_WITH_TYPED_REASON"
    supported, _ = prepare_canonical_events(_rows())
    robust = robust_sets(supported, 4)
    assert robust["stage"].nunique() == 1


def test_bootstrap_duplicate_instances_are_not_folded_or_self_paired():
    frame = scores(_rows())
    expanded = expand_draw(frame, ("e1", "e1"))
    assert len(expanded) == 2
    assert expanded.bootstrap_instance_id.nunique() == 2
    assert expanded.technical_node_id.nunique() == 2
    result = evaluate_stages(expanded)
    assert result.iloc[0].n_nodes == 2
    assert result.iloc[0].heterogeneity_status == "ABSTAIN_INSUFFICIENT_MATCHES"


def test_exp3_reference_and_optimized_bootstrap_match_on_fixed_draw():
    frame = scores(_rows())
    draw = np.asarray([["e1", "e2"]], dtype=object)
    reference = bootstrap_stage(frame, plan=draw, reference=True)
    optimized = bootstrap_stage_fast(frame, plan=draw)
    columns = [
        "stage", "n_nodes", "kendall_tau_b", "top10_overlap",
        "median_rank_displacement", "p90_rank_displacement",
        "median_consequence_priority_percentile_gap",
        "p90_consequence_priority_percentile_gap",
    ]
    pd.testing.assert_frame_equal(
        reference[columns].reset_index(drop=True),
        optimized[columns].reset_index(drop=True),
        check_dtype=False,
    )


def test_exp4_stage_local_top10_and_no_f_execution_from_shared_scores():
    frame = scores(_rows())
    canonical, _ = prepare_canonical_events(frame)
    result, _ = evaluate_screening(canonical)
    nonempty = result[result.n.gt(0)]
    assert set(nonempty.stage) == {"PRE_IB"}
    assert nonempty.iloc[0].k == 1
    assert frame.iloc[0].NO_F_EXECUTION == pytest.approx(
        ((1.0 + 3.0) / 2.0 + 5.0 + 7.0) / 3.0
    )
