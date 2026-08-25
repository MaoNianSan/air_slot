"""Contract-only M2 baseline -> future M3 action-response boundary.

This module contains no action catalog, response model, or adjustment logic.
M2 owns native consequence definitions; M3 may only supply an explicitly
lineaged action response over the baseline CU representation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import SupportState
from model.common.identity import content_id
from model.common.value_objects import FrozenModel


class M3BaselineCUQuantity(FrozenModel):
    """One immutable M2 baseline CU component serialized for M3."""

    component_id: str = Field(min_length=1)
    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0, le=1)
    value_cu: float | None
    native_support_state: SupportState
    support_state: SupportState
    cu_artifact_id: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    reference_lineage_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reason_code: str | None = None

    @model_validator(mode="after")
    def explicit_baseline_support(self):
        if self.component_id not in CONSEQUENCE_COMPONENTS:
            raise ValueError("UNKNOWN_M2_CONSEQUENCE_COMPONENT")
        if self.support_state is SupportState.ABSTAIN:
            if (
                self.value_cu is not None
                or self.cu_artifact_id is not None
                or not self.reason_code
            ):
                raise ValueError("M3_BASELINE_ABSTAIN_MUST_REMAIN_NULL")
        elif self.value_cu is None or self.cu_artifact_id is None:
            raise ValueError("M3_BASELINE_SUPPORTED_REQUIRES_CU_ARTIFACT")
        return self


class M3BaselineConsequenceInput(FrozenModel):
    """Serialized, action-free `C^{0,CU}(s)` envelope received from M2."""

    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0, le=1)
    baseline_consequence_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    baseline_interface_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    component_ids: tuple[str, ...]
    native_artifact_ids: tuple[str, ...]
    cu_artifact_ids: tuple[str | None, ...]
    component_quantities: tuple[M3BaselineCUQuantity, ...]
    reference_lineage: tuple[str, ...] = Field(min_length=1)
    consequence_state: Literal["BASELINE"] = "BASELINE"
    action_id: Literal[None] = None
    action_adjustments_applied: Literal[False] = False

    @model_validator(mode="after")
    def baseline_is_action_free(self):
        if self.component_ids != CONSEQUENCE_COMPONENTS:
            raise ValueError("M3_BASELINE_REQUIRES_EXACT_SEVEN_COMPONENTS")
        if not (
            len(self.native_artifact_ids)
            == len(self.cu_artifact_ids)
            == len(CONSEQUENCE_COMPONENTS)
        ):
            raise ValueError("M3_BASELINE_COMPONENT_ARTIFACT_COUNT_MISMATCH")
        if (
            tuple(item.component_id for item in self.component_quantities)
            != CONSEQUENCE_COMPONENTS
        ):
            raise ValueError("M3_BASELINE_COMPONENT_QUANTITY_ORDER_MISMATCH")
        if (
            tuple(item.cu_artifact_id for item in self.component_quantities)
            != self.cu_artifact_ids
        ):
            raise ValueError("M3_BASELINE_CU_ARTIFACT_LINEAGE_MISMATCH")
        if any(
            item.scenario_id != self.scenario_id
            or abs(item.scenario_weight - self.scenario_weight) > 1e-12
            for item in self.component_quantities
        ):
            raise ValueError("M3_BASELINE_COMPONENT_SCENARIO_MISMATCH")
        payload = self.model_dump(mode="json", exclude={"baseline_interface_hash"})
        if self.baseline_interface_hash != content_id(payload):
            raise ValueError("M3_BASELINE_INTERFACE_HASH_MISMATCH")
        return self


class ActionConditionedCUQuantity(FrozenModel):
    """M3-owned scenario-conditioned CU response for one component.

    The response draw fields are deterministic implementation lineage, not an
    observed intervention outcome or a causal action-effect estimate.
    """

    component_id: str = Field(min_length=1)
    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0, le=1)
    baseline_cu_artifact_id: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    baseline_support_state: SupportState
    adjusted_value_cu: float | None
    support_state: SupportState
    action_response_reference_id: str = Field(min_length=1)
    action_response_parameter_version: str = Field(min_length=1)
    action_response_freeze_id: str = Field(min_length=1)
    response_rule_id: str = Field(min_length=1)
    response_rule_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_source_type: str = Field(min_length=1)
    baseline_reference_lineage_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_provenance: tuple[str, ...] = Field(min_length=1)
    response_intensity: float | None = None
    response_draw_id: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    reason_code: str | None = None

    @model_validator(mode="after")
    def explicit_adjusted_support(self):
        if self.component_id not in CONSEQUENCE_COMPONENTS:
            raise ValueError("UNKNOWN_M2_CONSEQUENCE_COMPONENT")
        if self.support_state is SupportState.ABSTAIN:
            if (
                self.adjusted_value_cu is not None
                or self.response_intensity is not None
                or self.response_draw_id is not None
                or not self.reason_code
            ):
                raise ValueError("M3_ACTION_CU_ABSTAIN_REQUIRES_NULL_AND_REASON")
        elif self.adjusted_value_cu is None:
            raise ValueError("M3_ACTION_CU_SUPPORTED_REQUIRES_VALUE")
        if self.response_intensity is None and self.response_draw_id is not None:
            raise ValueError("M3_RESPONSE_DRAW_ID_REQUIRES_INTENSITY")
        if self.response_intensity is not None:
            if not 0.0 <= self.response_intensity <= 1.0:
                raise ValueError("M3_RESPONSE_INTENSITY_OUT_OF_RANGE")
            if self.response_draw_id is None:
                raise ValueError("M3_RESPONSE_INTENSITY_REQUIRES_DRAW_ID")
        if (
            self.baseline_support_state is SupportState.ABSTAIN
            and self.support_state is not SupportState.ABSTAIN
        ):
            raise ValueError("M3_BASELINE_ABSTAIN_CANNOT_BECOME_SUPPORTED")
        if self.response_source_type not in {
            "LITERATURE",
            "OPERATIONAL_RULE",
            "SCENARIO_ASSUMPTION",
            "EXPERT_JUDGEMENT",
            "HYBRID",
        }:
            raise ValueError("M3_UNKNOWN_RESPONSE_SOURCE_TYPE")
        return self


class M3ActionConditionedConsequence(FrozenModel):
    """Future `C^{a,CU}(s)` result shape; construction is not implemented here."""

    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0, le=1)
    action_id: str = Field(min_length=1)
    action_family: str = Field(min_length=1)
    baseline_consequence_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    baseline_interface_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    eligibility_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_rule_id: str = Field(min_length=1)
    response_rule_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    component_quantities: tuple[ActionConditionedCUQuantity, ...]
    consequence_state: Literal["ACTION_CONDITIONED"] = "ACTION_CONDITIONED"
    action_response_applied: Literal[True] = True

    @model_validator(mode="after")
    def exact_action_conditioned_vector(self):
        if (
            tuple(item.component_id for item in self.component_quantities)
            != CONSEQUENCE_COMPONENTS
        ):
            raise ValueError("M3_ACTION_INTERFACE_REQUIRES_EXACT_SEVEN_COMPONENTS")
        if any(
            item.scenario_id != self.scenario_id
            or abs(item.scenario_weight - self.scenario_weight) > 1e-12
            for item in self.component_quantities
        ):
            raise ValueError("M3_ACTION_INTERFACE_SCENARIO_MISMATCH")
        if any(
            item.response_rule_id != self.response_rule_id
            or item.response_rule_hash != self.response_rule_hash
            for item in self.component_quantities
        ):
            raise ValueError("M3_ACTION_INTERFACE_RESPONSE_RULE_MISMATCH")
        return self


__all__ = [
    "ActionConditionedCUQuantity",
    "M3BaselineCUQuantity",
    "M3ActionConditionedConsequence",
    "M3BaselineConsequenceInput",
]
