"""Stage-II recoverable-value cohort and summaries."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from statistics import median

import numpy as np

from model.M2.comparison_support import PRIMARY_AGGREGATION_VIEW
from model.M3.stage2 import (
    LAMBDA_NOMINAL,
    RecoveryPolicy,
    expected_objective,
    action_grid,
    solve_recovery,
)
from model.M3.transition import TransitionContext
from model.common.decision_contracts import HeadroomSummary, RecoveryDecision, TypedStatus
from model.common.enums import OperationalStage, SupportState
from model.common.errors import ContractError
from model.PRE.decision_environment import action_stage_class, is_actionable

from .contracts import (
    FLATTENED_UNION_SEMANTICS,
    STAGE1_ACTIONABLE_STAGES,
    ComparatorRecoveryResult,
    ReferenceRecoveryCohort,
    ReferenceRecoveryNode,
    RepresentationNode,
)


NUMERICAL_TOLERANCE = 1e-9


def transition_context(node: RepresentationNode, headroom: HeadroomSummary) -> TransitionContext:
    """Use the node-specific schedule-relative SOBT coordinate."""

    return TransitionContext(
        sobt_minutes=float(node.sobt_minutes),
        turnaround_lower_bound_minutes=float(headroom.turnaround_lower_bound_q),
    )


def _state_supported(node: RepresentationNode, representation: str) -> bool:
    return all(
        scenario.support is not SupportState.ABSTAIN
        for scenario in node.state(representation).scenarios
    )


def _stage_values(
    source_shortlists: Mapping[object, Sequence[str]],
    stage: OperationalStage,
) -> tuple[str, ...]:
    values = source_shortlists.get(stage)
    if values is None:
        values = source_shortlists.get(stage.value, ())
    return tuple(str(value) for value in values)


def reference_recovery_cohort(
    nodes: Sequence[RepresentationNode],
    *,
    source_shortlists: Mapping[object, Sequence[str]],
) -> tuple[RepresentationNode, ...]:
    selected = {
        node_id
        for stage in STAGE1_ACTIONABLE_STAGES
        for node_id in _stage_values(source_shortlists, stage)
    }
    output = []
    for node in nodes:
        if not is_actionable(node.stage):
            continue
        if node.node_id not in selected:
            continue
        if not node.support_full.get("HISTORY_JOINT", False):
            continue
        output.append(node)
    output.sort(
        key=lambda node: (
            action_stage_class(node.stage),
            node.episode_id,
            node.node_id,
        )
    )
    return tuple(output)


def prepare_reference_recovery(
    nodes: Sequence[RepresentationNode],
    *,
    source_shortlists: Mapping[object, Sequence[str]],
    service,
    headroom: HeadroomSummary,
) -> ReferenceRecoveryCohort:
    selected = reference_recovery_cohort(nodes, source_shortlists=source_shortlists)
    output: list[ReferenceRecoveryNode] = []
    for node in selected:
        context = transition_context(node, headroom)
        decision = solve_recovery(
            node.state("HISTORY_JOINT"),
            context=context,
            service=service,
            headroom_summary=headroom,
        )
        if decision.u_star not in decision.action_grid:
            raise RuntimeError(f"JATM_SECTION5_U_STAR_NOT_IN_GRID:{node.node_id}")
        if decision.recoverable_value is None or decision.recoverable_value < -NUMERICAL_TOLERANCE:
            raise RuntimeError(f"JATM_SECTION5_NEGATIVE_RECOVERABLE_VALUE:{node.node_id}")
        objectives = {
            (node.node_id, float(u)): expected_objective(
                node.state("HISTORY_JOINT"),
                context=context,
                service=service,
                u=float(u),
                u_max=float(headroom.u_max),
                lambda_policy=LAMBDA_NOMINAL,
                view=PRIMARY_AGGREGATION_VIEW,
            )
            for u in decision.action_grid
        }
        output.append(
            ReferenceRecoveryNode(
                node=node,
                reference_decision=decision,
                reference_objectives=objectives,
                reference_recoverable_value=max(0.0, float(decision.recoverable_value)),
                action_grid=tuple(float(u) for u in decision.action_grid),
            )
        )

    shortlist_by_stage = {
        action_stage_class(stage): _stage_values(source_shortlists, stage)
        for stage in STAGE1_ACTIONABLE_STAGES
    }
    actionable_by_stage = {
        action_stage_class(stage): tuple(
            item.node.node_id for item in output if item.node.stage is stage
        )
        for stage in STAGE1_ACTIONABLE_STAGES
    }
    flattened = tuple(
        node_id
        for stage in STAGE1_ACTIONABLE_STAGES
        for node_id in actionable_by_stage[action_stage_class(stage)]
    )
    if set(flattened) != {item.node.node_id for item in output}:
        raise RuntimeError("JATM_SECTION5_RSTAR_FLATTENED_UNION_MISMATCH")
    if any(node.stage not in STAGE1_ACTIONABLE_STAGES for node in selected):
        raise RuntimeError("JATM_SECTION5_RSTAR_NON_ACTIONABLE_STAGE")
    return ReferenceRecoveryCohort(
        nodes=tuple(output),
        source_shortlists=dict(source_shortlists),
        shortlist_node_ids_by_stage=shortlist_by_stage,
        stage2_actionable_node_ids_by_stage=actionable_by_stage,
        stage2_actionable_node_ids_flattened=flattened,
        flattened_union_semantics=FLATTENED_UNION_SEMANTICS,
    )


def comparator_recovery(
    cohort: ReferenceRecoveryCohort,
    *,
    representation: str,
    service,
    headroom: HeadroomSummary,
) -> ComparatorRecoveryResult:
    actions: dict[str, float] = {}
    decisions: dict[str, RecoveryDecision] = {}
    fallbacks: dict[str, str] = {}
    for item in cohort.nodes:
        node_id = item.node.node_id
        node = item.node
        if not _state_supported(node, representation):
            actions[node_id] = 0.0
            fallbacks[node_id] = "TYPED_ZERO_ACTION_UNSUPPORTED_REPRESENTATION"
            continue
        try:
            decision = solve_recovery(
                node.state(representation),
                context=transition_context(node, headroom),
                service=service,
                headroom_summary=headroom,
            )
        except ContractError as error:
            actions[node_id] = 0.0
            fallbacks[node_id] = f"TYPED_ZERO_ACTION:{error}"
            continue
        if decision.actionable_status is TypedStatus.NOT_ACTIONABLE:
            actions[node_id] = 0.0
            fallbacks[node_id] = "TYPED_ZERO_ACTION_NOT_ACTIONABLE"
        else:
            actions[node_id] = float(decision.u_star)
            decisions[node_id] = decision
    from model.M4.evaluation import evaluate_recovery_loss

    evaluation = evaluate_recovery_loss(
        cohort_id=f"RSTAR_{representation}",
        reference_id="HISTORY_JOINT",
        comparator_id=representation,
        fixed_cohort=tuple(item.node.node_id for item in cohort.nodes),
        reference_actions={
            item.node.node_id: float(item.reference_decision.u_star or 0.0)
            for item in cohort.nodes
        },
        comparator_actions=actions,
        reference_objectives={
            key: value
            for item in cohort.nodes
            for key, value in item.reference_objectives.items()
        },
        reference_recoverable_values={
            item.node.node_id: item.reference_recoverable_value
            for item in cohort.nodes
        },
    )
    return ComparatorRecoveryResult(
        representation=representation,
        actions=actions,
        decisions=decisions,
        typed_fallbacks=fallbacks,
        evaluation=evaluation,
    )


def _iqr(values: Sequence[float]) -> float | None:
    array = np.asarray(list(values), dtype=float)
    if array.size == 0:
        return None
    return float(np.quantile(array, 0.75) - np.quantile(array, 0.25))


def stage_recovery_summary(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["stage"])].append(row)
    output = []
    for stage in sorted(grouped):
        group = grouped[stage]
        v = [float(row["V"]) for row in group]
        j0 = [float(row["J_zero"]) for row in group]
        jstar = [float(row["J_star"]) for row in group]
        u_positive = [float(row["u_star"]) for row in group if float(row["u_star"]) > 0.0]
        positive = sum(value > 0.0 for value in v)
        output.append(
            {
                "stage": stage,
                "N_actionable": len(group),
                "median_J_zero": float(np.median(j0)) if j0 else None,
                "IQR_J_zero": _iqr(j0),
                "median_J_star": float(np.median(jstar)) if jstar else None,
                "IQR_J_star": _iqr(jstar),
                "median_V": float(np.median(v)) if v else None,
                "IQR_V": _iqr(v),
                "P90_V": float(np.quantile(v, 0.90)) if v else None,
                "positive_V_count": positive,
                "positive_V_share": positive / len(group) if group else None,
                "activation_count": len(u_positive),
                "activation_share": len(u_positive) / len(group) if group else None,
                "median_positive_u": float(np.median(u_positive)) if u_positive else None,
                "IQR_positive_u": _iqr(u_positive),
                "P90_positive_u": float(np.quantile(u_positive, 0.90)) if u_positive else None,
            }
        )
    return output


def recovery_atomic_rows(cohort: ReferenceRecoveryCohort) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in cohort.nodes:
        decision = item.reference_decision
        rows.append(
            {
                "node_id": item.node.node_id,
                "episode_id": item.node.episode_id,
                "stage": action_stage_class(item.node.stage),
                "P_C": item.node.consequence_scores["HISTORY_JOINT"],
                "J_zero": decision.j_zero,
                "J_star": decision.j_star,
                "V": decision.recoverable_value,
                "u_star": decision.u_star,
                "u_max": decision.u_max,
                "actionable": decision.actionable_status.value,
                "solver_status": decision.solver_status.value,
                "sobt_minutes": item.node.sobt_minutes,
            }
        )
    return rows


def severity_recoverability_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "node_id": row["node_id"],
            "episode_id": row["episode_id"],
            "stage": row["stage"],
            "P_C": row["P_C"],
            "V": row["V"],
            "u_star": row["u_star"],
            "J_zero": row["J_zero"],
            "J_star": row["J_star"],
        }
        for row in rows
    ]


def severity_summary(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    from scipy import stats

    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["stage"])].append(row)
    output = []
    for stage in sorted(grouped):
        group = grouped[stage]
        p = np.asarray([float(row["P_C"]) for row in group], dtype=float)
        v = np.asarray([float(row["V"]) for row in group], dtype=float)
        spearman = stats.spearmanr(p, v).statistic if len(group) >= 2 and np.ptp(p) > 0 and np.ptp(v) > 0 else None
        kendall = stats.kendalltau(p, v).statistic if len(group) >= 2 and np.ptp(p) > 0 and np.ptp(v) > 0 else None
        order = np.argsort(p)
        quantiles = np.array_split(order, min(4, len(group))) if len(group) else []
        for index, selected_index in enumerate(quantiles, start=1):
            vals = v[selected_index]
            output.append(
                {
                    "stage": stage,
                    "N": len(group),
                    "spearman_P_V": None if spearman is None else float(spearman),
                    "kendall_P_V": None if kendall is None else float(kendall),
                    "priority_quantile": f"Q{index}" if len(quantiles) > 1 else "Q1",
                    "quantile_N": len(vals),
                    "median_V": float(np.median(vals)) if len(vals) else None,
                    "IQR_V": _iqr(vals),
                    "positive_V_share": float(np.mean(vals > 0.0)) if len(vals) else None,
                }
            )
    return output


__all__ = [
    "comparator_recovery",
    "prepare_reference_recovery",
    "recovery_atomic_rows",
    "reference_recovery_cohort",
    "severity_recoverability_rows",
    "severity_summary",
    "stage_recovery_summary",
    "transition_context",
]
