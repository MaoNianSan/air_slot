import pandas as pd

from exp.exp2.informativeness import informativeness_table
from exp.exp3.analysis import stage_agreement, stage_heterogeneity
from exp.exp4.triage import prepare_canonical_events, robust_sets


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
        "delay_to_mean_cs": 10.0,
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


def test_exp3_primary_support_and_percentile_gap():
    frame = _rows()
    frame.loc[1, "support_primary"] = False
    assert stage_agreement(frame).iloc[0].n_nodes == 1
    assert stage_heterogeneity(_rows()).iloc[0].median_consequence_priority_percentile_gap == 0


def test_exp4_canonical_before_support_and_stage_local_robust_sets():
    frame = _rows()
    frame.loc[0, "support_primary"] = False
    canonical, _ = prepare_canonical_events(frame)
    assert canonical.iloc[0].canonical_event_status == "EXCLUDE_WITH_TYPED_REASON"
    supported, _ = prepare_canonical_events(_rows())
    robust = robust_sets(supported, 4)
    assert robust["stage"].nunique() == 1
