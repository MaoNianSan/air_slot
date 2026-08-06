from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from .factories import build_test_service


def test_existing_hidden_state_does_not_reencode_history(input_bundle_factory) -> None:
    service = build_test_service()
    first = input_bundle_factory(snapshot_id="s1", feature_vector=(1.0,))
    second = replace(
        first,
        snapshot_id="s2",
        query_time=first.query_time + timedelta(minutes=5),
        information_cutoff=first.information_cutoff + timedelta(minutes=5),
        feature_vector=(2.0,),
    )
    first_prediction = service.scheduled_update(first)
    expected = service.predict_snapshot(
        second,
        first_prediction.hidden_state,
        first_prediction.state_commit_status,
        trigger_type="SCHEDULED",
        replay_reason=None,
        replay_node_count=0,
    )
    actual = service.scheduled_update(second)
    assert actual.hidden_state == expected.hidden_state
