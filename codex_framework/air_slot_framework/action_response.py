"""Scenario-conditioned M3 action response contracts."""

from __future__ import annotations

from enum import Enum
import hashlib
import math
import random
from typing import Any

from pydantic import Field, model_validator

from .contracts import CONSEQUENCE_COMPONENTS, ConsequenceScenario, FrozenModel, SupportState, content_hash


class EligibilityState(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"


class ResponseSupport(str, Enum):
    SUPPORTED = "SUPPORTED"
    SCENARIO_ASSUMPTION = "SCENARIO_ASSUMPTION"
    ABSTAIN = "ABSTAIN"


class ActionTemplate(FrozenModel):
    action_id: str = Field(min_length=1)
    action_family: str = Field(min_length=1)
    affected_components: tuple[str, ...]
    mitigation: dict[str, float]
    induced: dict[str, float]
    literature_references: tuple[str, ...] = Field(min_length=1)
    operational_constraints: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope(self):
        if not set(self.affected_components) <= set(CONSEQUENCE_COMPONENTS):
            raise ValueError("ACTION_UNKNOWN_COMPONENT")
        declared = set(self.mitigation) | set(self.induced)
        if len(self.affected_components) != len(set(self.affected_components)):
            raise ValueError("ACTION_DUPLICATE_COMPONENT")
        if not declared <= set(CONSEQUENCE_COMPONENTS):
            raise ValueError("ACTION_UNKNOWN_COMPONENT")
        if not declared <= set(self.affected_components):
            raise ValueError("ACTION_EFFECT_SCOPE_NOT_DECLARED")
        if any(not math.isfinite(v) or v < 0 for v in self.mitigation.values()):
            raise ValueError("ACTION_MITIGATION_INVALID")
        if any(not math.isfinite(v) or v < 0 for v in self.induced.values()):
            raise ValueError("ACTION_INDUCED_INVALID")
        if self.action_id == "A00" and declared:
            raise ValueError("A00_MUST_HAVE_NO_EFFECT_COMPONENTS")
        return self


class ActionEligibility(FrozenModel):
    action_id: str = Field(min_length=1)
    action_family: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    state: EligibilityState
    conditions: tuple[str, ...]
    fact_references: tuple[str, ...]
    provenance: tuple[str, ...] = Field(min_length=1)
    eligibility_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def create(cls, **values: Any) -> "ActionEligibility":
        return cls(**values, eligibility_id=content_hash(values))

    @model_validator(mode="after")
    def validate_id(self):
        payload = self.model_dump(mode="json", exclude={"eligibility_id"})
        if self.eligibility_id != content_hash(payload):
            raise ValueError("ACTION_ELIGIBILITY_HASH_MISMATCH")
        return self


class ResponseParameter(FrozenModel):
    parameter_name: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    parameter_version: str = Field(min_length=1)
    freeze_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def finite_value(self):
        if not math.isfinite(self.value):
            raise ValueError("RESPONSE_PARAMETER_NONFINITE")
        return self


class ActionResponseRule(FrozenModel):
    response_rule_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    action_family: str = Field(min_length=1)
    support: ResponseSupport
    response_model: str = Field(min_length=1)
    affected_components: tuple[str, ...]
    source_references: tuple[str, ...] = Field(min_length=1)
    parameter_version: str = Field(min_length=1)
    freeze_id: str = Field(min_length=1)
    parameters: tuple[ResponseParameter, ...] = ()
    provenance: tuple[str, ...] = Field(min_length=1)
    rule_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def create(cls, **values: Any) -> "ActionResponseRule":
        # Include Pydantic defaults (notably parameters=()) in the canonical
        # payload before validating the final immutable object.
        candidate = cls.model_construct(**values, rule_hash="")
        payload = candidate.model_dump(mode="json", exclude={"rule_hash"})
        return cls(**values, rule_hash=content_hash(payload))

    @model_validator(mode="after")
    def validate_rule(self):
        if not set(self.affected_components) <= set(CONSEQUENCE_COMPONENTS):
            raise ValueError("RESPONSE_UNKNOWN_COMPONENT")
        if self.support is ResponseSupport.ABSTAIN and self.parameters:
            raise ValueError("ABSTAIN_RESPONSE_CANNOT_HAVE_PARAMETERS")
        names = tuple(item.parameter_name for item in self.parameters)
        if len(names) != len(set(names)):
            raise ValueError("RESPONSE_DUPLICATE_PARAMETER")
        if any(item.parameter_version != self.parameter_version or item.freeze_id != self.freeze_id or item.source_reference not in self.source_references for item in self.parameters):
            raise ValueError("RESPONSE_PARAMETER_LINEAGE_MISMATCH")
        payload = self.model_dump(mode="json", exclude={"rule_hash"})
        if self.rule_hash != content_hash(payload):
            raise ValueError("RESPONSE_RULE_HASH_MISMATCH")
        return self


class ActionConditionedCUComponent(FrozenModel):
    """One component after applying a declared action response scenario.

    The object deliberately retains the baseline CU lineage and response
    provenance.  It is a constructed, model-implied consequence and never an
    observed intervention outcome.
    """

    component_id: str
    value_cu: float | None
    support_state: SupportState
    source_cu_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    action_id: str = Field(min_length=1)
    response_support: ResponseSupport
    mitigation_intensity: float | None = Field(default=None, ge=0, le=1)
    induced_intensity: float | None = Field(default=None, ge=0)
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_value(self):
        if self.component_id not in CONSEQUENCE_COMPONENTS:
            raise ValueError("ACTION_CU_UNKNOWN_COMPONENT")
        if self.support_state is SupportState.ABSTAIN:
            if self.value_cu is not None:
                raise ValueError("ACTION_CU_ABSTAIN_MUST_REMAIN_NULL")
            if not self.reason_code:
                raise ValueError("ACTION_CU_ABSTAIN_REQUIRES_REASON")
        elif self.value_cu is None or not math.isfinite(self.value_cu):
            raise ValueError("ACTION_CU_SUPPORTED_REQUIRES_FINITE_VALUE")
        if self.response_support is ResponseSupport.ABSTAIN and (
            self.mitigation_intensity is not None or self.induced_intensity is not None
        ):
            raise ValueError("ABSTAIN_ACTION_CU_CANNOT_HAVE_INTENSITIES")
        return self

    @property
    def action_cu_id(self) -> str:
        return content_hash(self.model_dump(mode="json"))


class ActionConditionedScenario(FrozenModel):
    """Scenario-specific action-conditioned CU vector (C^a -> CU^a)."""

    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0, le=1)
    action_id: str = Field(min_length=1)
    baseline_scenario_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    components: tuple[ActionConditionedCUComponent, ...]
    response_support: ResponseSupport
    response_model: str = Field(min_length=1)
    response_draw_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_rule_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    provenance: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def exact_vector_and_context(self):
        ids = tuple(item.component_id for item in self.components)
        if ids != CONSEQUENCE_COMPONENTS:
            raise ValueError("ACTION_CU_EXACT_SEVEN_COMPONENTS_REQUIRED")
        if any(item.action_id != self.action_id for item in self.components):
            raise ValueError("ACTION_CU_ACTION_LINEAGE_MISMATCH")
        return self

    @property
    def scenario_hash(self) -> str:
        return content_hash(self.model_dump(mode="json"))


class ActionMaterialization(FrozenModel):
    """Materialized action response without RMB conversion or ranking."""

    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    action_family: str = Field(min_length=1)
    eligibility_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_rule_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_support: ResponseSupport
    response_model: str = Field(min_length=1)
    response_draw_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    scenarios: tuple[ActionConditionedScenario, ...] = Field(min_length=1)
    status: str
    claim_scope: str = "MODEL_IMPLIED_SCENARIO_REPLAY_NOT_CAUSAL"
    produces_rmb: bool = False
    produces_ranking: bool = False
    provenance: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def scenario_context(self):
        if any(
            item.episode_id != self.episode_id
            or item.decision_node_id != self.decision_node_id
            or item.action_id != self.action_id
            for item in self.scenarios
        ):
            raise ValueError("ACTION_MATERIALIZATION_CONTEXT_MISMATCH")
        if self.produces_rmb or self.produces_ranking:
            raise ValueError("ACTION_MATERIALIZATION_MUST_STOP_BEFORE_RMB_AND_RANKING")
        return self


def _parameter(rule: ActionResponseRule, name: str, *, default: float | None = None) -> float:
    for item in rule.parameters:
        if item.parameter_name == name:
            return item.value
    if default is not None:
        return default
    raise ValueError(f"RESPONSE_PARAMETER_MISSING:{name}")


def _response_draw(
    *,
    seed: int,
    episode_id: str,
    decision_node_id: str,
    scenario_id: int,
    action_id: str,
    rule: ActionResponseRule,
) -> tuple[float, str]:
    """Return deterministic response intensity and a reproducible draw id."""
    draw_payload = {
        "seed": seed,
        "episode_id": episode_id,
        "decision_node_id": decision_node_id,
        "scenario_id": scenario_id,
        "action_id": action_id,
        "response_rule_hash": rule.rule_hash,
    }
    draw_id = content_hash(draw_payload)
    seed_bytes = f"{draw_id}|{seed}".encode("utf-8")
    local_seed = int.from_bytes(hashlib.sha256(seed_bytes).digest()[:8], "big")
    rng = random.Random(local_seed)
    if rule.response_model == "DETERMINISTIC":
        intensity = _parameter(rule, "mean_intensity", default=1.0)
    elif rule.response_model == "BERNOULLI_BETA":
        probability = _parameter(rule, "success_probability")
        mean = _parameter(rule, "mean_intensity")
        concentration = _parameter(rule, "concentration")
        if not 0 <= probability <= 1 or not 0 <= mean <= 1 or concentration <= 0:
            raise ValueError("RESPONSE_BERNOULLI_BETA_PARAMETER_INVALID")
        success = rng.random() < probability
        intensity = rng.betavariate(mean * concentration, (1 - mean) * concentration) if success else 0.0
    else:
        raise ValueError(f"RESPONSE_MODEL_UNSUPPORTED:{rule.response_model}")
    if not 0 <= intensity <= 1 or not math.isfinite(intensity):
        raise ValueError("RESPONSE_INTENSITY_INVALID")
    return float(intensity), draw_id


def materialize_action(
    *,
    baseline: ConsequenceScenario,
    eligibility: ActionEligibility,
    action: ActionTemplate,
    response_rule: ActionResponseRule,
    seed: int = 0,
) -> ActionMaterialization:
    """Materialize A -> C^a -> CU^a under an explicit response assumption.

    A00 is a samplewise identity.  Non-A00 actions require explicit ELIGIBLE
    input and a SCENARIO_ASSUMPTION response rule.  Unsupported baseline
    components remain typed ABSTAIN and are never zero-filled.
    """
    if eligibility.action_id != action.action_id or response_rule.action_id != action.action_id:
        raise ValueError("ACTION_LINEAGE_MISMATCH")
    if eligibility.decision_node_id != baseline.decision_node_id:
        raise ValueError("ACTION_ELIGIBILITY_NODE_MISMATCH")
    if action.action_id == "A00":
        if eligibility.state is not EligibilityState.ELIGIBLE:
            raise ValueError("A00_REQUIRES_EXPLICIT_ELIGIBLE")
        if response_rule.support is not ResponseSupport.SUPPORTED:
            raise ValueError("A00_REQUIRES_SUPPORTED_IDENTITY_RULE")
        if response_rule.response_model != "IDENTITY":
            raise ValueError("A00_REQUIRES_IDENTITY_RESPONSE_MODEL")
    else:
        if eligibility.state is not EligibilityState.ELIGIBLE:
            raise ValueError("NON_A00_REQUIRES_EXPLICIT_ELIGIBILITY")
        if response_rule.support is not ResponseSupport.SCENARIO_ASSUMPTION:
            raise ValueError("NON_A00_REQUIRES_SCENARIO_ASSUMPTION")
    if tuple(response_rule.affected_components) != tuple(action.affected_components):
        raise ValueError("ACTION_RESPONSE_COMPONENT_SCOPE_MISMATCH")

    scenarios: list[ActionConditionedScenario] = []
    all_draw_ids: list[str] = []
    induced_scale = _parameter(response_rule, "induced_score_to_cu", default=0.0)
    for scenario in (baseline,):
        if action.action_id == "A00":
            intensity = 0.0
            draw_id = content_hash({"identity": True, "scenario_id": scenario.scenario_id, "rule": response_rule.rule_hash})
        else:
            intensity, draw_id = _response_draw(
                seed=seed,
                episode_id=scenario.episode_id,
                decision_node_id=scenario.decision_node_id,
                scenario_id=scenario.scenario_id,
                action_id=action.action_id,
                rule=response_rule,
            )
        all_draw_ids.append(draw_id)
        output_components: list[ActionConditionedCUComponent] = []
        for component, native in zip(scenario.cu_components, scenario.native_components, strict=True):
            if component.support_state is SupportState.ABSTAIN:
                output_components.append(
                    ActionConditionedCUComponent(
                        component_id=component.component_id,
                        value_cu=None,
                        support_state=SupportState.ABSTAIN,
                        source_cu_id=component.cu_id,
                        action_id=action.action_id,
                        response_support=ResponseSupport.ABSTAIN,
                        reason_code=component.reason_code or "BASELINE_COMPONENT_UNSUPPORTED",
                    )
                )
                continue
            mitigation = float(action.mitigation.get(component.component_id, 0.0))
            induced = float(action.induced.get(component.component_id, 0.0))
            if action.action_id == "A00":
                post_value = component.value_cu
                comp_support = ResponseSupport.SUPPORTED
                component_intensity = None
                induced_intensity = None
            else:
                post_value = max(0.0, component.value_cu * (1.0 - mitigation * intensity)) + induced_scale * induced * intensity
                comp_support = ResponseSupport.SCENARIO_ASSUMPTION
                component_intensity = intensity
                induced_intensity = induced
            output_components.append(
                ActionConditionedCUComponent(
                    component_id=component.component_id,
                    value_cu=float(post_value),
                    support_state=SupportState.SUPPORTED,
                    source_cu_id=component.cu_id,
                    action_id=action.action_id,
                    response_support=comp_support,
                    mitigation_intensity=component_intensity,
                    induced_intensity=induced_intensity,
                )
            )
        scenarios.append(
            ActionConditionedScenario(
                episode_id=scenario.episode_id,
                decision_node_id=scenario.decision_node_id,
                scenario_id=scenario.scenario_id,
                scenario_weight=scenario.scenario_weight,
                action_id=action.action_id,
                baseline_scenario_hash=scenario.scenario_consequence_hash,
                components=tuple(output_components),
                response_support=response_rule.support,
                response_model=response_rule.response_model,
                response_draw_id=draw_id,
                response_rule_hash=response_rule.rule_hash,
                provenance=(
                    "M3_ACTION_RESPONSE",
                    "SCENARIO_ASSUMPTION" if action.action_id != "A00" else "A00_IDENTITY",
                    *response_rule.provenance,
                ),
            )
        )
    materialization_draw_id = content_hash({"draw_ids": all_draw_ids, "rule": response_rule.rule_hash})
    return ActionMaterialization(
        episode_id=baseline.episode_id,
        decision_node_id=baseline.decision_node_id,
        action_id=action.action_id,
        action_family=action.action_family,
        eligibility_id=eligibility.eligibility_id,
        response_rule_hash=response_rule.rule_hash,
        response_support=response_rule.support,
        response_model=response_rule.response_model,
        response_draw_id=materialization_draw_id,
        scenarios=tuple(scenarios),
        status="IDENTITY" if action.action_id == "A00" else "CONDITIONAL_SCENARIO_ASSUMPTION",
        provenance=("M3_ACTION_MATERIALIZATION", "NO_CAUSAL_EFFECT", "NO_RMB_RANKING"),
    )


__all__ = [
    "ActionConditionedCUComponent",
    "ActionConditionedScenario",
    "ActionEligibility",
    "ActionMaterialization",
    "ActionResponseRule",
    "ActionTemplate",
    "EligibilityState",
    "ResponseParameter",
    "ResponseSupport",
    "materialize_action",
]
