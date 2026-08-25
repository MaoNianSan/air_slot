"""Contract-only M3 action envelope -> future M4 valuation boundary.

This module validates M3 CU distributions. It performs no monetary mapping,
aggregation, risk calculation, action ranking, or selection.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from model.M3.action_response import (
    ActionEvaluationEnvelope,
    ResponseParameter,
    ResponseSourceType,
    ResponseSupportClass,
)
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import SupportState
from model.common.value_objects import FrozenModel


class M4ActionCUComponentInput(FrozenModel):
    component_id: str = Field(min_length=1)
    C_a_CU: float | None
    support_state: SupportState
    baseline_cu_artifact_id: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    baseline_reference_lineage_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_intensity: float | None = None
    response_draw_id: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def explicit_support(self):
        if self.component_id not in CONSEQUENCE_COMPONENTS:
            raise ValueError("M4_UNKNOWN_M3_CONSEQUENCE_COMPONENT")
        if self.support_state is SupportState.ABSTAIN and self.C_a_CU is not None:
            raise ValueError("M4_M3_ABSTAIN_COMPONENT_MUST_BE_NULL")
        if self.support_state is not SupportState.ABSTAIN and self.C_a_CU is None:
            raise ValueError("M4_M3_SUPPORTED_COMPONENT_REQUIRES_CU")
        if self.response_intensity is None and self.response_draw_id is not None:
            raise ValueError("M4_RESPONSE_DRAW_ID_REQUIRES_INTENSITY")
        if self.response_intensity is not None:
            if not 0.0 <= self.response_intensity <= 1.0:
                raise ValueError("M4_RESPONSE_INTENSITY_OUT_OF_RANGE")
            if self.response_draw_id is None:
                raise ValueError("M4_RESPONSE_INTENSITY_REQUIRES_DRAW_ID")
        return self


class M4ScenarioActionConsequenceInput(FrozenModel):
    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0, le=1)
    components: tuple[M4ActionCUComponentInput, ...]

    @model_validator(mode="after")
    def exact_component_vector(self):
        if (
            tuple(item.component_id for item in self.components)
            != CONSEQUENCE_COMPONENTS
        ):
            raise ValueError("M4_M3_EXACT_SEVEN_COMPONENTS_REQUIRED")
        return self


class M4ActionEnvelopeInput(FrozenModel):
    """No-money action-conditioned distribution ready for later M4 functions."""

    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    action_family: str = Field(min_length=1)
    eligibility_state: str = Field(min_length=1)
    eligibility_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_support: ResponseSupportClass
    response_rule_id: str = Field(min_length=1)
    response_rule_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_source_type: ResponseSourceType
    response_source_references: tuple[str, ...] = Field(min_length=1)
    response_parameter_version: str = Field(min_length=1)
    response_freeze_id: str = Field(min_length=1)
    response_provenance: tuple[str, ...] = Field(min_length=1)
    response_parameters: tuple[ResponseParameter, ...] = ()
    scenario_ids: tuple[int, ...] = Field(min_length=1)
    scenario_weights: tuple[float, ...] = Field(min_length=1)
    scenario_consequences: tuple[M4ScenarioActionConsequenceInput, ...] = Field(
        min_length=1
    )
    m3_envelope_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def from_m3(cls, envelope: ActionEvaluationEnvelope) -> "M4ActionEnvelopeInput":
        return cls.model_validate(envelope.m4_payload())

    @model_validator(mode="after")
    def preserve_distribution(self):
        if not (
            len(self.scenario_ids)
            == len(self.scenario_weights)
            == len(self.scenario_consequences)
        ):
            raise ValueError("M4_M3_SCENARIO_COUNT_MISMATCH")
        if len(self.scenario_ids) != len(set(self.scenario_ids)):
            raise ValueError("M4_M3_DUPLICATE_SCENARIO_ID")
        if abs(sum(self.scenario_weights) - 1.0) > 1e-6:
            raise ValueError("M4_M3_SCENARIO_WEIGHTS_MUST_SUM_TO_ONE")
        if (
            tuple(item.scenario_id for item in self.scenario_consequences)
            != self.scenario_ids
        ):
            raise ValueError("M4_M3_SCENARIO_ID_MISMATCH")
        if (
            tuple(item.scenario_weight for item in self.scenario_consequences)
            != self.scenario_weights
        ):
            raise ValueError("M4_M3_SCENARIO_WEIGHT_MISMATCH")
        return self


__all__ = [
    "M4ActionCUComponentInput",
    "M4ActionEnvelopeInput",
    "M4ScenarioActionConsequenceInput",
]
