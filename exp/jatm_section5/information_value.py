"""Decision value of operational information under a fixed reference."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

import numpy as np

from model.M3.stage1 import select_attention
from model.M4.evaluation import evaluate_attention_allocation
from model.common.decision_contracts import PrioritySignal, SignalKind, TypedStatus
from model.common.enums import OperationalStage, SupportState

from .bootstrap import paired_information_increment_contrast, summarize_bootstrap
from .contracts import (
    STAGE1_ACTIONABLE_STAGES,
    ComparatorRecoveryResult,
    ReferenceRecoveryCohort,
    RepresentationComparisonCandidate,
    RepresentationNode,
)
from .recovery_value import comparator_recovery


COMPONENTS: dict[str, tuple[str, str]] = {
    "ROLLING_HISTORY": ("CURRENT_JOINT", "HISTORY_JOINT"),
    "DISTRIBUTIONAL_INFORMATION": ("HISTORY_POINT", "HISTORY_JOINT"),
    "CROSS_STATE_DEPENDENCE": ("HISTORY_MARGINAL", "HISTORY_JOINT"),
}


def _signal(
    candidate: RepresentationComparisonCandidate,
    *,
    comparator: bool,
    representation_id: str,
) -> PrioritySignal:
    score = candidate.comparator_score if comparator else candidate.reference_score
    return PrioritySignal(
        signal_type=SignalKind.CONSEQUENCE,
        episode_id=candidate.episode_id,
        chain_id=candidate.chain_id,
        node_id=candidate.node_id,
        representation_id=representation_id,
        score=float(score),
        support=SupportState.SUPPORTED,
        status=TypedStatus.SUPPORTED,
        comparison_support_mass=float(candidate.support_mass),
        comparison_support_threshold=float(candidate.support_threshold),
    )


def common_candidates(
    nodes: Sequence[RepresentationNode],
    *,
    comparator: str,
    require_complete: bool = True,
) -> tuple[RepresentationComparisonCandidate, ...]:
    """Bind one comparator to fixed canonical Stage-I node identities."""

    output: list[RepresentationComparisonCandidate] = []
    skipped = 0
    for node in nodes:
        if node.stage not in STAGE1_ACTIONABLE_STAGES:
            continue
        reference_score = node.consequence_scores["HISTORY_JOINT"]
        comparator_score = node.consequence_scores[comparator]
        domains = node.domain_scores["HISTORY_JOINT"]
        reference_support = node.support("HISTORY_JOINT")
        comparator_support = node.support(comparator)
        if (
            reference_score is None
            or comparator_score is None
            or domains is None
            or not reference_support.included
            or not comparator_support.included
        ):
            skipped += 1
            continue
        output.append(
            RepresentationComparisonCandidate(
                episode_id=node.episode_id,
                chain_id=node.chain_id,
                node_id=node.node_id,
                stage=node.stage,
                reference_score=float(reference_score),
                comparator_score=float(comparator_score),
                reference_domain_scores={
                    key: float(value) for key, value in domains.items()
                },
                support_mass=float(reference_support.supported_mass),
                support_threshold=float(reference_support.threshold),
            )
        )
    if require_complete and skipped:
        raise RuntimeError(
            "JATM_SECTION5_INFORMATION_CANONICAL_IDENTITY_MISSING:"
            f"{comparator}:{skipped}"
        )
    return tuple(output)


def evaluate_component_attention(
    candidates: Sequence[RepresentationComparisonCandidate],
    *,
    q: float,
    component: str,
) -> object | None:
    rows = tuple(candidates)
    if not rows:
        return None
    stage = rows[0].stage
    if any(row.stage is not stage for row in rows):
        raise RuntimeError("JATM_SECTION5_INFORMATION_MIXED_STAGE")
    if stage not in STAGE1_ACTIONABLE_STAGES:
        raise RuntimeError("JATM_SECTION5_INFORMATION_NON_ACTIONABLE_STAGE")
    comparator, reference = COMPONENTS[component]
    reference_signals = tuple(
        _signal(row, comparator=False, representation_id=reference) for row in rows
    )
    comparator_signals = tuple(
        _signal(row, comparator=True, representation_id=comparator) for row in rows
    )
    reference_decision = select_attention(reference_signals, q=q)
    comparator_decision = select_attention(comparator_signals, q=q)
    return evaluate_attention_allocation(
        cohort_id=f"INFO_{component}_{stage.value}",
        reference_id=reference,
        comparator_id=comparator,
        reference_decision=reference_decision,
        comparator_decision=comparator_decision,
        reference_priority={row.node_id: row.reference_score for row in rows},
        reference_domain_scores={
            row.node_id: row.reference_domain_scores for row in rows
        },
    )


def _component_estimates(
    candidates_by_stage: Mapping[
        OperationalStage, tuple[RepresentationComparisonCandidate, ...]
    ],
    *,
    q: float,
    component: str,
) -> tuple[list[object], float | None, int, int]:
    evaluations: list[object] = []
    for stage in STAGE1_ACTIONABLE_STAGES:
        rows = candidates_by_stage.get(stage)
        if not rows:
            continue
        evaluation = evaluate_component_attention(rows, q=q, component=component)
        if evaluation is not None:
            evaluations.append(evaluation)
    if not evaluations:
        return evaluations, None, 0, 0
    reference = sum(float(item.reference_attention_value) for item in evaluations)
    comparator = sum(float(item.comparator_attention_value) for item in evaluations)
    loss = None if reference <= 0.0 else (reference - comparator) / reference
    reassigned = sum(len(item.displaced) for item in evaluations)
    shortlist = sum(len(item.reference_shortlist) for item in evaluations)
    return evaluations, loss, reassigned, shortlist


def _clone_candidate(
    row: RepresentationComparisonCandidate,
    *,
    instance: int,
    replicate: int,
) -> RepresentationComparisonCandidate:
    suffix = f"::BOOT{int(instance)}:{int(replicate)}"
    return RepresentationComparisonCandidate(
        episode_id=row.episode_id + suffix,
        chain_id=row.chain_id + suffix,
        node_id=row.node_id + suffix,
        stage=row.stage,
        reference_score=row.reference_score,
        comparator_score=row.comparator_score,
        reference_domain_scores=dict(row.reference_domain_scores),
        support_mass=row.support_mass,
        support_threshold=row.support_threshold,
    )


def _component_bootstrap(
    stage_tables: Mapping[
        str, Mapping[OperationalStage, tuple[RepresentationComparisonCandidate, ...]]
    ],
    *,
    episodes: Sequence[str],
    q: float,
    seed: int,
    replicates: int,
) -> dict[str, np.ndarray]:
    episode_ids = tuple(str(value) for value in episodes)
    values = {
        component: np.full(int(replicates), np.nan, dtype=float)
        for component in stage_tables
    }
    if not episode_ids:
        return values
    by_stage: dict[
        str, dict[OperationalStage, dict[str, RepresentationComparisonCandidate]]
    ] = {
        component: {
            stage: {row.episode_id: row for row in rows}
            for stage, rows in table.items()
        }
        for component, table in stage_tables.items()
    }
    rng = np.random.default_rng(int(seed))
    for replicate in range(int(replicates)):
        draw = rng.integers(0, len(episode_ids), size=len(episode_ids))
        for component, stage_sources in by_stage.items():
            stage_groups: dict[
                OperationalStage, list[RepresentationComparisonCandidate]
            ] = defaultdict(list)
            for stage, source in stage_sources.items():
                for instance, index in enumerate(draw):
                    row = source.get(episode_ids[int(index)])
                    if row is not None:
                        stage_groups[stage].append(
                            _clone_candidate(
                                row, instance=instance, replicate=replicate
                            )
                        )
            _, loss, _, _ = _component_estimates(
                {stage: tuple(rows) for stage, rows in stage_groups.items()},
                q=q,
                component=component,
            )
            if loss is not None and np.isfinite(loss):
                values[component][replicate] = float(loss)
    return values


def _recovery_bootstrap(
    cohort: ReferenceRecoveryCohort,
    recovery_results: Mapping[str, ComparatorRecoveryResult],
    *,
    seed: int,
    replicates: int,
) -> dict[str, np.ndarray]:
    episodes = sorted({item.node.episode_id for item in cohort.nodes})
    values = {
        component: np.full(int(replicates), np.nan, dtype=float)
        for component in COMPONENTS
    }
    if not cohort.nodes or not episodes:
        return values
    by_episode = {
        episode: [
            index
            for index, item in enumerate(cohort.nodes)
            if item.node.episode_id == episode
        ]
        for episode in episodes
    }
    rng = np.random.default_rng(int(seed))
    for replicate in range(int(replicates)):
        draw = rng.integers(0, len(episodes), size=len(episodes))
        instances: list[int] = []
        for index in draw:
            instances.extend(by_episode[episodes[int(index)]])
        reference_total = sum(
            float(cohort.nodes[index].reference_recoverable_value)
            for index in instances
        )
        if reference_total <= 0.0:
            continue
        for component, result in recovery_results.items():
            evaluation = result.evaluation
            delta_total = sum(
                float(evaluation.delta_objectives[cohort.nodes[index].node.node_id])
                for index in instances
            )
            values[component][replicate] = delta_total / reference_total
    return values


def _finite_values(values: np.ndarray) -> np.ndarray:
    return np.asarray(
        [float(value) for value in values if np.isfinite(value)], dtype=float
    )


def information_value_main(
    nodes: Sequence[RepresentationNode],
    *,
    q: float,
    reference_cohort: ReferenceRecoveryCohort,
    service,
    headroom,
    seed: int,
    replicates: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    bootstrap_rows: list[dict[str, object]] = []
    stage_tables: dict[
        str, dict[OperationalStage, tuple[RepresentationComparisonCandidate, ...]]
    ] = {}
    recovery_results: dict[str, ComparatorRecoveryResult] = {}
    component_losses: dict[str, float | None] = {}
    component_reassign: dict[str, tuple[int, int]] = {}
    fixed_node_ids: tuple[str, ...] | None = None
    for component, (comparator, _reference) in COMPONENTS.items():
        candidates = common_candidates(nodes, comparator=comparator)
        candidate_ids = tuple(sorted(row.node_id for row in candidates))
        if fixed_node_ids is None:
            fixed_node_ids = candidate_ids
        elif candidate_ids != fixed_node_ids:
            raise RuntimeError(
                "JATM_SECTION5_INFORMATION_CANONICAL_IDS_DIFFER_BY_COMPARATOR"
            )
        grouped: dict[
            OperationalStage, list[RepresentationComparisonCandidate]
        ] = defaultdict(list)
        for row in candidates:
            grouped[row.stage].append(row)
        table = {stage: tuple(rows) for stage, rows in grouped.items()}
        stage_tables[component] = table
        _evaluations, loss, reassigned, shortlist = _component_estimates(
            table, q=q, component=component
        )
        component_losses[component] = loss
        component_reassign[component] = (reassigned, shortlist)
        recovery = comparator_recovery(
            reference_cohort,
            representation=comparator,
            service=service,
            headroom=headroom,
        )
        recovery_results[component] = recovery

    episodes = sorted({node.episode_id for node in nodes})
    attention_replicates = _component_bootstrap(
        stage_tables,
        episodes=episodes,
        q=q,
        seed=seed,
        replicates=replicates,
    )
    recovery_replicates = _recovery_bootstrap(
        reference_cohort,
        recovery_results,
        seed=seed,
        replicates=replicates,
    )

    for component, (comparator, _reference) in COMPONENTS.items():
        recovery = recovery_results[component]
        evaluation = recovery.evaluation
        attention_summary = summarize_bootstrap(
            _finite_values(attention_replicates[component]),
            estimate=component_losses[component],
        )
        recovery_summary = summarize_bootstrap(
            _finite_values(recovery_replicates[component]),
            estimate=evaluation.L_rec,
        )
        reassigned, shortlist = component_reassign[component]
        rows.append(
            {
                "information_component": component,
                "comparator": comparator,
                "L_att": component_losses[component],
                "L_att_ci_low": attention_summary["ci_low"],
                "L_att_ci_high": attention_summary["ci_high"],
                "delta_J": evaluation.delta_recovery_objective,
                "reference_V": evaluation.reference_recoverable_value,
                "L_rec": evaluation.L_rec,
                "L_rec_ci_low": recovery_summary["ci_low"],
                "L_rec_ci_high": recovery_summary["ci_high"],
                "stage1_reassigned_share": (
                    None if shortlist == 0 else reassigned / shortlist
                ),
                "A0": evaluation.A0,
                "A5": evaluation.A5,
                "missed_activation": evaluation.activation_events.get(
                    "MISSED_ACTIVATION", 0
                ),
                "false_activation": evaluation.activation_events.get(
                    "FALSE_ACTIVATION", 0
                ),
                "under_recovery": evaluation.activation_events.get(
                    "UNDER_RECOVERY", 0
                ),
                "over_recovery": evaluation.activation_events.get(
                    "OVER_RECOVERY", 0
                ),
            }
        )
        diagnostics.append(
            {
                "information_component": component,
                "comparator": comparator,
                "exact_action_agreement": evaluation.A0,
                "within_5min_agreement": evaluation.A5,
                "missed_activation": evaluation.activation_events.get(
                    "MISSED_ACTIVATION", 0
                ),
                "false_activation": evaluation.activation_events.get(
                    "FALSE_ACTIVATION", 0
                ),
                "under_recovery": evaluation.activation_events.get(
                    "UNDER_RECOVERY", 0
                ),
                "over_recovery": evaluation.activation_events.get(
                    "OVER_RECOVERY", 0
                ),
                "mean_absolute_action_difference": evaluation.diagnostics.get(
                    "mean_absolute_intensity_error"
                ),
                "median_absolute_action_difference": None,
                "typed_fallback_count": len(recovery.typed_fallbacks),
            }
        )
        for metric, summary in (
            ("L_att", attention_summary),
            ("L_rec", recovery_summary),
        ):
            bootstrap_rows.append(
                {"information_component": component, "metric": metric, **summary}
            )

    point_attention = attention_replicates["DISTRIBUTIONAL_INFORMATION"]
    marginal_attention = attention_replicates["CROSS_STATE_DEPENDENCE"]
    point_recovery = recovery_replicates["DISTRIBUTIONAL_INFORMATION"]
    marginal_recovery = recovery_replicates["CROSS_STATE_DEPENDENCE"]
    attention_increment = paired_information_increment_contrast(
        point_attention, marginal_attention, seed=seed, replicates=replicates
    )
    recovery_increment = paired_information_increment_contrast(
        point_recovery, marginal_recovery, seed=seed, replicates=replicates
    )
    point_delta = recovery_results[
        "DISTRIBUTIONAL_INFORMATION"
    ].evaluation.delta_recovery_objective
    marginal_delta = recovery_results[
        "CROSS_STATE_DEPENDENCE"
    ].evaluation.delta_recovery_objective
    delta_increment = (
        None
        if point_delta is None or marginal_delta is None
        else float(point_delta) - float(marginal_delta)
    )
    rows.append(
        {
            "information_component": "MARGINAL_UNCERTAINTY",
            "comparator": "POINT_MINUS_MARGINAL",
            "L_att": attention_increment["estimate"],
            "L_att_ci_low": attention_increment["ci_low"],
            "L_att_ci_high": attention_increment["ci_high"],
            "delta_J": delta_increment,
            "reference_V": None,
            "L_rec": recovery_increment["estimate"],
            "L_rec_ci_low": recovery_increment["ci_low"],
            "L_rec_ci_high": recovery_increment["ci_high"],
            "stage1_reassigned_share": None,
            "A0": None,
            "A5": None,
            "missed_activation": None,
            "false_activation": None,
            "under_recovery": None,
            "over_recovery": None,
        }
    )
    bootstrap_rows.extend(
        [
            {
                "information_component": "MARGINAL_UNCERTAINTY",
                "metric": "L_att_POINT_MINUS_MARGINAL",
                **attention_increment,
            },
            {
                "information_component": "MARGINAL_UNCERTAINTY",
                "metric": "L_rec_POINT_MINUS_MARGINAL",
                **recovery_increment,
            },
        ]
    )
    return rows, diagnostics, bootstrap_rows


__all__ = [
    "COMPONENTS",
    "common_candidates",
    "evaluate_component_attention",
    "information_value_main",
]
