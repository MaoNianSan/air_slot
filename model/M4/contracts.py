"""Legacy pre-V2 request contract; excluded from the public M4 V2 API."""

from __future__ import annotations

from pydantic import Field, model_validator

from model.M1.contracts import AlignedScenario
from model.M2.contracts import COMPONENTS, ScenarioConsequence
from model.M3.contracts import (
    ActionMaterialCoverageContract,
    CandidateAction,
)
from model.PRE.contracts.pre_state import PREState
from model.common.value_objects import FrozenModel


class M4DecisionRequest(FrozenModel):
    """Typed scientific boundary: PRE + M1 + M2 + M3, never raw rows.

    The monetary contract is explicit: ranking happens in a selected monetary
    system under a frozen monetary mapping registry, never on raw CU.
    """

    pre_state: PREState
    m1_scenarios: tuple[AlignedScenario, ...]
    m2_consequences: tuple[ScenarioConsequence, ...]
    candidates: tuple[CandidateAction, ...]
    material_coverage_contract: ActionMaterialCoverageContract
    monetary_system: str = "RMB"
    monetary_mapping_registry_id: str
    monetary_mapping_registry_hash: str
    lambda_risk: float = Field(default=0.25, ge=0, le=1)
    alpha: float = Field(default=0.90, gt=0, lt=1)
    seed: int = 0

    @model_validator(mode="after")
    def aligned_chain(self):
        if (
            not self.monetary_mapping_registry_id
            or not self.monetary_mapping_registry_hash
        ):
            raise ValueError("M4_MONETARY_MAPPING_REGISTRY_REQUIRED")
        episode = self.pre_state.decision_node.episode_id
        node = self.pre_state.decision_node.decision_node_id
        if not self.m1_scenarios or not self.m2_consequences:
            raise ValueError("M4_SCENARIO_SET_EMPTY")
        if any(
            row.episode_id != episode or row.decision_node_id != node
            for row in self.m1_scenarios
        ):
            raise ValueError("M4_M1_PRE_IDENTITY_MISMATCH")
        m1_ids = tuple(row.scenario_id for row in self.m1_scenarios)
        m2_ids = tuple(row.scenario_id for row in self.m2_consequences)
        if len(m1_ids) != len(set(m1_ids)) or len(m2_ids) != len(set(m2_ids)):
            raise ValueError("M4_DUPLICATE_SCENARIO_ID")
        m1 = {(row.scenario_id, row.scenario_weight) for row in self.m1_scenarios}
        m2 = {(row.scenario_id, row.scenario_weight) for row in self.m2_consequences}
        if m1 != m2 or any(
            row.decision_node_id != node for row in self.m2_consequences
        ):
            raise ValueError("M4_M1_M2_SCENARIO_LINEAGE_MISMATCH")
        if any(row.scenario_id not in m1_ids for row in self.m2_consequences):
            raise ValueError("M4_M2_SCENARIO_ID_UNKNOWN")
        scopes = []
        for row in self.m2_consequences:
            if (
                tuple(item.component_id for item in row.component_vector.rows)
                != COMPONENTS
            ):
                raise ValueError("M4_M2_SEVEN_COMPONENT_CONTRACT_REQUIRED")
            scopes.append(row.consequence_scope)
        if not any(candidate.template_id == "A00" for candidate in self.candidates):
            raise ValueError("M4_A00_BASELINE_CANDIDATE_REQUIRED")
        if scopes and any(not scopes[0].compatible_with(item) for item in scopes[1:]):
            raise ValueError("M4_COMMON_ESTIMAND_SCOPE_MISMATCH")
        if scopes and (
            scopes[0].material_coverage_contract_id
            != self.material_coverage_contract.contract_id
        ):
            raise ValueError("M4_MATERIAL_COVERAGE_CONTRACT_MISMATCH")
        identities = tuple(
            (item.action_index, item.candidate_index) for item in self.candidates
        )
        if len(identities) != len(set(identities)):
            raise ValueError("M4_STABLE_CANDIDATE_INDEX_DUPLICATE")
        candidate_ids = tuple(item.candidate_action_id for item in self.candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("M4_DUPLICATE_CANDIDATE_ID")
        return self
