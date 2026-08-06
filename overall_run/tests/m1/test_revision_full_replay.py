from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from .factories import build_test_service
from .test_state_replay import _Provider


def test_temporary_revision_replay_does_not_modify_committed_state(input_bundle_factory) -> None:
    first = input_bundle_factory(snapshot_id="s1")
    second = replace(
        first,
        snapshot_id="s2",
        query_time=first.query_time + timedelta(minutes=5),
        information_cutoff=first.information_cutoff + timedelta(minutes=5),
    )
    provider = _Provider((first, second))
    service = build_test_service(provider)
    service.scheduled_update(first)
    service.scheduled_update(second)
    revised = replace(first, snapshot_id="s1-v2", snapshot_version=2)
    provider.snapshots = (revised, second)
    result = service.replay_revision(revised, commit_state=False)
    assert result.replayed_node_count == 2
    assert [entry.snapshot.snapshot_id for entry in service.state_store.entries("ep-1")] == [
        "s1",
        "s2",
    ]
