from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from overall_run.src.m1.contracts import StateCommitStatus, TriggerType

from .test_state_idempotence import _service


def test_reset_discards_old_hidden_state(input_bundle_factory) -> None:
    service = _service()
    first = input_bundle_factory(snapshot_id="s1")
    service.update_and_predict(first, TriggerType.SCHEDULED, True)
    reset = replace(
        first,
        snapshot_id="s2",
        query_time=first.query_time + timedelta(minutes=5),
        information_cutoff=first.information_cutoff + timedelta(minutes=5),
        state_reset_signal=True,
    )
    result = service.update_and_predict(reset, TriggerType.EVENT, True)
    assert result.state_commit_status is StateCommitStatus.COMMITTED
    assert len(service.state_store.entries("ep-1")) == 1


def test_temporary_prediction_does_not_pollute_state(input_bundle_factory) -> None:
    service = _service()
    result = service.predict_now(input_bundle_factory(snapshot_id="preview"))
    assert result.state_commit_status is StateCommitStatus.TEMPORARY
    assert service.state_store.entries("ep-1") == ()
