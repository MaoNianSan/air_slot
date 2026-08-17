from datetime import datetime, timedelta, timezone

import pytest

from exp.exp1.history import adaptive_history, current_history, fixed_history
from model.common.errors import ContractError
from model.PRE.contracts.pre_state import DecisionNodeRecord, PREState


UTC = timezone.utc


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


def test_adaptive_history_is_full_current_episode_prefix():
    states = _prefix()
    assert adaptive_history(states) == states


def test_current_history_contains_only_current_node():
    states = _prefix()
    assert current_history(states) == (states[-1],)


def test_fixed_history_is_closed_maximum_lookback_interval():
    states = _prefix()
    selected = fixed_history(states, 30)
    assert tuple(item.decision_node.node_index for item in selected) == (2, 3, 4, 5, 6, 7, 8)
    assert selected[-1] is states[-1]


def test_fixed_history_preserves_rows_with_missing_evidence():
    states = list(_prefix())
    missing = states[5].model_copy(update={"current_state": {}})
    states[5] = missing
    assert missing in fixed_history(states, 30)


def test_history_cannot_cross_episode_or_use_future_cutoff():
    states = list(_prefix())
    node = states[2].decision_node.model_copy(update={"episode_id": "episode-b"})
    states[2] = states[2].model_copy(update={"decision_node": node})
    with pytest.raises(ContractError, match="M1_HISTORY_MULTIPLE_EPISODES"):
        adaptive_history(states)

    states = list(_prefix())
    node = states[-1].decision_node
    states[-1] = states[-1].model_copy(update={"decision_node": node.model_copy(
        update={"information_cutoff": node.decision_time + timedelta(minutes=5)})})
    with pytest.raises(ContractError, match="M1_HISTORY_FUTURE_INFORMATION"):
        adaptive_history(states)


def test_fixed_history_requires_five_minute_alignment():
    with pytest.raises(ValueError, match="FIXED_HISTORY_WINDOW_MUST_ALIGN"):
        fixed_history(_prefix(), 31)
