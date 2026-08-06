from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from overall_run.src.m1.contracts import TriggerType

from .factories import build_test_service


class _Provider:
    def __init__(self, snapshots):
        self.snapshots = tuple(snapshots)

    def ordered_snapshots(self, episode_id, *, up_to_query_time):
        return tuple(
            snapshot
            for snapshot in self.snapshots
            if snapshot.episode_id == episode_id
            and snapshot.query_time <= up_to_query_time
        )


def test_snapshot_revision_replays_every_affected_node(input_bundle_factory) -> None:
    first = input_bundle_factory(snapshot_id="s1")
    second = replace(
        first,
        snapshot_id="s2",
        query_time=first.query_time + timedelta(minutes=5),
        information_cutoff=first.information_cutoff + timedelta(minutes=5),
    )
    provider = _Provider((first, second))
    service = build_test_service(provider)
    service.update_and_predict(first, TriggerType.SCHEDULED, True)
    service.update_and_predict(second, TriggerType.SCHEDULED, True)
    revised = replace(first, snapshot_id="s1-v2", snapshot_version=2)
    provider.snapshots = (revised, second)
    result = service.update_and_predict(revised, TriggerType.EVENT, True)
    assert result.replay_reason == "SNAPSHOT_VERSION_INCREASED"
    assert result.replay_node_count == 2
    assert [entry.snapshot.snapshot_id for entry in service.state_store.entries("ep-1")] == [
        "s1-v2",
        "s2",
    ]
