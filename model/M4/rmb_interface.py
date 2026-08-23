"""M4 interface for the corrected C -> constructed RMB -> risk chain."""

from __future__ import annotations

from pydantic import Field, model_validator

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import SupportState
from model.common.value_objects import FrozenModel


class RMBConsequenceComponent(FrozenModel):
    component_id: str = Field(min_length=1)
    consequence_value: float | None
    support_state: SupportState
    native_artifact_id: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    reference_lineage_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reason_code: str | None = None

    @model_validator(mode="after")
    def explicit_support(self):
        if self.component_id not in CONSEQUENCE_COMPONENTS:
            raise ValueError("RMB_UNKNOWN_CONSEQUENCE_COMPONENT")
        if self.support_state is SupportState.ABSTAIN:
            if self.consequence_value is not None or not self.reason_code:
                raise ValueError("RMB_ABSTAIN_COMPONENT_MUST_BE_NULL")
        elif self.consequence_value is None:
            raise ValueError("RMB_SUPPORTED_COMPONENT_REQUIRES_CONSEQUENCE_VALUE")
        return self


class RMBScenarioActionConsequence(FrozenModel):
    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0, le=1)
    components: tuple[RMBConsequenceComponent, ...]

    @model_validator(mode="after")
    def exact_vector(self):
        if tuple(item.component_id for item in self.components) != CONSEQUENCE_COMPONENTS:
            raise ValueError("RMB_EXACT_SEVEN_COMPONENTS_REQUIRED")
        return self


class RMBActionEnvelopeInput(FrozenModel):
    """Action-conditioned consequence C^a before any RMB mapping."""

    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    action_family: str = Field(min_length=1)
    response_support: str = Field(min_length=1)
    response_rule_id: str = Field(min_length=1)
    response_rule_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_provenance: tuple[str, ...] = Field(min_length=1)
    scenario_ids: tuple[int, ...] = Field(min_length=1)
    scenario_weights: tuple[float, ...] = Field(min_length=1)
    scenario_consequences: tuple[RMBScenarioActionConsequence, ...] = Field(min_length=1)
    m3_envelope_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def preserve_distribution(self):
        if not (len(self.scenario_ids) == len(self.scenario_weights) == len(self.scenario_consequences)):
            raise ValueError("RMB_SCENARIO_COUNT_MISMATCH")
        if tuple(item.scenario_id for item in self.scenario_consequences) != self.scenario_ids:
            raise ValueError("RMB_SCENARIO_ID_MISMATCH")
        if tuple(item.scenario_weight for item in self.scenario_consequences) != self.scenario_weights:
            raise ValueError("RMB_SCENARIO_WEIGHT_MISMATCH")
        if abs(sum(self.scenario_weights) - 1.0) > 1e-6:
            raise ValueError("RMB_SCENARIO_WEIGHTS_MUST_SUM_TO_ONE")
        return self


__all__ = [
    "RMBActionEnvelopeInput",
    "RMBConsequenceComponent",
    "RMBScenarioActionConsequence",
]
