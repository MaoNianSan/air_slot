"""M4 V2 monetary mapping, weighted residual risk, and labelled ranking.

The evaluator accepts only the M3 action envelope contract plus frozen
scientific configuration. It never reads PRE/M1/M2 operational variables and
never reconstructs an action response.
"""

from __future__ import annotations

from enum import Enum
from math import isfinite

from pydantic import Field, computed_field, model_validator

from model.M3 import EligibilityState, InstantiationState, ResponseSupportClass
from model.M4.m3_action_interface import (
    ConsequenceComparisonScope,
    M4ActionEnvelopeInput,
    OpportunitySupportState,
)
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import SupportState
from model.common.errors import ContractError
from model.common.identity import content_id
from model.common.monetary_system import (
    MonetaryMappingRegistry,
    MonetaryMappingStatus,
)
from model.common.value_objects import FrozenModel
from model.M4.scientific_registry import (
    load_active_risk_policy_payload,
    load_active_rmb_mapping,
)

M1_POSITIVE_TAIL_DECISION_REQUIRED = "M1_POSITIVE_TAIL_DECISION_REQUIRED"


class RiskPolicyStatus(str, Enum):
    FROZEN = "FROZEN"
    TEST_ONLY = "TEST_ONLY"
    NOT_FROZEN = "NOT_FROZEN"


class TailSupportState(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNRESOLVED = "UNRESOLVED"
    FROZEN_ASSUMPTION_GROUNDED = "FROZEN_ASSUMPTION_GROUNDED"


class RiskEvaluationSupport(str, Enum):
    SUPPORTED = "SUPPORTED"
    ASSUMPTION_BASED = "ASSUMPTION_BASED"
    ABSTAINED = "ABSTAINED"


class NumericalComparisonStatus(str, Enum):
    """Interpretation of a numerical comparison, never selection authority."""

    SUPPORTED_INPUTS = "SUPPORTED_INPUTS"
    CONDITIONAL_INPUTS = "CONDITIONAL_INPUTS"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class NumericalEvaluationState(str, Enum):
    """χ_num: completeness of the numerical consequence/risk calculation."""

    DEFINED = "DEFINED"
    UNDEFINED = "UNDEFINED"


class SelectionState(str, Enum):
    """χ_sel: the current model exposes no operational selector."""

    UNIMPLEMENTED = "UNIMPLEMENTED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"


class ResidualRiskPolicy(FrozenModel):
    """Frozen metric definition; parameter values are never implicit."""

    alpha: float = Field(gt=0, lt=1)
    expected_loss_coefficient: float = Field(ge=0, le=1)
    cvar_coefficient: float = Field(ge=0, le=1)
    risk_metric_version: str = Field(min_length=1)
    policy_status: RiskPolicyStatus
    freeze_id: str | None = None
    tail_support_state: TailSupportState
    tail_reference: tuple[str, ...] = Field(min_length=1)
    provenance: tuple[str, ...] = Field(min_length=1)
    policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def create(cls, **values) -> "ResidualRiskPolicy":
        payload = {
            **values,
            "policy_status": (
                values["policy_status"].value
                if isinstance(values["policy_status"], RiskPolicyStatus)
                else values["policy_status"]
            ),
            "tail_support_state": (
                values["tail_support_state"].value
                if isinstance(values["tail_support_state"], TailSupportState)
                else values["tail_support_state"]
            ),
        }
        return cls(**payload, policy_hash=content_id(payload))

    @model_validator(mode="after")
    def frozen_metric(self):
        if abs(self.expected_loss_coefficient + self.cvar_coefficient - 1.0) > 1e-12:
            raise ValueError("M4_RISK_COEFFICIENTS_MUST_SUM_TO_ONE")
        if self.policy_status in {RiskPolicyStatus.FROZEN, RiskPolicyStatus.TEST_ONLY}:
            if not self.freeze_id:
                raise ValueError("M4_EXECUTABLE_RISK_POLICY_REQUIRES_FREEZE_ID")
        elif self.freeze_id is not None:
            raise ValueError("M4_UNFROZEN_RISK_POLICY_CANNOT_HAVE_FREEZE_ID")
        payload = self.model_dump(mode="json", exclude={"policy_hash"})
        if self.policy_hash != content_id(payload):
            raise ValueError("M4_RISK_POLICY_HASH_MISMATCH")
        return self


def load_active_risk_policy() -> ResidualRiskPolicy:
    """Materialize the unique frozen BASE policy from the model registry."""
    payload = load_active_risk_policy_payload()
    return ResidualRiskPolicy.create(
        alpha=float(payload["alpha"]),
        expected_loss_coefficient=float(payload["expected_loss_weight"]),
        cvar_coefficient=float(payload["cvar_weight"]),
        risk_metric_version=f'{payload["policy_id"]}@{payload["version"]}',
        policy_status=RiskPolicyStatus.FROZEN,
        freeze_id=payload["freeze_id"],
        tail_support_state=TailSupportState(payload["tail_support_state"]),
        tail_reference=("M1_EXPLICIT_OVERFLOW_TAIL_CONTRACT",),
        provenance=tuple(payload["provenance"]),
    )


class ComponentMonetaryLoss(FrozenModel):
    component_id: str
    C_a_CU: float | None
    cu_support_state: SupportState
    L_k_m: float | None
    mapping_rule_id: str | None
    mapping_rule_hash: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    baseline_cu_artifact_id: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    baseline_reference_lineage_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reason_code: str | None = None

    @model_validator(mode="after")
    def loss_support(self):
        mapped = self.mapping_rule_id is not None
        if mapped != (self.mapping_rule_hash is not None):
            raise ValueError("M4_MAPPING_RULE_LINEAGE_INCOMPLETE")
        if self.L_k_m is None and not self.reason_code:
            raise ValueError("M4_NULL_COMPONENT_LOSS_REQUIRES_REASON")
        if self.L_k_m is not None and (
            self.C_a_CU is None
            or self.cu_support_state is SupportState.ABSTAIN
            or not mapped
        ):
            raise ValueError("M4_COMPONENT_LOSS_WITHOUT_SUPPORTED_CU_MAPPING")
        return self


class ScenarioMonetaryLoss(FrozenModel):
    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0, le=1)
    component_losses: tuple[ComponentMonetaryLoss, ...]
    comparison_component_ids: tuple[str, ...] = ()
    total_loss_m: float | None
    loss_artifact_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reason_code: str | None = None

    @model_validator(mode="after")
    def exact_loss_vector(self):
        if (
            tuple(item.component_id for item in self.component_losses)
            != CONSEQUENCE_COMPONENTS
        ):
            raise ValueError("M4_LOSS_REQUIRES_EXACT_SEVEN_COMPONENTS")
        if not set(self.comparison_component_ids) <= set(CONSEQUENCE_COMPONENTS):
            raise ValueError("M4_LOSS_SCOPE_UNKNOWN_COMPONENT")
        by_id = {item.component_id: item for item in self.component_losses}
        values = tuple(by_id[item].L_k_m for item in self.comparison_component_ids)
        if self.total_loss_m is None:
            if not self.reason_code:
                raise ValueError("M4_NULL_SCENARIO_LOSS_REQUIRES_REASON")
        elif (
            any(value is None for value in values)
            or abs(self.total_loss_m - sum(values)) > 1e-9
        ):
            raise ValueError("M4_SCENARIO_TOTAL_LOSS_MISMATCH")
        payload = self.model_dump(mode="json", exclude={"loss_artifact_id"})
        if self.loss_artifact_id != content_id(payload):
            raise ValueError("M4_LOSS_ARTIFACT_ID_MISMATCH")
        return self


class RiskEvaluationEnvelope(FrozenModel):
    episode_id: str
    decision_node_id: str
    action_id: str
    instantiation_state: InstantiationState
    eligibility_state: EligibilityState
    opportunity_state: OpportunitySupportState
    m3_envelope_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    monetary_system_id: str
    monetary_mapping_registry_id: str
    monetary_mapping_registry_version: str
    monetary_mapping_registry_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    risk_metric_version: str
    risk_policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    alpha: float = Field(gt=0, lt=1)
    response_support: ResponseSupportClass
    response_provenance: tuple[str, ...] = Field(min_length=1)
    reference_lineage_hashes: tuple[str, ...] = Field(min_length=1)
    scenario_ids: tuple[int, ...] = Field(min_length=1)
    scenario_weights: tuple[float, ...] = Field(min_length=1)
    scenario_losses: tuple[ScenarioMonetaryLoss, ...] = Field(min_length=1)
    comparison_scope_id: str | None = None
    comparison_scope_version: str | None = None
    comparison_scope_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    comparison_measurement_registry_id: str | None = None
    comparison_component_ids: tuple[str, ...] = ()
    coverage_components: tuple[str, ...]
    coverage_fraction: float = Field(ge=0, le=1)
    expected_monetary_loss: float | None
    monetary_loss_variance: float | None
    monetary_loss_var_alpha: float | None
    monetary_loss_cvar_alpha: float | None
    residual_risk_objective: float | None
    numerical_state: NumericalEvaluationState
    support_state: RiskEvaluationSupport
    comparison_status: NumericalComparisonStatus
    selection_state: SelectionState = SelectionState.UNIMPLEMENTED
    reason_codes: tuple[str, ...]

    @model_validator(mode="after")
    def coherent_risk_envelope(self):
        if (
            tuple(item.scenario_id for item in self.scenario_losses)
            != self.scenario_ids
        ):
            raise ValueError("M4_RISK_SCENARIO_ID_MISMATCH")
        if (
            tuple(item.scenario_weight for item in self.scenario_losses)
            != self.scenario_weights
        ):
            raise ValueError("M4_RISK_SCENARIO_WEIGHT_MISMATCH")
        if len(self.reference_lineage_hashes) != len(self.scenario_ids) * len(
            CONSEQUENCE_COMPONENTS
        ):
            raise ValueError("M4_RISK_REFERENCE_LINEAGE_COUNT_MISMATCH")
        if len(self.coverage_components) != len(
            set(self.coverage_components)
        ) or not set(self.coverage_components) <= set(CONSEQUENCE_COMPONENTS):
            raise ValueError("M4_RISK_COVERAGE_COMPONENTS_INVALID")
        denominator = len(self.comparison_component_ids)
        expected_fraction = len(self.coverage_components) / denominator if denominator else 0.0
        if abs(self.coverage_fraction - expected_fraction) > 1e-12:
            raise ValueError("M4_RISK_COVERAGE_FRACTION_MISMATCH")
        if self.comparison_scope_id is None and (
            self.comparison_scope_version is not None
            or self.comparison_scope_hash is not None
            or self.comparison_measurement_registry_id is not None
            or self.comparison_component_ids
        ):
            raise ValueError("M4_COMPARISON_SCOPE_METADATA_INCOMPLETE")
        if self.comparison_scope_id is not None and (
            not self.comparison_scope_version
            or not self.comparison_scope_hash
            or not self.comparison_measurement_registry_id
            or not self.comparison_component_ids
        ):
            raise ValueError("M4_COMPARISON_SCOPE_METADATA_INCOMPLETE")
        metrics = (
            self.expected_monetary_loss,
            self.monetary_loss_variance,
            self.monetary_loss_var_alpha,
            self.monetary_loss_cvar_alpha,
            self.residual_risk_objective,
        )
        if any(value is not None and not isfinite(value) for value in metrics):
            raise ValueError("M4_RISK_METRIC_NONFINITE")
        if self.numerical_state is NumericalEvaluationState.UNDEFINED:
            if any(value is not None for value in metrics):
                raise ValueError("M4_UNDEFINED_NUMERICAL_STATE_CANNOT_HAVE_METRICS")
            if self.comparison_status is not NumericalComparisonStatus.NOT_COMPARABLE:
                raise ValueError("M4_UNDEFINED_NUMERICAL_STATE_CANNOT_BE_RANKED")
            if self.support_state is not RiskEvaluationSupport.ABSTAINED:
                raise ValueError("M4_UNDEFINED_NUMERICAL_STATE_REQUIRES_ABSTAIN")
        else:
            if any(value is None for value in metrics):
                raise ValueError("M4_DEFINED_NUMERICAL_STATE_REQUIRES_ALL_METRICS")
            if self.coverage_fraction != 1.0:
                raise ValueError("M4_DEFINED_NUMERICAL_STATE_REQUIRES_SCOPE_MAPPING_COVERAGE")
            if self.support_state is RiskEvaluationSupport.ABSTAINED:
                raise ValueError("M4_DEFINED_NUMERICAL_STATE_CANNOT_ABSTAIN")
        if (
            self.support_state is RiskEvaluationSupport.SUPPORTED
            and self.comparison_status
            is not NumericalComparisonStatus.SUPPORTED_INPUTS
        ) or (
            self.support_state is RiskEvaluationSupport.ASSUMPTION_BASED
            and self.comparison_status
            is not NumericalComparisonStatus.CONDITIONAL_INPUTS
        ):
            raise ValueError("M4_RISK_SUPPORT_COMPARISON_STATUS_MISMATCH")
        if self.selection_state is not SelectionState.UNIMPLEMENTED:
            raise ValueError("M4_SELECTION_STATE_UNIMPLEMENTED_REQUIRED")
        return self

    @computed_field
    @property
    def risk_envelope_hash(self) -> str:
        return content_id(self.model_dump(mode="json", exclude={"risk_envelope_hash"}))


class RiskRankingEntry(FrozenModel):
    action_id: str
    instantiation_state: InstantiationState
    eligibility_state: EligibilityState
    opportunity_state: OpportunitySupportState
    response_support: ResponseSupportClass
    expected_risk: float
    tail_risk: float
    residual_risk: float
    support_state: RiskEvaluationSupport
    coverage_fraction: float
    numerical_state: NumericalEvaluationState
    comparison_status: NumericalComparisonStatus
    comparison_scope_id: str | None = None
    comparison_measurement_registry_id: str | None = None
    comparison_component_ids: tuple[str, ...] = ()
    selection_state: SelectionState = SelectionState.UNIMPLEMENTED
    ranking_position: int = Field(ge=1)
    risk_envelope_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class PairedA00Diagnostic(FrozenModel):
    action_id: str
    a00_action_id: str = "A00"
    action_residual_risk: float
    a00_residual_risk: float
    delta_vs_a00: float


class RiskRankingEnvelope(FrozenModel):
    episode_id: str
    decision_node_id: str
    scenario_ids: tuple[int, ...]
    scenario_weights: tuple[float, ...]
    monetary_system_id: str
    monetary_mapping_registry_hash: str
    risk_policy_hash: str
    comparison_scope_id: str | None = None
    comparison_scope_version: str | None = None
    comparison_scope_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    comparison_measurement_registry_id: str | None = None
    comparison_component_ids: tuple[str, ...] = ()
    supported_input_ranking: tuple[RiskRankingEntry, ...]
    conditional_input_ranking: tuple[RiskRankingEntry, ...]
    not_comparable_action_ids: tuple[str, ...]
    paired_a00_diagnostics: tuple[PairedA00Diagnostic, ...] = ()

    @computed_field
    @property
    def ranking_hash(self) -> str:
        return content_id(self.model_dump(mode="json", exclude={"ranking_hash"}))


def _validated_distribution(
    values: tuple[float, ...], weights: tuple[float, ...]
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    if not values or len(values) != len(weights):
        raise ValueError("M4_WEIGHTED_DISTRIBUTION_LENGTH_MISMATCH")
    if any(not isfinite(value) for value in values) or any(
        not isfinite(weight) or weight <= 0 for weight in weights
    ):
        raise ValueError("M4_WEIGHTED_DISTRIBUTION_INVALID")
    total = sum(weights)
    if abs(total - 1.0) > 1e-6:
        raise ValueError("M4_SCENARIO_WEIGHTS_MUST_SUM_TO_ONE")
    return values, tuple(weight / total for weight in weights)


def weighted_expectation(
    values: tuple[float, ...], weights: tuple[float, ...]
) -> float:
    values, weights = _validated_distribution(values, weights)
    return sum(value * weight for value, weight in zip(values, weights, strict=True))


def weighted_variance(values: tuple[float, ...], weights: tuple[float, ...]) -> float:
    values, weights = _validated_distribution(values, weights)
    mean = weighted_expectation(values, weights)
    return sum(
        weight * (value - mean) ** 2
        for value, weight in zip(values, weights, strict=True)
    )


def weighted_var_cvar(
    values: tuple[float, ...], weights: tuple[float, ...], alpha: float
) -> tuple[float, float]:
    """Upper-loss VaR/CVaR with fractional mass at the quantile boundary.

    Weights are normalized after validation. VaR is the first loss whose
    cumulative mass reaches alpha. CVaR is the greatest-loss mass totaling
    exactly `1-alpha`, including a fractional boundary scenario if required.
    """
    if not 0 < alpha < 1:
        raise ValueError("M4_CVAR_ALPHA_OUT_OF_RANGE")
    values, weights = _validated_distribution(values, weights)
    pairs = sorted(zip(values, weights, strict=True))
    cumulative = 0.0
    var = pairs[-1][0]
    for value, weight in pairs:
        cumulative += weight
        if cumulative + 1e-12 >= alpha:
            var = value
            break
    tail_mass = 1.0 - alpha
    remaining = tail_mass
    weighted_tail = 0.0
    for value, weight in reversed(pairs):
        take = min(weight, remaining)
        weighted_tail += value * take
        remaining -= take
        if remaining <= 1e-12:
            break
    if remaining > 1e-9:
        raise ValueError("M4_CVAR_TAIL_MASS_UNAVAILABLE")
    return var, weighted_tail / tail_mass


def _abstained_scenario_loss(
    scenario, reason: str, *, comparison_component_ids: tuple[str, ...] = ()
) -> ScenarioMonetaryLoss:
    components = tuple(
        ComponentMonetaryLoss(
            component_id=item.component_id,
            C_a_CU=item.C_a_CU,
            cu_support_state=item.support_state,
            L_k_m=None,
            mapping_rule_id=None,
            mapping_rule_hash=None,
            baseline_cu_artifact_id=item.baseline_cu_artifact_id,
            baseline_reference_lineage_hash=item.baseline_reference_lineage_hash,
            reason_code=reason,
        )
        for item in scenario.components
    )
    payload = {
        "scenario_id": scenario.scenario_id,
        "scenario_weight": scenario.scenario_weight,
        "component_losses": components,
        "comparison_component_ids": comparison_component_ids,
        "total_loss_m": None,
        "reason_code": reason,
    }
    return ScenarioMonetaryLoss(**payload, loss_artifact_id=content_id(payload))


def evaluate_residual_risk(
    envelope: M4ActionEnvelopeInput,
    *,
    monetary_mapping: MonetaryMappingRegistry | None = None,
    risk_policy: ResidualRiskPolicy | None = None,
) -> RiskEvaluationEnvelope:
    """Map `C^{a,CU}` to `L^{a,m}` and aggregate weighted residual risk."""
    if not isinstance(envelope, M4ActionEnvelopeInput):
        raise TypeError("M4_V2_REQUIRES_ACTION_EVALUATION_ENVELOPE")
    if monetary_mapping is None:
        monetary_mapping = load_active_rmb_mapping()
    if risk_policy is None:
        risk_policy = load_active_risk_policy()
    if not isinstance(monetary_mapping, MonetaryMappingRegistry):
        raise TypeError("M4_V2_REQUIRES_MONETARY_MAPPING_REGISTRY")
    if not isinstance(risk_policy, ResidualRiskPolicy):
        raise TypeError("M4_V2_REQUIRES_RESIDUAL_RISK_POLICY")
    if risk_policy.policy_status is RiskPolicyStatus.NOT_FROZEN:
        raise ContractError("M4_RISK_POLICY_NOT_FROZEN")
    if risk_policy.tail_support_state is TailSupportState.UNRESOLVED:
        raise ContractError(M1_POSITIVE_TAIL_DECISION_REQUIRED)

    mapping_hash = monetary_mapping.registry_hash or monetary_mapping.digest()
    reference_hashes = tuple(
        component.baseline_reference_lineage_hash
        for scenario in envelope.scenario_consequences
        for component in scenario.components
    )
    reasons = []
    qualification_reasons = []
    if envelope.eligibility_state is EligibilityState.UNKNOWN:
        qualification_reasons.extend(
            ["FACTUAL_ELIGIBILITY_UNKNOWN", "NOT_OPERATIONALLY_SUPPORTED"]
        )
    elif envelope.eligibility_state is EligibilityState.INELIGIBLE:
        qualification_reasons.extend(
            ["M3_ACTION_INELIGIBLE", "NOT_OPERATIONALLY_SUPPORTED"]
        )
    scope = envelope.comparison_scope
    scope_declared = isinstance(scope, ConsequenceComparisonScope)
    scope_ready = scope_declared and scope.frozen
    comparison_components = tuple(scope.component_ids) if scope_declared else ()
    if not scope_ready:
        reasons.append("COMPARISON_SCOPE_NOT_FROZEN")
    elif scope.valuation_measurement_registry_id != monetary_mapping.registry_id:
        reasons.append("COMPARISON_SCOPE_MEASUREMENT_REGISTRY_MISMATCH")
    complete_mapping = scope_ready and set(comparison_components) <= set(
        monetary_mapping.component_mappings
    )
    all_cu_supported = all(
        component.support_state is not SupportState.ABSTAIN
        and component.C_a_CU is not None
        for scenario in envelope.scenario_consequences
        for component in scenario.components
        if component.component_id in comparison_components
    )
    all_cu_finite = all(
        component.C_a_CU is not None and isfinite(float(component.C_a_CU))
        for scenario in envelope.scenario_consequences
        for component in scenario.components
        if component.component_id in comparison_components
    )
    mapping_executable = monetary_mapping.frozen
    if scope_ready and not complete_mapping:
        reasons.append("MONETARY_MAPPING_COMPONENT_COVERAGE_INCOMPLETE")
    if not all_cu_supported:
        reasons.append("ACTION_CONSEQUENCE_COMPONENT_ABSTAIN")
    if not all_cu_finite:
        reasons.append("ACTION_CONSEQUENCE_NONFINITE")
    if not mapping_executable:
        reasons.append("MONETARY_MAPPING_NOT_FROZEN")
    # χ_num is deliberately independent of χ_fact, χ_resp, χ_opp, and χ_sel.
    # A normal M3 ABSTAIN response produces ABSTAIN consequence components, but
    # M4 does not use the response evidence label itself as a numerical gate.
    can_map = (
        complete_mapping
        and all_cu_supported
        and all_cu_finite
        and mapping_executable
        and scope.valuation_measurement_registry_id == monetary_mapping.registry_id
        and not reasons
    )
    scenario_losses = []
    if can_map:
        for scenario in envelope.scenario_consequences:
            components = []
            for item in scenario.components:
                if item.component_id not in comparison_components:
                    components.append(
                        ComponentMonetaryLoss(
                            component_id=item.component_id,
                            C_a_CU=item.C_a_CU,
                            cu_support_state=item.support_state,
                            L_k_m=None,
                            mapping_rule_id=None,
                            mapping_rule_hash=None,
                            baseline_cu_artifact_id=item.baseline_cu_artifact_id,
                            baseline_reference_lineage_hash=item.baseline_reference_lineage_hash,
                            reason_code="OUT_OF_COMPARISON_SCOPE",
                        )
                    )
                    continue
                rule = monetary_mapping.component_mappings[item.component_id]
                loss = rule.map_cu(item.C_a_CU)
                if not isfinite(loss):
                    reasons.append("MONETARY_MAPPING_NONFINITE")
                    can_map = False
                    break
                components.append(
                    ComponentMonetaryLoss(
                        component_id=item.component_id,
                        C_a_CU=item.C_a_CU,
                        cu_support_state=item.support_state,
                        L_k_m=loss,
                        mapping_rule_id=rule.rule_id,
                        mapping_rule_hash=rule.rule_hash,
                        baseline_cu_artifact_id=item.baseline_cu_artifact_id,
                        baseline_reference_lineage_hash=item.baseline_reference_lineage_hash,
                    )
                )
            if not can_map:
                break
            total = sum(
                item.L_k_m
                for item in components
                if item.component_id in comparison_components
            )
            if not isfinite(total):
                reasons.append("M4_SCENARIO_LOSS_NONFINITE")
                can_map = False
                break
            payload = {
                "scenario_id": scenario.scenario_id,
                "scenario_weight": scenario.scenario_weight,
                "component_losses": tuple(components),
                "comparison_component_ids": comparison_components,
                "total_loss_m": total,
                "reason_code": None,
            }
            scenario_losses.append(
                ScenarioMonetaryLoss(**payload, loss_artifact_id=content_id(payload))
            )
    if not can_map:
        reason = ";".join(sorted(set(reasons)))
        scenario_losses = [
            _abstained_scenario_loss(
                scenario,
                reason,
                comparison_component_ids=comparison_components,
            )
            for scenario in envelope.scenario_consequences
        ]

    if can_map:
        totals = tuple(item.total_loss_m for item in scenario_losses)
        weights = envelope.scenario_weights
        expected = weighted_expectation(totals, weights)
        variance = weighted_variance(totals, weights)
        var, cvar = weighted_var_cvar(totals, weights, risk_policy.alpha)
        objective = (
            risk_policy.expected_loss_coefficient * expected
            + risk_policy.cvar_coefficient * cvar
        )
        operational_support = (
            envelope.eligibility_state is EligibilityState.ELIGIBLE
            and envelope.response_support is ResponseSupportClass.SUPPORTED
            and monetary_mapping.authoritative
            and risk_policy.policy_status is RiskPolicyStatus.FROZEN
            and envelope.opportunity_state
            in {
                OpportunitySupportState.AVAILABLE,
                OpportunitySupportState.NOT_REQUIRED,
            }
        )
        if operational_support:
            support = RiskEvaluationSupport.SUPPORTED
            authority = NumericalComparisonStatus.SUPPORTED_INPUTS
        else:
            support = RiskEvaluationSupport.ASSUMPTION_BASED
            authority = NumericalComparisonStatus.CONDITIONAL_INPUTS
            qualification_reasons.append("NOT_OPERATIONALLY_SUPPORTED")
            if envelope.response_support is not ResponseSupportClass.SUPPORTED or not monetary_mapping.authoritative:
                qualification_reasons.append("NON_AUTHORITATIVE_INPUT_OR_POLICY")
            if envelope.opportunity_state not in {
                OpportunitySupportState.AVAILABLE,
                OpportunitySupportState.NOT_REQUIRED,
            }:
                qualification_reasons.append("OPPORTUNITY_SUPPORT_NOT_CONFIRMED")
    else:
        expected = variance = var = cvar = objective = None
        support = RiskEvaluationSupport.ABSTAINED
        authority = NumericalComparisonStatus.NOT_COMPARABLE

    return RiskEvaluationEnvelope(
        episode_id=envelope.episode_id,
        decision_node_id=envelope.decision_node_id,
        action_id=envelope.action_id,
        instantiation_state=envelope.instantiation_state,
        eligibility_state=envelope.eligibility_state,
        opportunity_state=envelope.opportunity_state,
        m3_envelope_hash=envelope.m3_envelope_hash,
        monetary_system_id=monetary_mapping.monetary_system_id,
        monetary_mapping_registry_id=monetary_mapping.registry_id,
        monetary_mapping_registry_version=monetary_mapping.registry_version,
        monetary_mapping_registry_hash=mapping_hash,
        risk_metric_version=risk_policy.risk_metric_version,
        risk_policy_hash=risk_policy.policy_hash,
        alpha=risk_policy.alpha,
        response_support=envelope.response_support,
        response_provenance=envelope.response_provenance,
        reference_lineage_hashes=reference_hashes,
        scenario_ids=envelope.scenario_ids,
        scenario_weights=envelope.scenario_weights,
        scenario_losses=tuple(scenario_losses),
        comparison_scope_id=scope.scope_id if scope_declared else None,
        comparison_scope_version=scope.version if scope_declared else None,
        comparison_scope_hash=scope.scope_hash if scope_declared else None,
        comparison_measurement_registry_id=(
            scope.valuation_measurement_registry_id if scope_declared else None
        ),
        comparison_component_ids=comparison_components,
        coverage_components=tuple(
            component
            for component in comparison_components
            if component in monetary_mapping.component_mappings
        ),
        coverage_fraction=(
            len(set(monetary_mapping.component_mappings) & set(comparison_components))
            / len(comparison_components)
            if comparison_components
            else 0.0
        ),
        expected_monetary_loss=expected,
        monetary_loss_variance=variance,
        monetary_loss_var_alpha=var,
        monetary_loss_cvar_alpha=cvar,
        residual_risk_objective=objective,
        numerical_state=(
            NumericalEvaluationState.DEFINED
            if can_map
            else NumericalEvaluationState.UNDEFINED
        ),
        support_state=support,
        comparison_status=authority,
        reason_codes=tuple(sorted(set(reasons + qualification_reasons))),
    )


def rank_risk_evaluations(
    evaluations: tuple[RiskEvaluationEnvelope, ...],
) -> RiskRankingEnvelope:
    if not evaluations:
        raise ValueError("M4_RANKING_REQUIRES_EVALUATIONS")
    identities = {
        (
            item.episode_id,
            item.decision_node_id,
            item.scenario_ids,
            item.scenario_weights,
            item.monetary_system_id,
            item.monetary_mapping_registry_hash,
            item.risk_policy_hash,
            item.comparison_scope_id,
            item.comparison_scope_version,
            item.comparison_scope_hash,
            item.comparison_measurement_registry_id,
            item.comparison_component_ids,
        )
        for item in evaluations
    }
    if len(identities) != 1:
        raise ValueError("M4_RANKING_COMMON_BASIS_MISMATCH")
    action_ids = tuple(item.action_id for item in evaluations)
    if len(action_ids) != len(set(action_ids)):
        raise ValueError("M4_RANKING_DUPLICATE_ACTION")

    def ranked(status: NumericalComparisonStatus) -> tuple[RiskRankingEntry, ...]:
        rows = sorted(
            (item for item in evaluations if item.comparison_status is status),
            key=lambda item: (item.residual_risk_objective, item.action_id),
        )
        return tuple(
            RiskRankingEntry(
                action_id=item.action_id,
                instantiation_state=item.instantiation_state,
                eligibility_state=item.eligibility_state,
                opportunity_state=item.opportunity_state,
                response_support=item.response_support,
                expected_risk=item.expected_monetary_loss,
                tail_risk=item.monetary_loss_cvar_alpha,
                residual_risk=item.residual_risk_objective,
                support_state=item.support_state,
                coverage_fraction=item.coverage_fraction,
                numerical_state=item.numerical_state,
                comparison_status=status,
                comparison_scope_id=item.comparison_scope_id,
                comparison_measurement_registry_id=item.comparison_measurement_registry_id,
                comparison_component_ids=item.comparison_component_ids,
                selection_state=item.selection_state,
                ranking_position=index,
                risk_envelope_hash=item.risk_envelope_hash,
            )
            for index, item in enumerate(rows, start=1)
        )

    (
        episode_id,
        decision_node_id,
        scenario_ids,
        scenario_weights,
        system,
        mapping_hash,
        policy_hash,
        scope_id,
        scope_version,
        scope_hash,
        measurement_registry_id,
        scope_components,
    ) = next(iter(identities))
    return RiskRankingEnvelope(
        episode_id=episode_id,
        decision_node_id=decision_node_id,
        scenario_ids=scenario_ids,
        scenario_weights=scenario_weights,
        monetary_system_id=system,
        monetary_mapping_registry_hash=mapping_hash,
        risk_policy_hash=policy_hash,
        comparison_scope_id=scope_id,
        comparison_scope_version=scope_version,
        comparison_scope_hash=scope_hash,
        comparison_measurement_registry_id=measurement_registry_id,
        comparison_component_ids=scope_components,
        supported_input_ranking=ranked(NumericalComparisonStatus.SUPPORTED_INPUTS),
        conditional_input_ranking=ranked(
            NumericalComparisonStatus.CONDITIONAL_INPUTS
        ),
        not_comparable_action_ids=tuple(
            sorted(
                item.action_id
                for item in evaluations
                if item.comparison_status
                is NumericalComparisonStatus.NOT_COMPARABLE
            )
        ),
    )


__all__ = [
    "ComponentMonetaryLoss",
    "M1_POSITIVE_TAIL_DECISION_REQUIRED",
    "NumericalComparisonStatus",
    "ResidualRiskPolicy",
    "load_active_risk_policy",
    "RiskEvaluationEnvelope",
    "RiskEvaluationSupport",
    "RiskPolicyStatus",
    "RiskRankingEnvelope",
    "RiskRankingEntry",
    "ScenarioMonetaryLoss",
    "TailSupportState",
    "evaluate_residual_risk",
    "rank_risk_evaluations",
    "weighted_expectation",
    "weighted_var_cvar",
    "weighted_variance",
]
