"""M3 V2 action-response contracts and conditional scenario materialization.

Non-A00 responses are materialized only as explicit, versioned scenario
assumptions. They are not observed intervention effects or causal estimates.
"""

from __future__ import annotations

from enum import Enum
from collections.abc import Mapping
from math import isfinite
from typing import Any

from pydantic import Field, computed_field, model_validator

from model.M3.m2_action_interface import (
    ActionConditionedCUQuantity,
    M3ActionConditionedConsequence,
    M3BaselineConsequenceInput,
)
from model.M3.contracts import InstantiationState
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import SupportState
from model.common.errors import ContractError
from model.common.identity import content_id
from model.common.value_objects import FrozenModel
from model.M3.response import action_post_consequences, response_draw


class EligibilityState(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"


class ResponseSupportClass(str, Enum):
    SUPPORTED = "SUPPORTED"
    REFERENCE_BASED = "REFERENCE_BASED"
    SCENARIO_ASSUMPTION = "SCENARIO_ASSUMPTION"
    ABSTAIN = "ABSTAIN"


class ResponseSourceType(str, Enum):
    LITERATURE = "LITERATURE"
    OPERATIONAL_RULE = "OPERATIONAL_RULE"
    SCENARIO_ASSUMPTION = "SCENARIO_ASSUMPTION"
    EXPERT_JUDGEMENT = "EXPERT_JUDGEMENT"
    HYBRID = "HYBRID"


class ActionResponseType(str, Enum):
    IDENTITY = "IDENTITY"
    DIRECT_REDUCTION = "DIRECT_REDUCTION"
    RESOURCE_SUBSTITUTION = "RESOURCE_SUBSTITUTION"
    SEQUENCE_MODIFICATION = "SEQUENCE_MODIFICATION"
    PASSENGER_SERVICE_PROTECTION = "PASSENGER_SERVICE_PROTECTION"
    ABSTAIN = "ABSTAIN"


class ActionEligibility(FrozenModel):
    """`I(a)`: state/fact eligibility only, with no response parameters."""

    action_id: str = Field(min_length=1)
    action_family: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    state: EligibilityState
    eligibility_conditions: tuple[str, ...]
    fact_reference_ids: tuple[str, ...]
    provenance: tuple[str, ...] = Field(min_length=1)
    eligibility_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def create(
        cls,
        *,
        action_id: str,
        action_family: str,
        decision_node_id: str,
        state: EligibilityState,
        eligibility_conditions: tuple[str, ...],
        fact_reference_ids: tuple[str, ...],
        provenance: tuple[str, ...],
    ) -> "ActionEligibility":
        payload = {
            "action_id": action_id,
            "action_family": action_family,
            "decision_node_id": decision_node_id,
            "state": state.value,
            "eligibility_conditions": eligibility_conditions,
            "fact_reference_ids": fact_reference_ids,
            "provenance": provenance,
        }
        return cls(**payload, eligibility_id=content_id(payload))

    @model_validator(mode="after")
    def identity_matches(self):
        payload = self.model_dump(mode="json", exclude={"eligibility_id"})
        if self.eligibility_id != content_id(payload):
            raise ValueError("M3_ELIGIBILITY_ID_MISMATCH")
        return self


class ResponseParameter(FrozenModel):
    """Optional named parameter; anonymous gamma/weight is prohibited."""

    parameter_name: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    parameter_version: str = Field(min_length=1)
    freeze_id: str = Field(min_length=1)


class ActionResponseRule(FrozenModel):
    """`P(a)`: response mechanism and scientific support, never eligibility."""

    response_rule_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    action_family: str = Field(min_length=1)
    affected_components: tuple[str, ...]
    response_types: tuple[ActionResponseType, ...] = Field(min_length=1)
    response_rule: str = Field(min_length=1)
    parameter_source: ResponseSourceType
    support_state: ResponseSupportClass
    source_references: tuple[str, ...] = Field(min_length=1)
    parameter_version: str = Field(min_length=1)
    freeze_id: str = Field(min_length=1)
    parameters: tuple[ResponseParameter, ...] = ()
    provenance: tuple[str, ...] = Field(min_length=1)
    rule_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def create(cls, **values: Any) -> "ActionResponseRule":
        payload = {
            **values,
            "response_types": tuple(
                item.value if isinstance(item, ActionResponseType) else item
                for item in values["response_types"]
            ),
            "parameter_source": (
                values["parameter_source"].value
                if isinstance(values["parameter_source"], ResponseSourceType)
                else values["parameter_source"]
            ),
            "support_state": (
                values["support_state"].value
                if isinstance(values["support_state"], ResponseSupportClass)
                else values["support_state"]
            ),
        }
        return cls(**payload, rule_hash=content_id(payload))

    @model_validator(mode="after")
    def explicit_response_support(self):
        if len(self.affected_components) != len(set(self.affected_components)):
            raise ValueError("M3_RESPONSE_DUPLICATE_AFFECTED_COMPONENT")
        if not set(self.affected_components) <= set(CONSEQUENCE_COMPONENTS):
            raise ValueError("M3_RESPONSE_UNKNOWN_AFFECTED_COMPONENT")
        if self.action_id == "A00":
            if self.affected_components or self.response_types != (
                ActionResponseType.IDENTITY,
            ):
                raise ValueError("M3_A00_RESPONSE_MUST_BE_IDENTITY_ONLY")
        if self.support_state is ResponseSupportClass.ABSTAIN and (
            self.response_types != (ActionResponseType.ABSTAIN,) or self.parameters
        ):
            raise ValueError("M3_ABSTAIN_RESPONSE_CANNOT_HAVE_EFFECT_PARAMETERS")
        if (
            self.support_state is ResponseSupportClass.SCENARIO_ASSUMPTION
            and self.parameter_source is not ResponseSourceType.SCENARIO_ASSUMPTION
        ):
            raise ValueError("M3_SCENARIO_RESPONSE_SOURCE_MISMATCH")
        if (
            self.support_state is ResponseSupportClass.SUPPORTED
            and self.parameter_source
            in {
                ResponseSourceType.SCENARIO_ASSUMPTION,
                ResponseSourceType.EXPERT_JUDGEMENT,
            }
        ):
            raise ValueError("M3_SCENARIO_OR_EXPERT_RESPONSE_NOT_SUPPORTED")
        payload = self.model_dump(mode="json", exclude={"rule_hash"})
        if self.rule_hash != content_id(payload):
            raise ValueError("M3_RESPONSE_RULE_HASH_MISMATCH")
        return self


class ActionEvaluationEnvelope(FrozenModel):
    """M3 output consumed later by M4; CU/support/provenance only, no money."""

    action_id: str = Field(min_length=1)
    action_family: str = Field(min_length=1)
    instantiation_state: InstantiationState = InstantiationState.FORMED
    eligibility: ActionEligibility
    response_rule: ActionResponseRule
    input_scenario_ids: tuple[int, ...]
    input_scenario_weights: tuple[float, ...]
    scenario_evaluations: tuple[M3ActionConditionedConsequence, ...] = Field(
        min_length=1
    )

    @model_validator(mode="after")
    def scenario_and_contract_identity(self):
        if self.instantiation_state is not InstantiationState.FORMED:
            raise ValueError("M3_NONINSTANTIATED_ACTION_CANNOT_HAVE_CONSEQUENCE_ENVELOPE")
        if not (
            self.action_id == self.eligibility.action_id == self.response_rule.action_id
        ) or not (
            self.action_family
            == self.eligibility.action_family
            == self.response_rule.action_family
        ):
            raise ValueError("M3_ACTION_ELIGIBILITY_RESPONSE_IDENTITY_MISMATCH")
        output_ids = tuple(item.scenario_id for item in self.scenario_evaluations)
        output_weights = tuple(
            item.scenario_weight for item in self.scenario_evaluations
        )
        if (
            output_ids != self.input_scenario_ids
            or output_weights != self.input_scenario_weights
        ):
            raise ValueError("M3_SCENARIO_DISTRIBUTION_NOT_PRESERVED")
        if len(output_ids) != len(set(output_ids)):
            raise ValueError("M3_DUPLICATE_SCENARIO_ID")
        if abs(sum(output_weights) - 1.0) > 1e-6:
            raise ValueError("M3_SCENARIO_WEIGHTS_MUST_SUM_TO_ONE")
        if any(
            item.action_id != self.action_id
            or item.action_family != self.action_family
            or item.eligibility_id != self.eligibility.eligibility_id
            or item.response_rule_hash != self.response_rule.rule_hash
            for item in self.scenario_evaluations
        ):
            raise ValueError("M3_SCENARIO_EVALUATION_LINEAGE_MISMATCH")
        episode_ids = {item.episode_id for item in self.scenario_evaluations}
        decision_node_ids = {
            item.decision_node_id for item in self.scenario_evaluations
        }
        if len(episode_ids) != 1 or decision_node_ids != {
            self.eligibility.decision_node_id
        }:
            raise ValueError("M3_SCENARIO_CONTEXT_NOT_PRESERVED")
        if self.response_rule.support_state is ResponseSupportClass.ABSTAIN and any(
            component.support_state is not SupportState.ABSTAIN
            for item in self.scenario_evaluations
            for component in item.component_quantities
        ):
            raise ValueError("M3_ABSTAIN_RESPONSE_CANNOT_PRODUCE_SUPPORTED_OUTPUT")
        return self

    @computed_field
    @property
    def envelope_hash(self) -> str:
        return content_id(self.model_dump(mode="json", exclude={"envelope_hash"}))

    def m4_payload(self) -> dict[str, Any]:
        """Serialize action-conditioned CU for M4 without monetary fields."""
        return {
            "episode_id": self.scenario_evaluations[0].episode_id,
            "decision_node_id": self.scenario_evaluations[0].decision_node_id,
            "action_id": self.action_id,
            "action_family": self.action_family,
            "instantiation_state": self.instantiation_state.value,
            "eligibility_state": self.eligibility.state.value,
            "opportunity_state": (
                "NOT_REQUIRED" if self.action_id == "A00" else "NOT_INSTANTIATED"
            ),
            "eligibility_id": self.eligibility.eligibility_id,
            "response_support": self.response_rule.support_state.value,
            "response_rule_id": self.response_rule.response_rule_id,
            "response_rule_hash": self.response_rule.rule_hash,
            "response_source_type": self.response_rule.parameter_source.value,
            "response_source_references": self.response_rule.source_references,
            "response_parameter_version": self.response_rule.parameter_version,
            "response_freeze_id": self.response_rule.freeze_id,
            "response_provenance": self.response_rule.provenance,
            "response_parameters": self.response_rule.parameters,
            "scenario_ids": self.input_scenario_ids,
            "scenario_weights": self.input_scenario_weights,
            "scenario_consequences": tuple(
                {
                    "scenario_id": item.scenario_id,
                    "scenario_weight": item.scenario_weight,
                    "components": tuple(
                        {
                            "component_id": component.component_id,
                            "C_a_CU": component.adjusted_value_cu,
                            "support_state": component.support_state.value,
                            "baseline_cu_artifact_id": component.baseline_cu_artifact_id,
                            "baseline_reference_lineage_hash": component.baseline_reference_lineage_hash,
                            "response_intensity": component.response_intensity,
                            "response_draw_id": component.response_draw_id,
                        }
                        for component in item.component_quantities
                    ),
                }
                for item in self.scenario_evaluations
            ),
            "m3_envelope_hash": self.envelope_hash,
        }


def build_a00_identity_envelope(
    baselines: tuple[M3BaselineConsequenceInput, ...],
    *,
    eligibility: ActionEligibility,
    response_rule: ActionResponseRule,
) -> ActionEvaluationEnvelope:
    """Implement only the frozen A00 identity: `C^A00 = C^0`."""
    if not baselines:
        raise ValueError("M3_A00_REQUIRES_BASELINE_SCENARIOS")
    if (
        eligibility.action_id != "A00"
        or eligibility.state is not EligibilityState.ELIGIBLE
    ):
        raise ValueError("M3_A00_REQUIRES_ELIGIBLE_IDENTITY_ACTION")
    if response_rule.action_id != "A00" or response_rule.response_types != (
        ActionResponseType.IDENTITY,
    ):
        raise ValueError("M3_A00_IDENTITY_RULE_REQUIRED")
    evaluations = []
    for baseline in baselines:
        components = tuple(
            ActionConditionedCUQuantity(
                component_id=item.component_id,
                scenario_id=baseline.scenario_id,
                scenario_weight=baseline.scenario_weight,
                baseline_cu_artifact_id=item.cu_artifact_id,
                baseline_support_state=item.support_state,
                adjusted_value_cu=item.value_cu,
                support_state=item.support_state,
                action_response_reference_id=response_rule.source_references[0],
                action_response_parameter_version=response_rule.parameter_version,
                action_response_freeze_id=response_rule.freeze_id,
                response_rule_id=response_rule.response_rule_id,
                response_rule_hash=response_rule.rule_hash,
                response_source_type=response_rule.parameter_source.value,
                baseline_reference_lineage_hash=item.reference_lineage_hash,
                response_provenance=response_rule.provenance,
                reason_code=item.reason_code,
            )
            for item in baseline.component_quantities
        )
        evaluations.append(
            M3ActionConditionedConsequence(
                episode_id=baseline.episode_id,
                decision_node_id=baseline.decision_node_id,
                scenario_id=baseline.scenario_id,
                scenario_weight=baseline.scenario_weight,
                action_id="A00",
                action_family="null",
                baseline_consequence_id=baseline.baseline_consequence_id,
                baseline_interface_hash=baseline.baseline_interface_hash,
                eligibility_id=eligibility.eligibility_id,
                response_rule_id=response_rule.response_rule_id,
                response_rule_hash=response_rule.rule_hash,
                component_quantities=components,
            )
        )
    return ActionEvaluationEnvelope(
        action_id="A00",
        action_family="null",
        eligibility=eligibility,
        response_rule=response_rule,
        input_scenario_ids=tuple(item.scenario_id for item in baselines),
        input_scenario_weights=tuple(item.scenario_weight for item in baselines),
        scenario_evaluations=tuple(evaluations),
    )


def build_conditional_scenario_envelope(
    baselines: tuple[M3BaselineConsequenceInput, ...],
    *,
    eligibility: ActionEligibility,
    response_rule: ActionResponseRule,
    response_parameters: Mapping[str, Any],
    mitigation: Mapping[str, float],
    induced: Mapping[str, float],
    seed: int,
    response_registry_hash: str,
    sensitivity_level: str = "BASE",
) -> ActionEvaluationEnvelope:
    """Materialize ``A -> C^a -> CU^a`` in the conditional scenario lane.

    The deterministic draw is keyed by the frozen episode/node/scenario/action
    identity. Baseline abstentions remain abstentions, and no monetary mapping
    or risk ranking occurs at this boundary.
    """
    if not baselines:
        raise ValueError("M3_CONDITIONAL_REQUIRES_BASELINE_SCENARIOS")
    # χ_num is independent of χ_fact. A declared scenario response may be
    # evaluated on a mathematically formed instance while factual eligibility
    # remains TRUE, FALSE, or UNKNOWN as retained metadata.
    if response_rule.action_id == "A00":
        raise ValueError("M3_CONDITIONAL_NON_A00_ACTION_REQUIRED")
    if response_rule.support_state is not ResponseSupportClass.SCENARIO_ASSUMPTION:
        raise ValueError("M3_CONDITIONAL_SCENARIO_SUPPORT_REQUIRED")
    if response_rule.parameter_source is not ResponseSourceType.SCENARIO_ASSUMPTION:
        raise ValueError("M3_CONDITIONAL_SCENARIO_SOURCE_REQUIRED")
    if (
        not isinstance(response_registry_hash, str)
        or not response_registry_hash.startswith("sha256:")
        or len(response_registry_hash) != 71
    ):
        raise ValueError("M3_RESPONSE_REGISTRY_HASH_REQUIRED")
    if response_parameters.get("response_parameter_status") == "NOT_FROZEN":
        raise ContractError("M3_CONDITIONAL_RESPONSE_PARAMETERS_NOT_FROZEN")
    response_model = response_parameters.get("response_model")
    if response_model not in {"DETERMINISTIC", "BERNOULLI_BETA"}:
        raise ContractError(f"M3_RESPONSE_MODEL_NOT_IMPLEMENTED:{response_model}")
    gamma = response_parameters.get("induced_score_to_cu")
    if gamma is None or not isfinite(float(gamma)) or float(gamma) <= 0:
        raise ContractError("M3_INDUCED_SCORE_TO_CU_SOURCE_MISSING")
    unknown = (set(mitigation) | set(induced)) - set(CONSEQUENCE_COMPONENTS)
    if unknown:
        raise ValueError(f"M3_CONDITIONAL_UNKNOWN_COMPONENT:{sorted(unknown)}")
    if not (set(mitigation) | set(induced)) <= set(response_rule.affected_components):
        raise ValueError("M3_CONDITIONAL_RESPONSE_COMPONENT_SCOPE_MISMATCH")

    scenario_ids = tuple(item.scenario_id for item in baselines)
    scenario_weights = tuple(item.scenario_weight for item in baselines)
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("M3_DUPLICATE_SCENARIO_ID")
    if abs(sum(scenario_weights) - 1.0) > 1e-6:
        raise ValueError("M3_SCENARIO_WEIGHTS_MUST_SUM_TO_ONE")

    evaluations = []
    for baseline in baselines:
        rho = response_draw(
            seed=seed,
            episode_id=baseline.episode_id,
            decision_node_id=baseline.decision_node_id,
            scenario_id=baseline.scenario_id,
            action_template_id=response_rule.action_id,
            parameters=dict(response_parameters),
            response_registry_hash=response_registry_hash,
            sensitivity_level=sensitivity_level,
        )
        draw_id = content_id(
            {
                "seed": seed,
                "episode_id": baseline.episode_id,
                "decision_node_id": baseline.decision_node_id,
                "scenario_id": baseline.scenario_id,
                "action_id": response_rule.action_id,
                "sensitivity_level": sensitivity_level,
                "response_registry_hash": response_registry_hash,
                "response_intensity": rho,
            }
        )
        supported_values = {
            item.component_id: item.value_cu
            for item in baseline.component_quantities
            if item.support_state is not SupportState.ABSTAIN
            and item.value_cu is not None
        }
        post_values = action_post_consequences(
            pre_by_component=supported_values,
            mitigation=mitigation,
            induced=induced,
            rho=float(rho),
            induced_score_to_cu=float(gamma),
            included_components=tuple(supported_values),
        )
        components = []
        for item in baseline.component_quantities:
            if item.support_state is SupportState.ABSTAIN:
                adjusted_value = None
                support_state = SupportState.ABSTAIN
                reason_code = item.reason_code or "BASELINE_COMPONENT_ABSTAIN"
                intensity = None
                realization_id = None
            else:
                adjusted_value = post_values[item.component_id]
                support_state = item.support_state
                reason_code = None
                intensity = float(rho)
                realization_id = draw_id
            components.append(
                ActionConditionedCUQuantity(
                    component_id=item.component_id,
                    scenario_id=baseline.scenario_id,
                    scenario_weight=baseline.scenario_weight,
                    baseline_cu_artifact_id=item.cu_artifact_id,
                    baseline_support_state=item.support_state,
                    adjusted_value_cu=adjusted_value,
                    support_state=support_state,
                    action_response_reference_id=response_rule.source_references[0],
                    action_response_parameter_version=response_rule.parameter_version,
                    action_response_freeze_id=response_rule.freeze_id,
                    response_rule_id=response_rule.response_rule_id,
                    response_rule_hash=response_rule.rule_hash,
                    response_source_type=response_rule.parameter_source.value,
                    baseline_reference_lineage_hash=item.reference_lineage_hash,
                    response_provenance=response_rule.provenance,
                    response_intensity=intensity,
                    response_draw_id=realization_id,
                    reason_code=reason_code,
                )
            )
        evaluations.append(
            M3ActionConditionedConsequence(
                episode_id=baseline.episode_id,
                decision_node_id=baseline.decision_node_id,
                scenario_id=baseline.scenario_id,
                scenario_weight=baseline.scenario_weight,
                action_id=response_rule.action_id,
                action_family=response_rule.action_family,
                baseline_consequence_id=baseline.baseline_consequence_id,
                baseline_interface_hash=baseline.baseline_interface_hash,
                eligibility_id=eligibility.eligibility_id,
                response_rule_id=response_rule.response_rule_id,
                response_rule_hash=response_rule.rule_hash,
                component_quantities=tuple(components),
            )
        )
    return ActionEvaluationEnvelope(
        action_id=response_rule.action_id,
        action_family=response_rule.action_family,
        eligibility=eligibility,
        response_rule=response_rule,
        input_scenario_ids=scenario_ids,
        input_scenario_weights=scenario_weights,
        scenario_evaluations=tuple(evaluations),
    )


__all__ = [
    "ActionEligibility",
    "ActionEvaluationEnvelope",
    "ActionResponseRule",
    "ActionResponseType",
    "EligibilityState",
    "ResponseParameter",
    "ResponseSourceType",
    "ResponseSupportClass",
    "build_a00_identity_envelope",
    "build_conditional_scenario_envelope",
]
