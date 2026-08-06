from __future__ import annotations

import numpy as np

from overall_run.src.m1.contracts import StateCommitStatus, TriggerType

from .factories import build_test_service


def test_repeated_query_reuses_committed_state(input_bundle_factory) -> None:
    service = build_test_service()
    snapshot = input_bundle_factory()
    first = service.update_and_predict(snapshot, TriggerType.SCHEDULED, True)
    second = service.update_and_predict(snapshot, TriggerType.SCHEDULED, True)
    assert len(service.state_store.entries("ep-1")) == 1
    assert second.state_commit_status is StateCommitStatus.REUSED
    for target in first.distributions:
        np.testing.assert_array_equal(
            first.distributions[target].probabilities,
            second.distributions[target].probabilities,
        )


def test_all_triggers_use_one_incremental_node(input_bundle_factory) -> None:
    snapshot = input_bundle_factory()
    scheduled = build_test_service().scheduled_update(snapshot)
    event = build_test_service().event_update(snapshot)
    direct = build_test_service().predict_now(snapshot)
    assert scheduled.hidden_state == event.hidden_state == direct.hidden_state
    assert direct.state_commit_status is StateCommitStatus.TEMPORARY
