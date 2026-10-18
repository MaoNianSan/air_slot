"""PRE decision-environment contract (Phase 1).

PRE owns:

- the canonical decision-stage rule (which stage admits a local recovery
  decision, and which collapses to the baseline action);
- evidence / data support for a decision node, including the no-future-evidence
  rule that inference may only consume evidence available at or before the
  decision time.

PRE does **not** own comparison support. ``Omega^CS``, ``m^CS`` and the nominal
``m^CS >= 0.90`` requirement belong to the M2 consequence-comparison layer
(:mod:`model.M2.comparison_support`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Literal

from model.common.decision_contracts import (
    DecisionEvidence,
    EvidenceItem,
    SplitName,
    StaticReference,
)
from model.common.value_objects import FrozenModel
from pydantic import Field
from model.common.enums import (
    DecisionTimeRole,
    EvidenceClass,
    OperationalStage,
    SupportState,
    weaker_or_equal,
)
from model.common.errors import ContractError


__all__ = [
    "ACTIONABLE_STAGES",
    "NON_ACTIONABLE_STAGES",
    "STAGE_CLASS",
    "CanonicalNodeChoice",
    "action_stage_class",
    "assert_split_isolation",
    "build_decision_evidence",
    "choose_canonical_node",
    "evidence_support",
    "is_actionable",
    "validate_no_future_evidence",
]


# Stage-II is solved only for PRE and TURN nodes; after successor off-block is
# factual the local action set collapses to the baseline action.
ACTIONABLE_STAGES: tuple[OperationalStage, ...] = (
    OperationalStage.PRE_IB,
    OperationalStage.POST_IB_PRE_OB,
)
NON_ACTIONABLE_STAGES: tuple[OperationalStage, ...] = (
    OperationalStage.POST_OB_PRE_TO,
    OperationalStage.COMPLETED,
)

STAGE_CLASS: dict[OperationalStage, str] = {
    OperationalStage.PRE_IB: "PRE",
    OperationalStage.POST_IB_PRE_OB: "TURN",
    OperationalStage.POST_OB_PRE_TO: "TAXI",
    OperationalStage.COMPLETED: "COMP",
}


def is_actionable(stage: OperationalStage) -> bool:
    """Return whether a local off-block recovery decision exists at ``stage``."""

    return stage in ACTIONABLE_STAGES


def action_stage_class(stage: OperationalStage) -> Literal["PRE", "TURN", "TAXI", "COMP"]:
    """Canonical stage class used by Stage-I condition views."""

    try:
        return STAGE_CLASS[stage]  # type: ignore[return-value]
    except KeyError as error:  # pragma: no cover - enum is closed
        raise ContractError(f"PRE_UNKNOWN_OPERATIONAL_STAGE:{stage}") from error


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractError(f"PRE_NAIVE_TIMESTAMP:{field}")
    return value.astimezone(timezone.utc)


def validate_no_future_evidence(
    *,
    decision_time: datetime,
    items: Iterable[EvidenceItem],
    information_cutoff: datetime | None = None,
) -> None:
    """Enforce the PRE no-future-evidence rule.

    Raises :class:`ContractError` when an inference-evidence item becomes
    available after the decision time, or when it has no availability basis at
    all. Evaluation-only roles (``EVAL_OUTCOME``) are tolerated because they are
    never consumed as inference evidence, but they must still be well formed.
    """

    decision_time = _utc(decision_time, "decision_time")
    if information_cutoff is not None:
        cutoff = _utc(information_cutoff, "information_cutoff")
        if cutoff > decision_time:
            raise ContractError("PRE_INFORMATION_CUTOFF_AFTER_DECISION_TIME")
    for item in items:
        if item.availability_time is None:
            if item.decision_time_role == DecisionTimeRole.INFERENCE_EVIDENCE.value:
                raise ContractError(f"PRE_EVIDENCE_WITHOUT_AVAILABILITY:{item.record_id}")
            continue
        availability = _utc(item.availability_time, "availability_time")
        role = item.decision_time_role
        if role == DecisionTimeRole.INFERENCE_EVIDENCE.value and availability > decision_time:
            raise ContractError(f"PRE_FUTURE_EVIDENCE:{item.record_id}")
        if role == DecisionTimeRole.FACTUAL_REPLAY_EVIDENCE.value and availability > decision_time:
            raise ContractError(f"PRE_FUTURE_FACTUAL_EVIDENCE:{item.record_id}")


def evidence_support(items: Iterable[EvidenceItem]) -> SupportState:
    """Aggregate PRE evidence/data support from inference-evidence items only."""

    considered = [
        item
        for item in items
        if item.decision_time_role == DecisionTimeRole.INFERENCE_EVIDENCE.value
    ]
    if not considered:
        return SupportState.ABSTAIN
    if any(item.support is SupportState.ABSTAIN for item in considered):
        return SupportState.ABSTAIN
    if any(item.support is SupportState.DEGRADED for item in considered):
        return SupportState.DEGRADED
    return SupportState.SUPPORTED


class CanonicalNodeChoice(FrozenModel):
    """One candidate canonical node for a stage, before support is applied."""

    node_id: str = Field(min_length=1)
    stage: OperationalStage
    decision_time: datetime
    supported: bool
    reason_codes: tuple[str, ...] = ()


def choose_canonical_node(
    candidates: Iterable[CanonicalNodeChoice],
) -> CanonicalNodeChoice:
    """Choose the canonical node first, then evaluate support.

    The canonical node is the earliest node of the stage,
    ``t_i^g = min{t : G_{i,t} = g}``, ordered deterministically by
    ``(decision_time, node_id)``. An unsupported canonical node is returned as
    the canonical choice with ``supported=False``; it is never replaced by a
    later supported node.
    """

    ordered = []
    for candidate in candidates:
        _utc(candidate.decision_time, "decision_time")
        ordered.append(candidate)
    if not ordered:
        raise ContractError("PRE_NO_CANONICAL_NODE_FOR_STAGE")
    return min(ordered, key=lambda item: (item.decision_time, item.node_id))


def assert_split_isolation(
    *,
    split: SplitName,
    referenced_splits: Iterable[str],
    allow_references: Iterable[str] = ("train", "calibration"),
    ) -> None:
    """Reject evidence crossing the split boundary of ``split``.

    Train and calibration references stay admissible everywhere; Development
    may never read Test objects and Test may never read Development ones.
    """

    allowed = {split.value, *allow_references}
    foreign = sorted({str(item) for item in referenced_splits} - allowed)
    if foreign:
        raise ContractError("PRE_SPLIT_ISOLATION_VIOLATION:" + ",".join(foreign))


def build_decision_evidence(
    *,
    episode_id: str,
    chain_id: str,
    node_id: str,
    decision_time: datetime,
    information_cutoff: datetime,
    stage: OperationalStage,
    split: SplitName,
    dynamic_evidence: Iterable[EvidenceItem],
    scheduled_milestones: Iterable[str] = (),
    observed_milestones: Iterable[str] = (),
    static_references: Iterable[StaticReference] = (),
    support_ceiling: EvidenceClass = EvidenceClass.UNSUPPORTED,
) -> DecisionEvidence:
    """Build the PRE-owned evidence envelope for one decision node.

    The returned envelope carries evidence/data support only. Comparison
    support (``m^CS``) is M2's responsibility and never appears here.
    """

    items = tuple(dynamic_evidence)
    validate_no_future_evidence(
        decision_time=decision_time,
        items=items,
        information_cutoff=information_cutoff,
    )
    support = evidence_support(items)
    inference = [
        item
        for item in items
        if item.decision_time_role == DecisionTimeRole.INFERENCE_EVIDENCE.value
    ]
    if not items:
        availability = SupportState.ABSTAIN
    elif any(item.availability_time is None for item in items):
        availability = SupportState.DEGRADED
    else:
        availability = SupportState.SUPPORTED
    if availability is SupportState.ABSTAIN and support is not SupportState.ABSTAIN:
        support = SupportState.ABSTAIN
    reasons: list[str] = []
    if support is SupportState.ABSTAIN:
        reasons.append(
            "PRE_NO_SUPPORTED_INFERENCE_EVIDENCE"
            if not inference
            else "PRE_EVIDENCE_ABSTAIN"
        )
    for item in inference:
        if not weaker_or_equal(item.evidence_class, support_ceiling):
            reasons.append(f"PRE_EVIDENCE_CEILING_EXCEEDED:{item.record_id}")
    return DecisionEvidence(
        episode_id=episode_id,
        chain_id=chain_id,
        node_id=node_id,
        decision_time=_utc(decision_time, "decision_time"),
        information_cutoff=_utc(information_cutoff, "information_cutoff"),
        stage=stage,
        split=split,
        scheduled_milestones=tuple(scheduled_milestones),
        observed_milestones=tuple(observed_milestones),
        dynamic_evidence=items,
        static_references=tuple(static_references),
        availability=availability,
        support=support,
        evidence_class_ceiling=support_ceiling,
        inference_record_count=len(inference),
        evidence_record_count=len(items),
        reason_codes=tuple(sorted(set(reasons))),
    )
