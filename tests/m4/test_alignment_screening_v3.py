from model.M4.alignment import compare_priority_representations
from model.M4.contracts import (
    PriorityOrdering,
    PriorityRepresentation,
    ScreeningCapacity,
)
from model.M4.screening import build_shortlist


def _ordering(rep, entries):
    return PriorityOrdering(
        population_digest="sha256:" + "a" * 64,
        representation=rep,
        entries=tuple((node, score, rank) for rank, (node, score) in enumerate(entries, 1)),
    )


def test_stable_top_k_and_paired_replacement():
    delay = _ordering(
        PriorityRepresentation.DELAY,
        (("A", 40.0), ("B", 30.0), ("C", 30.0), ("D", 10.0)),
    )
    consequence = _ordering(
        PriorityRepresentation.CONSEQUENCE,
        (("B", 40.0), ("C", 30.0), ("D", 20.0), ("A", 10.0)),
    )
    result = compare_priority_representations(
        delay, consequence, ScreeningCapacity(k=2)
    )
    assert result.delay_shortlist.selected_node_ids == ("A", "B")
    assert result.consequence_shortlist.selected_node_ids == ("B", "C")
    assert result.intersection == ("B",)
    assert result.delay_only == ("A",)
    assert result.consequence_only == ("C",)
    assert result.replacement_count == 1
    assert result.overlap_rate == 0.5
    assert result.rank_displacements[0].rank_displacement == 3


def test_empty_population_is_typed():
    ordering = _ordering(PriorityRepresentation.DELAY, ())
    result = build_shortlist(ordering, ScreeningCapacity(k=1))
    assert result.status == "EMPTY_POPULATION"
    assert result.effective_k == 0
    assert result.reason_code == "M4_EMPTY_POPULATION"
    assert result.boundary_score is None
