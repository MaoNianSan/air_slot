"""Experiment-neutral interface for the frozen recovery-priority contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from .contracts import (
    SHARED_PRIORITY_AUTHORITY,
    RecoveryPriorityScoreRecord,
    SharedPriorityAuthority,
    SupportedScore,
)


@runtime_checkable
class PriorityAggregator(Protocol):
    def __call__(self, values: Mapping[str, SupportedScore]) -> SupportedScore: ...


@runtime_checkable
class PriorityScoreProvider(Protocol):
    def score_node(
        self,
        scenarios: Sequence[object],
        consequences: Sequence[object],
        *,
        repository_head: str,
        m1_lineage: Sequence[str],
    ) -> RecoveryPriorityScoreRecord: ...


def validate_development_scope(*, final_test_access_count: int) -> None:
    if final_test_access_count != 0:
        raise RuntimeError("SHARED_PRIORITY_FINAL_TEST_ACCESS_FORBIDDEN")


def current_scientific_authority() -> SharedPriorityAuthority:
    return SHARED_PRIORITY_AUTHORITY


__all__ = [
    "PriorityAggregator",
    "PriorityScoreProvider",
    "current_scientific_authority",
    "validate_development_scope",
]
