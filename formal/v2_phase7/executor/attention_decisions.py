"""``ATTENTION_DECISIONS`` stage: one shared Stage-I selector per variant/capacity.

``P^D`` and ``P^C`` are distinct priority signals but they are ranked by exactly
one selector over exactly one candidate queue:

``K = ceil(q N)`` with ``rank = sort by (-score, episode_id, node_id)`` and
``q in {0.05, 0.10, 0.20, 0.30}``.

The candidate queue always contains every canonical node of the variant; nodes
without common support are carried as typed abstentions and are excluded from
``N`` by the frozen selector, never zero-filled.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from model.M3.stage1 import (
    ATTENTION_CAPACITY_GRID,
    NOMINAL_ATTENTION_CAPACITY,
    STAGE_I_TIE_BREAK,
    select_paired_attention,
)
from model.PRE.decision_environment import action_stage_class
from model.common.decision_contracts import AttentionDecision
from model.common.enums import OperationalStage

from .. import constants as C
from ..errors import _require
from . import stages as S
from .codec import attention_decision_to_payload, attention_decision_from_payload
from .consequence_variants import signals_by_variant


def build_attention_decisions(
    nodes: Sequence[str],
    *,
    consequence_variants: Mapping[str, Any],
) -> dict[str, Any]:
    """Select both Stage-I shortlists for every variant and capacity."""

    _require(bool(nodes), "PHASE7_ATTENTION_EMPTY_NODE_SET")
    node_ids = tuple(sorted(str(node_id) for node_id in nodes))
    stage_by_node = _stage_by_node(consequence_variants, node_ids)
    rows: list[dict[str, Any]] = []
    for variant in S.PRIMARY_STATE_VARIANTS:
        signals = signals_by_variant(consequence_variants, variant)
        _require(
            set(signals) == set(node_ids),
            "PHASE7_ATTENTION_CANDIDATE_QUEUE_MISMATCH",
            {"variant": variant},
        )
        delay_queue = tuple(signals[node_id][0] for node_id in node_ids)
        consequence_queue = tuple(signals[node_id][1] for node_id in node_ids)
        abstaining = sum(
            1
            for node_id in node_ids
            if signals[node_id][1].score is None
        )
        for q in C.Q_GRID:
            delay_decision, consequence_decision = select_paired_attention(
                delay_queue,
                consequence_queue,
                q=q,
            )
            _require(
                delay_decision.k == consequence_decision.k
                and delay_decision.cohort_size == consequence_decision.cohort_size,
                "PHASE7_ATTENTION_SHARED_SELECTOR_VIOLATION",
                {"variant": variant, "q": q},
            )
            selected_ids = tuple(
                entry.node_id
                for entry in consequence_decision.entries
                if entry.selected
            )
            rows.append(
                {
                    "variant": variant,
                    "q": float(q),
                    "k": int(consequence_decision.k),
                    "cohort_size": int(consequence_decision.cohort_size),
                    "abstaining_node_count": abstaining,
                    "selected_node_ids": list(selected_ids),
                    "selected_stage_counts": _stage_counts(
                        selected_ids, stage_by_node
                    ),
                    "selected_stage_class_counts": _stage_class_counts(
                        selected_ids, stage_by_node
                    ),
                    "delay_decision": attention_decision_to_payload(delay_decision),
                    "consequence_decision": attention_decision_to_payload(
                        consequence_decision
                    ),
                }
            )
    return {
        "reference_variant": S.REFERENCE_VARIANT,
        "q_grid": [float(value) for value in C.Q_GRID],
        "nominal_q": C.NOMINAL_Q,
        "selector": {
            "selector_id": "M3_STAGE1_SHARED_SELECTOR",
            "capacity_rule": "K = ceil(q * N)",
            "tie_break": STAGE_I_TIE_BREAK,
            "grid": [float(value) for value in ATTENTION_CAPACITY_GRID],
            "nominal_q": NOMINAL_ATTENTION_CAPACITY,
            "shared_for_signals": ["DELAY", "CONSEQUENCE"],
            "abstaining_nodes_excluded": True,
        },
        "row_count": len(rows),
        "rows": rows,
    }


def _stage_by_node(
    consequence_variants: Mapping[str, Any], node_ids: Sequence[str]
) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for row in consequence_variants["rows"]:
        node_id = str(row["node_id"])
        if node_id in node_ids:
            resolved[node_id] = str(row["stage"])
    missing = sorted(set(node_ids) - set(resolved))
    _require(
        not missing,
        "PHASE7_ATTENTION_NODE_STAGE_MISSING",
        missing,
    )
    return resolved


def _stage_counts(
    node_ids: Sequence[str], stage_by_node: Mapping[str, str]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node_id in node_ids:
        stage = stage_by_node[str(node_id)]
        counts[stage] = counts.get(stage, 0) + 1
    return dict(sorted(counts.items()))


def _stage_class_counts(
    node_ids: Sequence[str], stage_by_node: Mapping[str, str]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node_id in node_ids:
        stage_class = action_stage_class(
            OperationalStage(stage_by_node[str(node_id)])
        )
        counts[stage_class] = counts.get(stage_class, 0) + 1
    return dict(sorted(counts.items()))


def decision_rows(
    payload: Mapping[str, Any], variant: str, q: float
) -> Mapping[str, Any]:
    for row in payload["rows"]:
        if row["variant"] == variant and abs(float(row["q"]) - float(q)) <= 1e-9:
            return row
    raise KeyError((variant, q))


def attention_decision(
    payload: Mapping[str, Any], variant: str, q: float, signal: str
) -> AttentionDecision:
    row = decision_rows(payload, variant, q)
    key = "delay_decision" if signal == "DELAY" else "consequence_decision"
    return attention_decision_from_payload(row[key])


__all__ = [
    "attention_decision",
    "build_attention_decisions",
    "decision_rows",
]
