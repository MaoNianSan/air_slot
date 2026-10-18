"""``REFERENCE_RECOVERY_COHORT``: stage-local ``R_g*`` and their union.

The frozen authority defines the consequence Stage-I shortlist independently
inside PRE and TURN. Each stage-local shortlist is then support-qualified
against the reference state set. The formal Stage-II cohort is the deterministic
union, ordered PRE then TURN. TAXI and COMP never enter this cohort.
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
FLATTENED_UNION_SEMANTICS = (
    "COMPATIBILITY_FLATTENED_UNION_NOT_A_POOLED_STAGE1_DECISION"
)


def reference_shortlist_node_ids(
    attention_decisions: Mapping[str, Any],
    *,
    variant: str = S.REFERENCE_VARIANT,
    stage: str,
    q: float = C.NOMINAL_Q,
) -> tuple[str, ...]:
    """``H_g^{C,*}`` for one Stage-I actionable stage."""

    _require(
        stage in S.ACTIONABLE_STAGE_I_STAGES,
        "PHASE7_REFERENCE_NON_ACTIONABLE_STAGE",
        stage,
    )
    decision = attention_decision(
        attention_decisions, variant, stage, q, "CONSEQUENCE"
    )
    return tuple(entry.node_id for entry in decision.entries if entry.selected)


def build_reference_recovery_cohort(
    nodes_payload: Mapping[str, Any],
    state_variants: Mapping[str, Any],
    attention_decisions: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish stage-local shortlists and the deterministic support-qualified union."""

    nodes = nodes_by_id(nodes_payload)
    shortlist_by_stage: dict[str, tuple[str, ...]] = {}
    for stage in S.ACTIONABLE_STAGE_I_STAGES:
        if not any(node.stage == stage for node in nodes.values()):
            shortlist_by_stage[str(stage)] = ()
            continue
        try:
            shortlist_by_stage[str(stage)] = reference_shortlist_node_ids(
                attention_decisions, stage=stage
            )
        except KeyError as error:
            raise TypedBlocker(
                "PHASE7_REFERENCE_ATTENTION_ROW_MISSING", stage
            ) from error
    _require(
        any(shortlist_by_stage[stage] for stage in S.ACTIONABLE_STAGE_I_STAGES),
        "PHASE7_REFERENCE_SHORTLIST_EMPTY",
    )

    reference_state_sets = state_sets_by_node(
        state_variants, S.REFERENCE_VARIANT
    )
    included_by_stage: dict[str, list[str]] = {
        str(stage): [] for stage in S.ACTIONABLE_STAGE_I_STAGES
    }
    excluded: list[dict[str, Any]] = []
    for stage in S.ACTIONABLE_STAGE_I_STAGES:
        for node_id in shortlist_by_stage[str(stage)]:
            node = nodes.get(node_id)
            if node is None:
                raise TypedBlocker(
                    "PHASE7_REFERENCE_SHORTLIST_NODE_NOT_MATERIALIZED", node_id
                )
            operational_stage = OperationalStage(node.stage)
            if (
                operational_stage.value != str(stage)
                or operational_stage not in {
                    OperationalStage(value) for value in S.ACTIONABLE_STAGE_I_STAGES
                }
            ):
                excluded.append(
                    _exclusion(
                        node,
                        typed_state=NOT_ACTIONABLE_TYPED_STATE,
                        reason_codes=(
                            "PHASE7_STAGE2_STAGE_SCOPE_VIOLATION",
                        ),
                    )
                )
                continue
            if not is_actionable(operational_stage):
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
                raise TypedBlocker("PHASE7_REFERENCE_STATE_SET_MISSING", node_id)
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
                        "abstaining_scenario_ids": [
                            int(value) for value in abstaining
                        ],
                    }
                )
                continue
            included_by_stage[str(stage)].append(node_id)

    flattened_shortlist = tuple(
        node_id
        for stage in S.ACTIONABLE_STAGE_I_STAGES
        for node_id in shortlist_by_stage[str(stage)]
    )
    flattened = tuple(
        node_id
        for stage in S.ACTIONABLE_STAGE_I_STAGES
        for node_id in included_by_stage[str(stage)]
    )
    if len(set(flattened)) != len(flattened):
        raise TypedBlocker("PHASE7_REFERENCE_COHORT_NOT_UNIQUE", flattened)
    if any(node_id not in nodes for node_id in flattened):
        raise TypedBlocker("PHASE7_REFERENCE_COHORT_NODE_NOT_MATERIALIZED", flattened)

    return {
        "reference_variant": S.REFERENCE_VARIANT,
        "reference_authority": C.REFERENCE_AUTHORITY,
        "reference_representation_id": C.REFERENCE_REPRESENTATION_ID,
        "nominal_q": float(C.NOMINAL_Q),
        "cohort_id": C.STAGE2_INFORMATION_COHORT,
        "stage1_actionable_stages": list(S.ACTIONABLE_STAGE_I_STAGES),
        "shortlist_rule": "STAGE_LOCAL_CONSEQUENCE_TOP_K_SHARED_SELECTOR",
        "shortlist_authority": "P^C = Phi_C(C^CU)",
        "shortlist_node_ids_by_stage": {
            stage: list(shortlist_by_stage[str(stage)])
            for stage in S.ACTIONABLE_STAGE_I_STAGES
        },
        "shortlist_node_ids": list(flattened_shortlist),
        "shortlist_size": len(flattened_shortlist),
        "shortlist_stage_counts": {
            stage: len(shortlist_by_stage[str(stage)])
            for stage in S.ACTIONABLE_STAGE_I_STAGES
        },
        "flattened_union_semantics": FLATTENED_UNION_SEMANTICS,
        "stage2_support_rule": (
            "ACTIONABLE_STAGE_AND_REFERENCE_STATE_FULLY_SUPPORTED"
        ),
        "stage2_actionable_node_ids_by_stage": {
            stage: list(included_by_stage[str(stage)])
            for stage in S.ACTIONABLE_STAGE_I_STAGES
        },
        "stage2_actionable_node_ids_flattened": list(flattened),
        "stage2_actionable_node_ids": list(flattened),
        "stage2_cohort_size": len(flattened),
        "stage2_excluded": excluded,
        "stage2_excluded_count": len(excluded),
        "alternative_representations_use_fixed_r_star": True,
        "no_pooled_stage1_decision": True,
        "typed_states": sorted({entry["typed_state"] for entry in excluded}),
    }


def actionable_cohort(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Decode the deterministic ``R*`` union from the published cohort."""

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


__all__ = [
    "ABSTAIN_TYPED_STATE",
    "FLATTENED_UNION_SEMANTICS",
    "NOT_ACTIONABLE_TYPED_STATE",
    "actionable_cohort",
    "build_reference_recovery_cohort",
    "reference_shortlist_node_ids",
]
