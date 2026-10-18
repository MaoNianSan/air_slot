from __future__ import annotations

from model.common.errors import ContractError

from .contracts import (
    PriorityAlignmentRecord,
    PriorityOrdering,
    RankDisplacement,
    ScreeningCapacity,
)
from .screening import build_shortlist


def compare_priority_representations(
    delay: PriorityOrdering,
    consequence: PriorityOrdering,
    capacity: ScreeningCapacity,
) -> PriorityAlignmentRecord:
    if delay.population_digest != consequence.population_digest:
        raise ContractError("M4_COMPARISON_BASIS_MISMATCH")
    if delay.representation.value != "DELAY" or consequence.representation.value != "CONSEQUENCE":
        raise ContractError("M4_COMPARISON_REPRESENTATION_MISMATCH")
    delay_ranks = {node_id: rank for node_id, _, rank in delay.entries}
    consequence_ranks = {node_id: rank for node_id, _, rank in consequence.entries}
    if set(delay_ranks) != set(consequence_ranks):
        raise ContractError("M4_COMPARISON_BASIS_MISMATCH")
    displacements = tuple(
        RankDisplacement(
            decision_node_id=node_id,
            delay_rank=delay_ranks[node_id],
            consequence_rank=consequence_ranks[node_id],
            rank_displacement=consequence_ranks[node_id] - delay_ranks[node_id],
            absolute_rank_displacement=abs(consequence_ranks[node_id] - delay_ranks[node_id]),
        )
        for node_id in sorted(delay_ranks)
    )
    delay_shortlist = build_shortlist(delay, capacity)
    consequence_shortlist = build_shortlist(consequence, capacity)
    hd = set(delay_shortlist.selected_node_ids)
    hc = set(consequence_shortlist.selected_node_ids)
    k = delay_shortlist.effective_k
    overlap = tuple(sorted(hd & hc))
    delay_only = tuple(sorted(hd - hc))
    consequence_only = tuple(sorted(hc - hd))
    return PriorityAlignmentRecord(
        population_digest=delay.population_digest,
        delay=delay,
        consequence=consequence,
        delay_shortlist=delay_shortlist,
        consequence_shortlist=consequence_shortlist,
        intersection=overlap,
        delay_only=delay_only,
        consequence_only=consequence_only,
        rank_displacements=displacements,
        overlap_count=len(overlap),
        replacement_count=len(delay_only),
        overlap_rate=(len(overlap) / k if k else None),
        replacement_rate=(len(delay_only) / k if k else None),
        status="READY" if k else "UNSUPPORTED",
        reason_code=None if k else "M4_EMPTY_POPULATION",
    )


__all__ = ["compare_priority_representations"]
