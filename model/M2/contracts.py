from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field, computed_field, model_validator

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.cu_normalization import CUNormalizationStatus
from model.common.enums import EvidenceClass, SupportState
from model.common.estimand import ConsequenceScope, FormalEstimandStatus
from model.common.identity import content_id
from model.common.value_objects import FrozenModel
from model.PRE import ConstructionType

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
    reference_id: str | None = None
    reference_version: str | None = None
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

    @computed_field
    @property
    def lineage_hash(self) -> str:
        return content_id(
            {
                "object_id": self.object_id,
                "support_state": self.support_state.value,
                "source_type": self.source_type.value,
                "support_level": (
                    self.support_level.value if self.support_level else None
                ),
                "reference_source": self.reference_source,
                "reference_id": self.reference_id,
                "reference_version": self.reference_version,
                "confidence": self.confidence.value if self.confidence else None,
                "reference_period": self.reference_period,
                "freeze_id": self.freeze_id,
                "provenance": self.provenance,
            }
        )


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
    expected_passengers_per_flight: ScientificContextValue
    connection_share_reference: ScientificContextValue
    itinerary_buffer_reference: ScientificContextValue
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
    scenario_weight: float = Field(gt=0, le=1)
    native_quantity: float | None
    native_unit: str
    driver: str
    evidence_class: EvidenceClass
    support_state: SupportState
    source_type: SourceType
    reference_source: str = Field(min_length=1)
    reference_lineage: tuple[str, ...] = Field(min_length=1)
    confidence: ExposureConfidence
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

    @computed_field
    @property
    def artifact_id(self) -> str:
        return content_id(
            {
                "component_id": self.component_id,
                "scenario_id": self.scenario_id,
                "scenario_weight": self.scenario_weight,
                "native_quantity": self.native_quantity,
                "native_unit": self.native_unit,
                "driver": self.driver,
                "evidence_class": self.evidence_class.value,
                "support_state": self.support_state.value,
                "source_type": self.source_type.value,
                "reference_source": self.reference_source,
                "reference_lineage": self.reference_lineage,
                "confidence": self.confidence.value,
                "reason_code": self.reason_code,
                "provenance": self.provenance,
            }
        )

    @computed_field
    @property
    def reference_lineage_hash(self) -> str:
        return content_id(
            {
                "reference_source": self.reference_source,
                "reference_lineage": self.reference_lineage,
                "confidence": self.confidence.value,
            }
        )


class CUQuantity(FrozenModel):
    """A distinct CU object with version-sensitive frozen-scale identity."""

    component_id: Component
    scenario_id: int
    scenario_weight: float = Field(gt=0, le=1)
    value_cu: float | None
    status: CUNormalizationStatus
    native_artifact_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    registry_id: str | None = None
    registry_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    rule_id: str | None = None
    rule_version: str | None = None
    normalization_parameter: float | None = Field(default=None, gt=0)
    scale_freeze_id: str | None = None
    reference_period: str | None = None
    artifact_id: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def frozen(
        cls,
        *,
        native: NativeQuantity,
        value_cu: float,
        registry_id: str,
        registry_hash: str,
        rule_id: str,
        rule_version: str,
        normalization_parameter: float,
        scale_freeze_id: str,
        reference_period: str,
    ) -> "CUQuantity":
        payload = {
            "component_id": native.component_id,
            "scenario_id": native.scenario_id,
            "scenario_weight": native.scenario_weight,
            "value_cu": float(value_cu),
            "native_artifact_id": native.artifact_id,
            "registry_id": registry_id,
            "registry_hash": registry_hash,
            "rule_id": rule_id,
            "rule_version": rule_version,
            "normalization_parameter": float(normalization_parameter),
            "scale_freeze_id": scale_freeze_id,
            "reference_period": reference_period,
        }
        return cls(
            **payload,
            status=CUNormalizationStatus.CU_FROZEN,
            artifact_id=content_id(payload),
        )

    @classmethod
    def unavailable(
        cls,
        *,
        native: NativeQuantity,
        status: CUNormalizationStatus,
        registry_id: str | None = None,
    ) -> "CUQuantity":
        if status is CUNormalizationStatus.CU_FROZEN:
            raise ValueError("M2_UNAVAILABLE_CU_CANNOT_BE_FROZEN")
        return cls(
            component_id=native.component_id,
            scenario_id=native.scenario_id,
            scenario_weight=native.scenario_weight,
            value_cu=None,
            status=status,
            native_artifact_id=native.artifact_id,
            registry_id=registry_id,
        )

    @model_validator(mode="after")
    def frozen_lineage_complete(self):
        frozen_fields = (
            self.value_cu,
            self.registry_id,
            self.registry_hash,
            self.rule_id,
            self.rule_version,
            self.normalization_parameter,
            self.scale_freeze_id,
            self.reference_period,
            self.artifact_id,
        )
        if self.status is CUNormalizationStatus.CU_FROZEN:
            if any(value is None for value in frozen_fields):
                raise ValueError("M2_FROZEN_CU_REQUIRES_COMPLETE_SCALE_LINEAGE")
            payload = {
                "component_id": self.component_id,
                "scenario_id": self.scenario_id,
                "scenario_weight": self.scenario_weight,
                "value_cu": self.value_cu,
                "native_artifact_id": self.native_artifact_id,
                "registry_id": self.registry_id,
                "registry_hash": self.registry_hash,
                "rule_id": self.rule_id,
                "rule_version": self.rule_version,
                "normalization_parameter": self.normalization_parameter,
                "scale_freeze_id": self.scale_freeze_id,
                "reference_period": self.reference_period,
            }
            if self.artifact_id != content_id(payload):
                raise ValueError("M2_CU_ARTIFACT_ID_MISMATCH")
        elif self.value_cu is not None or self.artifact_id is not None:
            raise ValueError("M2_UNFROZEN_CU_MUST_NOT_HAVE_VALUE_OR_ARTIFACT")
        return self

    def compatible_with_registry(self, registry: Any) -> bool:
        """Return false when registry/rule/scale lineage has changed."""
        if self.status is not CUNormalizationStatus.CU_FROZEN:
            return False
        try:
            rule = registry.rule(self.component_id)
        except (AttributeError, ValueError):
            return False
        return (
            self.registry_id,
            self.registry_hash,
            self.rule_id,
            self.rule_version,
            self.normalization_parameter,
            self.scale_freeze_id,
            self.reference_period,
        ) == (
            registry.registry_id,
            registry.digest(),
            rule.rule_id,
            rule.version,
            rule.normalization_parameter,
            rule.freeze_id,
            rule.reference_period,
        )


class ConsequenceRow(FrozenModel):
    component_id: Component
    scenario_id: int
    scenario_weight: float = Field(gt=0, le=1)
    aspect: Literal["Flight", "Passenger", "Resource"]
    native_quantity: float | None
    native_unit: str
    driver: str
    constructed_value_cu: float | None
    support_state: SupportState
    evidence_class: EvidenceClass
    source_type: SourceType
    reference_source: str = Field(min_length=1)
    reference_lineage: tuple[str, ...] = Field(min_length=1)
    confidence: ExposureConfidence
    native_artifact_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    cu_quantity: CUQuantity
    cu_status: CUNormalizationStatus = CUNormalizationStatus.CU_UNSUPPORTED
    cu_normalization_registry_id: str | None = None
    cu_normalization_rule_id: str | None = None
    cu_normalization_parameter_version: str | None = None
    reason_code: str | None = None
    provenance: tuple[str, ...] = ()

    @model_validator(mode="after")
    def value_support_and_normalization(self):
        if self.support_state is SupportState.ABSTAIN:
            if (
                self.native_quantity is not None
                or self.constructed_value_cu is not None
            ):
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
        cu = self.cu_quantity
        if (
            cu.component_id,
            cu.scenario_id,
            cu.scenario_weight,
            cu.value_cu,
            cu.status,
            cu.native_artifact_id,
        ) != (
            self.component_id,
            self.scenario_id,
            self.scenario_weight,
            self.constructed_value_cu,
            self.cu_status,
            self.native_artifact_id,
        ):
            raise ValueError("M2_CU_OBJECT_ROW_MISMATCH")
        if self.cu_status is CUNormalizationStatus.CU_FROZEN and (
            cu.registry_id != self.cu_normalization_registry_id
            or cu.rule_id != self.cu_normalization_rule_id
            or cu.rule_version != self.cu_normalization_parameter_version
        ):
            raise ValueError("M2_CU_OBJECT_LINEAGE_MISMATCH")
        return self

    @computed_field
    @property
    def cu_artifact_id(self) -> str | None:
        return self.cu_quantity.artifact_id

    @computed_field
    @property
    def reference_lineage_hash(self) -> str:
        return content_id(
            {
                "reference_source": self.reference_source,
                "reference_lineage": self.reference_lineage,
                "confidence": self.confidence.value,
            }
        )


class ComponentVector(FrozenModel):
    rows: tuple[ConsequenceRow, ...]

    @model_validator(mode="after")
    def exact_ontology(self):
        if tuple(row.component_id for row in self.rows) != COMPONENTS:
            raise ValueError("M2_EXACT_SEVEN_COMPONENT_VECTOR_REQUIRED")
        scenario_ids = {row.scenario_id for row in self.rows}
        if len(scenario_ids) != 1:
            raise ValueError("M2_COMPONENT_VECTOR_SCENARIO_MISMATCH")
        scenario_weights = {row.scenario_weight for row in self.rows}
        if len(scenario_weights) != 1:
            raise ValueError("M2_COMPONENT_VECTOR_WEIGHT_MISMATCH")
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
        if any(
            abs(row.scenario_weight - self.scenario_weight) > 1e-12
            for row in self.component_vector.rows
        ):
            raise ValueError("M2_SCENARIO_COMPONENT_WEIGHT_MISMATCH")
        if self.reference_lineage and any(
            not set(self.reference_lineage) <= set(row.reference_lineage)
            for row in self.component_vector.rows
        ):
            raise ValueError("M2_SCENARIO_REFERENCE_LINEAGE_NOT_PRESERVED")
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

    @computed_field
    @property
    def consequence_artifact_id(self) -> str:
        return content_id(
            {
                "episode_id": self.episode_id,
                "decision_node_id": self.decision_node_id,
                "scenario_id": self.scenario_id,
                "scenario_weight": self.scenario_weight,
                "scope_hash": self.consequence_scope.scope_hash,
                "native_artifact_ids": tuple(
                    row.native_artifact_id for row in self.component_vector.rows
                ),
                "cu_artifact_ids": tuple(
                    row.cu_artifact_id for row in self.component_vector.rows
                ),
                "pre_lineage": self.pre_lineage,
                "reference_lineage": self.reference_lineage,
                "m1_scenario_seed_key": self.m1_scenario_seed_key,
                "consequence_state": self.consequence_state.value,
            }
        )

    def m3_baseline_payload(self) -> dict[str, Any]:
        """Serialize the action-free boundary without creating an M2 -> M3 import."""
        if self.consequence_state is not ConsequenceState.BASELINE:
            raise ValueError("M2_M3_EXPORT_REQUIRES_BASELINE_C0")
        if self.action_id is not None or self.action_adjustments_applied:
            raise ValueError("M2_M3_EXPORT_REJECTS_ACTION_LEAKAGE")
        payload = {
            "episode_id": self.episode_id,
            "decision_node_id": self.decision_node_id,
            "scenario_id": self.scenario_id,
            "scenario_weight": self.scenario_weight,
            "baseline_consequence_id": self.consequence_artifact_id,
            "component_ids": tuple(
                row.component_id for row in self.component_vector.rows
            ),
            "native_artifact_ids": tuple(
                row.native_artifact_id for row in self.component_vector.rows
            ),
            "cu_artifact_ids": tuple(
                row.cu_artifact_id for row in self.component_vector.rows
            ),
            "component_quantities": tuple(
                {
                    "component_id": row.component_id,
                    "scenario_id": row.scenario_id,
                    "scenario_weight": row.scenario_weight,
                    "value_cu": row.constructed_value_cu,
                    "native_support_state": row.support_state.value,
                    "support_state": (
                        SupportState.SUPPORTED.value
                        if row.constructed_value_cu is not None
                        else SupportState.ABSTAIN.value
                    ),
                    "cu_artifact_id": row.cu_artifact_id,
                    "reference_lineage_hash": row.reference_lineage_hash,
                    "reason_code": (
                        row.reason_code
                        if row.constructed_value_cu is not None
                        else row.reason_code or row.cu_status.value
                    ),
                }
                for row in self.component_vector.rows
            ),
            "reference_lineage": self.reference_lineage,
            "consequence_state": "BASELINE",
            "action_id": None,
            "action_adjustments_applied": False,
        }
        return {**payload, "baseline_interface_hash": content_id(payload)}


class ScenarioConsequenceDistribution(FrozenModel):
    """Immutable all-scenario M2 output for one M1 decision node."""

    consequences: tuple[ScenarioConsequence, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def complete_node_distribution(self):
        identities = {
            (item.episode_id, item.decision_node_id) for item in self.consequences
        }
        if len(identities) != 1:
            raise ValueError("M2_DISTRIBUTION_MIXED_DECISION_NODES")
        scenario_ids = tuple(item.scenario_id for item in self.consequences)
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("M2_DISTRIBUTION_DUPLICATE_SCENARIO_ID")
        if abs(sum(item.scenario_weight for item in self.consequences) - 1.0) > 1e-6:
            raise ValueError("M2_DISTRIBUTION_WEIGHTS_MUST_SUM_TO_ONE")
        return self

    @computed_field
    @property
    def scenario_ids(self) -> tuple[int, ...]:
        return tuple(item.scenario_id for item in self.consequences)

    @computed_field
    @property
    def scenario_weights(self) -> tuple[float, ...]:
        return tuple(item.scenario_weight for item in self.consequences)

    @computed_field
    @property
    def distribution_artifact_id(self) -> str:
        return content_id(
            {
                "consequence_artifact_ids": tuple(
                    item.consequence_artifact_id for item in self.consequences
                ),
                "scenario_ids": self.scenario_ids,
                "scenario_weights": self.scenario_weights,
            }
        )
