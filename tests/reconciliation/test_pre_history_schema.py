"""Tests H/I/J — PRE evidence boundary, adaptive history, FAST/STATE schema.

Test H: information_cutoff <= decision_time is enforced on the typed PRE node
and future outcomes cannot enter E_{<=t}.  Test I: ADAPTIVE_HISTORY is the
causal prefix of the current episode only.  Test J: FAST and STATE_AWARE M1
paths emit the same M1Forecast schema.
"""

from datetime import datetime, timedelta, timezone

import pytest
import torch

from exp.exp1.history import adaptive_history
from model.M1.service import M1Service
from model.M1.pipeline import M1Pipeline
from model.PRE.contracts.pre_state import DecisionNodeRecord, PREState
from model.PRE.foundation import PREBuildRequest, build_pre_state
from model.common.errors import ContractError
from tests.fixtures.pre.foundation_cases import build_request


UTC = timezone.utc


def test_h_information_cutoff_cannot_exceed_decision_time():
    with pytest.raises(ValueError, match="information cutoff exceeds decision time"):
        DecisionNodeRecord(
            decision_node_id="n", episode_id="e",
            decision_time=datetime(2019, 1, 1, 12, tzinfo=UTC),
            information_cutoff=datetime(2019, 1, 1, 12, 5, tzinfo=UTC),
            operational_stage="PRE_IB", roll_minutes=5, node_index=0,
            status="CONSTRUCTED", formal_eligible=True,
            config_hash="sha256:a", registry_manifest_hash="sha256:b",
            legal_record_ids=(),
        )


def test_h_pre_state_carries_the_evidence_boundary_into_m1():
    request = build_request()
    assert request.information_cutoff <= request.decision_time
    pre_state = build_pre_state(request).pre_state
    node = pre_state.decision_node
    assert node.information_cutoff <= node.decision_time
    assert node.information_cutoff == datetime(2019, 1, 1, 11, 55, tzinfo=UTC)


def _prefix(count=9):
    start = datetime(2019, 8, 1, tzinfo=UTC)
    states = []
    for index in range(count):
        time = start + timedelta(minutes=5 * index)
        node = DecisionNodeRecord(
            decision_node_id=f"node-{index}", episode_id="episode-a",
            decision_time=time, information_cutoff=time,
            operational_stage="PRE_IB", roll_minutes=5, node_index=index,
            status="CONSTRUCTED", formal_eligible=True,
            config_hash="sha256:a", registry_manifest_hash="sha256:b",
            legal_record_ids=(),
        )
        states.append(PREState(decision_node=node))
    return tuple(states)


def test_i_adaptive_history_is_the_causal_prefix_only():
    states = _prefix()
    assert adaptive_history(states) == states
    assert all(
        item.decision_node.decision_time <= states[-1].decision_node.decision_time
        for item in adaptive_history(states)
    )
    # Future information is rejected on entry to the history builder.
    states = list(_prefix())
    node = states[-1].decision_node
    states[-1] = states[-1].model_copy(update={"decision_node": node.model_copy(
        update={"information_cutoff": node.decision_time + timedelta(minutes=5)})})
    with pytest.raises(ContractError, match="M1_HISTORY_FUTURE_INFORMATION"):
        adaptive_history(states)


def test_j_fast_and_state_aware_share_the_output_schema():
    pre_state = build_pre_state(build_request()).pre_state
    values = torch.zeros(1, 2, 4)
    lengths = torch.tensor([2])
    service = M1Service(
        M1Pipeline.smoke(input_size=4),
        model_version="fixture",
        fast_predictor=lambda *_: {"path": "fixture-fast"},
    )
    service.scheduled_update(pre_state)
    generated_at = pre_state.decision_node.decision_time + timedelta(minutes=5)
    fast = service.predict_now(pre_state, values, lengths, mode="fast", generated_at=generated_at)
    state = service.predict_now(pre_state, values, lengths, mode="state", generated_at=generated_at)
    fast_fields = set(fast.model_dump())
    state_fields = set(state.model_dump())
    assert fast_fields == state_fields
    assert fast.model_path.value == "FAST"
    assert state.model_path.value == "STATE_AWARE"
    # Both paths carry the same formal forecast/delay-threshold contract.
    assert fast.forecast_horizons_minutes == state.forecast_horizons_minutes
    assert fast.delay_thresholds_minutes == state.delay_thresholds_minutes
