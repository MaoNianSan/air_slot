from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import EvidenceClass, SupportState
from model.common.estimand import ConsequenceScope, FormalEstimandStatus
from model.common.value_objects import FrozenModel
from model.PRE.transformation import ConstructionType


COMPONENTS = CONSEQUENCE_COMPONENTS
Component = Literal[
    "F_continuity",
    "F_execution",
    "F_propagation",
    "P_time",
    "P_itinerary",
    "P_service",
    "R_operating",
]


class ValuationStatus(str, Enum):
    VALUATION_FROZEN = "VALUATION_FROZEN"
    VALUATION_NOT_FROZEN = "VALUATION_NOT_FROZEN"
    VALUATION_NOT_REQUIRED_FOR_SCOPE = "VALUATION_NOT_REQUIRED_FOR_SCOPE"
    VALUATION_UNSUPPORTED = "VALUATION_UNSUPPORTED"


class ScientificContextValue(FrozenModel):
    object_id: str = Field(min_length=1)
    value: Any | None
    unit: str = Field(min_length=1)
    support_state: SupportState
    evidence_class: EvidenceClass
    construction_type: ConstructionType
    source_time: datetime | None = None
    reference_period: str | None = None
    freeze_id: str | None = None
    reason_code: str | None = None
    provenance: tuple[str, ...] = ()

    @model_validator(mode="after")
    def explicit_support(self):
        if self.support_state is SupportState.ABSTAIN:
            if self.value is not None or not self.reason_code:
                raise ValueError("M2_CONTEXT_ABSTAIN_REQUIRES_NULL_AND_REASON")
        elif self.value is None:
            raise ValueError("M2_CONTEXT_NULL_REQUIRES_ABSTAIN")
        if self.evidence_class is EvidenceClass.UNSUPPORTED and (
            self.value is not None or self.support_state is not SupportState.ABSTAIN
        ):
            raise ValueError("UNSUPPORTED_EVIDENCE_MUST_ABSTAIN")
        if self.construction_type is ConstructionType.TRAIN_FROZEN_REFERENCE:
            if self.support_state is not SupportState.ABSTAIN and (
                not self.reference_period or not self.freeze_id
            ):
                raise ValueError("TRAIN_FROZEN_REFERENCE_LINEAGE_REQUIRED")
        return self


class M2ScientificContext(FrozenModel):
    turnaround_reference: ScientificContextValue
    turnaround_floor: ScientificContextValue
    expected_downstream_exposure: ScientificContextValue
    passenger_exposure: ScientificContextValue
    itinerary_disruption_events: ScientificContextValue
    service_policy_reference: ScientificContextValue
    taxi_reference: ScientificContextValue


class ComponentInputContract(FrozenModel):
    component_id: Component
    critical_inputs: tuple[str, ...]
    degradable_inputs: tuple[str, ...] = ()
    irrelevant_inputs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def disjoint_inputs(self):
        groups = (
            set(self.critical_inputs),
            set(self.degradable_inputs),
            set(self.irrelevant_inputs),
        )
        if any(groups[i] & groups[j] for i in range(3) for j in range(i + 1, 3)):
            raise ValueError("COMPONENT_INPUT_ROLES_MUST_BE_DISJOINT")
        return self


class NativeQuantity(FrozenModel):
    component_id: Component
    scenario_id: int
    native_quantity: float | None
    native_unit: str
    driver: str
    evidence_class: EvidenceClass
    support_state: SupportState
    reason_code: str | None = None
    provenance: tuple[str, ...] = ()

    @model_validator(mode="after")
    def explicit(self):
        if self.support_state is SupportState.ABSTAIN:
            if self.native_quantity is not None or not self.reason_code:
                raise ValueError("ABSTAIN_REQUIRES_NULL_AND_REASON")
        elif self.native_quantity is None:
            raise ValueError("NULL_NATIVE_QUANTITY_MUST_ABSTAIN")
        if self.evidence_class is EvidenceClass.UNSUPPORTED and (
            self.native_quantity is not None
            or self.support_state is not SupportState.ABSTAIN
        ):
            raise ValueError("UNSUPPORTED_EVIDENCE_MUST_ABSTAIN")
        return self


class ConsequenceRow(FrozenModel):
    component_id: Component
    scenario_id: int
    aspect: Literal["Flight", "Passenger", "Resource"]
    native_quantity: float | None
    native_unit: str
    driver: str
    constructed_value_cu: float | None
    support_state: SupportState
    evidence_class: EvidenceClass
    valuation_status: ValuationStatus
    valuation_registry_id: str | None = None
    valuation_rule_id: str | None = None
    valuation_parameter_version: str | None = None
    reason_code: str | None = None
    provenance: tuple[str, ...] = ()

    @model_validator(mode="after")
    def value_support_and_valuation(self):
        if self.support_state is SupportState.ABSTAIN:
            if self.native_quantity is not None or self.constructed_value_cu is not None:
                raise ValueError("ABSTAIN_COMPONENT_MUST_REMAIN_NULL")
        if self.constructed_value_cu is not None and (
            self.valuation_status is not ValuationStatus.VALUATION_FROZEN
            or not self.valuation_registry_id
        ):
            raise ValueError("CONSTRUCTED_CU_REQUIRES_FROZEN_VALUATION")
        if self.valuation_status is ValuationStatus.VALUATION_FROZEN and (
            self.constructed_value_cu is None
            or not self.valuation_rule_id
            or not self.valuation_parameter_version
        ):
            raise ValueError("FROZEN_VALUATION_REQUIRES_VALUE_AND_LINEAGE")
        return self


class ComponentVector(FrozenModel):
    rows: tuple[ConsequenceRow, ...]

    @model_validator(mode="after")
    def exact_ontology(self):
        if tuple(row.component_id for row in self.rows) != COMPONENTS:
            raise ValueError("M2_EXACT_SEVEN_COMPONENT_VECTOR_REQUIRED")
        scenario_ids = {row.scenario_id for row in self.rows}
        if len(scenario_ids) != 1:
            raise ValueError("M2_COMPONENT_VECTOR_SCENARIO_MISMATCH")
        return self


class AvailableComponentSumDiagnostic(FrozenModel):
    value_cu: float | None
    included_components: tuple[Component, ...]
    status: Literal["DIAGNOSTIC_AVAILABLE", "NO_VALUED_COMPONENTS"]
    sortable: Literal[False] = False

    @model_validator(mode="after")
    def no_empty_zero(self):
        if not self.included_components:
            if self.value_cu is not None or self.status != "NO_VALUED_COMPONENTS":
                raise ValueError("EMPTY_DIAGNOSTIC_SUM_MUST_BE_NULL")
        elif self.value_cu is None or self.status != "DIAGNOSTIC_AVAILABLE":
            raise ValueError("DIAGNOSTIC_COMPONENTS_REQUIRE_VALUE")
        return self


class FormalEstimandValue(FrozenModel):
    value_cu: float | None
    status: FormalEstimandStatus
    estimand_id: str
    estimand_version: str
    scope_hash: str
    valuation_registry_id: str
    aggregation_rule_id: str
    included_components: tuple[Component, ...]
    reason_code: str | None = None

    @model_validator(mode="after")
    def formal_value_only_when_available(self):
        if self.status is FormalEstimandStatus.FORMAL_AVAILABLE:
            if self.value_cu is None:
                raise ValueError("FORMAL_AVAILABLE_REQUIRES_VALUE")
        elif self.value_cu is not None or not self.reason_code:
            raise ValueError("UNAVAILABLE_FORMAL_ESTIMAND_REQUIRES_NULL_AND_REASON")
        return self


class ScenarioConsequence(FrozenModel):
    decision_node_id: str
    scenario_id: int
    scenario_weight: float
    consequence_scope: ConsequenceScope
    component_vector: ComponentVector
    available_component_sum_diagnostic: AvailableComponentSumDiagnostic
    formal_estimand_value: FormalEstimandValue

    @model_validator(mode="after")
    def aligned_scenario_and_scope(self):
        if any(
            row.scenario_id != self.scenario_id for row in self.component_vector.rows
        ):
            raise ValueError("M2_SCENARIO_COMPONENT_IDENTITY_MISMATCH")
        formal = self.formal_estimand_value
        scope = self.consequence_scope
        if (
            formal.estimand_id,
            formal.estimand_version,
            formal.scope_hash,
            formal.valuation_registry_id,
            formal.aggregation_rule_id,
        ) != (
            scope.estimand_id,
            scope.estimand_version,
            scope.scope_hash,
            scope.valuation_registry_id,
            scope.aggregation_rule_id,
        ):
            raise ValueError("M2_FORMAL_ESTIMAND_SCOPE_MISMATCH")
        return self

