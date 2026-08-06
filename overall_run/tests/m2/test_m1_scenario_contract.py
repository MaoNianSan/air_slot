from __future__ import annotations

from overall_run.src.m1 import scenario_from_dict, scenario_to_dict


def test_scenario_bundle_round_trip_and_structural_identities(m1_scenario_factory) -> None:
    scenario = m1_scenario_factory()
    restored = scenario_from_dict(scenario_to_dict(scenario))
    assert restored.metadata["episode_id"] == "ep-1"
    for sample in restored.joint_samples:
        assert sample.T_predecessor_inblock == sample.query_time + __import__("datetime").timedelta(minutes=sample.r_ib_minutes)
        assert sample.AOBT_successor == sample.earliest_offblock_time + __import__("datetime").timedelta(minutes=sample.r_ob_minutes)
        assert sample.ATOT_successor == sample.AOBT_successor + __import__("datetime").timedelta(minutes=sample.taxi_time)
