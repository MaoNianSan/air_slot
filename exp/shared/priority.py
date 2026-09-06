"""Experiment-neutral typed interface for recovery-priority candidates.

The objects in this module are deliberately *candidate* objects.  They make
the shared score shape and callable boundary explicit without registering a
paper protocol or selecting the final recovery-priority aggregation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from .contracts import (
    CURRENT_AGGREGATION_CANDIDATE,
    PriorityAggregationCandidate,
    RecoveryPriorityScoreRecord,
    SupportedScore,
)


@runtime_checkable
class PriorityAggregator(Protocol):
    """Callable boundary implemented by a future frozen aggregation."""

    def __call__(
        self, values: Mapping[str, SupportedScore]
    ) -> SupportedScore: ...


@runtime_checkable
class PriorityScoreProvider(Protocol):
    """Node-level provider boundary consumed by downstream experiments."""

    def score_node(
        self,
        scenarios: Sequence[object],
        consequences: Sequence[object],
        *,
        repository_head: str,
        m1_lineage: Sequence[str],
    ) -> RecoveryPriorityScoreRecord: ...


def validate_development_scope(*, final_test_access_count: int) -> None:
    """Guard the shared candidate layer against accidental Test access."""

    if final_test_access_count != 0:
        raise RuntimeError("SHARED_PRIORITY_FINAL_TEST_ACCESS_FORBIDDEN")


def current_aggregation_candidate() -> PriorityAggregationCandidate:
    """Return the current candidate descriptor without protocol registration."""

    return CURRENT_AGGREGATION_CANDIDATE


__all__ = [
    "PriorityAggregator",
    "PriorityScoreProvider",
    "current_aggregation_candidate",
    "validate_development_scope",
]
