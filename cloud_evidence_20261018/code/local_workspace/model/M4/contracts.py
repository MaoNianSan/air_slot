from pydantic import Field, model_validator

from model.common.value_objects import FrozenModel
from model.M1.contracts import AlignedScenario
from model.M2.contracts import ScenarioConsequence
from model.M3.contracts import CandidateAction
from model.PRE.contracts.pre_state import PREState
from model.M2.contracts import COMPONENTS


class M4DecisionRequest(FrozenModel):
    """Typed scientific boundary: PRE + M1 + M2 + M3, never raw rows."""

    pre_state: PREState
    m1_scenarios: tuple[AlignedScenario, ...]
    m2_consequences: tuple[ScenarioConsequence, ...]
    candidates: tuple[CandidateAction, ...]
    lambda_risk: float = Field(default=.25, ge=0, le=1)
    alpha: float = Field(default=.90, gt=0, lt=1)
    seed: int = 0

    @model_validator(mode="after")
    def aligned_chain(self):
        episode=self.pre_state.decision_node.episode_id
        node=self.pre_state.decision_node.decision_node_id
        if any(row.episode_id!=episode or row.decision_node_id!=node for row in self.m1_scenarios):
            raise ValueError("M4_M1_PRE_IDENTITY_MISMATCH")
        m1={(row.scenario_id,row.scenario_weight) for row in self.m1_scenarios}
        m2={(row.scenario_id,row.scenario_weight) for row in self.m2_consequences}
        if m1!=m2 or any(row.decision_node_id!=node for row in self.m2_consequences):
            raise ValueError("M4_M1_M2_SCENARIO_LINEAGE_MISMATCH")
        for row in self.m2_consequences:
            if tuple(item.component for item in row.components)!=COMPONENTS:
                raise ValueError("M4_M2_SEVEN_COMPONENT_CONTRACT_REQUIRED")
            if row.formal_total_cu is None:
                raise ValueError("M4_M2_FORMAL_TOTAL_UNAVAILABLE")
        return self
