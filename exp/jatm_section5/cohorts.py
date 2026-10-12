"""Canonical Stage-I cohort construction.

The canonical node is selected only by ``(decision_time, node_id)`` within each
``episode_id x operational_stage``. Support and representation eligibility are
checked after that identity is fixed; an unsupported canonical node is kept as
a typed abstention and never replaced by a later node in the same stage.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from model.common.enums import OperationalStage

from .contracts import CanonicalStageRow, RepresentationNode


def _get(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        return row[name]
    return getattr(row, name)


def _stage(row: Any) -> OperationalStage:
    value = _get(row, "stage") if _has(row, "stage") else _get(row, "operational_stage")
    return value if isinstance(value, OperationalStage) else OperationalStage(value)


def _has(row: Any, name: str) -> bool:
    if isinstance(row, Mapping):
        return name in row
    return hasattr(row, name)


def canonical_stage_cohort(
    rows: Iterable[Any],
    *,
    stage: OperationalStage,
    eligibility: Callable[[Any], bool],
) -> tuple[CanonicalStageRow, ...]:
    """Return one fixed canonical node per episode for one operational stage."""

    stage = stage if isinstance(stage, OperationalStage) else OperationalStage(stage)
    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        if _stage(row) is stage:
            grouped[str(_get(row, "episode_id"))].append(row)
    output: list[CanonicalStageRow] = []
    for episode_id in sorted(grouped):
        candidates = grouped[episode_id]
        canonical = min(
            candidates,
            key=lambda row: (
                _get(row, "decision_time"),
                str(_get(row, "node_id") if _has(row, "node_id") else _get(row, "decision_node_id")),
            ),
        )
        accepted = bool(eligibility(canonical))
        reason = "ELIGIBLE" if accepted else "CANONICAL_NODE_NOT_ELIGIBLE"
        output.append(
            CanonicalStageRow(
                node=canonical, eligible=accepted, eligibility_reason=reason
            )
        )
    return tuple(output)


def canonical_node_ids(rows: Sequence[CanonicalStageRow]) -> tuple[str, ...]:
    return tuple(
        row.node.node_id if isinstance(row.node, RepresentationNode) else str(_get(row.node, "node_id"))
        for row in rows
    )


def assert_unique_episode_stage(rows: Sequence[CanonicalStageRow]) -> None:
    keys = [(row.node.episode_id, row.node.stage) for row in rows]
    if len(keys) != len(set(keys)):
        raise RuntimeError("JATM_SECTION5_CANONICAL_EPISODE_STAGE_NOT_UNIQUE")


__all__ = [
    "assert_unique_episode_stage",
    "canonical_node_ids",
    "canonical_stage_cohort",
]
