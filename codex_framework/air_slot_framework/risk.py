"""M4 constructed RMB and residual-risk contracts.

This module intentionally exposes a constructed monetary representation.  It
does not claim real currency, monetary ground truth, or an authoritative action
ranking when mapping, tail support, or the response specification is not
frozen.
"""

from __future__ import annotations

from enum import Enum
import math
from typing import Any

from pydantic import Field, model_validator

from .action_response import ActionConditionedScenario, ActionMaterialization, ResponseSupport
from .contracts import CONSEQUENCE_COMPONENTS, FrozenModel, SupportState, content_hash


class MappingStatus(str, Enum):
    FROZEN = "FROZEN"
    TEST_ONLY = "TEST_ONLY"
    NOT_FROZEN = "NOT_FROZEN"


class TailSupport(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNRESOLVED = "UNRESOLVED"


class RiskPolicyStatus(str, Enum):
    FROZEN = "FROZEN"
    TEST_ONLY = "TEST_ONLY"
    NOT_FROZEN = "NOT_FROZEN"


class RMBMappingRule(FrozenModel):
    """CU to constructed RMB rule; baseline is RMB_k = 1.0 * CU_k."""

    mapping_id: str = Field(min_length=1)
    rmb_per_cu: float = 1.0
    mapping_status: MappingStatus = MappingStatus.TEST_ONLY
    source_references: tuple[str, ...] = ("M4_CONSTRUCTED_RMB_BASELINE",)
    provenance: tuple[str, ...] = ("CONSTRUCTED_RMB_NOT_REAL_CURRENCY",)
    mapping_hash: str | None = None

    @model_validator(mode="after")
    def validate_mapping(self):
        if not math.isfinite(self.rmb_per_cu) or self.rmb_per_cu <= 0:
            raise ValueError("RMB_PER_CU_INVALID")
        expected = content_hash(self.model_dump(mode="json", exclude={"mapping_hash"}))
        if self.mapping_hash is not None and self.mapping_hash != expected:
            raise ValueError("RMB_MAPPING_HASH_MISMATCH")
        return self

    @property
    def rule_hash(self) -> str:
        return content_hash(self.model_dump(mode="json", exclude={"mapping_hash"}))


class RMBMappingRegistry(FrozenModel):
    """Immutable registry wrapper used by the decision chain."""

    mapping_rule: RMBMappingRule
    registry_id: str = Field(min_length=1)
    provenance: tuple[str, ...] = ("M4_MAPPING_REGISTRY",)

    @property
    def registry_hash(self) -> str:
        return content_hash(self.model_dump(mode="json"))


class ResidualRiskPolicy(FrozenModel):
    """Risk aggregation policy with explicit scientific status."""

    policy_id: str = Field(min_length=1)
    lambda_value: float = Field(default=0.25, ge=0)
    alpha: float = Field(default=0.90, gt=0, lt=1)
    tail_support: TailSupport = TailSupport.UNRESOLVED
    policy_status: RiskPolicyStatus = RiskPolicyStatus.TEST_ONLY
    provenance: tuple[str, ...] = ("RESIDUAL_RISK_POLICY",)
    policy_hash: str | None = None

    @model_validator(mode="after")
    def validate_policy(self):
        expected = content_hash(self.model_dump(mode="json", exclude={"policy_hash"}))
        if self.policy_hash is not None and self.policy_hash != expected:
            raise ValueError("RISK_POLICY_HASH_MISMATCH")
        return self

    @property
    def rule_hash(self) -> str:
        return content_hash(self.model_dump(mode="json", exclude={"policy_hash"}))


class RiskEvaluationStatus(str, Enum):
    EVALUATED = "EVALUATED"
    CONDITIONAL = "CONDITIONAL"
    ABSTAINED = "ABSTAINED"


class RMBScenario(FrozenModel):
    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0, le=1)
    component_values: tuple[float, ...]
    total_rmb: float

    @model_validator(mode="after")
    def validate_values(self):
        if len(self.component_values) != len(CONSEQUENCE_COMPONENTS):
            raise ValueError("RMB_EXACT_SEVEN_COMPONENTS_REQUIRED")
        if any(not math.isfinite(v) or v < 0 for v in self.component_values):
            raise ValueError("RMB_COMPONENT_VALUE_INVALID")
        if not math.isfinite(self.total_rmb) or self.total_rmb < 0:
            raise ValueError("RMB_TOTAL_INVALID")
        if abs(self.total_rmb - sum(self.component_values)) > 1e-9:
            raise ValueError("RMB_TOTAL_COMPONENT_MISMATCH")
        return self


class ResidualRiskEvaluation(FrozenModel):
    status: RiskEvaluationStatus
    action_id: str
    expected_loss: float | None = None
    variance: float | None = None
    value_at_risk: float | None = None
    conditional_value_at_risk: float | None = None
    objective: float | None = None
    scenario_losses: tuple[RMBScenario, ...] = ()
    mapping_status: MappingStatus
    risk_policy_status: RiskPolicyStatus
    tail_support: TailSupport
    ranking_allowed: bool = False
    reason_codes: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ("M4_RESIDUAL_RISK",)

    @model_validator(mode="after")
    def finite_metrics(self):
        for value in (self.expected_loss, self.variance, self.value_at_risk, self.conditional_value_at_risk, self.objective):
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError("RISK_METRIC_INVALID")
        if self.ranking_allowed and self.status is not RiskEvaluationStatus.EVALUATED:
            raise ValueError("RISK_RANKING_REQUIRES_EVALUATED_STATUS")
        return self


def _weighted_quantile(losses: list[tuple[float, float]], alpha: float) -> float:
    cumulative = 0.0
    for loss, weight in sorted(losses):
        cumulative += weight
        if cumulative + 1e-12 >= alpha:
            return loss
    return losses[-1][0]


def _cvar(losses: list[tuple[float, float]], var: float, alpha: float) -> float:
    tail_mass = 1.0 - alpha
    if tail_mass <= 0:
        return var
    remaining = tail_mass
    total = 0.0
    for loss, weight in sorted(losses, reverse=True):
        take = min(weight, remaining)
        total += take * loss
        remaining -= take
        if remaining <= 1e-12:
            break
    return total / tail_mass


def evaluate_residual_risk(
    *,
    materialization: ActionMaterialization,
    mapping: RMBMappingRule | RMBMappingRegistry,
    policy: ResidualRiskPolicy,
) -> ResidualRiskEvaluation:
    """Evaluate scenario-weighted residual risk when all hard rules permit it."""
    mapping_rule = mapping.mapping_rule if isinstance(mapping, RMBMappingRegistry) else mapping
    reasons: list[str] = []
    if mapping_rule.mapping_status is MappingStatus.NOT_FROZEN:
        reasons.append("RMB_MAPPING_NOT_FROZEN")
    if mapping_rule.mapping_status is MappingStatus.TEST_ONLY:
        reasons.append("RMB_MAPPING_TEST_ONLY")
    if policy.policy_status is RiskPolicyStatus.NOT_FROZEN:
        reasons.append("RISK_POLICY_NOT_FROZEN")
    if policy.policy_status is RiskPolicyStatus.TEST_ONLY:
        reasons.append("RISK_POLICY_TEST_ONLY")
    if policy.tail_support is TailSupport.UNRESOLVED:
        reasons.append("POSITIVE_TAIL_UNRESOLVED")
    if materialization.response_support is ResponseSupport.ABSTAIN:
        reasons.append("ACTION_RESPONSE_ABSTAIN")
    if materialization.response_support is ResponseSupport.SCENARIO_ASSUMPTION:
        reasons.append("ACTION_RESPONSE_SCENARIO_ASSUMPTION")

    scenario_losses: list[RMBScenario] = []
    for scenario in materialization.scenarios:
        if abs(sum(item.scenario_weight for item in materialization.scenarios) - 1.0) > 1e-9:
            reasons.append("SCENARIO_WEIGHTS_NOT_NORMALIZED")
            break
        if any(item.support_state is SupportState.ABSTAIN or item.value_cu is None for item in scenario.components):
            reasons.append(f"SCENARIO_{scenario.scenario_id}_CU_ABSTAIN")
            continue
        values = tuple(float(item.value_cu) * mapping_rule.rmb_per_cu for item in scenario.components)
        scenario_losses.append(
            RMBScenario(
                scenario_id=scenario.scenario_id,
                scenario_weight=scenario.scenario_weight,
                component_values=values,
                total_rmb=sum(values),
            )
        )
    if len(scenario_losses) != len(materialization.scenarios):
        return ResidualRiskEvaluation(
            status=RiskEvaluationStatus.ABSTAINED,
            action_id=materialization.action_id,
            mapping_status=mapping_rule.mapping_status,
            risk_policy_status=policy.policy_status,
            tail_support=policy.tail_support,
            reason_codes=tuple(dict.fromkeys(reasons)),
        )

    # A positive-tail estimate is required before VaR/CVaR or the derived
    # residual-risk objective can be treated as numerically evaluable.  Keep
    # the constructed scenario losses available for audit, but abstain from
    # emitting risk statistics while the tail contract is unresolved.
    if policy.tail_support is TailSupport.UNRESOLVED:
        return ResidualRiskEvaluation(
            status=RiskEvaluationStatus.CONDITIONAL,
            action_id=materialization.action_id,
            scenario_losses=tuple(scenario_losses),
            mapping_status=mapping_rule.mapping_status,
            risk_policy_status=policy.policy_status,
            tail_support=policy.tail_support,
            ranking_allowed=False,
            reason_codes=tuple(dict.fromkeys(reasons)),
        )

    weighted = [(item.total_rmb, item.scenario_weight) for item in scenario_losses]
    expected = sum(loss * weight for loss, weight in weighted)
    variance = sum(weight * (loss - expected) ** 2 for loss, weight in weighted)
    var = _weighted_quantile(weighted, policy.alpha)
    cvar = _cvar(weighted, var, policy.alpha)
    objective = expected + policy.lambda_value * cvar
    authoritative = not reasons
    status = RiskEvaluationStatus.EVALUATED if authoritative else RiskEvaluationStatus.CONDITIONAL
    return ResidualRiskEvaluation(
        status=status,
        action_id=materialization.action_id,
        expected_loss=expected,
        variance=variance,
        value_at_risk=var,
        conditional_value_at_risk=cvar,
        objective=objective,
        scenario_losses=tuple(scenario_losses),
        mapping_status=mapping_rule.mapping_status,
        risk_policy_status=policy.policy_status,
        tail_support=policy.tail_support,
        ranking_allowed=authoritative,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


__all__ = [
    "MappingStatus",
    "RMBMappingRegistry",
    "RMBMappingRule",
    "RMBScenario",
    "ResidualRiskEvaluation",
    "ResidualRiskPolicy",
    "RiskEvaluationStatus",
    "RiskPolicyStatus",
    "TailSupport",
    "evaluate_residual_risk",
]
