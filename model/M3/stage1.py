"""M3 Stage-I attention: one shared Top-K selector (Phase 3).

The delay comparator ``P^D`` and the consequence authority ``P^C`` are distinct
priority signals, but they are consumed by exactly one selector over exactly one
candidate queue. The selector is deterministic:

``rank = sort by (-score, episode_id, node_id)`` and
``K = ceil(q * N)`` for the manuscript capacity grid
``q in {0.05, 0.10, 0.20, 0.30}`` with nominal ``q_0 = 0.10``.

Nodes whose common-support attestation fails are typed ``ABSTAIN_NO_COMMON_SUPPORT``
and are excluded from the eligible cohort; they are never zero-filled and never
enter ``N``.
"""

from __future__ import annotations

from typing import Iterable

import math

from pydantic import Field

from model.common.decision_contracts import (
    AttentionDecision,
    AttentionEntry,
    PrioritySignal,
    SignalKind,
    TypedStatus,
)
from model.common.enums import SupportState
from model.common.errors import ContractError
from model.common.value_objects import FrozenModel


__all__ = [
    "ATTENTION_CAPACITY_GRID",
    "NOMINAL_ATTENTION_CAPACITY",
    "STAGE_I_TIE_BREAK",
    "AttentionCapacityRule",
    "attention_capacity_k",
    "eligible_signals",
    "rank_signals",
    "select_attention",
    "select_paired_attention",
]


ATTENTION_CAPACITY_GRID: tuple[float, ...] = (0.05, 0.10, 0.20, 0.30)
NOMINAL_ATTENTION_CAPACITY = 0.10
STAGE_I_TIE_BREAK = "(-score, episode_id, node_id)"


class AttentionCapacityRule(FrozenModel):
    """Manuscript capacity specification; the grid is substantive, not a knob."""

    nominal_q: float = Field(default=NOMINAL_ATTENTION_CAPACITY, gt=0.0, le=1.0)
    grid: tuple[float, ...] = ATTENTION_CAPACITY_GRID

    def validate_q(self, q: float) -> float:
        value = float(q)
        if not any(abs(value - allowed) <= 1e-9 for allowed in self.grid):
            raise ContractError(f"M3_ATTENTION_CAPACITY_OUTSIDE_MANUSCRIPT_GRID:{value}")
        return value


def attention_capacity_k(q: float, cohort_size: int) -> int:
    """``K = ceil(q N)`` without floating-point ceil drift."""

    if cohort_size < 0:
        raise ContractError("M3_ATTENTION_NEGATIVE_COHORT")
    if cohort_size == 0:
        return 0
    return int(math.ceil(float(q) * cohort_size - 1e-9))


def eligible_signals(
    signals: Iterable[PrioritySignal],
) -> tuple[tuple[PrioritySignal, ...], int]:
    """Split the candidate queue into eligible signals and abstaining count."""

    eligible: list[PrioritySignal] = []
    abstaining = 0
    for signal in signals:
        if signal.support is SupportState.ABSTAIN:
            if signal.status is not TypedStatus.ABSTAIN_NO_COMMON_SUPPORT:
                raise ContractError("M3_ATTENTION_UNEXPECTED_ABSTAIN_STATUS")
            abstaining += 1
            continue
        if signal.score is None:
            raise ContractError("M3_ATTENTION_SCORED_SIGNAL_WITHOUT_SCORE")
        eligible.append(signal)
    return tuple(eligible), abstaining


def rank_signals(signals: Iterable[PrioritySignal]) -> tuple[PrioritySignal, ...]:
    """Deterministic Stage-I order: ``(-score, episode_id, node_id)``."""

    resolved = tuple(signals)
    for item in resolved:
        if item.score is None:
            raise ContractError("M3_ATTENTION_RANKING_ABSTAINING_SIGNAL")

    return tuple(
        sorted(
            resolved,
            key=lambda item: (-float(item.score), item.episode_id, item.node_id),
        )
    )


def select_attention(
    signals: Iterable[PrioritySignal],
    *,
    q: float,
    rule: AttentionCapacityRule | None = None,
) -> AttentionDecision:
    """Select the Top-``K`` cohort for one priority signal."""

    active_rule = rule or AttentionCapacityRule()
    q_value = active_rule.validate_q(q)
    all_signals = tuple(signals)
    if not all_signals:
        raise ContractError("M3_ATTENTION_EMPTY_CANDIDATE_QUEUE")
    signal_types = {item.signal_type for item in all_signals}
    if len(signal_types) != 1:
        raise ContractError("M3_ATTENTION_MIXED_SIGNAL_TYPES")
    signal_type = all_signals[0].signal_type
    eligible, abstaining = eligible_signals(all_signals)
    if not eligible:
        return AttentionDecision(
            signal_type=signal_type,
            q=q_value,
            k=0,
            cohort_size=0,
            entries=(),
            status=TypedStatus.ABSTAIN_NO_EVIDENCE,
        )
    ranked = rank_signals(eligible)
    k = attention_capacity_k(q_value, len(ranked))
    entries = tuple(
        AttentionEntry(
            episode_id=item.episode_id,
            chain_id=item.chain_id,
            node_id=item.node_id,
            score=float(item.score),
            rank=rank,
            selected=rank <= k,
            selected_for=item.signal_type,
        )
        for rank, item in enumerate(ranked, start=1)
    )
    status = (
        TypedStatus.DEGRADED
        if any(item.support is SupportState.DEGRADED for item in eligible)
        else TypedStatus.SUPPORTED
    )
    reason_codes = (
        ("M3_ATTENTION_ABSTAINING_NODES_EXCLUDED",) if abstaining else ()
    )
    return AttentionDecision(
        signal_type=signal_type,
        q=q_value,
        k=k,
        cohort_size=len(ranked),
        entries=entries,
        status=status,
    )


def select_paired_attention(
    delay_signals: Iterable[PrioritySignal],
    consequence_signals: Iterable[PrioritySignal],
    *,
    q: float,
    rule: AttentionCapacityRule | None = None,
) -> tuple[AttentionDecision, AttentionDecision]:
    """Select both shortlists from one shared candidate queue.

    The candidate queue, the capacity rule and the selector are shared; only the
    priority signal differs.
    """

    delay = tuple(delay_signals)
    consequence = tuple(consequence_signals)
    for signal in delay:
        if signal.signal_type is not SignalKind.DELAY:
            raise ContractError("M3_ATTENTION_EXPECTED_DELAY_SIGNAL")
    for signal in consequence:
        if signal.signal_type is not SignalKind.CONSEQUENCE:
            raise ContractError("M3_ATTENTION_EXPECTED_CONSEQUENCE_SIGNAL")
    delay_queue = {(item.episode_id, item.chain_id, item.node_id) for item in delay}
    consequence_queue = {
        (item.episode_id, item.chain_id, item.node_id) for item in consequence
    }
    if delay_queue != consequence_queue:
        raise ContractError("M3_ATTENTION_CANDIDATE_QUEUE_MISMATCH")
    active_rule = rule or AttentionCapacityRule()
    return (
        select_attention(delay, q=q, rule=active_rule),
        select_attention(consequence, q=q, rule=active_rule),
    )
