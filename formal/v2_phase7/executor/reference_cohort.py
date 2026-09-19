"""``REFERENCE_RECOVERY_COHORT``: the frozen reference shortlist and ``R_g*``.

The frozen Freeze-R2 authority fixes

``H_g^{C,*} = H_g^{C,History+Joint}``

and

``R_g* = H_g^{C,History+Joint} \u2229 StageIISupported``.

``H_g^{C,*}`` is the consequence-based Stage-I shortlist of the
``HISTORY_JOINT`` reference variant at the nominal attention environment
``q_0 = 0.10``. ``StageIISupported`` means the node can actually carry a
Stage-II decision under the reference representation:

* the operational stage has a non-empty local off-block recovery action set
  (``PRE_IB`` / ``POST_IB_PRE_OB``), and
* every scenario of the reference state set is supported, because the frozen
  Stage-II objective is undefined on an abstaining scenario.

Nodes that fail either condition stay typed (``NOT_ACTIONABLE`` /
``ABSTAIN_NO_COMMON_SUPPORT``): they are excluded from ``R_g*`` and are never
zero-filled. Every alternative representation is later evaluated on exactly
this same ``R_g*``; only the reference variant defines the cohort.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from model.PRE.decision_environment import is_actionable
from model.common.enums import OperationalStage, SupportState

from .. import constants as C
from ..errors import TypedBlocker, _require
from . import stages as S
from .attention_decisions import attention_decision
from .nodes import CanonicalNode, nodes_by_id
from .state_variants import state_sets_by_node

NOT_ACTIONABLE_TYPED_STATE = "NOT_ACTIONABLE"
ABSTAIN_TYPED_STATE = "ABSTAIN_NO_COMMON_SUPPORT"


def reference_shortlist_node_ids(
    attention_decisions: Mapping[str, Any],
    *,
    variant: str = S.REFERENCE_VARIANT,
    q: float = C.NOMINAL_Q,
) -> tuple[str, ...]:
    """``H_g^{C,*}``: selected nodes of the consequence Stage-I decision."""

    decision = attention_decision(attention_decisions, variant, q, "CONSEQUENCE")
    return tuple(entry.node_id for entry in decision.entries if entry.selected)


def build_reference_recovery_cohort(
    nodes_payload: Mapping[str, Any],
    state_variants: Mapping[str, Any],
    attention_decisions: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish ``H_g^{C,*}`` and ``R_g*`` for the frozen reference authority."""

    nodes = nodes_by_id(nodes_payload)
    shortlist = reference_shortlist_node_ids(attention_decisions)
    _require(bool(shortlist), "PHASE7_REFERENCE_SHORTLIST_EMPTY")
    reference_state_sets = state_sets_by_node(state_variants, S.REFERENCE_VARIANT)

    included: list[str] = []
    excluded: list[dict[str, Any]] = []
    for node_id in shortlist:
        node = nodes.get(node_id)
        if node is None:
            raise TypedBlocker(
                "PHASE7_REFERENCE_SHORTLIST_NODE_NOT_MATERIALIZED", node_id
            )
        stage = OperationalStage(node.stage)
        if not is_actionable(stage):
            excluded.append(
                _exclusion(
                    node,
                    typed_state=NOT_ACTIONABLE_TYPED_STATE,
                    reason_codes=(
                        "PHASE7_STAGE_NOT_ACTIONABLE_LOCAL_ACTION_SET_IS_ZERO",
                    ),
                )
            )
            continue
        state_set = reference_state_sets.get(node_id)
        if state_set is None:
            raise TypedBlocker(
                "PHASE7_REFERENCE_STATE_SET_MISSING", node_id
            )
        abstaining = tuple(
            scenario.scenario_id
            for scenario in state_set.scenarios
            if scenario.support is SupportState.ABSTAIN
        )
        if abstaining:
            excluded.append(
                {
                    **_exclusion(
                        node,
                        typed_state=ABSTAIN_TYPED_STATE,
                        reason_codes=(
                            "PHASE7_REFERENCE_STATE_SCENARIO_UNSUPPORTED",
                        ),
                    ),
                    "abstaining_scenario_ids": [int(value) for value in abstaining],
                }
            )
            continue
        included.append(node_id)

    stage_counts = _stage_counts(tuple(shortlist), nodes)
    return {
        "reference_variant": S.REFERENCE_VARIANT,
        "reference_authority": C.REFERENCE_AUTHORITY,
        "reference_representation_id": C.REFERENCE_REPRESENTATION_ID,
        "nominal_q": float(C.NOMINAL_Q),
        "cohort_id": C.STAGE2_INFORMATION_COHORT,
        "shortlist_rule": "STAGE_I_CONSEQUENCE_TOP_K_SHARED_SELECTOR",
        "shortlist_authority": "P^C = Phi_C(C^CU)",
        "shortlist_node_ids": list(shortlist),
        "shortlist_size": len(shortlist),
        "shortlist_stage_counts": stage_counts,
        "stage2_support_rule": (
            "ACTIONABLE_STAGE_AND_REFERENCE_STATE_FULLY_SUPPORTED"
        ),
        "stage2_actionable_node_ids": included,
        "stage2_cohort_size": len(included),
        "stage2_excluded": excluded,
        "stage2_excluded_count": len(excluded),
        "alternative_representations_use_fixed_r_star": True,
        "typed_states": sorted(
            {entry["typed_state"] for entry in excluded}
        ),
    }


def actionable_cohort(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Decode ``R_g*`` from the published cohort checkpoint."""

    cohort = tuple(str(value) for value in payload["stage2_actionable_node_ids"])
    _require(
        len(set(cohort)) == len(cohort),
        "PHASE7_REFERENCE_COHORT_NOT_UNIQUE",
    )
    return cohort


def _exclusion(
    node: CanonicalNode, *, typed_state: str, reason_codes: Sequence[str]
) -> dict[str, Any]:
    return {
        "node_id": node.node_id,
        "episode_id": node.episode_id,
        "stage": node.stage,
        "typed_state": typed_state,
        "reason_codes": [str(code) for code in reason_codes],
    }


def _stage_counts(
    node_ids: Sequence[str], nodes: Mapping[str, CanonicalNode]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node_id in node_ids:
        stage = nodes[node_id].stage
        counts[stage] = counts.get(stage, 0) + 1
    return dict(sorted(counts.items()))


__all__ = [
    "ABSTAIN_TYPED_STATE",
    "NOT_ACTIONABLE_TYPED_STATE",
    "actionable_cohort",
    "build_reference_recovery_cohort",
    "reference_shortlist_node_ids",
]
