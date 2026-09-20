"""Shared typed records for the JATM Section 5 experiment layer.

These records carry experiment identities and pointers to model-owned objects.
They do not redefine any M1/M2/M3/M4 estimand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping

from model.common.decision_contracts import (
    AttentionDecision,
    ComparisonSupport,
    ConsequenceScenarioSet,
    RecoveryDecision,
    StateScenarioSet,
)
from model.common.enums import OperationalStage, SupportState

STAGE1_ACTIONABLE_STAGES: tuple[OperationalStage, ...] = (
    OperationalStage.PRE_IB,
    OperationalStage.POST_IB_PRE_OB,
)

STAGE1_ACTIONABLE_STAGE_CLASSES: tuple[str, ...] = ("PRE", "TURN")

FLATTENED_UNION_SEMANTICS = (
    "COMPATIBILITY_FLATTENED_UNION_NOT_A_POOLED_STAGE1_DECISION"
)


REPRESENTATIONS: tuple[str, ...] = (
    "HISTORY_JOINT",
    "CURRENT_JOINT",
    "HISTORY_POINT",
    "HISTORY_MARGINAL",
)


@dataclass(frozen=True)
class RepresentationNode:
    """One fixed empirical decision node for all Section 5 representations."""

    episode_id: str
    chain_id: str
    node_id: str
    stage: OperationalStage
    decision_time: datetime
    sobt_minutes: float
    state_sets: Mapping[str, StateScenarioSet]
    consequence_sets: Mapping[str, ConsequenceScenarioSet]
    supports: Mapping[str, ComparisonSupport]
    support_full: Mapping[str, bool]
    delay_scores: Mapping[str, float | None]
    consequence_scores: Mapping[str, float | None]
    domain_scores: Mapping[str, Mapping[str, float] | None]
    component_scores: Mapping[str, Mapping[str, float] | None] = field(
        default_factory=dict
    )

    def state(self, representation: str) -> StateScenarioSet:
        return self.state_sets[representation]

    def consequences(self, representation: str) -> ConsequenceScenarioSet:
        return self.consequence_sets[representation]

    def support(self, representation: str) -> ComparisonSupport:
        return self.supports[representation]


@dataclass(frozen=True)
class CanonicalStageRow:
    node: RepresentationNode
    eligible: bool
    eligibility_reason: str


@dataclass(frozen=True)
class AttentionCandidate:
    episode_id: str
    chain_id: str
    node_id: str
    stage: OperationalStage
    delay_score: float
    consequence_score: float
    p_c: float
    domain_scores: Mapping[str, float]
    support_mass: float
    support_threshold: float


@dataclass(frozen=True)
class AttentionStageResult:
    stage: OperationalStage
    q: float
    candidates: tuple[AttentionCandidate, ...]
    reference_decision: AttentionDecision
    comparator_decision: AttentionDecision
    evaluation: object
    canonical_node_ids: tuple[str, ...] = ()
    eligible_candidate_ids: tuple[str, ...] = ()
    abstaining_node_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepresentationComparisonCandidate:
    """One fixed canonical node with scores from two representations."""

    episode_id: str
    chain_id: str
    node_id: str
    stage: OperationalStage
    reference_score: float
    comparator_score: float
    reference_domain_scores: Mapping[str, float]
    support_mass: float
    support_threshold: float


@dataclass(frozen=True)
class ReferenceRecoveryNode:
    node: RepresentationNode
    reference_decision: RecoveryDecision
    reference_objectives: Mapping[tuple[str, float], float]
    reference_recoverable_value: float
    action_grid: tuple[float, ...]


@dataclass(frozen=True)
class ReferenceRecoveryCohort:
    nodes: tuple[ReferenceRecoveryNode, ...]
    source_shortlists: Mapping[str, tuple[str, ...]]
    shortlist_node_ids_by_stage: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    stage2_actionable_node_ids_by_stage: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    stage2_actionable_node_ids_flattened: tuple[str, ...] = ()
    flattened_union_semantics: str = FLATTENED_UNION_SEMANTICS


@dataclass(frozen=True)
class ComparatorRecoveryResult:
    representation: str
    actions: Mapping[str, float]
    decisions: Mapping[str, RecoveryDecision]
    typed_fallbacks: Mapping[str, str]
    evaluation: object


__all__ = [
    "FLATTENED_UNION_SEMANTICS",
    "STAGE1_ACTIONABLE_STAGE_CLASSES",
    "STAGE1_ACTIONABLE_STAGES",
    "REPRESENTATIONS",
    "AttentionCandidate",
    "AttentionStageResult",
    "CanonicalStageRow",
    "ComparatorRecoveryResult",
    "ReferenceRecoveryCohort",
    "ReferenceRecoveryNode",
    "RepresentationComparisonCandidate",
    "RepresentationNode",
]
