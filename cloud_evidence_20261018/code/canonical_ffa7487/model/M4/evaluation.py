"""M4 common-basis evaluator (V2 Phase 4).

M4 answers one question: how much decision value is lost under a comparator
information/screening representation? It is deliberately a *pure evaluator*:

- it never reconstructs state;
- it never defines the seven consequences or the CU scales;
- it never chooses a shortlist or runs the Stage-I selector;
- it never optimizes recovery actions.

Stage-I evaluation uses the manuscript reference attention value
``A_g^*(H) = sum_{i in H} S_{C,i}^*`` and
``L_att = [A^*(H^*) - A^*(H^(r))] / A^*(H^*)``. Stage-II evaluation uses the
fixed reference cohort ``R_g^* = H_g^{C,*} intersect StageIISupported`` and
``L_rec = sum_i [J_i^*(u_i^{*(r)}) - J_i^*(u_i^*)] / sum_i V_i^*``. A zero
reference recoverable value is returned as
``UNDEFINED_ZERO_RECOVERABLE_VALUE`` rather than as a numerical zero.

The two loss families are never combined: this module contains no
``L_total``-style object and no monetary mapping. The legacy secondary monetary
interpretation remains optional, non-primary, and outside this evaluator.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np
from pydantic import Field, model_validator
from scipy import stats

from model.common.decision_contracts import (
    ATTENTION_ACTIVATION_EVENTS,
    AttentionDecision,
    DecisionEvaluation,
    EvaluationFamily,
    TypedStatus,
    WEIGHT_TOLERANCE,
)
from model.common.enums import SupportState
from model.common.errors import ContractError
from model.common.value_objects import FrozenModel


__all__ = [
    "AttentionEvaluation",
    "RecoveryEvaluation",
    "aggregate_attention_evaluations",
    "aggregate_recovery_evaluations",
    "evaluate_attention_allocation",
    "evaluate_recovery_loss",
]


DOMAINS = ("F", "P", "R")
_RECOVERY_EVENT_KEYS = tuple(ATTENTION_ACTIVATION_EVENTS)


def _relative_tolerance(reference: float, floor: float = 1.0) -> float:
    return WEIGHT_TOLERANCE * max(floor, abs(reference))


def _finite(value: float, name: str) -> float:
    resolved = float(value)
    if not math.isfinite(resolved):
        raise ContractError(f"M4_NON_FINITE_VALUE:{name}")
    return resolved


def _require_same_keys(mapping: Mapping, keys: Sequence[str], name: str) -> None:
    if set(mapping) != set(keys):
        missing = sorted(set(keys) - set(mapping))
        extra = sorted(set(mapping) - set(keys))
        raise ContractError(
            f"M4_{name}_KEY_MISMATCH:missing={missing}:extra={extra}"
        )


class AttentionEvaluation(FrozenModel):
    """Detailed Stage-I common-basis evaluation for one cohort."""

    cohort_id: str = Field(min_length=1)
    reference_id: str = Field(min_length=1)
    comparator_id: str = Field(min_length=1)
    candidate_node_ids: tuple[str, ...]
    reference_shortlist: tuple[str, ...]
    comparator_shortlist: tuple[str, ...]
    reference_attention_value: float
    comparator_attention_value: float
    delta_attention_value: float
    L_att: float | None = None  # noqa: N815 - scientific name
    overlap_count: int = Field(ge=0)
    overlap_fraction_of_reference: float = Field(ge=0.0, le=1.0)
    entered: tuple[str, ...]
    displaced: tuple[str, ...]
    diagnostics: dict[str, float] = Field(default_factory=dict)
    kendall_tau: float | None = None
    spearman_rho: float | None = None
    mean_rank_displacement: float | None = None
    max_rank_displacement: int | None = None
    status: TypedStatus = TypedStatus.SUPPORTED
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _common_basis_consistency(self):
        candidates = set(self.candidate_node_ids)
        if len(candidates) != len(self.candidate_node_ids):
            raise ValueError("M4_ATTENTION_CANDIDATE_NODE_NOT_UNIQUE")
        if not set(self.reference_shortlist) <= candidates:
            raise ValueError("M4_ATTENTION_REFERENCE_SHORTLIST_NOT_IN_COHORT")
        if not set(self.comparator_shortlist) <= candidates:
            raise ValueError("M4_ATTENTION_COMPARATOR_SHORTLIST_NOT_IN_COHORT")
        if len(set(self.reference_shortlist)) != len(self.reference_shortlist):
            raise ValueError("M4_ATTENTION_REFERENCE_SHORTLIST_NOT_UNIQUE")
        if len(set(self.comparator_shortlist)) != len(self.comparator_shortlist):
            raise ValueError("M4_ATTENTION_COMPARATOR_SHORTLIST_NOT_UNIQUE")
        expected_delta = self.reference_attention_value - self.comparator_attention_value
        if abs(self.delta_attention_value - expected_delta) > _relative_tolerance(
            expected_delta
        ):
            raise ValueError("M4_ATTENTION_DELTA_IDENTITY_VIOLATION")
        if self.L_att is None:
            if self.status is not TypedStatus.N_A_NOT_DEFINED:
                raise ValueError("M4_ATTENTION_UNDEFINED_LOSS_STATUS_INVALID")
            if abs(self.reference_attention_value) > WEIGHT_TOLERANCE:
                raise ValueError("M4_ATTENTION_UNDEFINED_NONZERO_REFERENCE")
        else:
            if self.reference_attention_value <= 0.0:
                raise ValueError("M4_ATTENTION_ZERO_REFERENCE_WITH_LOSS")
            expected = self.delta_attention_value / self.reference_attention_value
            if abs(self.L_att - expected) > _relative_tolerance(expected):
                raise ValueError("M4_ATTENTION_LOSS_IDENTITY_VIOLATION")
            if self.status not in {TypedStatus.SUPPORTED, TypedStatus.DEGRADED}:
                raise ValueError("M4_ATTENTION_DEFINED_LOSS_STATUS_INVALID")
        reference = set(self.reference_shortlist)
        comparator = set(self.comparator_shortlist)
        if self.overlap_count != len(reference & comparator):
            raise ValueError("M4_ATTENTION_OVERLAP_COUNT_MISMATCH")
        expected_fraction = (
            self.overlap_count / len(reference) if reference else 0.0
        )
        if abs(self.overlap_fraction_of_reference - expected_fraction) > WEIGHT_TOLERANCE:
            raise ValueError("M4_ATTENTION_OVERLAP_FRACTION_MISMATCH")
        if self.entered != tuple(sorted(comparator - reference)):
            raise ValueError("M4_ATTENTION_ENTERED_MISMATCH")
        if self.displaced != tuple(sorted(reference - comparator)):
            raise ValueError("M4_ATTENTION_DISPLACED_MISMATCH")
        return self

    def contract_record(self) -> DecisionEvaluation:
        """Return the shared :class:`DecisionEvaluation` interchange record."""

        return DecisionEvaluation(
            reference_id=self.reference_id,
            comparator_id=self.comparator_id,
            cohort_id=self.cohort_id,
            family=EvaluationFamily.ATTENTION,
            delta_attention_value=self.delta_attention_value,
            reference_attention_value=self.reference_attention_value,
            L_att=self.L_att,
            diagnostics=dict(self.diagnostics),
            support_status=(
                SupportState.DEGRADED
                if self.status is TypedStatus.DEGRADED
                else (
                    SupportState.ABSTAIN
                    if self.status is TypedStatus.N_A_NOT_DEFINED
                    else SupportState.SUPPORTED
                )
            ),
            value_status=self.status,
        )


class RecoveryEvaluation(FrozenModel):
    """Detailed Stage-II common-basis evaluation for one fixed cohort."""

    cohort_id: str = Field(min_length=1)
    reference_id: str = Field(min_length=1)
    comparator_id: str = Field(min_length=1)
    fixed_cohort: tuple[str, ...]
    reference_actions: dict[str, float] = Field(default_factory=dict)
    comparator_actions: dict[str, float] = Field(default_factory=dict)
    reference_objectives: dict[str, float] = Field(default_factory=dict)
    comparator_objectives: dict[str, float] = Field(default_factory=dict)
    delta_objectives: dict[str, float] = Field(default_factory=dict)
    reference_recoverable_values: dict[str, float] = Field(default_factory=dict)
    reference_recoverable_value: float
    delta_recovery_objective: float
    L_rec: float | None = None  # noqa: N815 - scientific name
    A0: float = Field(ge=0.0, le=1.0)  # noqa: N815
    A5: float = Field(ge=0.0, le=1.0)  # noqa: N815
    exact_action_count: int = Field(ge=0)
    within_five_count: int = Field(ge=0)
    activation_events: dict[str, int] = Field(default_factory=dict)
    diagnostics: dict[str, float] = Field(default_factory=dict)
    status: TypedStatus = TypedStatus.SUPPORTED
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _common_basis_consistency(self):
        cohort = set(self.fixed_cohort)
        if not cohort or len(cohort) != len(self.fixed_cohort):
            raise ValueError("M4_RECOVERY_FIXED_COHORT_INVALID")
        _require_same_keys(self.reference_actions, self.fixed_cohort, "REFERENCE_ACTIONS")
        _require_same_keys(
            self.comparator_actions, self.fixed_cohort, "COMPARATOR_ACTIONS"
        )
        _require_same_keys(
            self.reference_objectives, self.fixed_cohort, "REFERENCE_OBJECTIVES"
        )
        _require_same_keys(
            self.comparator_objectives, self.fixed_cohort, "COMPARATOR_OBJECTIVES"
        )
        _require_same_keys(
            self.delta_objectives, self.fixed_cohort, "DELTA_OBJECTIVES"
        )
        _require_same_keys(
            self.reference_recoverable_values,
            self.fixed_cohort,
            "REFERENCE_RECOVERABLE_VALUES",
        )
        for node_id in self.fixed_cohort:
            for name, value in (
                ("reference_action", self.reference_actions[node_id]),
                ("comparator_action", self.comparator_actions[node_id]),
                ("reference_objective", self.reference_objectives[node_id]),
                ("comparator_objective", self.comparator_objectives[node_id]),
                ("reference_recoverable_value", self.reference_recoverable_values[node_id]),
            ):
                _finite(value, f"{node_id}:{name}")
            if self.reference_actions[node_id] < 0.0:
                raise ValueError("M4_RECOVERY_NEGATIVE_REFERENCE_ACTION")
            if self.comparator_actions[node_id] < 0.0:
                raise ValueError("M4_RECOVERY_NEGATIVE_COMPARATOR_ACTION")
            expected_delta = (
                self.comparator_objectives[node_id]
                - self.reference_objectives[node_id]
            )
            if abs(self.delta_objectives[node_id] - expected_delta) > _relative_tolerance(
                expected_delta
            ):
                raise ValueError("M4_RECOVERY_DELTA_IDENTITY_VIOLATION")
            if self.reference_recoverable_values[node_id] < 0.0:
                raise ValueError("M4_RECOVERY_NEGATIVE_REFERENCE_VALUE")
        expected_total_delta = sum(self.delta_objectives.values())
        if abs(self.delta_recovery_objective - expected_total_delta) > _relative_tolerance(
            expected_total_delta
        ):
            raise ValueError("M4_RECOVERY_TOTAL_DELTA_IDENTITY_VIOLATION")
        expected_reference_value = sum(self.reference_recoverable_values.values())
        if abs(self.reference_recoverable_value - expected_reference_value) > _relative_tolerance(
            expected_reference_value
        ):
            raise ValueError("M4_RECOVERY_REFERENCE_VALUE_IDENTITY_VIOLATION")
        if self.reference_recoverable_value < 0.0:
            raise ValueError("M4_RECOVERY_NEGATIVE_AGGREGATE_REFERENCE_VALUE")
        if self.L_rec is None:
            if self.status is not TypedStatus.UNDEFINED_ZERO_RECOVERABLE_VALUE:
                raise ValueError("M4_RECOVERY_UNDEFINED_LOSS_STATUS_INVALID")
            if abs(self.reference_recoverable_value) > WEIGHT_TOLERANCE:
                raise ValueError("M4_RECOVERY_UNDEFINED_NONZERO_REFERENCE")
        else:
            if self.reference_recoverable_value <= 0.0:
                raise ValueError("M4_RECOVERY_ZERO_DENOMINATOR_WITH_LOSS")
            expected = self.delta_recovery_objective / self.reference_recoverable_value
            if abs(self.L_rec - expected) > _relative_tolerance(expected):
                raise ValueError("M4_RECOVERY_LOSS_IDENTITY_VIOLATION")
            if self.status not in {TypedStatus.SUPPORTED, TypedStatus.DEGRADED}:
                raise ValueError("M4_RECOVERY_DEFINED_LOSS_STATUS_INVALID")
        size = len(self.fixed_cohort)
        if self.exact_action_count > size or self.within_five_count > size:
            raise ValueError("M4_RECOVERY_COUNT_EXCEEDS_COHORT")
        if self.within_five_count < self.exact_action_count:
            raise ValueError("M4_RECOVERY_WITHIN_FIVE_BELOW_EXACT")
        if abs(self.A0 - self.exact_action_count / size) > WEIGHT_TOLERANCE:
            raise ValueError("M4_RECOVERY_A0_IDENTITY_VIOLATION")
        if abs(self.A5 - self.within_five_count / size) > WEIGHT_TOLERANCE:
            raise ValueError("M4_RECOVERY_A5_IDENTITY_VIOLATION")
        unknown_events = set(self.activation_events) - set(_RECOVERY_EVENT_KEYS)
        if unknown_events:
            raise ValueError("M4_RECOVERY_UNKNOWN_ACTIVATION_EVENT")
        if any(value < 0 for value in self.activation_events.values()):
            raise ValueError("M4_RECOVERY_NEGATIVE_ACTIVATION_EVENT")
        total_events = sum(self.activation_events.values())
        if total_events > size:
            raise ValueError("M4_RECOVERY_ACTIVATION_EVENTS_EXCEED_COHORT")
        return self

    def contract_record(self) -> DecisionEvaluation:
        """Return the shared :class:`DecisionEvaluation` interchange record."""


        return DecisionEvaluation(
            reference_id=self.reference_id,
            comparator_id=self.comparator_id,
            cohort_id=self.cohort_id,
            family=EvaluationFamily.RECOVERY,
            delta_recovery_objective=self.delta_recovery_objective,
            reference_recoverable_value=self.reference_recoverable_value,
            L_rec=self.L_rec,
            A0=self.A0,
            A5=self.A5,
            activation_events=dict(self.activation_events),
            diagnostics=dict(self.diagnostics),
            support_status=SupportState.SUPPORTED,
            value_status=self.status,
        )


def _selected(decision: AttentionDecision) -> tuple[str, ...]:
    return tuple(
        item.node_id for item in decision.entries if item.selected
    )


def _rank_map(decision: AttentionDecision) -> dict[str, int]:
    return {item.node_id: item.rank for item in decision.entries}


def _score_map(decision: AttentionDecision) -> dict[str, float]:
    return {item.node_id: float(item.score) for item in decision.entries}


def _coverage(
    shortlist: Sequence[str],
    values: Mapping[str, float],
    total: float,
) -> float | None:
    if total <= 0.0:
        return None
    return sum(float(values[node_id]) for node_id in shortlist) / total


def evaluate_attention_allocation(
    *,
    cohort_id: str,
    reference_id: str,
    comparator_id: str,
    reference_decision: AttentionDecision,
    comparator_decision: AttentionDecision,
    reference_priority: Mapping[str, float],
    reference_domain_scores: Mapping[str, Mapping[str, float]] | None = None,
) -> AttentionEvaluation:
    """Evaluate one comparator shortlist on the reference consequence basis.

    ``reference_priority`` is ``S_{C,i}^*``, supplied by the reference
    consequence evaluator. It is never recomputed or re-ranked here. The two
    decisions must cover the same eligible candidate cohort and the same
    attention capacity; only their priority signals may differ.
    """

    reference_candidates = set(_rank_map(reference_decision))
    comparator_candidates = set(_rank_map(comparator_decision))
    if reference_candidates != comparator_candidates:
        raise ContractError("M4_ATTENTION_CANDIDATE_QUEUE_MISMATCH")
    if reference_decision.cohort_size != comparator_decision.cohort_size:
        raise ContractError("M4_ATTENTION_COHORT_SIZE_MISMATCH")
    if abs(reference_decision.q - comparator_decision.q) > WEIGHT_TOLERANCE:
        raise ContractError("M4_ATTENTION_CAPACITY_MISMATCH")
    candidates = tuple(sorted(reference_candidates))
    _require_same_keys(reference_priority, candidates, "REFERENCE_PRIORITY")
    priorities = {
        node_id: _finite(reference_priority[node_id], f"priority:{node_id}")
        for node_id in candidates
    }
    if any(value < 0.0 for value in priorities.values()):
        raise ContractError("M4_ATTENTION_NEGATIVE_REFERENCE_PRIORITY")

    reference_shortlist = _selected(reference_decision)
    comparator_shortlist = _selected(comparator_decision)
    reference_value = sum(priorities[node_id] for node_id in reference_shortlist)
    comparator_value = sum(priorities[node_id] for node_id in comparator_shortlist)
    delta = reference_value - comparator_value
    reference_set = set(reference_shortlist)
    comparator_set = set(comparator_shortlist)
    overlap = len(reference_set & comparator_set)
    entered = tuple(sorted(comparator_set - reference_set))
    displaced = tuple(sorted(reference_set - comparator_set))

    reason_codes: list[str] = []
    if reference_value <= 0.0:
        L_att = None
        status = TypedStatus.N_A_NOT_DEFINED
        reason_codes.append("M4_ATTENTION_REFERENCE_VALUE_ZERO")
    else:
        L_att = delta / reference_value
        status = TypedStatus.SUPPORTED

    diagnostics: dict[str, float] = {
        "overlap_count": float(overlap),
        "overlap_fraction_of_reference": (
            overlap / len(reference_shortlist) if reference_shortlist else 0.0
        ),
        "entered_count": float(len(entered)),
        "displaced_count": float(len(displaced)),
        "candidate_count": float(len(candidates)),
        "reference_shortlist_size": float(len(reference_shortlist)),
        "comparator_shortlist_size": float(len(comparator_shortlist)),
    }
    cohort_total = sum(priorities.values())
    coverage_reference = _coverage(reference_shortlist, priorities, cohort_total)
    coverage_comparator = _coverage(comparator_shortlist, priorities, cohort_total)
    if coverage_reference is not None:
        diagnostics["coverage_total_reference"] = coverage_reference
    else:
        reason_codes.append("M4_COVERAGE_TOTAL_REFERENCE_UNDEFINED")
    if coverage_comparator is not None:
        diagnostics["coverage_total_comparator"] = coverage_comparator
    else:
        reason_codes.append("M4_COVERAGE_TOTAL_COMPARATOR_UNDEFINED")

    if reference_domain_scores is not None:
        _require_same_keys(reference_domain_scores, candidates, "REFERENCE_DOMAIN_SCORES")
        for domain in DOMAINS:
            domain_values = {}
            for node_id in candidates:
                score_map = reference_domain_scores[node_id]
                if set(score_map) != set(DOMAINS):
                    raise ContractError(
                        f"M4_ATTENTION_DOMAIN_SCORE_KEYS_MISMATCH:{node_id}"
                    )
                domain_values[node_id] = _finite(
                    score_map[domain], f"domain:{domain}:{node_id}"
                )
            domain_total = sum(domain_values.values())
            reference_coverage = _coverage(
                reference_shortlist, domain_values, domain_total
            )
            comparator_coverage = _coverage(
                comparator_shortlist, domain_values, domain_total
            )
            if reference_coverage is not None:
                diagnostics[f"coverage_{domain}_reference"] = reference_coverage
            else:
                reason_codes.append(f"M4_COVERAGE_{domain}_REFERENCE_UNDEFINED")
            if comparator_coverage is not None:
                diagnostics[f"coverage_{domain}_comparator"] = comparator_coverage
            else:
                reason_codes.append(f"M4_COVERAGE_{domain}_COMPARATOR_UNDEFINED")

    kendall_tau: float | None = None
    spearman_rho: float | None = None
    if len(candidates) >= 2:
        reference_vector = np.asarray(
            [priorities[node_id] for node_id in candidates], dtype=float
        )
        comparator_scores = _score_map(comparator_decision)
        comparator_vector = np.asarray(
            [comparator_scores[node_id] for node_id in candidates], dtype=float
        )
        if np.ptp(reference_vector) > 0.0 and np.ptp(comparator_vector) > 0.0:
            kendall = stats.kendalltau(reference_vector, comparator_vector)
            spearman = stats.spearmanr(reference_vector, comparator_vector)
            if math.isfinite(float(kendall.statistic)):
                kendall_tau = float(kendall.statistic)
                diagnostics["kendall_tau"] = kendall_tau
            else:
                reason_codes.append("M4_KENDALL_UNDEFINED")
            if math.isfinite(float(spearman.statistic)):
                spearman_rho = float(spearman.statistic)
                diagnostics["spearman_rho"] = spearman_rho
            else:
                reason_codes.append("M4_SPEARMAN_UNDEFINED")
        else:
            reason_codes.append("M4_RANK_CORRELATION_UNDEFINED_CONSTANT")
    else:
        reason_codes.append("M4_RANK_CORRELATION_UNDEFINED_COHORT_TOO_SMALL")

    reference_ranks = _rank_map(reference_decision)
    comparator_ranks = _rank_map(comparator_decision)
    displaced_nodes = sorted(reference_set | comparator_set)
    if displaced_nodes:
        displacements = [
            abs(reference_ranks[node_id] - comparator_ranks[node_id])
            for node_id in displaced_nodes
        ]
        mean_displacement = float(np.mean(displacements))
        max_displacement = int(max(displacements))
    else:
        mean_displacement = 0.0
        max_displacement = 0
    diagnostics["mean_rank_displacement"] = mean_displacement
    diagnostics["max_rank_displacement"] = float(max_displacement)

    return AttentionEvaluation(
        cohort_id=cohort_id,
        reference_id=reference_id,
        comparator_id=comparator_id,
        candidate_node_ids=candidates,
        reference_shortlist=reference_shortlist,
        comparator_shortlist=comparator_shortlist,
        reference_attention_value=reference_value,
        comparator_attention_value=comparator_value,
        delta_attention_value=delta,
        L_att=L_att,
        overlap_count=overlap,
        overlap_fraction_of_reference=(
            overlap / len(reference_shortlist) if reference_shortlist else 0.0
        ),
        entered=entered,
        displaced=displaced,
        diagnostics=diagnostics,
        kendall_tau=kendall_tau,
        spearman_rho=spearman_rho,
        mean_rank_displacement=mean_displacement,
        max_rank_displacement=max_displacement,
        status=status,
        reason_codes=tuple(sorted(set(reason_codes))),
    )


def evaluate_recovery_loss(
    *,
    cohort_id: str,
    reference_id: str,
    comparator_id: str,
    fixed_cohort: Sequence[str],
    reference_actions: Mapping[str, float],
    comparator_actions: Mapping[str, float],
    reference_objectives: Mapping[tuple[str, float], float],
    reference_recoverable_values: Mapping[str, float],
) -> RecoveryEvaluation:
    """Evaluate comparator actions on the fixed reference Stage-II cohort.

    ``reference_objectives[(node_id, u)]`` is the reference objective
    ``J_i^*(u)`` supplied by M3. Both the reference and comparator actions are
    evaluated against this same map, so a comparator is never scored under its
    own objective.
    """

    cohort = tuple(fixed_cohort)
    unique = set(cohort)
    if not cohort or len(unique) != len(cohort):
        raise ContractError("M4_RECOVERY_FIXED_COHORT_INVALID")
    _require_same_keys(reference_actions, cohort, "REFERENCE_ACTIONS")
    _require_same_keys(comparator_actions, cohort, "COMPARATOR_ACTIONS")
    _require_same_keys(reference_recoverable_values, cohort, "REFERENCE_VALUES")

    reference_actions_resolved = {
        node_id: _finite(reference_actions[node_id], f"u*:{node_id}")
        for node_id in cohort
    }
    comparator_actions_resolved = {
        node_id: _finite(comparator_actions[node_id], f"u(r):{node_id}")
        for node_id in cohort
    }
    if any(value < 0.0 for value in reference_actions_resolved.values()):
        raise ContractError("M4_RECOVERY_NEGATIVE_REFERENCE_ACTION")
    if any(value < 0.0 for value in comparator_actions_resolved.values()):
        raise ContractError("M4_RECOVERY_NEGATIVE_COMPARATOR_ACTION")

    reference_objectives_resolved = {}
    comparator_objectives_resolved = {}
    delta_objectives = {}
    for node_id in cohort:
        reference_key = (node_id, reference_actions_resolved[node_id])
        comparator_key = (node_id, comparator_actions_resolved[node_id])
        if reference_key not in reference_objectives:
            raise ContractError(f"M4_RECOVERY_REFERENCE_OBJECTIVE_MISSING:{node_id}")
        if comparator_key not in reference_objectives:
            raise ContractError(
                f"M4_RECOVERY_COMPARATOR_OBJECTIVE_MISSING:{node_id}"
            )
        reference_value = _finite(
            reference_objectives[reference_key], f"J*(u*):{node_id}"
        )
        comparator_value = _finite(
            reference_objectives[comparator_key], f"J*(u(r)):{node_id}"
        )
        reference_objectives_resolved[node_id] = reference_value
        comparator_objectives_resolved[node_id] = comparator_value
        delta_objectives[node_id] = comparator_value - reference_value

    recoverable_values = {
        node_id: _finite(
            reference_recoverable_values[node_id], f"V*:{node_id}"
        )
        for node_id in cohort
    }
    if any(value < 0.0 for value in recoverable_values.values()):
        raise ContractError("M4_RECOVERY_NEGATIVE_REFERENCE_VALUE")
    total_reference_value = sum(recoverable_values.values())
    total_delta = sum(delta_objectives.values())
    reason_codes: list[str] = []
    if total_reference_value <= 0.0:
        L_rec = None
        status = TypedStatus.UNDEFINED_ZERO_RECOVERABLE_VALUE
        reason_codes.append("M4_RECOVERY_ZERO_REFERENCE_VALUE")
    else:
        L_rec = total_delta / total_reference_value
        status = TypedStatus.SUPPORTED

    exact = 0
    within_five = 0
    events = {key: 0 for key in _RECOVERY_EVENT_KEYS}
    absolute_errors = []
    signed_errors = []
    for node_id in cohort:
        reference_action = reference_actions_resolved[node_id]
        comparator_action = comparator_actions_resolved[node_id]
        difference = comparator_action - reference_action
        absolute_errors.append(abs(difference))
        signed_errors.append(difference)
        if abs(difference) <= 1e-9:
            exact += 1
            within_five += 1
        elif abs(difference) <= 5.0 + 1e-9:
            within_five += 1
        if reference_action > 0.0 and comparator_action == 0.0:
            events["MISSED_ACTIVATION"] += 1
        elif reference_action == 0.0 and comparator_action > 0.0:
            events["FALSE_ACTIVATION"] += 1
        elif (
            reference_action > 0.0
            and comparator_action > 0.0
            and comparator_action < reference_action
        ):
            events["UNDER_RECOVERY"] += 1
        elif (
            reference_action > 0.0
            and comparator_action > 0.0
            and comparator_action > reference_action
        ):
            events["OVER_RECOVERY"] += 1

    size = len(cohort)
    diagnostics = {
        "cohort_size": float(size),
        "mean_absolute_intensity_error": float(np.mean(absolute_errors)),
        "max_absolute_intensity_error": float(np.max(absolute_errors)),
        "mean_signed_intensity_error": float(np.mean(signed_errors)),
        "mean_delta_objective": float(np.mean(list(delta_objectives.values()))),
        "max_delta_objective": float(np.max(list(delta_objectives.values()))),
        "reference_activation_rate": float(
            sum(1 for value in reference_actions_resolved.values() if value > 0.0)
            / size
        ),
        "comparator_activation_rate": float(
            sum(1 for value in comparator_actions_resolved.values() if value > 0.0)
            / size
        ),
    }
    return RecoveryEvaluation(
        cohort_id=cohort_id,
        reference_id=reference_id,
        comparator_id=comparator_id,
        fixed_cohort=cohort,
        reference_actions=reference_actions_resolved,
        comparator_actions=comparator_actions_resolved,
        reference_objectives=reference_objectives_resolved,
        comparator_objectives=comparator_objectives_resolved,
        delta_objectives=delta_objectives,
        reference_recoverable_values=recoverable_values,
        reference_recoverable_value=total_reference_value,
        delta_recovery_objective=total_delta,
        L_rec=L_rec,
        A0=exact / size,
        A5=within_five / size,
        exact_action_count=exact,
        within_five_count=within_five,
        activation_events=events,
        diagnostics=diagnostics,
        status=status,
        reason_codes=tuple(sorted(set(reason_codes))),
    )


def aggregate_attention_evaluations(
    evaluations: Sequence[AttentionEvaluation],
    *,
    reference_id: str | None = None,
    comparator_id: str | None = None,
) -> DecisionEvaluation:
    """Aggregate Stage-I losses as a ratio of summed values, never a mean ratio."""

    if not evaluations:
        raise ContractError("M4_ATTENTION_AGGREGATE_EMPTY")
    active_reference = reference_id or evaluations[0].reference_id
    active_comparator = comparator_id or evaluations[0].comparator_id
    for item in evaluations:
        if item.reference_id != active_reference or item.comparator_id != active_comparator:
            raise ContractError("M4_ATTENTION_AGGREGATE_COMPARISON_MISMATCH")
    reference_value = sum(item.reference_attention_value for item in evaluations)
    comparator_value = sum(item.comparator_attention_value for item in evaluations)
    delta = reference_value - comparator_value
    if reference_value <= 0.0:
        return DecisionEvaluation(
            reference_id=active_reference,
            comparator_id=active_comparator,
            cohort_id="AGGREGATE",
            family=EvaluationFamily.ATTENTION,
            delta_attention_value=delta,
            reference_attention_value=reference_value,
            L_att=None,
            diagnostics={
                "cohort_count": float(len(evaluations)),
                "delta_attention_value": delta,
            },
            support_status=SupportState.ABSTAIN,
            value_status=TypedStatus.N_A_NOT_DEFINED,
        )
    return DecisionEvaluation(
        reference_id=active_reference,
        comparator_id=active_comparator,
        cohort_id="AGGREGATE",
        family=EvaluationFamily.ATTENTION,
        delta_attention_value=delta,
        reference_attention_value=reference_value,
        L_att=delta / reference_value,
        diagnostics={
            "cohort_count": float(len(evaluations)),
            "delta_attention_value": delta,
            "comparator_attention_value": comparator_value,
        },
        support_status=SupportState.SUPPORTED,
        value_status=TypedStatus.SUPPORTED,
    )


def aggregate_recovery_evaluations(
    evaluations: Sequence[RecoveryEvaluation],
    *,
    reference_id: str | None = None,
    comparator_id: str | None = None,
) -> DecisionEvaluation:
    """Aggregate Stage-II losses over fixed cohorts as a ratio of summed values."""

    if not evaluations:
        raise ContractError("M4_RECOVERY_AGGREGATE_EMPTY")
    active_reference = reference_id or evaluations[0].reference_id
    active_comparator = comparator_id or evaluations[0].comparator_id
    for item in evaluations:
        if item.reference_id != active_reference or item.comparator_id != active_comparator:
            raise ContractError("M4_RECOVERY_AGGREGATE_COMPARISON_MISMATCH")
    reference_value = sum(item.reference_recoverable_value for item in evaluations)
    delta = sum(item.delta_recovery_objective for item in evaluations)
    exact = sum(item.exact_action_count for item in evaluations)
    within_five = sum(item.within_five_count for item in evaluations)
    size = sum(len(item.fixed_cohort) for item in evaluations)
    events = {key: 0 for key in _RECOVERY_EVENT_KEYS}
    for item in evaluations:
        for key, value in item.activation_events.items():
            events[key] += value
    if reference_value <= 0.0:
        return DecisionEvaluation(
            reference_id=active_reference,
            comparator_id=active_comparator,
            cohort_id="AGGREGATE",
            family=EvaluationFamily.RECOVERY,
            delta_recovery_objective=delta,
            reference_recoverable_value=reference_value,
            L_rec=None,
            A0=exact / size,
            A5=within_five / size,
            activation_events=events,
            diagnostics={
                "cohort_count": float(len(evaluations)),
                "fixed_cohort_size": float(size),
            },
            support_status=SupportState.SUPPORTED,
            value_status=TypedStatus.UNDEFINED_ZERO_RECOVERABLE_VALUE,
        )
    return DecisionEvaluation(
        reference_id=active_reference,
        comparator_id=active_comparator,
        cohort_id="AGGREGATE",
        family=EvaluationFamily.RECOVERY,
        delta_recovery_objective=delta,
        reference_recoverable_value=reference_value,
        L_rec=delta / reference_value,
        A0=exact / size,
        A5=within_five / size,
        activation_events=events,
        diagnostics={
            "cohort_count": float(len(evaluations)),
            "fixed_cohort_size": float(size),
        },
        support_status=SupportState.SUPPORTED,
        value_status=TypedStatus.SUPPORTED,
    )
