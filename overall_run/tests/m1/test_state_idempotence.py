from __future__ import annotations

from dataclasses import replace

import numpy as np
import torch

from overall_run.src.m1.contracts import StateCommitStatus, TriggerType
from overall_run.src.m1.distribution import DiscreteBins
from overall_run.src.m1.model import SingleLightweightGRU
from overall_run.src.m1.runtime import M1UpdateService


def _service() -> M1UpdateService:
    torch.manual_seed(7)
    bins = {
        target: DiscreteBins((0.0, 5.0), (5.0, None))
        for target in ("R_IB", "R_OB", "T_TX")
    }
    return M1UpdateService(
        SingleLightweightGRU(1, {target: 2 for target in bins}),
        ("wind_speed",),
        bins,
        {target: 1.0 for target in bins},
        model_version="model-1",
        temperature_version="temperature-1",
    )


def test_repeated_query_reuses_committed_state(input_bundle_factory) -> None:
    service = _service()
    bundle = input_bundle_factory()
    first = service.update_and_predict(bundle, TriggerType.SCHEDULED, True)
    second = service.update_and_predict(bundle, TriggerType.SCHEDULED, True)
    assert len(service.state_store.entries("ep-1")) == 1
    assert second.state_commit_status is StateCommitStatus.REUSED
    for target in first.distributions:
        np.testing.assert_array_equal(
            first.distributions[target].probabilities,
            second.distributions[target].probabilities,
        )


def test_all_triggers_use_the_same_model(input_bundle_factory) -> None:
    bundle = input_bundle_factory()
    scheduled = _service().scheduled_update(bundle)
    event = _service().event_update(bundle)
    direct = _service().predict_now(bundle)
    assert scheduled.hidden_state == event.hidden_state == direct.hidden_state
    assert direct.state_commit_status is StateCommitStatus.TEMPORARY
