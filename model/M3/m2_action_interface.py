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
        payload = self.model_dump(mode="json", exclude={"baseline_interface_hash"})
        if self.baseline_interface_hash != content_id(payload):
            raise ValueError("M3_BASELINE_INTERFACE_HASH_MISMATCH")
        return self


class ActionConditionedCUQuantity(FrozenModel):
    """Future M3-owned CU response for one component; never a native quantity."""

    component_id: str = Field(min_length=1)
    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0, le=1)
    baseline_cu_artifact_id: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    adjusted_value_cu: float | None
    support_state: SupportState
    action_response_reference_id: str = Field(min_length=1)
    action_response_parameter_version: str = Field(min_length=1)
    reason_code: str | None = None

    @model_validator(mode="after")
    def explicit_adjusted_support(self):
        if self.component_id not in CONSEQUENCE_COMPONENTS:
            raise ValueError("UNKNOWN_M2_CONSEQUENCE_COMPONENT")
        if self.support_state is SupportState.ABSTAIN:
            if self.adjusted_value_cu is not None or not self.reason_code:
                raise ValueError("M3_ACTION_CU_ABSTAIN_REQUIRES_NULL_AND_REASON")
        elif self.adjusted_value_cu is None:
            raise ValueError("M3_ACTION_CU_SUPPORTED_REQUIRES_VALUE")
        return self


class M3ActionConditionedConsequence(FrozenModel):
    """Future `C^{a,CU}(s)` result shape; construction is not implemented here."""

    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0, le=1)
    action_id: str = Field(min_length=1)
    baseline_consequence_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    component_quantities: tuple[ActionConditionedCUQuantity, ...]
    consequence_state: Literal["ACTION_CONDITIONED"] = "ACTION_CONDITIONED"
    action_response_applied: Literal[True] = True

    @model_validator(mode="after")
    def exact_action_conditioned_vector(self):
        if tuple(item.component_id for item in self.component_quantities) != CONSEQUENCE_COMPONENTS:
            raise ValueError("M3_ACTION_INTERFACE_REQUIRES_EXACT_SEVEN_COMPONENTS")
        if any(
            item.scenario_id != self.scenario_id
            or abs(item.scenario_weight - self.scenario_weight) > 1e-12
            for item in self.component_quantities
        ):
            raise ValueError("M3_ACTION_INTERFACE_SCENARIO_MISMATCH")
        return self


__all__ = [
    "ActionConditionedCUQuantity",
    "M3ActionConditionedConsequence",
    "M3BaselineConsequenceInput",
]
