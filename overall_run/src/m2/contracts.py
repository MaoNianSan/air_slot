from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Mapping


M2_CONTRACT_VERSION = "EPISODE_PRE_ACTION_LOSS_RECONSTRUCTION_V2"


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
class FlightContext:
    successor_sobt: object | None
    turnaround_reference_minutes: float | None
    turnaround_reference_type: str
    continuity_exposure: float = 0.0
    downstream_leg_count: int = 0
    execution_window_margin: float = 0.0
    aircraft_flexibility: float = 0.0
    evidence_status: str = "UNSUPPORTED"


@dataclass(frozen=True)
class PassengerContext:
    passenger_load_proxy: float | None = None
    connection_pressure: float | None = None
    connection_slack: float | None = None
    rebooking_scarcity: float | None = None
    evidence_status: str = "UNSUPPORTED"


@dataclass(frozen=True)
class ResourceContext:
    airport_flow_pressure: float | None = None
    infrastructure_flexibility: float | None = None
    resource_availability: float | None = None
    ground_support_pressure: float | None = None
    evidence_status: str = "UNSUPPORTED"


@dataclass(frozen=True)
class ValuationContext:
    subitem_value_parameters: Mapping[str, float] = field(default_factory=dict)
    rule_parameters: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    constructed_unit_version: str = "CU_V2"
    valuation_version: str = "NOT_CONFIGURED"
    currency_mapping_version: str = "IDENTITY_V1"
    currency: str = "RMB"
    currency_mapping_mode: str = "IDENTITY"
    channel_rates: Mapping[str, float] = field(default_factory=lambda: {"F": 1.0, "P": 1.0, "R": 1.0})


@dataclass(frozen=True)
class AuditContext:
    evidence_status: Mapping[str, str]
    proxy_status: Mapping[str, str]
    overflow_status: str
    tail_resolution_status: str
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


@dataclass(frozen=True)
class M2InputBundle:
    metadata: M2Metadata
    joint_scenarios: tuple[object, ...]
    flight_context: FlightContext
    passenger_context: PassengerContext
    resource_context: ResourceContext
    subitem_activation: Mapping[str, SubitemActivation]
    valuation_context: ValuationContext
    audit_context: AuditContext
    input_status: M2InputStatus

    def __post_init__(self) -> None:
        ids = tuple(getattr(sample, "sample_id", -1) for sample in self.joint_scenarios)
        if ids != tuple(range(len(ids))):
            raise ValueError("M2_SAMPLE_ID_ALIGNMENT_FAILED")
        for sample in self.joint_scenarios:
            if getattr(sample, "episode_id", None) != self.metadata.episode_id:
                raise ValueError("M2_EPISODE_ALIGNMENT_FAILED")
            if getattr(sample, "snapshot_id", None) != self.metadata.snapshot_id:
                raise ValueError("M2_SNAPSHOT_ALIGNMENT_FAILED")
        if len(self.joint_scenarios) == 0:
            raise ValueError("M2_SAMPLE_SET_EMPTY")
        if int(self.metadata.snapshot_version) < 1:
            raise ValueError("M2_SNAPSHOT_VERSION_INVALID")


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
    quantities: Mapping[str, float | None]
    constructed_units: Mapping[str, float | None]
    channel_constructed_units: Mapping[str, float | None]
    channel_loss_rmb: Mapping[str, float | None]
    total_pre_action_loss_rmb: float | None
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
    constructed_unit_summary: Mapping[str, float | None]
    rmb_summary: Mapping[str, float | None]
    channel_contributions: Mapping[str, float | None]
    subitem_contributions: Mapping[str, float | None]
    dominant_channel: str | None
    dominant_subitem: str | None
    unsupported_subitems: tuple[str, ...]
    proxy_active_subitems: tuple[str, ...]
    overflow_probability: float
    tail_resolution_status: str
