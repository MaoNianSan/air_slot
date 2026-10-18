 """Decision value of operational information under a fixed reference."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

import numpy as np

from model.M3.stage1 import select_attention
from model.M4.evaluation import evaluate_attention_allocation, evaluate_recovery_loss
from model.common.decision_contracts import PrioritySignal, SignalKind, TypedStatus
from model.common.enums import OperationalStage, SupportState

from .attention_value import overall_objective
from .bootstrap import bootstrap_estimates, paired_information_increment_contrast, summarize_bootstrap
from .contracts import (
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


def _signal(candidate: RepresentationComparisonCandidate, *, comparator: bool) -> PrioritySignal:
    score = candidate.comparator_score if comparator else candidate.reference_score
    return PrioritySignal(
        signal_type=SignalKind.CONSEQUENCE,
        episode_id=candidate.episode_id,
        chain_id=candidate.chain_id,
        node_id=candidate.node_id,
        representation_id="SECTION5_COMPARATOR" if comparator else "HISTORY_JOINT",
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
) -> tuple[RepresentationComparisonCandidate, ...]:
    output = []
    for node in nodes:
        ref_score = node.consequence_scores["HISTORY_JOINT"]
        cmp_score = node.consequence_scores[comparator]
        domains = node.domain_scores["HISTORY_JOINT"]
        if ref_score is None or cmp_score is None or domains is None:
            continue
        support = node.support("HISTORY_JOINT")
        output.append(
            RepresentationComparisonCandidate(
                episode_id=node.episode_id,
                chain_id=node.chain_id,
                node_id=node.node_id,
                stage=node.stage,
                reference_score=float(ref_score),
                comparator_score=float(cmp_score),
                reference_domain_scores={key: float(value) for key, value in domains.items()},
                support_mass=float(support.supported_mass),
                support_threshold=float(support.threshold),
            )
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
    ref_signals = tuple(_signal(row, comparator=False) for row in rows)
    cmp_signals = tuple(_signal(row, comparator=True) for row in rows)
    ref_decision = select_attention(ref_signals, q=q)
    cmp_decision = select_attention(cmp_signals, q=q)
    return evaluate_attention_allocation(
        cohort_id=f"INFO_{component}",
        reference_id="HISTORY_JOINT",
        comparator_id=COMPONENTS[component][0],
        reference_decision=ref_decision,
        comparator_decision=cmp_decision,
        reference_priority={row.node_id: row.reference_score for row in rows},
        reference_domain_scores={row.node_id: row.reference_domain_scores for row in rows},
    )


def _information_stage_replicates(
    candidates_by_stage: Mapping[OperationalStage, tuple[RepresentationComparisonCandidate, ...]],
    *,
    episode_ids: Sequence[str],
    q: float,
    seed: int,
    replicates: int,
    component: str,
) -> np.ndarray:
    by_stage = {stage: {row.episode_id: row for row in rows} for stage, rows in candidates_by_stage.items()}
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for replicate_index in range(int(replicates)):
        draw = rng.integers(0, len(episode_ids), size=len(episode_ids))
        stage_results = []
        for stage, lookup in by_stage.items():
            synthetic: list[RepresentationComparisonCandidate] = []
            for instance, episode_index in enumerate(draw):
                original = lookup.get(str(episode_ids[int(episode_index)]))
                if original is None:
                    continue
                suffix = f"::BOOT{instance}:{replicate_index}"
                synthetic.append(
                    RepresentationComparisonCandidate(
                        episode_id=original.episode_id + suffix,
                        chain_id=original.chain_id + suffix,
                        node_id=original.node_id + suffix,
                        stage=original.stage,
                        reference_score=original.reference_score,
                        comparator_score=original.comparator_score,
                        reference_domain_scores=original.reference_domain_scores,
                        support_mass=original.support_mass,
                        support_threshold=original.support_threshold,
                    )
                )
            evaluation = evaluate_component_attention(tuple(synthetic), q=q, component=component)
            if evaluation is not None:
                stage_results.append(evaluation)
        if stage_results:
            total_ref = sum(float(item.reference_attention_value) for item in stage_results)
            total_cmp = sum(float(item.comparator_attention_value) for item in stage_results)
            values.append((total_ref - total_cmp) / total_ref if total_ref > 0.0 else float("nan"))
    return np.asarray([value for value in values if np.isfinite(value)], dtype=float)


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
    evaluations: dict[str, object] = {}
    recovery_results: dict[str, ComparatorRecoveryResult] = {}
    candidate_tables: dict[str, dict[OperationalStage, tuple[RepresentationComparisonCandidate, ...]]] = {}
    for component, (comparator, _reference) in COMPONENTS.items():
        candidates = common_candidates(nodes, comparator=comparator)
        by_stage: dict[OperationalStage, list[RepresentationComparisonCandidate]] = defaultdict(list)
        for row in candidates:
            by_stage[row.stage].append(row)
        stage_tables = {stage: tuple(rows) for stage, rows in by_stage.items()}
        candidate_tables[component] = stage_tables
        stage_evals = []
        for stage, stage_rows in sorted(stage_tables.items(), key=lambda item: item[0].value):
            evaluation = evaluate_component_attention(stage_rows, q=q, component=component)
            if evaluation is not None:
                stage_evals.append(evaluation)
        if stage_evals:
            total_ref = sum(float(item.reference_attention_value) for item in stage_evals)
            total_cmp = sum(float(item.comparator_attention_value) for item in stage_evals)
            L_att = None if total_ref <= 0.0 else (total_ref - total_cmp) / total_ref
        else:
            L_att = None
        recovery = comparator_recovery(
            reference_cohort,
            representation=comparator,
            service=service,
            headroom=headroom,
        )
        recovery_results[component] = recovery
        evaluations[component] = (stage_evals, L_att)
        evaluation = recovery.evaluation
        rows.append(
            {
                "information_component": component,
                "L_att": L_att,
                "delta_J": evaluation.delta_recovery_objective,
                "reference_V": evaluation.reference_recoverable_value,
                "L_rec": evaluation.L_rec,
                "stage1_reassigned_share": None,
                "A0": evaluation.A0,
                "A5": evaluation.A5,
                "missed_activation": evaluation.activation_events.get("MISSED_ACTIVATION", 0),
                "false_activation": evaluation.activation_events.get("FALSE_ACTIVATION", 0),
                "under_recovery": evaluation.activation_events.get("UNDER_RECOVERY", 0),
                "over_recovery": evaluation.activation_events.get("OVER_RECOVERY", 0),
                "information_component_removed": component,
                "comparator": comparator,
            }
        )
        diagnostics.append(
            {
                "information_component": component,
                "comparator": comparator,
                "exact_action_agreement": evaluation.A0,
                "within_5min_agreement": evaluation.A5,
                "missed_activation": evaluation.activation_events.get("MISSED_ACTIVATION", 0),
                "false_activation": evaluation.activation_events.get("FALSE_ACTIVATION", 0),
                "under_recovery": evaluation.activation_events.get("UNDER_RECOVERY", 0),
                "over_recovery": evaluation.activation_events.get("OVER_RECOVERY", 0),
                "mean_absolute_action_difference": evaluation.diagnostics.get("mean_absolute_intensity_error"),
                "median_absolute_action_difference": None,
                "typed_fallback_count": len(recovery.typed_fallbacks),
            }
        )
    episode_ids = sorted({node.episode_id for node in nodes})
    bootstrap_values: dict[tuple[str, str], np.ndarray] = {}
    for component, (comparator, _reference) in COMPONENTS.items():
        stage_tables = candidate_tables[component]
        stage_values = _information_stage_replicates(
            stage_tables,
            episode_ids=episode_ids,
            q=q,
            seed=seed,
            replicates=replicates,
            component=component,
        )
        bootstrap_values[(component, "L_att")] = stage_values
        point = evaluations[component][1]
        summary = summarize_bootstrap(stage_values, estimate=point)
        bootstrap_rows.append(
            {
                "information_component": component,
                "metric": "L_att",
                **summary,
            }
        )
        recovery = recovery_results[component]
        recovery_values = np.asarray(
            [
                (sum(
                    float(recovery.evaluation.delta_objectives.get(row.node.node_id, 0.0))
                    for row in reference_cohort.nodes
                )
                / sum(
                    float(row.reference_recoverable_value)
                    for row in reference_cohort.nodes
                ))
                if sum(float(row.reference_recoverable_value) for row in reference_cohort.nodes) > 0.0
                else np.nan
            ],
            dtype=float,
        )
        bootstrap_rows.append(
            {
                "information_component": component,
                "metric": "L_rec",
                **summarize_bootstrap(recovery_values, estimate=recovery.evaluation.L_rec),
            }
        )
    point_component = "DISTRIBUTIONAL_INFORMATION"
    marginal_component = "CROSS_STATE_DEPENDENCE"
    point_loss = evaluations[point_component][1]
    marginal_loss = evaluations[marginal_component][1]
    if point_loss is not None and marginal_loss is not None:
        point_reps = bootstrap_values[(point_component, "L_att")]
        marginal_reps = bootstrap_values[(marginal_component, "L_att")]
        length = min(len(point_reps), len(marginal_reps))
        paired = paired_information_increment_contrast(
            point_reps[:length] if length else np.asarray([float(point_loss)]),
            marginal_reps[:length] if length else np.asarray([float(marginal_loss)]),
            seed=seed,
            replicates=replicates,
        )
        rows.append(
            {
                "information_component": "MARGINAL_UNCERTAINTY",
                "L_att": point_loss - marginal_loss,
                **{f"L_att_{key}": value for key, value in paired.items() if key != "estimate"},
                "delta_J": None,
                "reference_V": None,
                "L_rec": None,
                "information_component_added": "MARGINAL_UNCERTAINTY",
                "paired_estimate": paired["estimate"],
            }
        )
        bootstrap_rows.append(
            {
                "information_component": "MARGINAL_UNCERTAINTY",
                "metric": "L_att_POINT_MINUS_MARGINAL",
                **paired,
            }
        )
    else:
        rows.append(
            {
                "information_component": "MARGINAL_UNCERTAINTY",
                "L_att": None,
                "delta_J": None,
                "reference_V": None,
                "L_rec": None,
                "information_component_added": "MARGINAL_UNCERTAINTY",
            }
        )
    return rows, diagnostics, bootstrap_rows


__all__ = [
    "COMPONENTS",
    "common_candidates",
    "evaluate_component_attention",
    "information_value_main",
]
