"""``ATTENTION_DECISIONS`` stage: stage-local Stage-I selectors.

``P^D`` and ``P^C`` remain distinct priority signals but they are ranked by
exactly one shared selector over one *stage-local* candidate queue. PRE and TURN
are evaluated independently; TAXI and COMP never enter a Stage-I queue.

For every ``variant x stage x q`` row the checkpoint persists the fixed
canonical queue, the post-support eligible queue, typed abstentions, the
eligible-ID hash and both decision payloads.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Mapping, Sequence

from model.M3.stage1 import (
    ATTENTION_CAPACITY_GRID,
    NOMINAL_ATTENTION_CAPACITY,
    STAGE_I_TIE_BREAK,
    select_paired_attention,
)
from model.PRE.decision_environment import action_stage_class
from model.common.decision_contracts import AttentionDecision
from model.common.enums import OperationalStage, SupportState

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
    """Select both Stage-I shortlists independently for PRE and TURN."""

    _require(bool(nodes), "PHASE7_ATTENTION_EMPTY_NODE_SET")
    node_ids = tuple(sorted(str(node_id) for node_id in nodes))
    identity_by_node = _identity_by_node(consequence_variants, node_ids)
    stage_by_node = {
        node_id: stage for node_id, (_episode_id, stage) in identity_by_node.items()
    }
    rows: list[dict[str, Any]] = []
    for variant in S.PRIMARY_STATE_VARIANTS:
        signals = signals_by_variant(consequence_variants, variant)
        _require(
            set(signals) == set(node_ids),
            "PHASE7_ATTENTION_CANDIDATE_QUEUE_MISMATCH",
            {"variant": variant},
        )
        for stage in S.ACTIONABLE_STAGE_I_STAGES:
            stage_node_ids = tuple(
                node_id
                for node_id in node_ids
                if stage_by_node[node_id] == stage
            )
            if not stage_node_ids:
                continue
            _require(
                all(stage_by_node[node_id] == stage for node_id in stage_node_ids),
                "PHASE7_ATTENTION_CROSS_STAGE_NODE_LEAKAGE",
                {"variant": variant, "stage": stage},
            )
            _assert_stage1_candidate_uniqueness(
                stage_node_ids,
                identity_by_node=identity_by_node,
                variant=variant,
                stage=stage,
            )
            delay_queue = tuple(signals[node_id][0] for node_id in stage_node_ids)
            consequence_queue = tuple(
                signals[node_id][1] for node_id in stage_node_ids
            )
            eligible_node_ids = tuple(
                node_id
                for node_id in stage_node_ids
                if signals[node_id][1].support is not SupportState.ABSTAIN
                and signals[node_id][1].score is not None
            )
            abstaining_node_ids = tuple(
                node_id
                for node_id in stage_node_ids
                if node_id not in set(eligible_node_ids)
            )
            delay_supported_ids = {
                node_id
                for node_id in stage_node_ids
                if signals[node_id][0].support is not SupportState.ABSTAIN
                and signals[node_id][0].score is not None
            }
            _require(
                set(eligible_node_ids) == delay_supported_ids,
                "PHASE7_ATTENTION_STAGE_CANDIDATE_MISMATCH",
                {"variant": variant, "stage": stage},
            )
            for q in C.Q_GRID:
                delay_decision, consequence_decision = select_paired_attention(
                    delay_queue,
                    consequence_queue,
                    q=q,
                )
                _require(
                    delay_decision.k == consequence_decision.k
                    and delay_decision.cohort_size
                    == consequence_decision.cohort_size,
                    "PHASE7_ATTENTION_SHARED_SELECTOR_VIOLATION",
                    {"variant": variant, "stage": stage, "q": q},
                )
                _require(
                    delay_decision.cohort_size == len(eligible_node_ids)
                    and consequence_decision.cohort_size == len(eligible_node_ids),
                    "PHASE7_ATTENTION_STAGE_CANDIDATE_MISMATCH",
                    {"variant": variant, "stage": stage, "q": q},
                )
                selected_ids = tuple(
                    entry.node_id
                    for entry in consequence_decision.entries
                    if entry.selected
                )
                selected_stages = {
                    stage_by_node[node_id] for node_id in selected_ids
                }
                _require(
                    selected_stages <= {stage},
                    "PHASE7_ATTENTION_CROSS_STAGE_NODE_LEAKAGE",
                    {
                        "variant": variant,
                        "stage": stage,
                        "q": q,
                        "selected_stages": sorted(selected_stages),
                    },
                )
                rows.append(
                    {
                        "variant": variant,
                        "stage": stage,
                        "q": float(q),
                        "k": int(consequence_decision.k),
                        "cohort_size": int(consequence_decision.cohort_size),
                        "canonical_stage_node_ids": list(stage_node_ids),
                        "canonical_stage_node_count": len(stage_node_ids),
                        "eligible_candidate_node_ids": list(eligible_node_ids),
                        "eligible_candidate_count": len(eligible_node_ids),
                        "abstaining_node_ids": list(abstaining_node_ids),
                        "abstaining_node_count": len(abstaining_node_ids),
                        "eligible_candidate_ids_hash": _id_hash(
                            eligible_node_ids
                        ),
                        "selected_node_ids": list(selected_ids),
                        "selected_stage_counts": _stage_counts(
                            selected_ids, stage_by_node
                        ),
                        "selected_stage_class_counts": _stage_class_counts(
                            selected_ids, stage_by_node
                        ),
                        "delay_decision": attention_decision_to_payload(
                            delay_decision
                        ),
                        "consequence_decision": attention_decision_to_payload(
                            consequence_decision
                        ),
                    }
                )
    return {
        "reference_variant": S.REFERENCE_VARIANT,
        "stage1_actionable_stages": list(S.ACTIONABLE_STAGE_I_STAGES),
        "stage1_non_actionable_stages": [
            stage
            for stage in C.STAGE_II_NON_ACTIONABLE_STAGES
            if stage not in S.ACTIONABLE_STAGE_I_STAGES
        ],
        "q_grid": [float(value) for value in C.Q_GRID],
        "nominal_q": C.NOMINAL_Q,
        "selector": {
            "selector_id": "M3_STAGE1_SHARED_SELECTOR",
            "capacity_rule": "K = ceil(q * N)",
            "tie_break": STAGE_I_TIE_BREAK,
            "grid": [float(value) for value in ATTENTION_CAPACITY_GRID],
            "nominal_q": NOMINAL_ATTENTION_CAPACITY,
            "shared_for_signals": ["DELAY", "CONSEQUENCE"],
            "operated_per_stage": True,
            "pooled_stage1_queue": False,
            "abstaining_nodes_excluded": True,
        },
        "row_count": len(rows),
        "rows": rows,
    }


def _identity_by_node(
    consequence_variants: Mapping[str, Any], node_ids: Sequence[str]
) -> dict[str, tuple[str, str]]:
    requested = set(str(node_id) for node_id in node_ids)
    resolved: dict[str, tuple[str, str]] = {}
    for row in consequence_variants["rows"]:
        node_id = str(row["node_id"])
        if node_id not in requested:
            continue
        identity = (str(row["episode_id"]), str(row["stage"]))
        previous = resolved.get(node_id)
        _require(
            previous is None or previous == identity,
            "PHASE7_ATTENTION_NODE_IDENTITY_MISMATCH",
            {"node_id": node_id, "previous": previous, "observed": identity},
        )
        resolved[node_id] = identity
    missing = sorted(requested - set(resolved))
    _require(not missing, "PHASE7_ATTENTION_NODE_STAGE_MISSING", missing)
    return resolved


def _assert_stage1_candidate_uniqueness(
    stage_node_ids: Sequence[str],
    *,
    identity_by_node: Mapping[str, tuple[str, str]],
    variant: str,
    stage: str,
) -> None:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for node_id in stage_node_ids:
        episode_id, observed_stage = identity_by_node[str(node_id)]
        counts[(episode_id, observed_stage)] += 1
    duplicates = {
        f"{episode_id}|{observed_stage}": count
        for (episode_id, observed_stage), count in counts.items()
        if count > 1
    }
    _require(
        not duplicates,
        "PHASE7_STAGE1_NONCANONICAL_EPISODE_STAGE_DUPLICATION",
        {"variant": variant, "stage": stage, "duplicates": duplicates},
    )


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
        stage = stage_by_node[str(node_id)]
        stage_class = action_stage_class(OperationalStage(stage))
        counts[stage_class] = counts.get(stage_class, 0) + 1
    return dict(sorted(counts.items()))


def _id_hash(node_ids: Sequence[str]) -> str:
    body = json.dumps(
        {"eligible_candidate_node_ids": [str(value) for value in node_ids]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def decision_rows(
    payload: Mapping[str, Any], variant: str, stage: str, q: float
) -> Mapping[str, Any]:
    for row in payload["rows"]:
        if (
            row["variant"] == variant
            and row["stage"] == stage
            and abs(float(row["q"]) - float(q)) <= 1e-9
        ):
            return row
    raise KeyError((variant, stage, q))


def attention_decision(
    payload: Mapping[str, Any],
    variant: str,
    stage: str,
    q: float,
    signal: str,
) -> AttentionDecision:
    row = decision_rows(payload, variant, stage, q)
    key = "delay_decision" if signal == "DELAY" else "consequence_decision"
    return attention_decision_from_payload(row[key])


__all__ = [
    "attention_decision",
    "build_attention_decisions",
    "decision_rows",
]
