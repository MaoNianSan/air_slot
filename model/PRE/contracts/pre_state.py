from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from model.common.enums import EvidenceClass, OperationalStage, SupportState
from model.common.value_objects import FrozenModel, SupportedValue


class EpisodeRecord(FrozenModel):
    episode_id: str
    dataset_instance_id: str
    predecessor_flight_id: str
    successor_flight_id: str
    aircraft_id: str
    aircraft_id_namespace: str
    connection_airport_id: str
    episode_start_time: datetime
    episode_end_time: datetime
    chain_rule_id: str
    chain_rule_version: str = "LEGACY_UNVERSIONED"
    chain_rule_parameters: tuple[str, ...] = ()
    relation_type: str = "PREDECESSOR_SUCCESSOR"
    join_keys: tuple[str, ...] = ()
    ordering_rule: str = "CHAIN_RULE_DEFINED"
    continuity_rule: str = "CHAIN_RULE_DEFINED"
    source_record_ids: tuple[str, ...] = ()
    construction_provenance: tuple[str, ...] = ()
    lineage_support: SupportState
    formal_eligible: bool
    quality_flags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def valid_episode(self):
        if self.predecessor_flight_id == self.successor_flight_id:
            raise ValueError("predecessor and successor must differ")
        if self.episode_start_time >= self.episode_end_time:
            raise ValueError("invalid episode interval")
        if self.chain_rule_version != "LEGACY_UNVERSIONED":
            if len(self.source_record_ids) != 2:
                raise ValueError("versioned episode requires two source record ids")
            if not self.join_keys or not self.ordering_rule or not self.continuity_rule:
                raise ValueError("versioned episode requires explicit relational rules")
            expected_rule = f"{self.chain_rule_id}@{self.chain_rule_version}"
            if expected_rule not in self.construction_provenance:
                raise ValueError("versioned episode requires rule provenance")
        return self


class DecisionNodeRecord(FrozenModel):
    decision_node_id: str
    episode_id: str
    decision_time: datetime
    information_cutoff: datetime
    operational_stage: OperationalStage
    roll_minutes: int = Field(gt=0)
    node_index: int = Field(ge=0)
    status: Literal["REQUESTED", "ADMISSIBILITY_CHECKED", "CONSTRUCTED", "ABSTAINED"]
    formal_eligible: bool
    config_hash: str
    registry_manifest_hash: str
    legal_record_ids: tuple[str, ...]
    node_invalidation_reason: str | None = None

    @model_validator(mode="after")
    def time_order(self):
        if self.information_cutoff > self.decision_time:
            raise ValueError("information cutoff exceeds decision time")
        if self.status == "ABSTAINED":
            if self.formal_eligible or not self.node_invalidation_reason:
                raise ValueError("node-level ABSTAINED requires ineligibility and reason")
        elif self.node_invalidation_reason is not None:
            raise ValueError("constructed/requested node cannot carry invalidation reason")
        return self


class EvidenceLedgerEntry(FrozenModel):
    decision_node_id: str
    scientific_object: str
    source_name: str
    source_record_id: str
    event_time: datetime | None
    availability_time: datetime | None
    availability_basis: str
    decision_time_role: str
    evidence_class: EvidenceClass
    support_ceiling: EvidenceClass
    episode_support: SupportState
    freshness_seconds: float | None = None
    fallback_level: str = "NONE"
    criticality: str = "OBJECT"
    abstention_reason: str | None = None
    quality_flags: tuple[str, ...] = ()
    episode_member: bool = True
    admissible: bool = True
    selected: bool = True


class VariableLineageEntry(FrozenModel):
    decision_node_id: str
    scientific_variable: str
    supported_value: SupportedValue
    canonical_variable: str
    rule_id: str
    source_name: str
    source_record_id: str
    event_time: datetime | None
    availability_time: datetime | None
    availability_basis: str
    age_seconds: float | None = None
    fallback_used: bool = False
    quality_flags: tuple[str, ...] = ()
    reference_role: Literal["origin", "destination", "connection"] | None = None


class AirportReferenceSlot(FrozenModel):
    reference_role: Literal["origin", "destination", "connection"]
    supported_value: SupportedValue
    source_record_id: str | None = None
    rule_id: str | None = None


class KeyedAirportReference(FrozenModel):
    origin: AirportReferenceSlot
    destination: AirportReferenceSlot
    connection: AirportReferenceSlot


class ReferenceState(FrozenModel):
    entries: dict[str, SupportedValue] = {}

    @field_validator("entries", mode="after")
    @classmethod
    def typed_airport_reference(cls, entries):
        item = entries.get("airport_reference")
        if item is not None and isinstance(item.value, dict) \
                and set(item.value) == {"origin", "destination", "connection"}:
            entries = dict(entries)
            entries["airport_reference"] = item.model_copy(update={
                "value": KeyedAirportReference.model_validate(item.value)})
        return entries


class TargetSupportState(FrozenModel):
    target_name: str
    active: bool
    support_state: SupportState
    target_definition_id: str
    dataset_ceiling: EvidenceClass
    formal_input_support: EvidenceClass
    realized_outcome_support: EvidenceClass
    abstention_reason: str | None = None

    @model_validator(mode="after")
    def reason_for_inactive(self):
        if not self.active and self.support_state is not SupportState.ABSTAIN:
            raise ValueError("inactive target must abstain")
        if self.support_state is SupportState.ABSTAIN and not self.abstention_reason:
            raise ValueError("abstention reason required")
        return self


class PREState(FrozenModel):
    decision_node: DecisionNodeRecord
    predecessor_state: dict[str, SupportedValue] = {}
    current_state: dict[str, SupportedValue] = {}
    successor_state: dict[str, SupportedValue] = {}
    evidence_ledger: tuple[EvidenceLedgerEntry, ...] = ()
    variable_lineage: tuple[VariableLineageEntry, ...] = ()
    reference_state: ReferenceState = ReferenceState()
    target_support: tuple[TargetSupportState, ...] = ()
    # Tranche 3: plain per-field publication metadata written by PRE (never an
    # M1 type — PRE does not import downstream).  M1 rebuilds its typed
    # ``M1StaticReferenceContext`` from this dict.
    static_reference_publication: dict[str, Any] | None = None
