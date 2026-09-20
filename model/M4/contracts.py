from __future__ import annotations

from datetime import datetime
from enum import Enum
from math import isclose, isfinite
from typing import Literal

from pydantic import Field, StrictInt, computed_field, model_validator

from model.PRE.contracts.pre_state import DecisionNodeRecord
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import OperationalStage
from model.common.identity import content_id
from model.common.value_objects import FrozenModel


class PriorityRepresentation(str, Enum):
    DELAY = "DELAY"
    CONSEQUENCE = "CONSEQUENCE"


class CommonSupportPolicy(FrozenModel):
    policy_id: Literal[
        "PRIMARY_COMMON_SUPPORT_090",
        "SENSITIVITY_COMMON_SUPPORT_050",
        "FULL_COMMON_SUPPORT_100",
    ]

    @property
    def threshold(self) -> float:
        return {
            "PRIMARY_COMMON_SUPPORT_090": 0.90,
            "SENSITIVITY_COMMON_SUPPORT_050": 0.50,
            "FULL_COMMON_SUPPORT_100": 1.00,
        }[self.policy_id]

    @classmethod
    def primary(cls) -> "CommonSupportPolicy":
        return cls(policy_id="PRIMARY_COMMON_SUPPORT_090")

    @classmethod
    def sensitivity(cls) -> "CommonSupportPolicy":
        return cls(policy_id="SENSITIVITY_COMMON_SUPPORT_050")

    @classmethod
    def full(cls) -> "CommonSupportPolicy":
        return cls(policy_id="FULL_COMMON_SUPPORT_100")


class ComponentSummary(FrozenModel):
    component_id: str
    value: float | None
    unit: str
    reason_code: str | None = None

    @model_validator(mode="after")
    def component_contract(self):
        if self.component_id not in CONSEQUENCE_COMPONENTS:
            raise ValueError("M4_UNKNOWN_COMPONENT")
        if self.value is not None and not isfinite(float(self.value)):
            raise ValueError("M4_COMPONENT_SUMMARY_NONFINITE")
        if self.value is None and not self.reason_code:
            raise ValueError("M4_COMPONENT_SUMMARY_NULL_REQUIRES_REASON")
        return self


class DomainScoreSummary(FrozenModel):
    domain_id: Literal["F", "P", "R"]
    value: float | None
    component_ids: tuple[str, ...]
    reason_code: str | None = None

    @model_validator(mode="after")
    def domain_contract(self):
        expected = {
            "F": ("F_continuity", "F_execution", "F_propagation"),
            "P": ("P_time", "P_itinerary", "P_service"),
            "R": ("R_operating",),
        }[self.domain_id]
        if self.component_ids != expected:
            raise ValueError("M4_DOMAIN_COMPONENT_MAPPING_INVALID")
        if self.value is not None and not isfinite(float(self.value)):
            raise ValueError("M4_DOMAIN_SCORE_NONFINITE")
        if self.value is None and not self.reason_code:
            raise ValueError("M4_DOMAIN_SCORE_NULL_REQUIRES_REASON")
        return self


class PriorityScoreRecord(FrozenModel):
    node: DecisionNodeRecord
    scenario_ids: tuple[int, ...]
    scenario_weights: tuple[float, ...]
    scenario_count: int
    scenario_lineage: tuple[str, ...]
    common_support_scenario_ids: tuple[int, ...]
    common_support_count: int
    common_support_mass: float = Field(ge=0, le=1)
    policy_id: str
    summary_state: Literal["AVAILABLE", "EMPTY_COMMON_SUPPORT"]
    comparative_eligible: bool
    eligibility_reasons: tuple[str, ...] = ()
    support_primary: bool
    support_sensitivity: bool
    support_full: bool
    delay_mean_cs: float | None
    native_cs: tuple[ComponentSummary, ...]
    cu_cs: tuple[ComponentSummary, ...]
    domain_scores: tuple[DomainScoreSummary, ...]
    aggregate_score: float | None
    input_digest: str
    cu_registry_digest: str
    m1_registry_lineage: tuple[str, ...] = ()
    m2_registry_id: str
    m2_registry_version: str
    m2_registry_hash: str
    aggregation_contract_id: str
    m1_registry_id: str | None = None
    m1_registry_version: str | None = None
    m1_registry_hash: str | None = None
    decision_support_output: Literal[True] = True
    operational_action: Literal[False] = False
    optimal_action: Literal[False] = False
    recovery_loss_objective: Literal[False] = False

    @property
    def episode_id(self) -> str:
        return self.node.episode_id

    @property
    def common_support_ids(self) -> tuple[int, ...]:
        return self.common_support_scenario_ids

    @computed_field
    @property
    def score_F(self) -> float | None:
        return self.domain_scores[0].value

    @computed_field
    @property
    def score_P(self) -> float | None:
        return self.domain_scores[1].value

    @computed_field
    @property
    def score_R(self) -> float | None:
        return self.domain_scores[2].value

    @computed_field
    @property
    def score_C(self) -> float | None:
        return self.aggregate_score

    @property
    def decision_node_id(self) -> str:
        return self.node.decision_node_id

    @property
    def decision_time(self) -> datetime:
        return self.node.decision_time

    @property
    def information_cutoff(self) -> datetime:
        return self.node.information_cutoff

    @property
    def operational_stage(self) -> OperationalStage:
        return self.node.operational_stage

    @model_validator(mode="after")
    def score_contract(self):
        if len(self.scenario_ids) != len(self.scenario_weights):
            raise ValueError("M4_SCENARIO_WEIGHT_VECTOR_INVALID")
        if len(self.scenario_ids) != len(set(self.scenario_ids)):
            raise ValueError("M4_DUPLICATE_SCENARIO_ID")
        if any(not isfinite(float(item)) or item <= 0 for item in self.scenario_weights):
            raise ValueError("M4_SCENARIO_WEIGHTS_INVALID")
        if not isclose(sum(self.scenario_weights), 1.0, rel_tol=1e-9, abs_tol=1e-6):
            raise ValueError("M4_SCENARIO_WEIGHTS_INVALID")
        if self.scenario_count != len(self.scenario_ids):
            raise ValueError("M4_SCENARIO_COUNT_INVALID")
        if self.common_support_count != len(self.common_support_scenario_ids):
            raise ValueError("M4_COMMON_SUPPORT_COUNT_INVALID")
        if not set(self.common_support_scenario_ids) <= set(self.scenario_ids):
            raise ValueError("M4_COMMON_SUPPORT_SCENARIO_ID_INVALID")
        expected_mass = sum(
            weight
            for scenario_id, weight in zip(
                self.scenario_ids, self.scenario_weights, strict=True
            )
            if scenario_id in self.common_support_scenario_ids
        )
        if not isclose(
            self.common_support_mass,
            expected_mass,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise ValueError("M4_COMMON_SUPPORT_MASS_MISMATCH")
        if tuple(item.component_id for item in self.native_cs) != CONSEQUENCE_COMPONENTS:
            raise ValueError("M4_SEVEN_COMPONENT_VECTOR_REQUIRED")
        if tuple(item.component_id for item in self.cu_cs) != CONSEQUENCE_COMPONENTS:
            raise ValueError("M4_SEVEN_COMPONENT_VECTOR_REQUIRED")
        if tuple(item.domain_id for item in self.domain_scores) != ("F", "P", "R"):
            raise ValueError("M4_DOMAIN_VECTOR_REQUIRED")
        if self.summary_state == "EMPTY_COMMON_SUPPORT":
            if self.common_support_mass != 0:
                raise ValueError("M4_EMPTY_SUPPORT_MASS_MISMATCH")
            if any(item.value is not None for item in self.native_cs + self.cu_cs):
                raise ValueError("M4_EMPTY_SUPPORT_VALUES_MUST_BE_NULL")
        if self.aggregate_score is not None and not isfinite(float(self.aggregate_score)):
            raise ValueError("M4_AGGREGATE_SCORE_NONFINITE")
        return self


class PopulationScope(FrozenModel):
    kind: Literal["LIVE_EPOCH", "RETROSPECTIVE_STAGE"]
    decision_time: datetime | None = None
    stage: OperationalStage | None = None
    cohort_id: str | None = None

    @model_validator(mode="after")
    def scope_contract(self):
        if self.kind == "LIVE_EPOCH":
            if self.decision_time is None or self.stage is not None or self.cohort_id is not None:
                raise ValueError("M4_LIVE_SCOPE_REQUIRES_DECISION_TIME")
        else:
            if self.stage is None or not self.cohort_id or self.decision_time is not None:
                raise ValueError("M4_RETROSPECTIVE_SCOPE_REQUIRES_STAGE_COHORT")
        return self


class ExcludedNode(FrozenModel):
    episode_id: str
    decision_node_id: str
    reason_code: str
    decision_time: datetime


class PriorityPopulation(FrozenModel):
    records: tuple[PriorityScoreRecord, ...]
    excluded: tuple[ExcludedNode, ...]
    scope: PopulationScope
    population_digest: str
    policy_id: str
    cu_registry_digest: str
    aggregation_contract_id: str
    is_live_queue: bool

    @model_validator(mode="after")
    def population_contract(self):
        if self.is_live_queue != (self.scope.kind == "LIVE_EPOCH"):
            raise ValueError("M4_POPULATION_LIVE_FLAG_MISMATCH")
        ids = tuple(item.decision_node_id for item in self.records)
        if len(ids) != len(set(ids)):
            raise ValueError("M4_POPULATION_ID_DUPLICATE")
        if any(
            (item.policy_id, item.cu_registry_digest, item.aggregation_contract_id)
            != (self.policy_id, self.cu_registry_digest, self.aggregation_contract_id)
            for item in self.records
        ):
            raise ValueError("M4_COMPARISON_BASIS_MISMATCH")
        if self.population_digest != content_id(
            {
                "scope": self.scope.model_dump(mode="json"),
                "policy_id": self.policy_id,
                "cu_registry_digest": self.cu_registry_digest,
                "aggregation_contract_id": self.aggregation_contract_id,
                "records": tuple(
                    (item.episode_id, item.decision_node_id, item.input_digest)
                    for item in sorted(self.records, key=lambda x: x.decision_node_id)
                ),
            }
        ):
            raise ValueError("M4_POPULATION_DIGEST_MISMATCH")
        return self


class PriorityOrdering(FrozenModel):
    population_digest: str
    representation: PriorityRepresentation
    entries: tuple[tuple[str, float, int], ...]
    excluded: tuple[ExcludedNode, ...] = ()
    provenance: tuple[str, ...] = ()
    decision_support_output: Literal[True] = True
    operational_action: Literal[False] = False
    optimal_action: Literal[False] = False
    recovery_loss_objective: Literal[False] = False

    @model_validator(mode="after")
    def ordering_contract(self):
        ranks = tuple(item[2] for item in self.entries)
        if ranks != tuple(range(1, len(ranks) + 1)):
            raise ValueError("M4_ORDERING_RANK_INVALID")
        node_ids = tuple(item[0] for item in self.entries)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("M4_POPULATION_ID_DUPLICATE")
        if any(not isfinite(float(item[1])) for item in self.entries):
            raise ValueError("M4_ORDERING_SCORE_INVALID")
        return self

    @property
    def ranked_nodes(self) -> tuple[tuple[str, float, int], ...]:
        return self.entries


class ScreeningCapacity(FrozenModel):
    k: StrictInt
    semantics: Literal["SCREENING_ATTENTION_ONLY"] = "SCREENING_ATTENTION_ONLY"

    @model_validator(mode="after")
    def positive_integer(self):
        if isinstance(self.k, bool) or not isinstance(self.k, int) or self.k <= 0:
            raise ValueError("M4_CAPACITY_INVALID")
        return self


class ScreeningShortlist(FrozenModel):
    population_digest: str
    representation: PriorityRepresentation
    requested_k: int
    effective_k: int
    population_size: int
    selected_node_ids: tuple[str, ...]
    boundary_score: float | None
    boundary_tie_count: int
    status: Literal["READY", "EMPTY_POPULATION"]
    reason_code: str | None = None
    decision_support_output: Literal[True] = True
    operational_action: Literal[False] = False
    optimal_action: Literal[False] = False
    recovery_loss_objective: Literal[False] = False

    @model_validator(mode="after")
    def shortlist_contract(self):
        if isinstance(self.requested_k, bool) or self.requested_k <= 0:
            raise ValueError("M4_CAPACITY_INVALID")
        if self.population_size < 0 or not 0 <= self.effective_k <= self.population_size:
            raise ValueError("M4_SHORTLIST_SIZE_INVALID")
        if len(self.selected_node_ids) != self.effective_k:
            raise ValueError("M4_SHORTLIST_SELECTION_INVALID")
        if self.status == "EMPTY_POPULATION":
            if self.population_size != 0 or self.effective_k != 0 or self.boundary_score is not None:
                raise ValueError("M4_EMPTY_POPULATION_OUTPUT_INVALID")
            if self.reason_code != "M4_EMPTY_POPULATION":
                raise ValueError("M4_EMPTY_POPULATION_REASON_INVALID")
        elif self.status == "READY":
            if self.population_size == 0 or self.effective_k == 0 or self.boundary_score is None:
                raise ValueError("M4_READY_SHORTLIST_OUTPUT_INVALID")
        return self


class RankDisplacement(FrozenModel):
    decision_node_id: str
    delay_rank: int
    consequence_rank: int
    rank_displacement: int
    absolute_rank_displacement: int


class PriorityAlignmentRecord(FrozenModel):
    population_digest: str
    delay: PriorityOrdering
    consequence: PriorityOrdering
    delay_shortlist: ScreeningShortlist
    consequence_shortlist: ScreeningShortlist
    intersection: tuple[str, ...]
    delay_only: tuple[str, ...]
    consequence_only: tuple[str, ...]
    rank_displacements: tuple[RankDisplacement, ...]
    overlap_count: int
    replacement_count: int
    overlap_rate: float | None
    replacement_rate: float | None
    status: Literal["READY", "UNSUPPORTED"]
    reason_code: str | None = None
    decision_support_output: Literal[True] = True
    operational_action: Literal[False] = False
    optimal_action: Literal[False] = False
    recovery_loss_objective: Literal[False] = False

    @model_validator(mode="after")
    def alignment_contract(self):
        if self.delay.population_digest != self.population_digest:
            raise ValueError("M4_ALIGNMENT_POPULATION_MISMATCH")
        if self.consequence.population_digest != self.population_digest:
            raise ValueError("M4_ALIGNMENT_POPULATION_MISMATCH")
        if self.delay_shortlist.population_digest != self.population_digest:
            raise ValueError("M4_ALIGNMENT_SHORTLIST_MISMATCH")
        if self.consequence_shortlist.population_digest != self.population_digest:
            raise ValueError("M4_ALIGNMENT_SHORTLIST_MISMATCH")
        k = self.delay_shortlist.effective_k
        if self.overlap_count != len(self.intersection):
            raise ValueError("M4_ALIGNMENT_OVERLAP_COUNT_INVALID")
        if self.replacement_count != len(self.delay_only):
            raise ValueError("M4_ALIGNMENT_REPLACEMENT_COUNT_INVALID")
        if k:
            if self.overlap_rate is None or self.replacement_rate is None:
                raise ValueError("M4_ALIGNMENT_RATE_INVALID")
        elif self.overlap_rate is not None or self.replacement_rate is not None:
            raise ValueError("M4_EMPTY_POPULATION_RATE_MUST_BE_NULL")
        return self


__all__ = [
    "CommonSupportPolicy",
    "ComponentSummary",
    "DomainScoreSummary",
    "ExcludedNode",
    "PopulationScope",
    "PriorityAlignmentRecord",
    "PriorityOrdering",
    "PriorityPopulation",
    "PriorityRepresentation",
    "PriorityScoreRecord",
    "RankDisplacement",
    "ScreeningCapacity",
    "ScreeningShortlist",
]
