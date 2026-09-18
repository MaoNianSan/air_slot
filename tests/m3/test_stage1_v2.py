"""M3 Stage-I shared-selector tests (V2 Phase 3)."""

from __future__ import annotations

import pytest

from model.M3.stage1 import (
    ATTENTION_CAPACITY_GRID,
    NOMINAL_ATTENTION_CAPACITY,
    STAGE_I_TIE_BREAK,
    AttentionCapacityRule,
    attention_capacity_k,
    eligible_signals,
    rank_signals,
    select_attention,
    select_paired_attention,
)
from model.common.decision_contracts import (
    PrioritySignal,
    SignalKind,
    TypedStatus,
)
from model.common.enums import SupportState
from model.common.errors import ContractError


def _signal(
    node_id: str,
    score: float | None,
    *,
    kind: SignalKind = SignalKind.CONSEQUENCE,
    episode_id: str = "episode-1",
    chain_id: str = "chain-1",
    support: SupportState = SupportState.SUPPORTED,
    status: TypedStatus = TypedStatus.SUPPORTED,
    mass: float | None = 0.95,
    threshold: float | None = 0.90,
) -> PrioritySignal:
    return PrioritySignal(
        signal_type=kind,
        episode_id=episode_id,
        chain_id=chain_id,
        node_id=node_id,
        representation_id="HISTORY_H16:JOINT",
        score=score,
        support=support,
        status=status,
        comparison_support_mass=mass,
        comparison_support_threshold=threshold,
        reason_codes=(),
    )


def _abstaining(node_id: str, *, kind: SignalKind = SignalKind.CONSEQUENCE) -> PrioritySignal:
    return _signal(
        node_id,
        None,
        kind=kind,
        support=SupportState.ABSTAIN,
        status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
        mass=0.5,
        threshold=0.90,
    )


def test_manuscript_capacity_constants() -> None:
    assert NOMINAL_ATTENTION_CAPACITY == 0.10
    assert ATTENTION_CAPACITY_GRID == (0.05, 0.10, 0.20, 0.30)
    assert STAGE_I_TIE_BREAK == "(-score, episode_id, node_id)"


@pytest.mark.parametrize(
    ("q", "cohort_size", "expected"),
    (
        (0.05, 1, 1),
        (0.05, 20, 1),
        (0.10, 10, 1),
        (0.10, 11, 2),
        (0.20, 5, 1),
        (0.30, 10, 3),
        (0.30, 11, 4),
    ),
)
def test_attention_capacity_is_ceiling_q_times_n(
    q: float, cohort_size: int, expected: int
) -> None:
    assert attention_capacity_k(q, cohort_size) == expected


def test_zero_cohort_has_zero_capacity() -> None:
    assert attention_capacity_k(0.10, 0) == 0


def test_capacity_outside_manuscript_grid_is_rejected() -> None:
    rule = AttentionCapacityRule()
    with pytest.raises(ContractError, match="M3_ATTENTION_CAPACITY_OUTSIDE"):
        rule.validate_q(0.15)
    with pytest.raises(ContractError, match="M3_ATTENTION_CAPACITY_OUTSIDE"):
        select_attention((_signal("n-1", 1.0),), q=0.15)


def test_tie_break_is_deterministic_and_identity_based() -> None:
    signals = (
        _signal("n-2", 5.0, episode_id="ep-b"),
        _signal("n-1", 5.0, episode_id="ep-b"),
        _signal("n-9", 5.0, episode_id="ep-a"),
        _signal("n-3", 6.0, episode_id="ep-c"),
    )
    ranked = rank_signals(signals)
    assert [(item.episode_id, item.node_id) for item in ranked] == [
        ("ep-c", "n-3"),
        ("ep-a", "n-9"),
        ("ep-b", "n-1"),
        ("ep-b", "n-2"),
    ]


def test_ranking_rejects_abstaining_signal() -> None:
    with pytest.raises(ContractError, match="M3_ATTENTION_RANKING_ABSTAINING_SIGNAL"):
        rank_signals((_abstaining("n-1"),))


def test_select_attention_excludes_abstaining_nodes_from_n_and_k() -> None:
    signals = (
        _signal("n-1", 4.0),
        _signal("n-2", 3.0),
        _signal("n-3", 2.0),
        _signal("n-4", 1.0),
        _abstaining("n-abstain"),
    )
    decision = select_attention(signals, q=0.05)
    assert decision.cohort_size == 4
    assert decision.k == 1
    assert [item.node_id for item in decision.entries] == ["n-1", "n-2", "n-3", "n-4"]
    assert [item.node_id for item in decision.entries if item.selected] == ["n-1"]
    assert all(item.node_id != "n-abstain" for item in decision.entries)


def test_all_abstaining_nodes_return_typed_no_evidence() -> None:
    decision = select_attention(
        (_abstaining("n-1"), _abstaining("n-2")), q=0.10
    )
    assert decision.status is TypedStatus.ABSTAIN_NO_EVIDENCE
    assert decision.cohort_size == 0
    assert decision.k == 0
    assert decision.entries == ()


def test_empty_candidate_queue_is_typed_error() -> None:
    with pytest.raises(ContractError, match="M3_ATTENTION_EMPTY_CANDIDATE_QUEUE"):
        select_attention((), q=0.10)


def test_mixed_signal_types_are_rejected() -> None:
    with pytest.raises(ContractError, match="M3_ATTENTION_MIXED_SIGNAL_TYPES"):
        select_attention(
            (
                _signal("n-1", 1.0, kind=SignalKind.DELAY),
                _signal("n-2", 2.0, kind=SignalKind.CONSEQUENCE),
            ),
            q=0.10,
        )


def test_eligible_signals_reports_abstaining_count() -> None:
    eligible, abstaining = eligible_signals(
        (_signal("n-1", 1.0), _abstaining("n-2"), _abstaining("n-3"))
    )
    assert [item.node_id for item in eligible] == ["n-1"]
    assert abstaining == 2


def test_paired_selector_uses_one_candidate_queue_and_capacity() -> None:
    delay = tuple(
        _signal(f"n-{index}", 10.0 - index, kind=SignalKind.DELAY)
        for index in range(4)
    )
    consequence = tuple(
        _signal(f"n-{index}", float(index), kind=SignalKind.CONSEQUENCE)
        for index in range(4)
    )
    delay_decision, consequence_decision = select_paired_attention(
        delay, consequence, q=0.10
    )
    assert delay_decision.k == consequence_decision.k == 1
    assert delay_decision.cohort_size == consequence_decision.cohort_size == 4
    assert [item.node_id for item in delay_decision.entries if item.selected] == ["n-0"]
    assert [
        item.node_id for item in consequence_decision.entries if item.selected
    ] == ["n-3"]


def test_paired_selector_rejects_different_candidate_queues() -> None:
    delay = (_signal("n-1", 1.0, kind=SignalKind.DELAY),)
    consequence = (
        _signal("n-1", 1.0, kind=SignalKind.CONSEQUENCE),
        _signal("n-2", 2.0, kind=SignalKind.CONSEQUENCE),
    )
    with pytest.raises(ContractError, match="M3_ATTENTION_CANDIDATE_QUEUE_MISMATCH"):
        select_paired_attention(delay, consequence, q=0.10)


def test_paired_selector_rejects_wrong_signal_kind() -> None:
    with pytest.raises(ContractError, match="M3_ATTENTION_EXPECTED_DELAY_SIGNAL"):
        select_paired_attention(
            (_signal("n-1", 1.0, kind=SignalKind.CONSEQUENCE),),
            (_signal("n-1", 1.0, kind=SignalKind.CONSEQUENCE),),
            q=0.10,
        )
