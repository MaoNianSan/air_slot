from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Mapping


M2_CONTRACT_VERSION = "EPISODE_PRE_ACTION_LOSS_RECONSTRUCTION_V2"
M2_CONTEXT_BUILDER_VERSION = "PRE_CORE_V2_TO_M2_CONTEXT_V1"


class M2ContractError(ValueError):
    pass


class M2InputStatus(str, Enum):
    VALID = "VALID"
    PARTIAL = "PARTIAL"
    PROXY_SUPPORTED = "PROXY_SUPPORTED"
    ABSTAIN = "ABSTAIN"


class ActivationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PROXY_ACTIVE = "PROXY_ACTIVE"
    UNSUPPORTED = "UNSUPPORTED"
    DISABLED_BY_CONFIG = "DISABLED_BY_CONFIG"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class AvailabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PROXY_AVAILABLE = "PROXY_AVAILABLE"
    MISSING = "MISSING"
    UNSUPPORTED = "UNSUPPORTED"
    TAIL_UNRESOLVED = "TAIL_UNRESOLVED"


class ContextDirection(str, Enum):
    LARGER_IS_HIGHER_RISK = "LARGER_IS_HIGHER_RISK"
    LARGER_IS_LOWER_RISK = "LARGER_IS_LOWER_RISK"
    NON_DIRECTIONAL = "NON_DIRECTIONAL"


class ParameterStatus(str, Enum):
    CONFIGURED = "CONFIGURED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    REQUIRES_DEVELOPMENT_FREEZE = "REQUIRES_DEVELOPMENT_FREEZE"


@dataclass(frozen=True)
class ContextFieldSpec:
    direction: ContextDirection
    normalized_unit_interval: bool


CONTEXT_FIELD_REGISTRY: Mapping[str, ContextFieldSpec] = {
    "continuity_exposure": ContextFieldSpec(ContextDirection.LARGER_IS_HIGHER_RISK, True),
    "downstream_leg_count": ContextFieldSpec(ContextDirection.LARGER_IS_HIGHER_RISK, False),
    "execution_window_margin": ContextFieldSpec(ContextDirection.LARGER_IS_LOWER_RISK, True),
    "execution_window_pressure": ContextFieldSpec(ContextDirection.LARGER_IS_HIGHER_RISK, True),
    "aircraft_flexibility": ContextFieldSpec(ContextDirection.LARGER_IS_LOWER_RISK, True),
    "aircraft_constraint": ContextFieldSpec(ContextDirection.LARGER_IS_HIGHER_RISK, True),
    "passenger_load_proxy": ContextFieldSpec(ContextDirection.NON_DIRECTIONAL, False),
    "connection_slack": ContextFieldSpec(ContextDirection.LARGER_IS_LOWER_RISK, True),
    "connection_pressure": ContextFieldSpec(ContextDirection.LARGER_IS_HIGHER_RISK, True),
    "rebooking_scarcity": ContextFieldSpec(ContextDirection.LARGER_IS_HIGHER_RISK, True),
    "airport_flow_pressure": ContextFieldSpec(ContextDirection.LARGER_IS_HIGHER_RISK, True),
    "infrastructure_flexibility": ContextFieldSpec(ContextDirection.LARGER_IS_LOWER_RISK, True),
    "infrastructure_constraint": ContextFieldSpec(ContextDirection.LARGER_IS_HIGHER_RISK, True),
    "resource_availability": ContextFieldSpec(ContextDirection.LARGER_IS_LOWER_RISK, True),
    "resource_scarcity": ContextFieldSpec(ContextDirection.LARGER_IS_HIGHER_RISK, True),
    "ground_support_pressure": ContextFieldSpec(ContextDirection.LARGER_IS_HIGHER_RISK, True),
}


@dataclass(frozen=True)
class M2Metadata:
    episode_id: str
    snapshot_id: str
    snapshot_version: int
    query_time: datetime
    information_cutoff: datetime
    pre_bundle_id: str
    m1_bundle_id: str
    m1_model_version: str
    m1_sampling_version: str
    m2_contract_version: str = M2_CONTRACT_VERSION


@dataclass(frozen=True)
class M2ContextMetadata:
    episode_id: str
    query_time: datetime
    information_cutoff: datetime
    pre_bundle_id: str
    pre_contract_id: str
    pre_schema_version: str
    pre_research_revision: str
    builder_version: str = M2_CONTEXT_BUILDER_VERSION


@dataclass(frozen=True)
class FlightContext:
    successor_sobt: object | None = None
    turnaround_reference_minutes: float | None = None
    turnaround_reference_type: str = "UNSUPPORTED"
    continuity_exposure: float | None = None
    downstream_leg_count: int | None = None
    execution_window_margin: float | None = None
    execution_window_pressure: float | None = None
    aircraft_flexibility: float | None = None
    aircraft_constraint: float | None = None


@dataclass(frozen=True)
class PassengerContext:
    passenger_load_proxy: float | None = None
    connection_pressure: float | None = None
    connection_slack: float | None = None
    rebooking_scarcity: float | None = None


@dataclass(frozen=True)
class ResourceContext:
    airport_flow_pressure: float | None = None
    infrastructure_flexibility: float | None = None
    infrastructure_constraint: float | None = None
    resource_availability: float | None = None
    resource_scarcity: float | None = None
    ground_support_pressure: float | None = None


@dataclass(frozen=True)
class M2ContextBundle:
    metadata: M2ContextMetadata
    flight_context: FlightContext
    passenger_context: PassengerContext
    resource_context: ResourceContext
    context_support: Mapping[str, AvailabilityStatus | str]
    normalization_version: str
    provenance: Mapping[str, Mapping[str, object]]

    def __post_init__(self) -> None:
        if not self.metadata.pre_bundle_id:
            raise M2ContractError("M2_CONTEXT_PRE_BUNDLE_ID_MISSING")
        unknown = set(self.context_support) - set(CONTEXT_FIELD_REGISTRY) - {
            "successor_sobt",
            "turnaround_reference_minutes",
        }
        if unknown:
            raise M2ContractError(
                f"M2_CONTEXT_SUPPORT_FIELD_UNKNOWN:{','.join(sorted(unknown))}"
            )


@dataclass(frozen=True)
class ValuationContext:
    subitem_value_parameters: Mapping[str, object] = field(default_factory=dict)
    rule_parameters: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    constructed_unit_version: str = "CU_V2"
    valuation_version: str = "NOT_CONFIGURED"
    parameter_status: ParameterStatus | str = ParameterStatus.REQUIRES_DEVELOPMENT_FREEZE
    currency_mapping_version: str = "NOT_CONFIGURED"
    currency: str = "RMB"
    currency_mapping_mode: str = "NOT_CONFIGURED"
    channel_rates: Mapping[str, object] = field(default_factory=dict)
    learned_correction_enabled: bool = False
    correction_rho: Mapping[str, float] = field(default_factory=dict)
    correction_epsilon: float | None = None
    correction_bound_status: ParameterStatus | str = ParameterStatus.NOT_CONFIGURED
    test_only: bool = False
    source: str = "NOT_CONFIGURED"

    def __post_init__(self) -> None:
        status = ParameterStatus(self.parameter_status)
        if status is ParameterStatus.CONFIGURED and not self.valuation_version:
            raise M2ContractError("M2_VALUATION_VERSION_MISSING")
        if self.source == "SYNTHETIC_FIXTURE" and not self.test_only:
            raise M2ContractError("M2_SYNTHETIC_FIXTURE_MUST_BE_TEST_ONLY")
        if self.learned_correction_enabled:
            raise M2ContractError("M2_LEARNED_CORRECTION_MUST_REMAIN_DISABLED")


@dataclass(frozen=True)
class AuditContext:
    evidence_status: Mapping[str, str]
    proxy_status: Mapping[str, str]
    overflow_status: str
    tail_resolution_status: str
    parameter_status: str
    currency_mapping_status: str
    formal_reconstruction_gate: str
    abstain_reasons: tuple[str, ...] = ()
    unresolved_sample_ids: tuple[int, ...] = ()
    audit_status: str = "UNVALIDATED"


@dataclass(frozen=True)
class SubitemActivation:
    subitem: str
    channel: str
    status: ActivationStatus
    support_reason: str
    input_evidence_level: str
    rule_version: str
    value_parameter_version: str
    dependency_status: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class M2InputBundle:
    metadata: M2Metadata
    joint_scenarios: tuple[object, ...]
    flight_context: FlightContext
    passenger_context: PassengerContext
    resource_context: ResourceContext
    context_support: Mapping[str, AvailabilityStatus | str]
    context_provenance: Mapping[str, Mapping[str, object]]
    normalization_version: str
    subitem_activation: Mapping[str, SubitemActivation]
    valuation_context: ValuationContext
    audit_context: AuditContext
    input_status: M2InputStatus

    def __post_init__(self) -> None:
        ids = tuple(getattr(sample, "sample_id", -1) for sample in self.joint_scenarios)
        if ids != tuple(range(len(ids))):
            raise M2ContractError("M2_SAMPLE_ID_ALIGNMENT_FAILED")
        for sample in self.joint_scenarios:
            if getattr(sample, "episode_id", None) != self.metadata.episode_id:
                raise M2ContractError("M2_EPISODE_ALIGNMENT_FAILED")
            if getattr(sample, "snapshot_id", None) != self.metadata.snapshot_id:
                raise M2ContractError("M2_SNAPSHOT_ALIGNMENT_FAILED")
        if len(self.joint_scenarios) == 0:
            raise M2ContractError("M2_SAMPLE_SET_EMPTY")
        if int(self.metadata.snapshot_version) < 1:
            raise M2ContractError("M2_SNAPSHOT_VERSION_INVALID")


@dataclass(frozen=True)
class M2SampleLoss:
    episode_id: str
    snapshot_id: str
    sample_id: int
    sample_weight: float
    turn_deficit_minutes: float | None
    turn_deficit_semantics: str
    extra_offblock_wait_minutes: float | None
    extra_taxi_minutes: float | None
    takeoff_delay_minutes: float | None
    event_status: Mapping[str, str]
    event_semantics: Mapping[str, str]
    event_source: Mapping[str, str]
    quantities: Mapping[str, float | None]
    constructed_units: Mapping[str, float | None]
    channel_constructed_units: Mapping[str, float | None]
    subitem_loss_rmb: Mapping[str, float | None]
    channel_loss_rmb: Mapping[str, float | None]
    total_pre_action_loss_rmb: float | None
    resolved_only_total_pre_action_loss_rmb: float | None
    m2_input_status: M2InputStatus
    tail_resolution_status: str
    evidence_status: Mapping[str, str]
    proxy_status: Mapping[str, str]
    audit_status: str
    overflow_present: bool = False

    @property
    def flight_turn_quantity(self): return self.quantities.get("F_TURN")
    @property
    def flight_wait_quantity(self): return self.quantities.get("F_WAIT")
    @property
    def flight_propagation_quantity(self): return self.quantities.get("F_PROPAGATION")
    @property
    def passenger_delay_quantity(self): return self.quantities.get("P_DELAY")
    @property
    def passenger_connection_quantity(self): return self.quantities.get("P_CONNECTION")
    @property
    def passenger_care_quantity(self): return self.quantities.get("P_CARE")
    @property
    def resource_ground_quantity(self): return self.quantities.get("R_GROUND")
    @property
    def resource_taxi_quantity(self): return self.quantities.get("R_TAXI")
    @property
    def resource_scarcity_quantity(self): return self.quantities.get("R_SCARCITY")
    @property
    def flight_turn_cu(self): return self.constructed_units.get("F_TURN")
    @property
    def flight_wait_cu(self): return self.constructed_units.get("F_WAIT")
    @property
    def flight_propagation_cu(self): return self.constructed_units.get("F_PROPAGATION")
    @property
    def passenger_delay_cu(self): return self.constructed_units.get("P_DELAY")
    @property
    def passenger_connection_cu(self): return self.constructed_units.get("P_CONNECTION")
    @property
    def passenger_care_cu(self): return self.constructed_units.get("P_CARE")
    @property
    def resource_ground_cu(self): return self.constructed_units.get("R_GROUND")
    @property
    def resource_taxi_cu(self): return self.constructed_units.get("R_TAXI")
    @property
    def resource_scarcity_cu(self): return self.constructed_units.get("R_SCARCITY")
    @property
    def flight_constructed_units(self): return self.channel_constructed_units.get("F")
    @property
    def passenger_constructed_units(self): return self.channel_constructed_units.get("P")
    @property
    def resource_constructed_units(self): return self.channel_constructed_units.get("R")
    @property
    def total_constructed_units(self):
        values = [value for value in self.channel_constructed_units.values() if value is not None]
        return sum(values) if values else None
    @property
    def flight_loss_rmb(self): return self.channel_loss_rmb.get("F")
    @property
    def passenger_loss_rmb(self): return self.channel_loss_rmb.get("P")
    @property
    def resource_loss_rmb(self): return self.channel_loss_rmb.get("R")


@dataclass(frozen=True)
class M2EpisodeSummary:
    episode_id: str
    constructed_unit_summary: Mapping[str, float | bool | None]
    rmb_summary: Mapping[str, float | bool | None]
    channel_mean_losses: Mapping[str, float | None]
    channel_loss_shares: Mapping[str, float | None]
    channel_loss_shares_status: str
    subitem_mean_losses: Mapping[str, float | None]
    subitem_loss_shares: Mapping[str, float | None]
    subitem_loss_shares_status: str
    dominant_channel: str | None
    dominant_subitem: str | None
    unsupported_subitems: tuple[str, ...]
    proxy_active_subitems: tuple[str, ...]
    unresolved_probability: float
    overflow_probability: float
    tail_resolution_status: str
    formal_q95_available: bool
    formal_cvar90_available: bool
    m4_gate_status: str
