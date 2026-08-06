from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Mapping


M1_CONTRACT_ID = "M1_CHAIN_DYNAMIC_DISTRIBUTION_V1"


class M1ContractError(ValueError):
    pass


class FlightChainStage(str, Enum):
    PREDECESSOR_ENROUTE = "PREDECESSOR_ENROUTE"
    PREDECESSOR_GROUND = "PREDECESSOR_GROUND"
    TURNAROUND = "TURNAROUND"
    SUCCESSOR_TAXI = "SUCCESSOR_TAXI"
    COMPLETED = "COMPLETED"
    UNSUPPORTED = "UNSUPPORTED"


class M1SupportLevel(str, Enum):
    OFFICIAL_OPERATIONAL = "OFFICIAL_OPERATIONAL"
    INFERRED_OPERATIONAL = "INFERRED_OPERATIONAL"
    OBSERVED_CHAIN_PROXY = "OBSERVED_CHAIN_PROXY"
    UNSUPPORTED = "UNSUPPORTED"


class StateCommitStatus(str, Enum):
    COMMITTED = "COMMITTED"
    TEMPORARY = "TEMPORARY"
    REUSED = "REUSED"


class TriggerType(str, Enum):
    SCHEDULED = "SCHEDULED"
    EVENT = "EVENT"
    DIRECT = "DIRECT"
    REPLAY = "REPLAY"


@dataclass(frozen=True)
class PreBundleIdentity:
    contract_id: str
    schema_version: str
    research_code_revision: str
    pre_manifest_hash: str
    source_manifest_hash: str
    frozen_config_hash: str
    git_commit: str
    mode: str


@dataclass(frozen=True)
class TargetContract:
    target_name: str
    target_semantics: str
    active: bool
    m1_support_level: str
    pre_event_support_levels: Mapping[str, str]
    chain_support_level: str
    target_reference: str | None
    target_units: str
    target_time_uncertainty_seconds: float | None
    inactive_reason: str | None
    event_details: Mapping[str, Mapping[str, object]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        allowed = {level.value for level in M1SupportLevel}
        if self.m1_support_level not in allowed:
            raise M1ContractError(f"M1_TARGET_SUPPORT_INVALID:{self.m1_support_level}")
        if self.active and self.m1_support_level == M1SupportLevel.UNSUPPORTED.value:
            raise M1ContractError("M1_ACTIVE_TARGET_UNSUPPORTED")
        if not self.active and not self.inactive_reason:
            raise M1ContractError("M1_INACTIVE_REASON_MISSING")


@dataclass(frozen=True)
class SupportedOperationalValue:
    value: object | None
    active: bool
    support_level: str
    source_field: str | None
    source_event_id: str | None
    availability_time: datetime | None
    reference_version: str | None
    inactive_reason: str | None

    def __post_init__(self) -> None:
        if self.active and self.value is None:
            raise M1ContractError("M1_ACTIVE_OPERATIONAL_VALUE_MISSING")
        if not self.active and not self.inactive_reason:
            raise M1ContractError("M1_OPERATIONAL_VALUE_INACTIVE_REASON_MISSING")


@dataclass(frozen=True)
class OperationalReferences:
    successor_sobt: SupportedOperationalValue
    turnaround_floor_minutes: SupportedOperationalValue
    taxi_reference_minutes: SupportedOperationalValue
    predecessor_inblock_observed: SupportedOperationalValue
    successor_offblock_observed: SupportedOperationalValue
    successor_takeoff_observed: SupportedOperationalValue


@dataclass(frozen=True)
class M1SnapshotNode:
    episode_id: str
    snapshot_id: str
    snapshot_version: int
    query_time: datetime
    information_cutoff: datetime
    pre_bundle_identity: PreBundleIdentity
    feature_vector: tuple[float, ...]
    feature_schema_hash: str
    source_observation_ids: tuple[str, ...]
    evidence_status: Mapping[str, str]
    fallback_status: Mapping[str, str]
    flight_chain_stage: FlightChainStage
    observed_event_mask: Mapping[str, bool]
    target_contracts: Mapping[str, TargetContract]
    operational_references: OperationalReferences
    state_reset_signal: bool

    def __post_init__(self) -> None:
        if self.information_cutoff > self.query_time:
            raise M1ContractError("M1_INFORMATION_CUTOFF_AFTER_QUERY_TIME")
        if self.snapshot_version < 1:
            raise M1ContractError("M1_SNAPSHOT_VERSION_INVALID")
        if not self.feature_vector:
            raise M1ContractError("M1_SNAPSHOT_FEATURE_VECTOR_EMPTY")
        if not self.feature_schema_hash:
            raise M1ContractError("M1_FEATURE_SCHEMA_HASH_MISSING")


@dataclass(frozen=True)
class M1EpisodeSequence:
    episode_id: str
    feature_schema_hash: str
    pre_manifest_hash: str
    snapshots: tuple[M1SnapshotNode, ...]

    def __post_init__(self) -> None:
        if not self.snapshots:
            raise M1ContractError("M1_EPISODE_SEQUENCE_EMPTY")
        if any(node.episode_id != self.episode_id for node in self.snapshots):
            raise M1ContractError("M1_EPISODE_SEQUENCE_ID_MISMATCH")
        if any(node.feature_schema_hash != self.feature_schema_hash for node in self.snapshots):
            raise M1ContractError("M1_EPISODE_SEQUENCE_SCHEMA_MISMATCH")
        times = tuple(node.query_time for node in self.snapshots)
        if times != tuple(sorted(times)) or len(set(times)) != len(times):
            raise M1ContractError("M1_EPISODE_SEQUENCE_ORDER_INVALID")


@dataclass(frozen=True)
class M1MarginalDistribution:
    episode_id: str
    snapshot_id: str
    snapshot_version: int
    query_time: datetime
    information_cutoff: datetime
    pre_manifest_hash: str
    m1_contract_id: str
    model_version: str
    temperature_version: str
    target_name: str
    target_support_level: str
    evidence_status: Mapping[str, str]
    bin_lower_minutes: tuple[float, ...]
    bin_upper_minutes: tuple[float | None, ...]
    probabilities: tuple[float, ...]
    feature_schema_hash: str = ""
    model_artifact_hash: str = ""
    temperature_artifact_hash: str = ""

    def __post_init__(self) -> None:
        if len(self.probabilities) != len(self.bin_lower_minutes):
            raise M1ContractError("M1_DISTRIBUTION_SHAPE_MISMATCH")
        if abs(sum(self.probabilities) - 1.0) > 1e-6:
            raise M1ContractError("M1_PROBABILITY_SUM_INVALID")
        if any(value < 0 for value in self.probabilities):
            raise M1ContractError("M1_NEGATIVE_PROBABILITY")


@dataclass(frozen=True)
class M1PredictionBundle:
    episode_id: str
    snapshot_id: str
    snapshot_version: int
    query_time: datetime
    information_cutoff: datetime
    pre_manifest_hash: str
    m1_contract_id: str
    model_version: str
    temperature_version: str
    target_support_level: Mapping[str, str]
    evidence_status: Mapping[str, str]
    distributions: Mapping[str, M1MarginalDistribution]
    hidden_state: tuple[float, ...]
    state_commit_status: StateCommitStatus
    feature_schema_hash: str = ""
    model_artifact_hash: str = ""
    temperature_artifact_hash: str = ""
    replay_reason: str | None = None
    replay_node_count: int = 0


@dataclass(frozen=True)
class M1JointSample:
    episode_id: str
    snapshot_id: str
    snapshot_version: int
    sample_id: int
    query_time: datetime
    information_cutoff: datetime
    pre_manifest_hash: str
    m1_contract_id: str
    m1_model_version: str
    temperature_version: str
    target_support_level: Mapping[str, str]
    r_ib_minutes: float | None
    r_ob_minutes: float | None
    earliest_offblock_time: datetime | None
    T_predecessor_inblock: datetime | None
    AOBT_successor: datetime | None
    ATOT_successor: datetime | None
    taxi_time: float | None
    offblock_delay: float | None
    extra_taxi_delay: float | None
    total_takeoff_delay: float | None
    overflow_flags: Mapping[str, bool]
    observed_event_mask: Mapping[str, bool]
    evidence_status: Mapping[str, str]
    fallback_status: Mapping[str, str]


@dataclass(frozen=True)
class M1ScenarioBundle:
    metadata: Mapping[str, object]
    operational_references: OperationalReferences
    marginal_distributions: Mapping[str, M1MarginalDistribution]
    sampling_metadata: Mapping[str, object]
    joint_samples: tuple[M1JointSample, ...]
    pre_context: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        sample_ids = tuple(sample.sample_id for sample in self.joint_samples)
        if tuple(sorted(sample_ids)) != tuple(range(len(sample_ids))):
            raise M1ContractError("M1_SCENARIO_SAMPLE_IDS_INVALID")
        episode_id = str(self.metadata.get("episode_id", ""))
        snapshot_id = str(self.metadata.get("snapshot_id", ""))
        if not episode_id or not snapshot_id:
            raise M1ContractError("M1_SCENARIO_METADATA_ID_MISSING")
        if any(sample.episode_id != episode_id or sample.snapshot_id != snapshot_id for sample in self.joint_samples):
            raise M1ContractError("M1_SCENARIO_SAMPLE_METADATA_MISMATCH")


@dataclass(frozen=True)
class EventHorizonProbabilities:
    horizons_minutes: tuple[int, ...]
    predecessor_inblock: Mapping[int, float]
    successor_offblock: Mapping[int, float]
    successor_takeoff: Mapping[int, float]


@dataclass(frozen=True)
class M1EvaluationRecord:
    episode_id: str
    snapshot_id: str
    snapshot_version: int
    query_time: datetime
    information_cutoff: datetime
    pre_manifest_hash: str
    m1_contract_id: str
    model_version: str
    temperature_version: str
    target_name: str
    target_support_level: str
    evidence_status: Mapping[str, str]
    metrics: Mapping[str, float]
    strata: Mapping[str, str]


@dataclass(frozen=True)
class M1RunManifest:
    pre_bundle_identity: PreBundleIdentity
    m1_contract_id: str
    feature_schema_status: str
    snapshot_builder_status: str
    target_support_status: str | Mapping[str, str]
    training_status: str
    checkpoint_status: str
    calibration_status: str
    evaluation_status: str
    runtime_state_status: str
    m2_interface_status: str
    engineering_status: str
    scientific_status: str
    model_version: str | None = None
    model_artifact_hash: str | None = None
    temperature_version: str | None = None
    temperature_artifact_hash: str | None = None
    split_definition: Mapping[str, object] = field(default_factory=dict)
