from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.cu_normalization import CUNormalizationStatus
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
    """Deprecated alias of CUNormalizationStatus.

    Kept only for short-term compatibility; the canonical contract uses
    CUNormalizationStatus and CU normalization is separate from any monetary
    mapping.
    """

    VALUATION_FROZEN = "CU_FROZEN"
    VALUATION_NOT_FROZEN = "CU_NOT_FROZEN"
    VALUATION_NOT_REQUIRED_FOR_SCOPE = "CU_NOT_REQUIRED_FOR_SCOPE"
    VALUATION_UNSUPPORTED = "CU_UNSUPPORTED"


class SourceType(str, Enum):
    """Auditable origin of an M2 consequence input or native quantity."""

    DATA = "DATA"
    LITERATURE = "LITERATURE"
    OPERATIONAL_RULE = "OPERATIONAL_RULE"
    SCENARIO_ASSUMPTION = "SCENARIO_ASSUMPTION"
    HYBRID = "HYBRID"


class ConsequenceState(str, Enum):
    BASELINE = "BASELINE"
    ACTION_ADJUSTABLE = "ACTION_ADJUSTABLE"


class ExposureSupportLevel(str, Enum):
    SAME_AIRCRAFT_SUCCESSOR_CHAIN = "SAME_AIRCRAFT_SUCCESSOR_CHAIN"
    SAME_ROUTE_PROPAGATION = "SAME_ROUTE_PROPAGATION"
    AIRPORT_REFERENCE = "AIRPORT_REFERENCE"
    GLOBAL_REFERENCE = "GLOBAL_REFERENCE"
    UNSUPPORTED = "UNSUPPORTED"


class ExposureConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


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
    source_type: SourceType = SourceType.DATA
    support_level: ExposureSupportLevel | None = None
    reference_source: str | None = None
    confidence: ExposureConfidence | None = None
    assumption_scope: str | None = None

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


class M2ScenarioInput(FrozenModel):
    """Strict, scenario-preserving M1 -> M2 boundary.

    Values are copied from one ``M1V2Scenario``. M2 validates identities but
    never reconstructs operational state or reads future observations.
    """

    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0, le=1)
    t_ib_a00_utc: str | None
    r_ib_minutes: float | None = Field(default=None, ge=0)
    d_ob_minutes: float | None = Field(default=None, ge=0)
    d_tx_minutes: float | None = Field(default=None, ge=0)
    d_to_minutes: float | None = Field(default=None, ge=0)
    r_ib_support: SupportState
    d_ob_support: SupportState
    d_tx_support: SupportState
    d_to_support: SupportState
    pre_lineage: tuple[str, ...] = Field(min_length=1)
    reference_lineage: tuple[str, ...] = Field(min_length=1)
    m1_scenario_seed_key: str = Field(min_length=1)

    @classmethod
    def from_m1(
        cls,
        scenario: Any,
        *,
        pre_lineage: tuple[str, ...],
        reference_lineage: tuple[str, ...],
    ) -> "M2ScenarioInput":
        """Copy the public M1 V2 scenario contract without deriving values."""
        from model.M1.contracts import M1V2Scenario

        if not isinstance(scenario, M1V2Scenario):
            raise TypeError("M2_INPUT_MUST_BE_M1_V2_SCENARIO")
        references = tuple(reference_lineage)
        if getattr(scenario, "taxi_reference_id", None):
            references = tuple(
                dict.fromkeys((*references, str(scenario.taxi_reference_id)))
            )
        return cls(
            episode_id=scenario.episode_id,
            decision_node_id=scenario.decision_node_id,
            scenario_id=scenario.scenario_id,
            scenario_weight=scenario.scenario_weight,
            t_ib_a00_utc=scenario.t_ib_a00_utc,
            r_ib_minutes=scenario.r_ib_minutes,
            d_ob_minutes=scenario.d_ob_minutes,
            d_tx_minutes=scenario.d_tx_minutes,
            d_to_minutes=scenario.d_to_minutes,
            r_ib_support=SupportState(scenario.t_ib_support),
            d_ob_support=SupportState(scenario.d_ob_support),
            d_tx_support=SupportState(scenario.d_tx_support),
            d_to_support=SupportState(scenario.d_to_support),
            pre_lineage=tuple(pre_lineage),
            reference_lineage=references,
            m1_scenario_seed_key=scenario.scenario_seed_key,
        )

    @model_validator(mode="after")
    def preserve_m1_identities(self):
        values = {
            "R_IB": (self.r_ib_minutes, self.r_ib_support),
            "D_OB": (self.d_ob_minutes, self.d_ob_support),
            "D_TX": (self.d_tx_minutes, self.d_tx_support),
            "D_TO": (self.d_to_minutes, self.d_to_support),
        }
        for name, (value, support) in values.items():
            if support is SupportState.ABSTAIN and value is not None:
                raise ValueError(f"M2_{name}_ABSTAIN_MUST_BE_NULL")
            if support is not SupportState.ABSTAIN and value is None:
                raise ValueError(f"M2_{name}_SUPPORTED_REQUIRES_VALUE")
        if self.d_to_minutes is not None:
            if self.d_ob_minutes is None or self.d_tx_minutes is None:
                raise ValueError("M2_D_TO_IDENTITY_INPUTS_REQUIRED")
            if abs(self.d_to_minutes - self.d_ob_minutes - self.d_tx_minutes) > 1e-6:
                raise ValueError("M2_D_TO_IDENTITY_VIOLATION")
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
    source_type: SourceType
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
    source_type: SourceType
    cu_status: CUNormalizationStatus = CUNormalizationStatus.CU_UNSUPPORTED
    cu_normalization_registry_id: str | None = None
    cu_normalization_rule_id: str | None = None
    cu_normalization_parameter_version: str | None = None
    reason_code: str | None = None
    provenance: tuple[str, ...] = ()

    @model_validator(mode="after")
    def value_support_and_normalization(self):
        if self.support_state is SupportState.ABSTAIN:
            if self.native_quantity is not None or self.constructed_value_cu is not None:
                raise ValueError("ABSTAIN_COMPONENT_MUST_REMAIN_NULL")
        if self.constructed_value_cu is not None and (
            self.cu_status is not CUNormalizationStatus.CU_FROZEN
            or not self.cu_normalization_registry_id
        ):
            raise ValueError("CONSTRUCTED_CU_REQUIRES_FROZEN_CU_NORMALIZATION")
        if self.cu_status is CUNormalizationStatus.CU_FROZEN and (
            self.constructed_value_cu is None
            or not self.cu_normalization_rule_id
            or not self.cu_normalization_parameter_version
        ):
            raise ValueError("FROZEN_CU_NORMALIZATION_REQUIRES_VALUE_AND_LINEAGE")
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
    cu_normalization_registry_id: str
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
    episode_id: str = "LEGACY_UNSPECIFIED"
    decision_node_id: str
    scenario_id: int
    scenario_weight: float
    consequence_scope: ConsequenceScope
    component_vector: ComponentVector
    available_component_sum_diagnostic: AvailableComponentSumDiagnostic
    formal_estimand_value: FormalEstimandValue
    pre_lineage: tuple[str, ...] = ()
    reference_lineage: tuple[str, ...] = ()
    m1_scenario_seed_key: str | None = None
    consequence_state: ConsequenceState = ConsequenceState.BASELINE
    action_id: str | None = None
    action_adjustments_applied: bool = False

    @model_validator(mode="after")
    def aligned_scenario_and_scope(self):
        if self.consequence_state is ConsequenceState.BASELINE and (
            self.action_id is not None or self.action_adjustments_applied
        ):
            raise ValueError("M2_BASELINE_CANNOT_CONTAIN_ACTION_EFFECT")
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
            formal.cu_normalization_registry_id,
            formal.aggregation_rule_id,
        ) != (
            scope.estimand_id,
            scope.estimand_version,
            scope.scope_hash,
            scope.cu_normalization_registry_id,
            scope.aggregation_rule_id,
        ):
            raise ValueError("M2_FORMAL_ESTIMAND_SCOPE_MISMATCH")
        return self
