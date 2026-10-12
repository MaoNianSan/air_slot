"""Stage-I consequence value of scarce-attention allocation."""

from __future__ import annotations

from collections.abc import Sequence

from model.M3.stage1 import select_paired_attention
from model.M4.evaluation import evaluate_attention_allocation
from model.common.decision_contracts import (
    AttentionDecision,
    PrioritySignal,
    SignalKind,
    TypedStatus,
)
from model.common.enums import SupportState
from model.common.identity import content_id
from model.PRE.decision_environment import action_stage_class

from .contracts import (
    STAGE1_ACTIONABLE_STAGES,
    AttentionCandidate,
    AttentionStageResult,
    RepresentationNode,
)


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


def _abstaining_signal(
    node: RepresentationNode,
    *,
    signal_type: SignalKind,
) -> PrioritySignal:
    """Carry an unsupported canonical node without changing its identity."""

    support = node.support("HISTORY_JOINT")
    return PrioritySignal(
        signal_type=signal_type,
        episode_id=node.episode_id,
        chain_id=node.chain_id,
        node_id=node.node_id,
        representation_id="HISTORY_H16:JOINT",
        score=None,
        support=SupportState.ABSTAIN,
        status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
        comparison_support_mass=float(support.supported_mass),
        comparison_support_threshold=float(support.threshold),
        reason_codes=("JATM_SECTION5_CANONICAL_NODE_UNSUPPORTED",),
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


def _eligible_hash(node_ids: Sequence[str]) -> str:
    return content_id({"eligible_candidate_node_ids": list(node_ids)})


def select_and_evaluate(
    candidates: Sequence[AttentionCandidate],
    *,
    q: float,
    cohort_id: str,
    canonical_nodes: Sequence[RepresentationNode] | None = None,
) -> AttentionStageResult | None:
    """Evaluate one stage-local queue.

    ``canonical_nodes`` is the fixed canonical population. Support is applied
    only after those identities are fixed, and unsupported canonical nodes are
    retained as typed abstentions. When it is omitted, ``candidates`` is treated
    as the already-supported canonical population for compatibility with the
    focused synthetic tests.
    """

    rows = tuple(candidates)
    canonical = None if canonical_nodes is None else tuple(canonical_nodes)
    if canonical is None:
        if not rows:
            return None
        stage = rows[0].stage
    else:
        if not canonical:
            return None
        stage = canonical[0].stage
    if stage not in STAGE1_ACTIONABLE_STAGES:
        raise RuntimeError("JATM_SECTION5_ATTENTION_NON_ACTIONABLE_STAGE")
    active_stage = stage
    if any(row.stage is not active_stage for row in rows):
        raise RuntimeError("JATM_SECTION5_ATTENTION_MIXED_STAGE")
    if canonical is not None and any(
        node.stage is not active_stage for node in canonical
    ):
        raise RuntimeError("JATM_SECTION5_ATTENTION_MIXED_STAGE")

    by_id = {row.node_id: row for row in rows}
    eligible: list[AttentionCandidate] = []
    abstaining_ids: list[str] = []
    delay_signals: list[PrioritySignal] = []
    consequence_signals: list[PrioritySignal] = []

    if canonical is None:
        eligible.extend(rows)
        delay_signals.extend(
            _signal(row, signal_type=SignalKind.DELAY, score=row.delay_score)
            for row in rows
        )
        consequence_signals.extend(
            _signal(
                row,
                signal_type=SignalKind.CONSEQUENCE,
                score=row.consequence_score,
            )
            for row in rows
        )
    else:
        if len({node.node_id for node in canonical}) != len(canonical):
            raise RuntimeError("JATM_SECTION5_ATTENTION_CANONICAL_NODE_DUPLICATE")
        for node in canonical:
            row = by_id.get(node.node_id)
            if row is None:
                abstaining_ids.append(node.node_id)
                delay_signals.append(
                    _abstaining_signal(node, signal_type=SignalKind.DELAY)
                )
                consequence_signals.append(
                    _abstaining_signal(
                        node, signal_type=SignalKind.CONSEQUENCE
                    )
                )
                continue
            eligible.append(row)
            delay_signals.append(
                _signal(row, signal_type=SignalKind.DELAY, score=row.delay_score)
            )
            consequence_signals.append(
                _signal(
                    row,
                    signal_type=SignalKind.CONSEQUENCE,
                    score=row.consequence_score,
                )
            )
        canonical_ids = tuple(node.node_id for node in canonical)
        if set(by_id) - set(canonical_ids):
            raise RuntimeError("JATM_SECTION5_ATTENTION_CANDIDATE_OUTSIDE_CANONICAL")

    if not delay_signals or len(delay_signals) != len(consequence_signals):
        raise RuntimeError("JATM_SECTION5_ATTENTION_CANDIDATE_QUEUE_MISMATCH")

    delay_decision, consequence_decision = select_paired_attention(
        delay_signals, consequence_signals, q=q
    )
    if (
        delay_decision.cohort_size != consequence_decision.cohort_size
        or delay_decision.k != consequence_decision.k
    ):
        raise RuntimeError("JATM_SECTION5_ATTENTION_SHARED_SELECTOR_VIOLATION")
    if delay_decision.cohort_size != len(eligible):
        raise RuntimeError("JATM_SECTION5_ATTENTION_ELIGIBLE_COUNT_MISMATCH")

    priorities = {row.node_id: row.p_c for row in eligible}
    domains = {row.node_id: row.domain_scores for row in eligible}
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
        stage=active_stage,
        q=float(q),
        candidates=tuple(eligible),
        reference_decision=consequence_decision,
        comparator_decision=delay_decision,
        evaluation=evaluation,
        canonical_node_ids=(
            tuple(row.node_id for row in rows)
            if canonical is None
            else tuple(node.node_id for node in canonical)
        ),
        eligible_candidate_ids=tuple(row.node_id for row in eligible),
        abstaining_node_ids=tuple(abstaining_ids),
    )


def _shortlist(decision: AttentionDecision) -> tuple[str, ...]:
    return tuple(item.node_id for item in decision.entries if item.selected)


def _domain_sums(
    candidates: Sequence[AttentionCandidate], shortlist: set[str]
) -> dict[str, float]:
    return {
        domain: sum(
            float(row.domain_scores[domain])
            for row in candidates
            if row.node_id in shortlist
        )
        for domain in ("F", "P", "R")
    }


def attention_row(result: AttentionStageResult, *, q: float) -> dict[str, object]:
    evaluation = result.evaluation
    diagnostics = dict(evaluation.diagnostics)
    reference_value = float(evaluation.reference_attention_value)
    comparator_value = float(evaluation.comparator_attention_value)
    value_retained = (
        comparator_value / reference_value if reference_value > 0.0 else None
    )
    reference_ids = set(evaluation.reference_shortlist)
    comparator_ids = set(evaluation.comparator_shortlist)
    reference_domains = _domain_sums(result.candidates, reference_ids)
    comparator_domains = _domain_sums(result.candidates, comparator_ids)
    eligible_ids = tuple(result.eligible_candidate_ids)
    return {
        "stage": action_stage_class(result.stage),
        "q": float(q),
        "N": int(len(result.candidates)),
        "K": int(result.reference_decision.k),
        "canonical_stage_node_ids": list(result.canonical_node_ids),
        "canonical_stage_node_count": len(result.canonical_node_ids),
        "eligible_candidate_node_ids": list(eligible_ids),
        "eligible_candidate_count": len(eligible_ids),
        "abstaining_node_ids": list(result.abstaining_node_ids),
        "abstaining_node_count": len(result.abstaining_node_ids),
        "eligible_candidate_ids_hash": _eligible_hash(eligible_ids),
        "cohort_size": int(result.reference_decision.cohort_size),
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
        "F_value_retained": (
            None
            if reference_domains["F"] <= 0.0
            else comparator_domains["F"] / reference_domains["F"]
        ),
        "P_value_retained": (
            None
            if reference_domains["P"] <= 0.0
            else comparator_domains["P"] / reference_domains["P"]
        ),
        "R_value_retained": (
            None
            if reference_domains["R"] <= 0.0
            else comparator_domains["R"] / reference_domains["R"]
        ),
    }


def overall_objective(
    results: Sequence[AttentionStageResult],
) -> dict[str, float | None]:
    active = tuple(result for result in results if result is not None)
    for result in active:
        if result.stage not in STAGE1_ACTIONABLE_STAGES:
            raise RuntimeError("JATM_SECTION5_OVERALL_NON_ACTIONABLE_STAGE")
    if not active:
        return {"A_C_overall": 0.0, "A_D_overall": 0.0, "L_att_overall": None}
    reference = sum(
        float(item.evaluation.reference_attention_value) for item in active
    )
    comparator = sum(
        float(item.evaluation.comparator_attention_value) for item in active
    )
    loss = None if reference <= 0.0 else (reference - comparator) / reference
    return {
        "A_C_overall": reference,
        "A_D_overall": comparator,
        "L_att_overall": loss,
    }


def attention_domain_rows(
    result: AttentionStageResult, *, q: float
) -> list[dict[str, object]]:
    if result.stage not in STAGE1_ACTIONABLE_STAGES:
        raise RuntimeError("JATM_SECTION5_DOMAIN_NON_ACTIONABLE_STAGE")
    reference_ids = set(result.evaluation.reference_shortlist)
    comparator_ids = set(result.evaluation.comparator_shortlist)
    rows = []
    for domain in ("F", "P", "R"):
        reference = sum(
            float(row.domain_scores[domain])
            for row in result.candidates
            if row.node_id in reference_ids
        )
        comparator = sum(
            float(row.domain_scores[domain])
            for row in result.candidates
            if row.node_id in comparator_ids
        )
        rows.append(
            {
                "stage": action_stage_class(result.stage),
                "q": float(q),
                "domain": domain,
                "A_reference": reference,
                "A_comparator": comparator,
                "value_retained": (
                    None if reference <= 0.0 else comparator / reference
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
