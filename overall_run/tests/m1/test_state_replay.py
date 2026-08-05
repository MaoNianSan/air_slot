from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from overall_run.src.m1.contracts import TriggerType

from .test_state_idempotence import _service


def test_snapshot_revision_truncates_from_revision_point(input_bundle_factory) -> None:
    service = _service()
    first = input_bundle_factory(snapshot_id="s1")
    second = replace(
        first,
        snapshot_id="s2",
        query_time=first.query_time + timedelta(minutes=5),
        information_cutoff=first.information_cutoff + timedelta(minutes=5),
    )
    service.update_and_predict(first, TriggerType.SCHEDULED, True)
    service.update_and_predict(second, TriggerType.SCHEDULED, True)
    revised = replace(first, snapshot_version=2)
    result = service.update_and_predict(revised, TriggerType.EVENT, True)
    assert result.replay_reason == "SNAPSHOT_VERSION_INCREASED"
    assert result.replay_node_count == 2
    assert [entry.input_bundle.snapshot_id for entry in service.state_store.entries("ep-1")] == ["s1"]
