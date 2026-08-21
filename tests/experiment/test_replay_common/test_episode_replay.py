from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from exp.common.replay import (
    EpisodeReplaySelector,
    ReplayAvailabilitySemantics,
    ReplayDecisionRecord,
    ReplayEpisodeRecord,
    ReplayEpisodeRegistry,
    ReplaySelectionStatus,
    construct_replay_scenario,
)


UTC = timezone.utc


def _episode(*, episode_id: str = "episode-001", split_id: str = "development") -> ReplayEpisodeRecord:
    decision_time = datetime(2019, 8, 15, 12, tzinfo=UTC)
    return ReplayEpisodeRecord(
        episode_id=episode_id,
        split_id=split_id,
        scenario_lineage=("pre:episode-001", "m1:seed-001"),
        decision_records=(
            ReplayDecisionRecord(
                decision_node_id="node-001",
                decision_time=decision_time,
                information_cutoff=decision_time - timedelta(minutes=5),
                legal_record_ids=("weather:001", "schedule:001"),
                legal_record_availability_times=(
                    decision_time - timedelta(minutes=10),
                    decision_time - timedelta(minutes=5),
                ),
            ),
        ),
    )


def _registry(*episodes: ReplayEpisodeRecord) -> ReplayEpisodeRegistry:
    return ReplayEpisodeRegistry(
        dataset_id="TEST_REPLAY",
        source_dataset_id="test_replay_2019",
        dataset_version="TEST-REPLAY-FREEZE-001",
        source_manifest_hash="sha256:" + "a" * 64,
        pre_schema_version="TEST_PRE_V1",
        episodes=episodes,
    )


def test_episode_identity_and_scenario_construction_are_preserved():
    result = EpisodeReplaySelector().select(
        _registry(_episode()),
        episode_ids=("episode-001",),
        expected_split="development",
    )

    assert result.status is ReplaySelectionStatus.READY
    selected = result.selected_episodes[0]
    binding = construct_replay_scenario(
        selected,
        decision_node_id="node-001",
        scenario_ids=(0, 1),
    )
    assert binding.episode_id == selected.episode_id
    assert binding.decision_node_id == selected.decision_node_ids[0]
    assert binding.decision_time == selected.decision_timestamps[0]
    assert binding.information_cutoff == selected.information_cutoffs[0]
    assert binding.scenario_lineage == selected.scenario_lineage


def test_cutoff_validation_rejects_future_information():
    decision_time = datetime(2019, 8, 15, 12, tzinfo=UTC)
    with pytest.raises(ValueError, match="REPLAY_FUTURE_INFORMATION_LEAKAGE"):
        ReplayDecisionRecord(
            decision_node_id="node-future",
            decision_time=decision_time,
            information_cutoff=decision_time,
            legal_record_ids=("future-weather",),
            legal_record_availability_times=(decision_time + timedelta(seconds=1),),
        )


def test_prevalidated_cutoff_legality_does_not_require_synthetic_availability():
    decision_time = datetime(2019, 8, 15, 12, tzinfo=UTC)
    record = ReplayDecisionRecord(
        decision_node_id="node-prevalidated",
        decision_time=decision_time,
        information_cutoff=decision_time,
        legal_record_ids=("flight:001",),
        availability_time_semantics=ReplayAvailabilitySemantics.PREVALIDATED_LEGAL_AT_CUTOFF,
    )
    assert record.legal_record_availability_times == ()
    assert record.availability_time_semantics.value == "PREVALIDATED_LEGAL_AT_CUTOFF"


def test_prevalidated_cutoff_legality_rejects_synthetic_timestamp():
    decision_time = datetime(2019, 8, 15, 12, tzinfo=UTC)
    with pytest.raises(
        ValueError,
        match="REPLAY_PREVALIDATED_RECORDS_MUST_NOT_CARRY_SYNTHETIC_AVAILABILITY",
    ):
        ReplayDecisionRecord(
            decision_node_id="node-prevalidated",
            decision_time=decision_time,
            information_cutoff=decision_time,
            legal_record_ids=("flight:001",),
            availability_time_semantics=(
                ReplayAvailabilitySemantics.PREVALIDATED_LEGAL_AT_CUTOFF
            ),
            legal_record_availability_times=(decision_time,),
        )


def test_split_containment_rejects_episodes_outside_the_requested_split():
    result = EpisodeReplaySelector().select(
        _registry(_episode(split_id="final_test")),
        episode_ids=("episode-001",),
        expected_split="development",
    )

    assert result.status is ReplaySelectionStatus.BLOCKED
    assert result.selected_episodes == ()
    assert result.reason_codes == (
        "REPLAY_EPISODE_SPLIT_MISMATCH:episode-001:expected=development:actual=final_test",
    )
