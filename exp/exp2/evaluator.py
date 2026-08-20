"""Common-schema Exp2 comparison metrics over M4 risk envelopes."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

from exp.common.evaluator import EvaluationSuite, MetricDefinition
from exp.common.result_schema import MetricLevel, MetricObservation, SupportStatus
from model.M4.residual_risk import RankingAuthority, RiskEvaluationEnvelope


@dataclass(frozen=True)
class Exp2EvaluationPayload:
    """Paired outputs produced by the same M3/M4 interface and policies."""

    reference_variant_id: str
    variant_id: str
    reference_m4: tuple[RiskEvaluationEnvelope, ...]
    variant_m4: tuple[RiskEvaluationEnvelope, ...]
    state_metric_reason: str = "NO_FROZEN_STATE_UNCERTAINTY_METRIC_OR_OBSERVATIONS"

    def validate(self) -> None:
        if any(not isinstance(item, RiskEvaluationEnvelope) for item in self.reference_m4):
            raise TypeError("EXP2_REFERENCE_M4_ENVELOPE_REQUIRED")
        if any(not isinstance(item, RiskEvaluationEnvelope) for item in self.variant_m4):
            raise TypeError("EXP2_VARIANT_M4_ENVELOPE_REQUIRED")
        reference_ids = tuple(item.action_id for item in self.reference_m4)
        variant_ids = tuple(item.action_id for item in self.variant_m4)
        if len(reference_ids) != len(set(reference_ids)) or len(variant_ids) != len(set(variant_ids)):
            raise ValueError("EXP2_DUPLICATE_ACTION_ID")
        if set(reference_ids) != set(variant_ids):
            raise ValueError("EXP2_ACTION_SET_MODIFIED")
        identities = {
            (
                item.monetary_system_id,
                item.monetary_mapping_registry_hash,
                item.risk_policy_hash,
                item.alpha,
            )
            for item in self.reference_m4 + self.variant_m4
        }
        if len(identities) > 1:
            raise ValueError("EXP2_M4_MAPPING_OR_POLICY_MODIFIED")


def _maps(payload: Exp2EvaluationPayload, attribute: str):
    reference = {
        item.action_id: getattr(item, attribute)
        for item in payload.reference_m4
        if getattr(item, attribute) is not None
        and item.ranking_authority is not RankingAuthority.NOT_RANKED
    }
    variant = {
        item.action_id: getattr(item, attribute)
        for item in payload.variant_m4
        if getattr(item, attribute) is not None
        and item.ranking_authority is not RankingAuthority.NOT_RANKED
    }
    return reference, variant


def _metadata(payload: Exp2EvaluationPayload) -> dict[str, Any]:
    if not payload.reference_m4:
        return {
            "reference_variant_id": payload.reference_variant_id,
            "comparison_variant_id": payload.variant_id,
            "reason": "M3_M4_OUTPUT_NOT_AVAILABLE",
        }
    first = payload.reference_m4[0]
    return {
        "reference_variant_id": payload.reference_variant_id,
        "comparison_variant_id": payload.variant_id,
        "monetary_mapping_registry_hash": first.monetary_mapping_registry_hash,
        "risk_policy_hash": first.risk_policy_hash,
        "alpha": first.alpha,
        "ranking_authority": sorted({
            item.ranking_authority.value
            for item in payload.reference_m4 + payload.variant_m4
        }),
    }


def _numeric_support(payload: Exp2EvaluationPayload) -> SupportStatus:
    envelopes = payload.reference_m4 + payload.variant_m4
    if not envelopes:
        return SupportStatus.NOT_RUN
    if any(item.ranking_authority is RankingAuthority.NOT_RANKED for item in envelopes):
        return SupportStatus.PARTIAL
    if all(item.ranking_authority is RankingAuthority.AUTHORITATIVE for item in envelopes):
        return SupportStatus.SUPPORTED
    return SupportStatus.PARTIAL


def _unsupported(metric_id: str, level: MetricLevel, unit: str, reason: str, payload):
    return MetricObservation(
        metric_id=metric_id,
        level=level,
        value=None,
        unit=unit,
        support_status=SupportStatus.NOT_RUN,
        metadata={**_metadata(payload), "reason": reason},
    )


def _state_crps(payload: Exp2EvaluationPayload) -> MetricObservation:
    return _unsupported(
        "STATE_CRPS",
        MetricLevel.STATE,
        "minutes",
        payload.state_metric_reason,
        payload,
    )


def _action_disagreement(payload: Exp2EvaluationPayload) -> MetricObservation:
    reference, variant = _maps(payload, "residual_risk_objective")
    if not reference or set(reference) != set(variant):
        return _unsupported(
            "DECISION_ACTION_DISAGREEMENT", MetricLevel.DECISION, "rate",
            "SUPPORTED_COMMON_M4_RANKING_UNAVAILABLE", payload,
        )
    value = float(min(reference, key=reference.get) != min(variant, key=variant.get))
    return MetricObservation(
        metric_id="DECISION_ACTION_DISAGREEMENT",
        level=MetricLevel.DECISION,
        value=value,
        unit="rate",
        support_status=_numeric_support(payload),
        metadata=_metadata(payload),
    )


def _ranking_change(payload: Exp2EvaluationPayload) -> MetricObservation:
    reference, variant = _maps(payload, "residual_risk_objective")
    if set(reference) != set(variant) or len(reference) < 2:
        return _unsupported(
            "DECISION_RANKING_CHANGE", MetricLevel.DECISION, "rate",
            "AT_LEAST_TWO_COMMON_SUPPORTED_M4_ACTIONS_REQUIRED", payload,
        )
    pairs = tuple(combinations(sorted(reference), 2))
    reversals = sum(
        (reference[left] - reference[right]) * (variant[left] - variant[right]) < 0
        for left, right in pairs
    )
    return MetricObservation(
        metric_id="DECISION_RANKING_CHANGE",
        level=MetricLevel.DECISION,
        value=reversals / len(pairs),
        unit="rate",
        support_status=_numeric_support(payload),
        metadata={**_metadata(payload), "pair_count": len(pairs)},
    )


def _mean_difference(
    payload: Exp2EvaluationPayload,
    *,
    metric_id: str,
    attribute: str,
) -> MetricObservation:
    reference, variant = _maps(payload, attribute)
    if not reference or set(reference) != set(variant):
        return _unsupported(
            metric_id, MetricLevel.DECISION, "M4_MONETARY_UNIT",
            "SUPPORTED_COMMON_M4_VALUES_UNAVAILABLE", payload,
        )
    differences = tuple(variant[key] - reference[key] for key in sorted(reference))
    return MetricObservation(
        metric_id=metric_id,
        level=MetricLevel.DECISION,
        value=sum(differences) / len(differences),
        unit="M4_MONETARY_UNIT",
        support_status=_numeric_support(payload),
        metadata={
            **_metadata(payload),
            "difference_direction": "variant_minus_reference",
            "action_count": len(differences),
        },
    )


def build_exp2_evaluation_suite() -> EvaluationSuite:
    suite = EvaluationSuite()
    entries = (
        (
            MetricDefinition(
                metric_id="STATE_CRPS",
                level=MetricLevel.STATE,
                description="State uncertainty metric when observations and a frozen CRPS protocol are available.",
                unit="minutes",
                claim_scope="NOT_RUN_WITHOUT_FROZEN_OBSERVATION_PROTOCOL",
            ),
            _state_crps,
        ),
        (
            MetricDefinition(
                metric_id="DECISION_ACTION_DISAGREEMENT",
                level=MetricLevel.DECISION,
                description="Top-ranked M4 action disagreement against the family reference representation.",
                unit="rate",
                claim_scope="PAIRED_REPRESENTATION_COMPARISON_ONLY",
            ),
            _action_disagreement,
        ),
        (
            MetricDefinition(
                metric_id="DECISION_RANKING_CHANGE",
                level=MetricLevel.DECISION,
                description="Pairwise M4 ranking reversal rate against the family reference representation.",
                unit="rate",
                claim_scope="PAIRED_REPRESENTATION_COMPARISON_ONLY",
            ),
            _ranking_change,
        ),
        (
            MetricDefinition(
                metric_id="DECISION_RISK_DIFFERENCE",
                level=MetricLevel.DECISION,
                description="Mean paired M4 residual-risk difference.",
                unit="M4_MONETARY_UNIT",
                claim_scope="PAIRED_REPRESENTATION_COMPARISON_ONLY",
            ),
            lambda payload: _mean_difference(
                payload,
                metric_id="DECISION_RISK_DIFFERENCE",
                attribute="residual_risk_objective",
            ),
        ),
        (
            MetricDefinition(
                metric_id="DECISION_CVAR_DIFFERENCE",
                level=MetricLevel.DECISION,
                description="Mean paired M4 CVaR difference when M4 supports CVaR.",
                unit="M4_MONETARY_UNIT",
                claim_scope="PAIRED_REPRESENTATION_COMPARISON_ONLY",
            ),
            lambda payload: _mean_difference(
                payload,
                metric_id="DECISION_CVAR_DIFFERENCE",
                attribute="monetary_loss_cvar_alpha",
            ),
        ),
    )
    for definition, evaluator in entries:
        suite.register(definition, evaluator)
    return suite


class Exp2Evaluator:
    def __init__(self, suite: EvaluationSuite | None = None):
        self.suite = suite or build_exp2_evaluation_suite()

    def evaluate(self, payload: Exp2EvaluationPayload) -> dict[str, MetricObservation]:
        if not isinstance(payload, Exp2EvaluationPayload):
            raise TypeError("EXP2_EVALUATION_PAYLOAD_REQUIRED")
        payload.validate()
        return self.suite.evaluate_many(self.suite.metric_ids(), payload)


__all__ = [
    "Exp2EvaluationPayload",
    "Exp2Evaluator",
    "build_exp2_evaluation_suite",
]
