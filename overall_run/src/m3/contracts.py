from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


M3_CONTRACT_VERSION = "M3_RESPONSE_V4_ATOMIC_SUBITEM"
M3_ACTION_LIBRARY_VERSION = "M3_ATOMIC_ACTION_LIBRARY_V1"
M3_RESPONSE_CONTRACT_VERSION = "M3_SUBITEM_RESPONSE_V1"
M2_SUBITEM_CONTRACT_VERSION = "M2_NINE_SUBITEM_V1"
SUBITEMS_M2_V2 = (
    "F_TURN",
    "F_WAIT",
    "F_PROPAGATION",
    "P_DELAY",
    "P_CONNECTION",
    "P_CARE",
    "R_GROUND",
    "R_TAXI",
    "R_SCARCITY",
)
COST_CHANNELS = ("F", "P", "R")
EXPECTED_ACTION_IDS = (
    "A00", "A11", "A12", "A13", "A21", "A22", "A23", "A31", "A33",
    "A41", "A42", "A43", "A61", "A62", "A63", "A64", "A71", "A72",
)
FORBIDDEN_ACTION_IDS = frozenset({"A51", "A52", "A53", "A54", "A55"})
FORBIDDEN_COMBINATION_TOKENS = (
    "PLUS",
    "WITH",
    "PACKAGE",
    "INTEGRATED",
    "BALANCED",
    "AGGRESSIVE",
)


class OutcomeCoverage(str, Enum):
    FORMAL_SUPPORTED = "FORMAL_SUPPORTED"
    PARTIAL_SUPPORTED = "PARTIAL_SUPPORTED"
    SCENARIO_ONLY = "SCENARIO_ONLY"


class FootprintRole(str, Enum):
    NONE = "NONE"
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"


class ParameterStatus(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    FROZEN_FOR_VALIDATION = "FROZEN_FOR_VALIDATION"


@dataclass(frozen=True)
class ActionCatalogEntry:
    contract_identity: str
    action_library_version: str
    action_id: str
    action_name: str
    action_family: str
    mechanism: str
    lead_time: float | None
    applicable_stage: tuple[str, ...]
    outcome_coverage: OutcomeCoverage
    parameter_status: ParameterStatus


@dataclass(frozen=True)
class ActionFootprintSpec:
    action_library_version: str
    action_id: str
    roles: Mapping[str, FootprintRole]

    def __post_init__(self) -> None:
        if tuple(self.roles) != SUBITEMS_M2_V2:
            raise ValueError(f"M3_M2_CONTRACT_MISMATCH:unknown subitem:{self.action_id}")
        primary = sum(role is FootprintRole.PRIMARY for role in self.roles.values())
        secondary = sum(role is FootprintRole.SECONDARY for role in self.roles.values())
        if primary + secondary > 4:
            raise ValueError(f"M3_FOOTPRINT_TOO_DENSE:{self.action_id}")
        if self.action_id == "A00" and any(
            role is not FootprintRole.NONE for role in self.roles.values()
        ):
            raise ValueError("M3_A00_FOOTPRINT_IDENTITY_FAILURE")


@dataclass(frozen=True)
class ActionResponseParameterSpec:
    action_library_version: str
    action_id: str
    response_mean: float | None
    response_concentration: float | None
    secondary_multiplier: float | None
    failure_probability: float | None
    parameter_status: ParameterStatus
    parameter_source: str
    parameter_version: str
    test_only: bool = False


@dataclass(frozen=True)
class ActionCostSpec:
    action_library_version: str
    action_id: str
    fixed_mean_rmb: Mapping[str, float | None]
    channel_status: Mapping[str, ParameterStatus]
    cost_cv: float | None
    parameter_status: ParameterStatus
    parameter_source: str
    parameter_version: str
    test_only: bool = False

    def __post_init__(self) -> None:
        if tuple(self.fixed_mean_rmb) != COST_CHANNELS:
            raise ValueError(f"M3_COST_CHANNEL_SCHEMA_MISMATCH:{self.action_id}")
        if tuple(self.channel_status) != COST_CHANNELS:
            raise ValueError(f"M3_COST_STATUS_SCHEMA_MISMATCH:{self.action_id}")


@dataclass(frozen=True)
class M3ContractBundle:
    contract_identity: str
    action_library_version: str
    response_contract_version: str
    parameter_freeze_status: str
    scientific_approved: bool
    publication_allowed: bool
    formal_library_status: str
    response_draw_count: int
    base_seed: int
    fixed_random_streams: bool
    required_m2: Mapping[str, str]
    catalog: Mapping[str, ActionCatalogEntry]
    footprints: Mapping[str, ActionFootprintSpec]
    response_parameters: Mapping[str, ActionResponseParameterSpec]
    cost_parameters: Mapping[str, ActionCostSpec]

    @property
    def contract_version(self) -> str:
        return self.contract_identity

    @property
    def formal_action_ids(self) -> tuple[str, ...]:
        return tuple(
            action_id
            for action_id, item in self.catalog.items()
            if item.outcome_coverage is OutcomeCoverage.FORMAL_SUPPORTED
        )
