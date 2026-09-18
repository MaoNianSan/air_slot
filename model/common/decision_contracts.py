"""V2 decision-chain contracts (Phase 1).

Ownership boundaries (instruction rev2, sections 5-12):

- ``common``      : transport contracts only; no scientific decision.
- ``PRE``         : decision environment + evidence/data support. Never
                    comparison support (``m^CS`` belongs to M2).
- ``M1``          : state representations (Current/History, Point/Marginal/Joint)
                    under one shared :class:`StateRepresentationSpec`.
- ``M2``          : native consequences, CU mapping, comparison support
                    (``Omega^CS``, ``m^CS``) and the unique consequence-based
                    priority authority ``P^C = Phi_C(C^CU)``.
- ``M3``          : sole decision authority. Stage I selects on a
                    :class:`PrioritySignal` (delay comparator ``P^D`` and
                    consequence priority ``P^C`` share one selector); Stage II
                    owns the state transition, action grid, objective and
                    recoverable value ``V``.
- ``M4``          : common-basis evaluation only. It never selects a shortlist,
                    never optimises recovery and never emits an action.

Dependency direction: ``common -> PRE -> M1 -> M2 -> M3 -> M4``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from .enums import (
    DecisionTimeRole,
    EvidenceClass,
    OperationalStage,
    SupportState,
)
from .value_objects import FrozenModel


__all__ = [
    "ATTENTION_ACTIVATION_EVENTS",
    "NOMINAL_COMMON_SUPPORT_MASS",
    "PREDEFINED_COMMON_SUPPORT_SENSITIVITY",
    "WEIGHT_TOLERANCE",
    "AttentionDecision",
    "AttentionEntry",
    "ComparisonSupport",
    "ConsequenceComponentProfile",
    "ConsequenceProfile",
    "ConsequenceScenario",
    "ConsequenceScenarioSet",
    "DecisionEvaluation",
    "DecisionEvidence",
    "EvaluationFamily",
    "EvidenceItem",
    "HeadroomSummary",
    "HistoryScope",
    "PrioritySignal",
    "RecoveryDecision",
    "SignalKind",
    "SolverStatus",
    "SplitName",
    "StateRepresentationSpec",
    "StateScenario",
    "StateScenarioSet",
    "StaticReference",
    "TemporalKind",
    "TypedStatus",
    "UncertaintyKind",
]


WEIGHT_TOLERANCE = 1e-6

#: Nominal common-support requirement. It belongs to M2/comparison-support.
NOMINAL_COMMON_SUPPORT_MASS = 0.90

#: The current manuscript body predefines no ``m^CS`` sensitivity values.
#: The appendix-only grid is not authoritative, so V2 keeps the nominal value
#: only and records the gap as an open manuscript item.
PREDEFINED_COMMON_SUPPORT_SENSITIVITY: tuple[float, ...] = ()

#: Stage-II activation diagnostics required by instruction section 12.
ATTENTION_ACTIVATION_EVENTS = (
    "MISSED_ACTIVATION",
    "FALSE_ACTIVATION",
    "UNDER_RECOVERY",
    "OVER_RECOVERY",
)


class TypedStatus(str, Enum):
    """Typed outcome statuses; never silently coerced to zero or success."""

    SUPPORTED = "SUPPORTED"
    DEGRADED = "DEGRADED"
    NOT_ACTIONABLE = "NOT_ACTIONABLE"
    ABSTAIN_NO_COMMON_SUPPORT = "ABSTAIN_NO_COMMON_SUPPORT"
    ABSTAIN_NO_EVIDENCE = "ABSTAIN_NO_EVIDENCE"
    UNDEFINED_ZERO_RECOVERABLE_VALUE = "UNDEFINED_ZERO_RECOVERABLE_VALUE"
    MISSING = "MISSING"
    N_A_NOT_DEFINED = "N/A_NOT_DEFINED"
    UNSUPPORTED = "UNSUPPORTED"


class SignalKind(str, Enum):
    """Stage-I priority signal identity."""

    DELAY = "DELAY"
    CONSEQUENCE = "CONSEQUENCE"


class TemporalKind(str, Enum):
    """M1 temporal dimension. Delay is not a temporal kind."""

    CURRENT = "CURRENT"
    HISTORY = "HISTORY"


class UncertaintyKind(str, Enum):
    """M1 uncertainty dimension."""

    POINT = "POINT"
    MARGINAL = "MARGINAL"
    JOINT = "JOINT"


class HistoryScope(str, Enum):
    FULL_PREFIX = "FULL_PREFIX"
    FIXED_WINDOW = "FIXED_WINDOW"


class SplitName(str, Enum):
    """Data lifecycle split; every scientific object carries one explicitly."""

    TRAIN = "train"
    CALIBRATION = "calibration"
    DEVELOPMENT = "development"
    TEST = "test"


class SolverStatus(str, Enum):
    """Stage-II solution provenance.

    The formal path is exact enumeration over the finite action grid; the HiGHS
    backend exists only for development-time parity checks.
    """

    EXACT_ENUMERATION = "EXACT_ENUMERATION"
    HIGHS_PARITY = "HIGHS_PARITY"
    NOT_RUN = "NOT_RUN"


class EvaluationFamily(str, Enum):
    """M4 evaluation family; attention and recovery losses stay separate."""

    ATTENTION = "ATTENTION"
    RECOVERY = "RECOVERY"


class EvidenceItem(FrozenModel):
    """One piece of decision-time evidence as seen by PRE.

    ``availability_time`` is the moment the evidence becomes usable. Evidence
    whose availability is after the decision time may not enter inference.
    """

    record_id: str = Field(min_length=1)
    chain_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    scientific_object: str = Field(min_length=1)
    availability_time: datetime | None = None
    decision_time_role: DecisionTimeRole = DecisionTimeRole.INFERENCE_EVIDENCE
    evidence_class: EvidenceClass = EvidenceClass.DIRECT
    support: SupportState = SupportState.ABSTAIN


class StaticReference(FrozenModel):
    """Frozen reference (schedule, registry, historical aggregate) usable at ``t``."""

    reference_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    reference_version: str = Field(min_length=1)
    artifact_hash: str | None = None


class DecisionEvidence(FrozenModel):
    """PRE-owned evidence envelope for one decision node.

    PRE carries evidence/data support only. It never carries comparison support;
    ``m^CS`` and ``Omega^CS`` live in M2 (:mod:`model.M2.comparison_support`).
    """

    episode_id: str = Field(min_length=1)
    chain_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    decision_time: datetime
    information_cutoff: datetime
    stage: OperationalStage
    split: SplitName
    scheduled_milestones: tuple[str, ...] = ()
    observed_milestones: tuple[str, ...] = ()
    dynamic_evidence: tuple[EvidenceItem, ...] = ()
    static_references: tuple[StaticReference, ...] = ()
    availability: SupportState
    support: SupportState
    evidence_class_ceiling: EvidenceClass = EvidenceClass.UNSUPPORTED
    inference_record_count: int = Field(ge=0)
    evidence_record_count: int = Field(ge=0)
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _support_never_exceeds_availability(self):
        if (
            self.availability is SupportState.ABSTAIN
            and self.support is not SupportState.ABSTAIN
        ):
            raise ValueError("DECISION_EVIDENCE_SUPPORT_EXCEEDS_AVAILABILITY")
        scheduled = set(self.scheduled_milestones)
        if scheduled and not set(self.observed_milestones) <= scheduled:
            raise ValueError("DECISION_EVIDENCE_UNSCHEDULED_OBSERVED_MILESTONE")
        for item in self.dynamic_evidence:
            if item.chain_id != self.chain_id or item.node_id != self.node_id:
                raise ValueError("DECISION_EVIDENCE_ITEM_IDENTITY_MISMATCH")
        return self

    @property
    def evidence_support(self) -> SupportState:
        """Alias making the PRE boundary explicit at call sites."""

        return self.support

    @property
    def missing_milestones(self) -> tuple[str, ...]:
        observed = set(self.observed_milestones)
        return tuple(
            name for name in self.scheduled_milestones if name not in observed
        )


class StateRepresentationSpec(FrozenModel):
    """M1-owned identity of one state representation.

    ``HISTORY_H16_PRIMARY`` is the primary History representation and
    ``HISTORY_H8`` the lower-capacity sensitivity comparator. H32 is legacy
    provenance only and is therefore not constructible here.
    """

    temporal: TemporalKind
    uncertainty: UncertaintyKind
    history_capacity: Literal[8, 16] | None = None
    history_scope: HistoryScope | None = None

    @model_validator(mode="after")
    def _history_dimension_consistency(self):
        if self.temporal is TemporalKind.CURRENT:
            if self.history_capacity is not None or self.history_scope is not None:
                raise ValueError("STATE_SPEC_CURRENT_CARRIES_HISTORY")
            return self
        if self.history_capacity is None:
            raise ValueError("STATE_SPEC_HISTORY_WITHOUT_CAPACITY")
        if self.history_scope is None:
            raise ValueError("STATE_SPEC_HISTORY_WITHOUT_SCOPE")
        return self

    @property
    def representation_id(self) -> str:
        if self.temporal is TemporalKind.CURRENT:
            return f"CURRENT:{self.uncertainty.value}"
        return f"HISTORY_H{self.history_capacity}:{self.uncertainty.value}"


class StateScenario(FrozenModel):
    """One aligned M1 state scenario.

    ``d_to_minutes`` is derived as ``d_ob_minutes + d_tx_minutes`` and may
    never be carried as an independent coordinate.
    """

    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0.0)
    stage: OperationalStage
    t_ib_minutes: float | None = None
    d_ob_minutes: float | None = None
    d_tx_minutes: float | None = None
    d_to_minutes: float | None = None
    tx_reference_minutes: float | None = None
    support: SupportState = SupportState.SUPPORTED
    ib_observed: bool = False
    ob_observed: bool = False
    tx_observed: bool = False

    @model_validator(mode="after")
    def _derived_d_to(self):
        if self.d_to_minutes is None:
            return self
        if self.d_ob_minutes is None or self.d_tx_minutes is None:
            raise ValueError("STATE_SCENARIO_ORPHAN_D_TO")
        expected = self.d_ob_minutes + self.d_tx_minutes
        if abs(expected - self.d_to_minutes) > WEIGHT_TOLERANCE:
            raise ValueError("STATE_SCENARIO_D_TO_IDENTITY_VIOLATION")
        return self

    @property
    def is_realized(self) -> bool:
        return self.ib_observed and self.ob_observed and self.tx_observed

    @property
    def T_IB(self) -> float | None:  # noqa: N802 - scientific name
        return self.t_ib_minutes

    @property
    def D_OB(self) -> float | None:  # noqa: N802 - scientific name
        return self.d_ob_minutes

    @property
    def D_TX(self) -> float | None:  # noqa: N802 - scientific name
        return self.d_tx_minutes

    @property
    def D_TO(self) -> float | None:  # noqa: N802 - scientific name
        return self.d_to_minutes


class StateScenarioSet(FrozenModel):
    """M1-owned scenario set for one decision node.

    Realized milestones replace uncertainty: a scenario whose milestones are
    already observed must be carried with weight 1.0 as the single scenario,
    or not carried at all.
    """

    episode_id: str = Field(min_length=1)
    chain_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    stage: OperationalStage
    representation: StateRepresentationSpec
    scenarios: tuple[StateScenario, ...] = ()

    @model_validator(mode="after")
    def _weight_and_identity(self):
        if not self.scenarios:
            raise ValueError("STATE_SCENARIO_SET_EMPTY")
        ids = [item.scenario_id for item in self.scenarios]
        if len(set(ids)) != len(ids):
            raise ValueError("STATE_SCENARIO_ID_NOT_UNIQUE")
        total = sum(item.scenario_weight for item in self.scenarios)
        if abs(total - 1.0) > WEIGHT_TOLERANCE:
            raise ValueError("STATE_SCENARIO_WEIGHT_SUM_VIOLATION")
        if any(item.scenario_weight <= WEIGHT_TOLERANCE for item in self.scenarios):
            raise ValueError("STATE_SCENARIO_ZERO_WEIGHT")
        realized = [item for item in self.scenarios if item.is_realized]
        if realized:
            if len(self.scenarios) != 1:
                raise ValueError("STATE_SCENARIO_REALIZED_NOT_COLLAPSED")
            if self.representation.uncertainty is not UncertaintyKind.POINT:
                raise ValueError("STATE_SCENARIO_REALIZED_REQUIRES_POINT")
            if abs(realized[0].scenario_weight - 1.0) > WEIGHT_TOLERANCE:
                raise ValueError("STATE_SCENARIO_REALIZED_WEIGHT_NOT_ONE")
        for item in self.scenarios:
            if item.stage is not self.stage:
                raise ValueError("STATE_SCENARIO_STAGE_MISMATCH")
        return self


class ComparisonSupport(FrozenModel):
    """M2-owned comparison support (``Omega^CS`` / ``m^CS``).

    The nominal requirement is ``m^CS >= 0.90``. Nodes below the requirement are
    excluded with a typed status and are never zero-filled.
    """

    episode_id: str = Field(min_length=1)
    chain_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    estimand: str = Field(min_length=1)
    supported_mass: float = Field(ge=0.0, le=1.0)
    supported_scenario_ids: tuple[int, ...] = ()
    scenario_count_total: int = Field(ge=0)
    threshold: float = Field(gt=0.0, le=1.0)
    included: bool
    status: TypedStatus
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _status_matches_inclusion(self):
        if self.included and self.status not in {TypedStatus.SUPPORTED, TypedStatus.DEGRADED}:
            raise ValueError("COMPARISON_SUPPORT_INCLUDED_STATUS_INVALID")
        if not self.included and self.status is not TypedStatus.ABSTAIN_NO_COMMON_SUPPORT:
            raise ValueError("COMPARISON_SUPPORT_EXCLUDED_STATUS_INVALID")
        if self.supported_mass + WEIGHT_TOLERANCE < self.threshold and self.included:
            raise ValueError("COMPARISON_SUPPORT_THRESHOLD_VIOLATION")
        if len(set(self.supported_scenario_ids)) != len(self.supported_scenario_ids):
            raise ValueError("COMPARISON_SUPPORT_SCENARIO_ID_NOT_UNIQUE")
        if len(self.supported_scenario_ids) > self.scenario_count_total:
            raise ValueError("COMPARISON_SUPPORT_SCENARIO_COUNT_EXCEEDED")
        return self


class ConsequenceComponentProfile(FrozenModel):
    """One M2 consequence component on the CU scale."""

    component_id: str = Field(min_length=1)
    native_quantity: float | None = None
    cu_quantity: float | None = None
    support: SupportState
    cu_status: str = Field(min_length=1)
    scale: float | None = Field(default=None, gt=0.0)
    scale_source: str = Field(min_length=1)
    reference_source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _cu_requires_scale(self):
        if self.cu_quantity is not None and self.scale is None:
            raise ValueError("CONSEQUENCE_CU_WITHOUT_SCALE")
        if self.native_quantity is not None and self.cu_quantity is not None:
            expected = self.native_quantity / self.scale
            if abs(expected - self.cu_quantity) > WEIGHT_TOLERANCE * max(1.0, abs(expected)):
                raise ValueError("CONSEQUENCE_CU_SCALE_VIOLATION")
        if self.support is SupportState.ABSTAIN and self.cu_quantity is not None:
            raise ValueError("CONSEQUENCE_CU_FOR_ABSTAINING_COMPONENT")
        if self.support is SupportState.SUPPORTED and (
            self.native_quantity is None or self.cu_quantity is None
        ):
            raise ValueError("CONSEQUENCE_SUPPORTED_COMPONENT_WITHOUT_VALUE")
        return self


class ConsequenceProfile(FrozenModel):
    """M2-owned consequence vector for one decision node."""

    episode_id: str = Field(min_length=1)
    chain_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    stage: OperationalStage
    representation_id: str = Field(min_length=1)
    registry_id: str = Field(min_length=1)
    registry_hash: str = Field(min_length=1)
    components: tuple[ConsequenceComponentProfile, ...] = ()
    support: SupportState = SupportState.SUPPORTED

    def component(self, component_id: str) -> ConsequenceComponentProfile:
        for item in self.components:
            if item.component_id == component_id:
                return item
        raise KeyError(component_id)


class ConsequenceScenario(FrozenModel):
    """One M2 consequence scenario aligned to one M1 state scenario.

    ``missing`` (no value), ``unsupported`` (no admissible source) and ``zero``
    (a supported zero) stay distinct states.
    """

    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0.0)
    native_components: dict[str, float | None] = {}
    cu_components: dict[str, float | None] = {}
    domain_scores: dict[str, float | None] = {}
    consequence_priority: float | None = None
    support: SupportState = SupportState.SUPPORTED

    @model_validator(mode="after")
    def _typed_priority(self):
        if set(self.cu_components) - set(self.native_components):
            raise ValueError("CONSEQUENCE_SCENARIO_CU_WITHOUT_NATIVE")
        if self.support is SupportState.ABSTAIN and self.consequence_priority is not None:
            raise ValueError("CONSEQUENCE_SCENARIO_ABSTAIN_WITH_PRIORITY")
        return self


class ConsequenceScenarioSet(FrozenModel):
    """M2-owned consequence scenarios for one decision node/representation."""

    episode_id: str = Field(min_length=1)
    chain_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    stage: OperationalStage
    representation: StateRepresentationSpec
    registry_id: str = Field(min_length=1)
    registry_hash: str = Field(min_length=1)
    scenarios: tuple[ConsequenceScenario, ...] = ()
    support: SupportState = SupportState.SUPPORTED

    @model_validator(mode="after")
    def _weight_and_identity(self):
        if not self.scenarios:
            raise ValueError("CONSEQUENCE_SCENARIO_SET_EMPTY")
        ids = [item.scenario_id for item in self.scenarios]
        if len(set(ids)) != len(ids):
            raise ValueError("CONSEQUENCE_SCENARIO_ID_NOT_UNIQUE")
        total = sum(item.scenario_weight for item in self.scenarios)
        if abs(total - 1.0) > WEIGHT_TOLERANCE:
            raise ValueError("CONSEQUENCE_SCENARIO_WEIGHT_SUM_VIOLATION")
        return self


class PrioritySignal(FrozenModel):
    """One Stage-I priority signal bound to a stable node identity.

    ``DELAY`` is the parallel delay comparator ``P^D``; ``CONSEQUENCE`` is the
    unique consequence-based priority authority ``P^C``. Both are consumed by the
    same M3 selector and are never mixed into one score. Both are evaluated on
    common support, so a supported signal carries an ``m^CS`` attestation.
    """

    signal_type: SignalKind
    episode_id: str = Field(min_length=1)
    chain_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    representation_id: str = Field(min_length=1)
    score: float | None = None
    support: SupportState
    status: TypedStatus
    comparison_support_mass: float | None = Field(default=None, ge=0.0, le=1.0)
    comparison_support_threshold: float | None = Field(default=None, gt=0.0, le=1.0)
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _support_matches_score(self):
        if self.support is SupportState.ABSTAIN:
            if self.score is not None:
                raise ValueError("PRIORITY_SIGNAL_ABSTAIN_WITH_SCORE")
            if self.status is TypedStatus.SUPPORTED:
                raise ValueError("PRIORITY_SIGNAL_ABSTAIN_STATUS_INVALID")
            return self
        if self.score is None:
            raise ValueError("PRIORITY_SIGNAL_SCORE_MISSING")
        if (
            self.comparison_support_mass is None
            or self.comparison_support_threshold is None
        ):
            raise ValueError("PRIORITY_SIGNAL_COMMON_SUPPORT_ATTESTATION_MISSING")
        if (
            self.comparison_support_mass + WEIGHT_TOLERANCE
            < self.comparison_support_threshold
        ):
            raise ValueError("PRIORITY_SIGNAL_BELOW_COMMON_SUPPORT")
        return self


class AttentionEntry(FrozenModel):
    """One ranked chain in a Stage-I shortlist."""

    episode_id: str = Field(min_length=1)
    chain_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    score: float
    rank: int = Field(ge=1)
    selected: bool
    selected_for: SignalKind


class AttentionDecision(FrozenModel):
    """M3-owned Stage-I output for one capacity ``q`` on one signal."""

    signal_type: SignalKind
    q: float = Field(gt=0.0, le=1.0)
    k: int = Field(ge=0)
    cohort_size: int = Field(ge=0)
    entries: tuple[AttentionEntry, ...] = ()
    status: TypedStatus = TypedStatus.SUPPORTED

    @model_validator(mode="after")
    def _rankings_are_consistent(self):
        if not self.entries:
            return self
        ranks = [item.rank for item in self.entries]
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            raise ValueError("ATTENTION_RANK_NOT_CONTIGUOUS")
        if len(self.entries) != self.cohort_size:
            raise ValueError("ATTENTION_COHORT_SIZE_MISMATCH")
        for item in self.entries:
            if item.selected_for is not self.signal_type:
                raise ValueError("ATTENTION_ENTRY_SIGNAL_MISMATCH")
        if sum(1 for item in self.entries if item.selected) != self.k:
            raise ValueError("ATTENTION_SELECTED_COUNT_MISMATCH")
        return self


class HeadroomSummary(FrozenModel):
    """Train-derived action cap (representation-independent)."""

    u_max: float = Field(ge=0.0)
    turnaround_lower_bound_q: float = Field(ge=0.0)
    turnaround_quantile: float = Field(gt=0.0, lt=1.0)
    headroom_quantile: float = Field(gt=0.0, lt=1.0)
    headroom_positive_n: int = Field(ge=0)
    source_id: str = Field(min_length=1)
    floor_to_minutes: float = Field(default=5.0, gt=0.0)

    @model_validator(mode="after")
    def _floor_to_grid(self):
        ratio = self.u_max / self.floor_to_minutes
        if abs(ratio - round(ratio)) > WEIGHT_TOLERANCE:
            raise ValueError("HEADROOM_U_MAX_NOT_ON_FLOOR_GRID")
        return self


class RecoveryDecision(FrozenModel):
    """M3-owned Stage-II output for one chain.

    ``recoverable_value`` is required for the reference representation and may
    be ``None`` for comparator representations that only need a comparator
    action.
    """

    episode_id: str = Field(min_length=1)
    chain_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    representation_id: str = Field(min_length=1)
    stage: OperationalStage
    actionable_status: TypedStatus
    headroom_summary: HeadroomSummary | None = None
    action_grid: tuple[float, ...] = ()
    u_max: float | None = None
    u_star: float | None = None
    j_zero: float | None = None
    j_star: float | None = None
    recoverable_value: float | None = None
    lambda_policy: float | None = None
    solver_status: SolverStatus = SolverStatus.NOT_RUN
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _typed_recovery_consistency(self):
        if self.actionable_status is TypedStatus.NOT_ACTIONABLE:
            if self.action_grid != (0.0,):
                raise ValueError("RECOVERY_NON_ACTIONABLE_GRID_INVALID")
            if self.u_star != 0.0:
                raise ValueError("RECOVERY_NON_ACTIONABLE_ACTION_INVALID")
            if self.recoverable_value is not None:
                raise ValueError("RECOVERY_NON_ACTIONABLE_VALUE_INVALID")
            if self.headroom_summary is not None:
                raise ValueError("RECOVERY_NON_ACTIONABLE_HEADROOM_INVALID")
            return self
        if self.actionable_status is not TypedStatus.SUPPORTED:
            raise ValueError("RECOVERY_ACTIONABLE_STATUS_INVALID")
        if not self.action_grid:
            raise ValueError("RECOVERY_ACTION_GRID_MISSING")
        if self.action_grid[0] != 0.0:
            raise ValueError("RECOVERY_GRID_MUST_INCLUDE_ZERO")
        if tuple(sorted(self.action_grid)) != self.action_grid:
            raise ValueError("RECOVERY_GRID_NOT_ASCENDING")
        if self.action_grid != tuple(sorted(set(self.action_grid))):
            raise ValueError("RECOVERY_GRID_NOT_UNIQUE")
        if self.u_star is None or self.u_star not in self.action_grid:
            raise ValueError("RECOVERY_U_STAR_NOT_IN_GRID")
        if len(self.action_grid) > 1 and self.u_max != self.action_grid[-1]:
            raise ValueError("RECOVERY_U_MAX_GRID_MISMATCH")
        if self.j_zero is not None and self.j_star is not None:
            if self.recoverable_value is None:
                raise ValueError("RECOVERY_VALUE_MISSING")
            expected = self.j_zero - self.j_star
            if abs(expected - self.recoverable_value) > WEIGHT_TOLERANCE * max(
                1.0, abs(expected)
            ):
                raise ValueError("RECOVERY_VALUE_IDENTITY_VIOLATION")
        return self


class DecisionEvaluation(FrozenModel):
    """M4-owned common-basis evaluation record.

    ``ATTENTION`` carries ``L_att = delta A / A*``; ``RECOVERY`` carries
    ``L_rec = sum delta J / V_g*``. The two are never combined into a total
    loss: no ``L_total`` field exists by construction.
    """

    reference_id: str = Field(min_length=1)
    comparator_id: str = Field(min_length=1)
    cohort_id: str = Field(min_length=1)
    family: EvaluationFamily
    delta_attention_value: float | None = None
    reference_attention_value: float | None = None
    L_att: float | None = None  # noqa: N815 - scientific name
    delta_recovery_objective: float | None = None
    reference_recoverable_value: float | None = None
    L_rec: float | None = None  # noqa: N815 - scientific name
    A0: float | None = Field(default=None, ge=0.0, le=1.0)  # noqa: N815
    A5: float | None = Field(default=None, ge=0.0, le=1.0)  # noqa: N815
    activation_events: dict[str, int] = {}
    diagnostics: dict[str, float] = {}
    support_status: SupportState = SupportState.SUPPORTED
    value_status: TypedStatus = TypedStatus.SUPPORTED

    @model_validator(mode="after")
    def _family_specific_fields(self):
        if self.family is EvaluationFamily.ATTENTION:
            if self.delta_recovery_objective is not None or self.L_rec is not None:
                raise ValueError("EVALUATION_ATTENTION_CARRIES_RECOVERY_LOSS")
            if self.L_att is not None:
                if (
                    self.delta_attention_value is None
                    or self.reference_attention_value is None
                ):
                    raise ValueError("EVALUATION_ATTENTION_DENOMINATOR_MISSING")
                if self.reference_attention_value == 0.0:
                    raise ValueError("EVALUATION_ATTENTION_ZERO_REFERENCE")
                expected = self.delta_attention_value / self.reference_attention_value
                if abs(expected - self.L_att) > WEIGHT_TOLERANCE * max(
                    1.0, abs(expected)
                ):
                    raise ValueError("EVALUATION_RATIO_IDENTITY_VIOLATION")
        else:
            if self.delta_attention_value is not None or self.L_att is not None:
                raise ValueError("EVALUATION_RECOVERY_CARRIES_ATTENTION_LOSS")
            if self.value_status is TypedStatus.UNDEFINED_ZERO_RECOVERABLE_VALUE:
                if self.L_rec is not None:
                    raise ValueError("EVALUATION_UNDEFINED_VALUE_MUST_BE_NONE")
                if self.reference_recoverable_value != 0.0:
                    raise ValueError("EVALUATION_UNDEFINED_DENOMINATOR_MUST_BE_ZERO")
            elif self.L_rec is not None:
                if (
                    self.delta_recovery_objective is None
                    or self.reference_recoverable_value is None
                ):
                    raise ValueError("EVALUATION_RECOVERY_DENOMINATOR_MISSING")
                if self.reference_recoverable_value == 0.0:
                    raise ValueError("EVALUATION_ZERO_DENOMINATOR_NOT_TYPED")
                expected = (
                    self.delta_recovery_objective / self.reference_recoverable_value
                )
                if abs(expected - self.L_rec) > WEIGHT_TOLERANCE * max(
                    1.0, abs(expected)
                ):
                    raise ValueError("EVALUATION_RATIO_IDENTITY_VIOLATION")
        if set(self.activation_events) - set(ATTENTION_ACTIVATION_EVENTS):
            raise ValueError("EVALUATION_UNKNOWN_ACTIVATION_EVENT")
        if (
            self.A0 is not None
            and self.A5 is not None
            and self.A5 + WEIGHT_TOLERANCE < self.A0
        ):
            raise ValueError("EVALUATION_A5_BELOW_A0")
        return self
