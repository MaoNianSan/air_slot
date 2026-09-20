from __future__ import annotations

from math import isfinite

from model.common.errors import ContractError

from .contracts import PriorityOrdering, ScreeningCapacity, ScreeningShortlist


def build_shortlist(
    ordering: PriorityOrdering,
    capacity: ScreeningCapacity,
) -> ScreeningShortlist:
    entries = ordering.entries
    n = len(entries)
    if n == 0:
        return ScreeningShortlist(
            population_digest=ordering.population_digest,
            representation=ordering.representation,
            requested_k=capacity.k,
            effective_k=0,
            population_size=0,
            selected_node_ids=(),
            boundary_score=None,
            boundary_tie_count=0,
            status="EMPTY_POPULATION",
            reason_code="M4_EMPTY_POPULATION",
        )
    k = min(capacity.k, n)
    boundary = float(entries[k - 1][1])
    if not isfinite(boundary):
        raise ContractError("M4_ORDERING_SCORE_INVALID")
    tie_count = sum(float(score) == boundary for _, score, _ in entries)
    return ScreeningShortlist(
        population_digest=ordering.population_digest,
        representation=ordering.representation,
        requested_k=capacity.k,
        effective_k=k,
        population_size=n,
        selected_node_ids=tuple(item[0] for item in entries[:k]),
        boundary_score=boundary,
        boundary_tie_count=tie_count,
        status="READY",
    )


__all__ = ["build_shortlist"]
