"""Stage-I consequence value of scarce-attention allocation."""

from __future__ import annotations

from collections.abc import Sequence

from model.M3.stage1 import select_paired_attention
from model.M4.evaluation import evaluate_attention_allocation
from model.common.decision_contracts import AttentionDecision, PrioritySignal, SignalKind, TypedStatus
from model.common.identity import content_id
from model.common.enums import SupportState

from .contracts import AttentionCandidate, AttentionStageResult, RepresentationNode


def _signal(
    candidate: AttentionCandidate,
    *,
    signal_type: SignalKind,
    score: float,
) -> PrioritySignal:
    return PrioritySignal(
        signal_type=signal_type,
        episode_id=candidate.episode_id,
        chain_id=candidate.chain_id,
        node_id=candidate.node_id,
        representation_id="HISTORY_H16:JOINT",
        score=float(score),
        support=SupportState.SUPPORTED,
        status=TypedStatus.SUPPORTED,
        comparison_support_mass=float(candidate.support_mass),
        comparison_support_threshold=float(candidate.support_threshold),
    )


def candidate(
    node: RepresentationNode,
    *,
    representation: str = "HISTORY_JOINT",
) -> AttentionCandidate | None:
    delay = node.delay_scores[representation]
    consequence = node.consequence_scores[representation]
    domains = node.domain_scores[representation]
    if delay is None or consequence is None or domains is None:
        return None
    support = node.support(representation)
    return AttentionCandidate(
        episode_id=node.episode_id,
        chain_id=node.chain_id,
        node_id=node.node_id,
        stage=node.stage,
        delay_score=float(delay),
        consequence_score=float(consequence),
        p_c=float(consequence),
        domain_scores={key: float(value) for key, value in domains.items()},
        support_mass=float(support.supported_mass),
        support_threshold=float(support.threshold),
    )


def select_and_evaluate(
    candidates: Sequence[AttentionCandidate],
    *,
    q: float,
    cohort_id: str,
) -> AttentionStageResult | None:
    rows = tuple(candidates)
    if not rows:
        return None
    stage = rows[0].stage
    if any(row.stage is not stage for row in rows):
        raise RuntimeError("JATM_SECTION5_ATTENTION_MIXED_STAGE")
    delay_signals = tuple(
        _signal(row, signal_type=SignalKind.DELAY, score=row.delay_score)
        for row in rows
    )
    consequence_signals = tuple(
        _signal(
            row,
            signal_type=SignalKind.CONSEQUENCE,
            score=row.consequence_score,
        )
        for row in rows
    )
    delay_decision, consequence_decision = select_paired_attention(
        delay_signals, consequence_signals, q=q
    )
    priorities = {row.node_id: row.p_c for row in rows}
    domains = {row.node_id: row.domain_scores for row in rows}
    evaluation = evaluate_attention_allocation(
        cohort_id=cohort_id,
        reference_id="HISTORY_JOINT_CONSEQUENCE",
        comparator_id="HISTORY_JOINT_DELAY",
        reference_decision=consequence_decision,
        comparator_decision=delay_decision,
        reference_priority=priorities,
        reference_domain_scores=domains,
    )
    return AttentionStageResult(
        stage=stage,
        q=float(q),
        candidates=rows,
        reference_decision=consequence_decision,
        comparator_decision=delay_decision,
        evaluation=evaluation,
    )


def _shortlist(decision: AttentionDecision) -> tuple[str, ...]:
    return tuple(item.node_id for item in decision.entries if item.selected)


def attention_row(result: AttentionStageResult, *, q: float) -> dict[str, object]:
    evaluation = result.evaluation
    diagnostics = dict(evaluation.diagnostics)
    reference_value = float(evaluation.reference_attention_value)
    comparator_value = float(evaluation.comparator_attention_value)
    value_retained = (
        comparator_value / reference_value if reference_value > 0.0 else None
    )
    return {
        "stage": result.stage.value,
        "q": float(q),
        "N": int(len(result.candidates)),
        "K": int(result.reference_decision.k),
        "A_C": reference_value,
        "A_D": comparator_value,
        "value_retained": value_retained,
        "L_att": evaluation.L_att,
        "overlap_count": int(evaluation.overlap_count),
        "entered_count": int(diagnostics.get("entered_count", 0.0)),
        "displaced_count": int(diagnostics.get("displaced_count", 0.0)),
        "reassigned_count": int(len(evaluation.displaced)),
        "reassigned_share": (
            len(evaluation.displaced) / len(_shortlist(result.reference_decision))
            if _shortlist(result.reference_decision)
            else None
        ),
        "kendall_tau": evaluation.kendall_tau,
        "spearman_rho": evaluation.spearman_rho,
        "mean_rank_displacement": evaluation.mean_rank_displacement,
        "F_value_retained": diagnostics.get("coverage_F_comparator"),
        "P_value_retained": diagnostics.get("coverage_P_comparator"),
        "R_value_retained": diagnostics.get("coverage_R_comparator"),
    }


def overall_objective(results: Sequence[AttentionStageResult]) -> dict[str, float | None]:
    active = tuple(result for result in results if result is not None)
    if not active:
        return {"A_C_overall": 0.0, "A_D_overall": 0.0, "L_att_overall": None}
    reference = sum(float(item.evaluation.reference_attention_value) for item in active)
    comparator = sum(float(item.evaluation.comparator_attention_value) for item in active)
    loss = None if reference <= 0.0 else (reference - comparator) / reference
    return {
        "A_C_overall": reference,
        "A_D_overall": comparator,
        "L_att_overall": loss,
    }


def attention_domain_rows(result: AttentionStageResult, *, q: float) -> list[dict[str, object]]:
    diagnostics = dict(result.evaluation.diagnostics)
    rows = []
    for domain in ("F", "P", "R"):
        reference = diagnostics.get(f"coverage_{domain}_reference")
        comparator = diagnostics.get(f"coverage_{domain}_comparator")
        rows.append(
            {
                "stage": result.stage.value,
                "q": float(q),
                "domain": domain,
                "A_reference": reference,
                "A_comparator": comparator,
                "value_retained": (
                    None
                    if reference in (None, 0.0) or comparator is None
                    else float(comparator) / float(reference)
                ),
            }
        )
    return rows


__all__ = [
    "attention_domain_rows",
    "attention_row",
    "candidate",
    "overall_objective",
    "select_and_evaluate",
]
