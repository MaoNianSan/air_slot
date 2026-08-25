from __future__ import annotations

from datetime import datetime, timedelta, timezone

from exp.common.replay import (
    ReplayConsequenceBinding,
    ReplayDecisionRecord,
    ReplayEpisodeRecord,
    ReplayScenarioBinding,
    validate_replay_lineage,
)


def test_lineage_preservation_requires_exact_m1_to_m2_scenario_identity():
    decision_time = datetime(2019, 8, 15, 12, tzinfo=timezone.utc)
    episode = ReplayEpisodeRecord(
        episode_id="episode-001",
        split_id="development",
        scenario_lineage=("pre:episode-001", "m1:seed-001"),
        decision_records=(
            ReplayDecisionRecord(
                decision_node_id="node-001",
                decision_time=decision_time,
                information_cutoff=decision_time - timedelta(minutes=5),
                legal_record_ids=("weather:001",),
                legal_record_availability_times=(decision_time - timedelta(minutes=10),),
            ),
        ),
    )
    m1 = ReplayScenarioBinding(
        episode_id=episode.episode_id,
        decision_node_id="node-001",
        decision_time=decision_time,
        information_cutoff=decision_time - timedelta(minutes=5),
        scenario_lineage=episode.scenario_lineage,
        scenario_ids=(0, 1),
    )
    m2 = ReplayConsequenceBinding(
        episode_id=episode.episode_id,
        decision_node_id="node-001",
        scenario_lineage=episode.scenario_lineage,
        scenario_ids=(0, 1),
    )

    preserved = validate_replay_lineage(episode, "node-001", m1, m2)
    assert preserved.pre_compatible is True
    assert preserved.m1_compatible is True
    assert preserved.m2_compatible is True
    assert preserved.reason_codes == ("REPLAY_LINEAGE_COMPATIBLE",)

    reordered = m2.model_copy(update={"scenario_ids": (1, 0)})
    rejected = validate_replay_lineage(episode, "node-001", m1, reordered)
    assert rejected.m2_compatible is False
    assert "M2_SCENARIO_IDENTITY_NOT_PRESERVED" in rejected.reason_codes
