from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from enum import Enum
from hashlib import sha256
import json
from typing import Any

from pydantic import Field, model_validator

from model.common.enums import (
    AvailabilityBasis,
    DecisionTimeRole,
    EvidenceClass,
    SupportState,
    weaker_or_equal,
)
from model.common.errors import ContractError, RegistryError
from model.common.value_objects import FrozenModel, SupportedValue


class ConstructionType(str, Enum):
    DIRECT_OBSERVATION = "DIRECT_OBSERVATION"
    DETERMINISTIC_DERIVATION = "DETERMINISTIC_DERIVATION"
    EVENT_STATE_INFERENCE = "EVENT_STATE_INFERENCE"
    RELATIONAL_DERIVATION = "RELATIONAL_DERIVATION"
    TRAIN_FROZEN_REFERENCE = "TRAIN_FROZEN_REFERENCE"
    EXTERNAL_OR_POLICY_REFERENCE = "EXTERNAL_OR_POLICY_REFERENCE"
    SCENARIO_ASSUMPTION = "SCENARIO_ASSUMPTION"
    UNSUPPORTED = "UNSUPPORTED"


class TransformationStatus(str, Enum):
    FROZEN = "FROZEN"
    DEVELOPMENT_FROZEN = "DEVELOPMENT_FROZEN"
    DEVELOPMENT_CANDIDATE = "DEVELOPMENT_CANDIDATE"
    UNSUPPORTED = "UNSUPPORTED"


class TransformationRule(FrozenModel):
    transformation_rule_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    construction_type: ConstructionType
    input_object_types: tuple[str, ...]
    input_fields: tuple[str, ...]
    relation_keys: tuple[str, ...] = ()
    group_by_keys: tuple[str, ...] = ()
    order_by_keys: tuple[str, ...] = ()
    join_on_keys: tuple[str, ...] = ()
    window_rule: str | None = None
    adjacency_rule: str | None = None
    tie_break_rule: str | None = None
    duplicate_rule: str = "REJECT_EXACT_DUPLICATE_SCIENTIFIC_KEY"
    missing_key_rule: str = "ABSTAIN_OR_REJECT"
    temporal_rule: str = Field(min_length=1)
    formula_or_algorithm: str = Field(min_length=1)
    output_variable: str = Field(min_length=1)
    output_unit: str = Field(min_length=1)
    evidence_rule: str = Field(min_length=1)
    support_rule: str = Field(min_length=1)
    consumer_roles: tuple[DecisionTimeRole, ...]
    availability_basis: AvailabilityBasis
    evidence_class: EvidenceClass
    support_ceiling: EvidenceClass
    status: TransformationStatus
    reason_code: str | None = None

    @model_validator(mode="after")
    def explicit_unfrozen_state(self):
        if not weaker_or_equal(self.evidence_class, self.support_ceiling):
            raise ValueError("TRANSFORMATION_EVIDENCE_EXCEEDS_SUPPORT_CEILING")
        if self.status in {
            TransformationStatus.DEVELOPMENT_CANDIDATE,
            TransformationStatus.UNSUPPORTED,
        } and not self.reason_code:
            raise ValueError("UNFROZEN_TRANSFORMATION_REQUIRES_REASON")
        if self.status is TransformationStatus.UNSUPPORTED and (
            self.construction_type is not ConstructionType.UNSUPPORTED
            or self.evidence_class is not EvidenceClass.UNSUPPORTED
        ):
            raise ValueError("UNSUPPORTED_TRANSFORMATION_STATE_MISMATCH")
        return self

    @property
    def formal_executable(self) -> bool:
        return self.status is TransformationStatus.FROZEN


class TransformationRegistry(FrozenModel):
    registry_version: str
    rules: tuple[TransformationRule, ...]

    @model_validator(mode="after")
    def unique_rules(self):
        identities = tuple(
            (rule.transformation_rule_id, rule.version) for rule in self.rules
        )
        if len(identities) != len(set(identities)):
            raise ValueError("DUPLICATE_TRANSFORMATION_RULE")
        return self

    def get(self, rule_id: str, version: str) -> TransformationRule:
        matches = [
            rule
            for rule in self.rules
            if rule.transformation_rule_id == rule_id and rule.version == version
        ]
        if not matches:
            raise RegistryError("TRANSFORMATION_RULE_NOT_REGISTERED")
        return matches[0]


class ScientificObjectValue(FrozenModel):
    scientific_variable_id: str
    value: Any | None
    unit: str
    construction_type: ConstructionType
    transformation_rule_id: str
    transformation_version: str
    evidence_class: EvidenceClass
    support_state: SupportState
    support_ceiling: EvidenceClass
    reason_code: str | None = None
    parent_object_ids: tuple[str, ...]
    source_object_types: tuple[str, ...]
    source_fields: tuple[str, ...]
    relation_keys: tuple[str, ...] = ()
    temporal_rule: str
    evidence_rule: str
    support_rule: str
    consumer_roles: tuple[DecisionTimeRole, ...]
    transformation_status: TransformationStatus
    decision_time_role: DecisionTimeRole
    availability_basis: AvailabilityBasis
    provenance: tuple[str, ...]

    @model_validator(mode="after")
    def preserve_abstention(self):
        if self.support_state is SupportState.ABSTAIN:
            if self.value is not None or not self.reason_code:
                raise ValueError("DERIVED_ABSTAIN_REQUIRES_NULL_AND_REASON")
        elif self.value is None:
            raise ValueError("DERIVED_NULL_REQUIRES_ABSTAIN")
        return self


_EVIDENCE_RANK = {
    EvidenceClass.DIRECT: 0,
    EvidenceClass.DERIVED: 1,
    EvidenceClass.DOMAIN_PROXY: 2,
    EvidenceClass.EMPIRICAL_REFERENCE: 2,
    EvidenceClass.EXTERNAL_STANDARD: 2,
    EvidenceClass.SCENARIO_PARAMETER: 3,
    EvidenceClass.UNSUPPORTED: 4,
}


def _weakest_evidence(values: Iterable[EvidenceClass]) -> EvidenceClass:
    return max(tuple(values), key=lambda item: _EVIDENCE_RANK[item])


def derive_scientific_object(
    *,
    rule: TransformationRule,
    parents: dict[str, SupportedValue],
    parent_object_ids: tuple[str, ...],
    transform: Callable[[dict[str, Any]], Any],
    formal_path: bool = True,
) -> ScientificObjectValue:
    if formal_path and not rule.formal_executable:
        raise ContractError("CONSTRUCTION_RULE_NOT_FROZEN")
    if not parents:
        raise ContractError("DERIVED_OBJECT_PARENTS_REQUIRED")
    missing = tuple(
        name
        for name, parent in parents.items()
        if parent.support_state is SupportState.ABSTAIN or parent.value is None
    )
    provenance = tuple(sorted(parent_object_ids)) + (
        f"{rule.transformation_rule_id}@{rule.version}",
    )
    effective_ceiling = _weakest_evidence(
        (rule.support_ceiling, *(parent.support_ceiling for parent in parents.values()))
    )
    if missing:
        return ScientificObjectValue(
            scientific_variable_id=rule.output_variable,
            value=None,
            unit=rule.output_unit,
            construction_type=rule.construction_type,
            transformation_rule_id=rule.transformation_rule_id,
            transformation_version=rule.version,
            evidence_class=EvidenceClass.UNSUPPORTED,
            support_state=SupportState.ABSTAIN,
            support_ceiling=effective_ceiling,
            reason_code=f"CRITICAL_PARENT_ABSTAIN:{','.join(sorted(missing))}",
            parent_object_ids=tuple(sorted(parent_object_ids)),
            source_object_types=rule.input_object_types,
            source_fields=rule.input_fields,
            relation_keys=rule.relation_keys,
            temporal_rule=rule.temporal_rule,
            evidence_rule=rule.evidence_rule,
            support_rule=rule.support_rule,
            consumer_roles=rule.consumer_roles,
            transformation_status=rule.status,
            decision_time_role=rule.consumer_roles[0],
            availability_basis=rule.availability_basis,
            provenance=provenance,
        )
    parent_evidence = _weakest_evidence(
        parent.evidence_class for parent in parents.values()
    )
    evidence = _weakest_evidence((parent_evidence, rule.evidence_class))
    support = (
        SupportState.DEGRADED
        if any(parent.support_state is SupportState.DEGRADED for parent in parents.values())
        else SupportState.SUPPORTED
    )
    reason = "PARENT_SUPPORT_DEGRADED" if support is SupportState.DEGRADED else None
    return ScientificObjectValue(
        scientific_variable_id=rule.output_variable,
        value=transform({name: parent.value for name, parent in parents.items()}),
        unit=rule.output_unit,
        construction_type=rule.construction_type,
        transformation_rule_id=rule.transformation_rule_id,
        transformation_version=rule.version,
        evidence_class=evidence,
        support_state=support,
        support_ceiling=effective_ceiling,
        reason_code=reason,
        parent_object_ids=tuple(sorted(parent_object_ids)),
        source_object_types=rule.input_object_types,
        source_fields=rule.input_fields,
        relation_keys=rule.relation_keys,
        temporal_rule=rule.temporal_rule,
        evidence_rule=rule.evidence_rule,
        support_rule=rule.support_rule,
        consumer_roles=rule.consumer_roles,
        transformation_status=rule.status,
        decision_time_role=rule.consumer_roles[0],
        availability_basis=rule.availability_basis,
        provenance=provenance,
    )


class ReferenceFitManifest(FrozenModel):
    transformation_rule_id: str
    transformation_version: str
    fit_partition: str
    fit_period: str
    grouping_keys: tuple[str, ...]
    statistic_id: str
    minimum_support_rule: str
    fallback_hierarchy: tuple[str, ...]
    applicability_scope: str
    evidence_class: EvidenceClass
    support_ceiling: EvidenceClass
    availability_basis: AvailabilityBasis
    consumer_roles: tuple[DecisionTimeRole, ...]
    rule_status: TransformationStatus
    training_record_ids: tuple[str, ...]
    training_source_fingerprints: tuple[str, ...]
    sample_count: int
    freeze_id: str


def build_reference_fit_manifest(
    records: Iterable[dict[str, Any]],
    *,
    rule: TransformationRule,
    fit_period: str,
    grouping_keys: tuple[str, ...],
    statistic_id: str,
    minimum_support_rule: str,
    fallback_hierarchy: tuple[str, ...] = (),
    applicability_scope: str,
) -> ReferenceFitManifest:
    if rule.construction_type is not ConstructionType.TRAIN_FROZEN_REFERENCE:
        raise ContractError("REFERENCE_RULE_CONSTRUCTION_TYPE_REQUIRED")
    training = sorted(
        (record for record in records if record.get("split") == "train"),
        key=lambda record: (record["record_id"], record["source_fingerprint"]),
    )
    if not training:
        raise ContractError("REFERENCE_TRAIN_PARTITION_EMPTY")
    ids = tuple(record["record_id"] for record in training)
    fingerprints = tuple(record["source_fingerprint"] for record in training)
    payload = {
        "fallback_hierarchy": fallback_hierarchy,
        "fit_partition": "train",
        "fit_period": fit_period,
        "grouping_keys": grouping_keys,
        "applicability_scope": applicability_scope,
        "minimum_support_rule": minimum_support_rule,
        "record_ids": ids,
        "source_fingerprints": fingerprints,
        "statistic_id": statistic_id,
        "transformation_rule_id": rule.transformation_rule_id,
        "transformation_version": rule.version,
    }
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ReferenceFitManifest(
        transformation_rule_id=rule.transformation_rule_id,
        transformation_version=rule.version,
        fit_partition="train",
        fit_period=fit_period,
        grouping_keys=grouping_keys,
        statistic_id=statistic_id,
        minimum_support_rule=minimum_support_rule,
        fallback_hierarchy=fallback_hierarchy,
        applicability_scope=applicability_scope,
        evidence_class=rule.evidence_class,
        support_ceiling=rule.support_ceiling,
        availability_basis=rule.availability_basis,
        consumer_roles=rule.consumer_roles,
        rule_status=rule.status,
        training_record_ids=ids,
        training_source_fingerprints=fingerprints,
        sample_count=len(training),
        freeze_id=f"sha256:{digest}",
    )


def current_transformation_registry() -> TransformationRegistry:
    """Typed boundary for existing objects; candidate rules remain non-executable."""
    rules = (
        TransformationRule(
            transformation_rule_id="SAME_AIRCRAFT_AIRPORT_GAP",
            version="1.0.0",
            construction_type=ConstructionType.RELATIONAL_DERIVATION,
            input_object_types=("FlightRecord",),
            input_fields=(
                "aircraft_id",
                "aircraft_id_namespace",
                "origin_airport_id",
                "destination_airport_id",
                "event_start_time",
                "event_end_time",
                "flight_id",
            ),
            relation_keys=("aircraft_id_namespace", "aircraft_id"),
            group_by_keys=(
                "dataset_instance_id",
                "aircraft_id_namespace",
                "aircraft_id",
            ),
            order_by_keys=("event_start_time", "event_end_time", "flight_id"),
            join_on_keys=(
                "dataset_instance_id",
                "aircraft_id_namespace",
                "aircraft_id",
                "predecessor.destination_airport_id=successor.origin_airport_id",
            ),
            window_rule="ADJACENT_ROWS_WITHIN_GROUP",
            adjacency_rule="POSITIVE_GAP_WITHIN_MAX_360_MINUTES",
            tie_break_rule="EVENT_START_THEN_EVENT_END_THEN_FLIGHT_ID",
            duplicate_rule="REJECT_EXACT_DUPLICATE_ORDERING_KEY",
            missing_key_rule="REJECT_LINK",
            temporal_rule="ORDER_BY_EVENT_START_END_FLIGHT_ID_THEN_ADJACENT",
            formula_or_algorithm="SAME_AIRCRAFT_AND_AIRPORT_CONTINUITY_WITH_MAX_GAP_360",
            output_variable="predecessor_successor_episode",
            output_unit="episode",
            evidence_rule="DERIVED_FROM_OFFLINE_EPISODE_CONSTRUCTION_RECORDS",
            support_rule="ALL_IDENTITY_TIME_AND_CONTINUITY_PARENTS_REQUIRED",
            consumer_roles=(DecisionTimeRole.EPISODE_CONSTRUCTION,),
            availability_basis=AvailabilityBasis.ARCHIVE_PUBLICATION_RULE,
            evidence_class=EvidenceClass.DERIVED,
            support_ceiling=EvidenceClass.DIRECT,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="ROLLING_DECISION_NODE_5MIN",
            version="1.0.0",
            construction_type=ConstructionType.DETERMINISTIC_DERIVATION,
            input_object_types=("EpisodeRecord",),
            input_fields=("episode_start_time", "episode_end_time"),
            temporal_rule="T_N_EQUALS_T0_PLUS_5N",
            formula_or_algorithm="FIVE_MINUTE_GRID_T0_EPISODE_START_TO_EPISODE_END",
            output_variable="rolling_decision_node",
            output_unit="node",
            evidence_rule="DERIVED",
            support_rule="EPISODE_IDENTITY_REQUIRED",
            consumer_roles=(DecisionTimeRole.EPISODE_CONSTRUCTION,),
            availability_basis=AvailabilityBasis.ARCHIVE_PUBLICATION_RULE,
            evidence_class=EvidenceClass.DERIVED,
            support_ceiling=EvidenceClass.DIRECT,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="TRAJECTORY_OPERATIONAL_EVENT_TRANSITION",
            version="1.0.0",
            construction_type=ConstructionType.EVENT_STATE_INFERENCE,
            input_object_types=("TrajectoryObservation", "AirportReference"),
            input_fields=(
                "latitude_deg",
                "longitude_deg",
                "velocity_mps",
                "vertical_rate_mps",
                "on_ground",
                "baro_altitude_m",
                "geo_altitude_m",
                "aircraft_id",
                "event_time",
            ),
            relation_keys=("aircraft_id", "airport_id"),
            temporal_rule="TIME_ORDERED_STATE_SEQUENCE",
            formula_or_algorithm="TRAJECTORY_ON_GROUND_PRIMARY_STATE_MACHINE_CROSSCHECK",
            output_variable="derived_operational_event",
            output_unit="UTC",
            evidence_rule="DERIVED_FROM_TRAJECTORY_STATE",
            support_rule="ON_GROUND_PRIMARY_AND_STATE_MACHINE_CROSSCHECK_REQUIRED",
            consumer_roles=(DecisionTimeRole.TRAIN_LABEL,),
            availability_basis=AvailabilityBasis.POSTHOC_ONLY,
            evidence_class=EvidenceClass.DERIVED,
            support_ceiling=EvidenceClass.DIRECT,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="DATA1_REALIZED_ARRIVAL_ROUTING",
            version="1.0.0",
            construction_type=ConstructionType.RELATIONAL_DERIVATION,
            input_object_types=("OperationalEventRecord", "FlightRecord"),
            input_fields=("aircraft_id", "flight_id", "event_type", "event_time",
                          "event_time_lower", "event_time_upper",
                          "event_start_time", "event_end_time"),
            relation_keys=("flight_id", "aircraft_id"),
            temporal_rule="EVENT_WITHIN_FLIGHT_INTERVAL_ORDERED",
            formula_or_algorithm="TRAJECTORY_EVENT_PREFERRED_FLIGHTLIST_PROXY_FALLBACK",
            output_variable="routed_predecessor_arrival",
            output_unit="UTC",
            evidence_rule="DERIVED_FROM_TRAJECTORY_OR_PROXY",
            support_rule="TRAJECTORY_PREFERRED_PROXY_DEGRADED",
            consumer_roles=(DecisionTimeRole.TRAIN_LABEL, DecisionTimeRole.EVAL_OUTCOME),
            availability_basis=AvailabilityBasis.POSTHOC_ONLY,
            evidence_class=EvidenceClass.DERIVED,
            support_ceiling=EvidenceClass.DERIVED,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="DATA1_REALIZED_TAXI_OUT_ROUTING",
            version="1.0.0",
            construction_type=ConstructionType.RELATIONAL_DERIVATION,
            input_object_types=("OperationalEventRecord", "FlightRecord"),
            input_fields=("aircraft_id", "flight_id", "event_type", "event_time",
                          "event_time_lower", "event_time_upper",
                          "event_start_time", "event_end_time"),
            relation_keys=("flight_id", "aircraft_id"),
            temporal_rule="EVENT_WITHIN_FLIGHT_INTERVAL_ORDERED",
            formula_or_algorithm="OUT_BLOCK_TAKEOFF_PAIR_ONLY",
            output_variable="routed_successor_taxi_out",
            output_unit="minutes",
            evidence_rule="DERIVED_FROM_TRAJECTORY_PAIR",
            support_rule="TRAJECTORY_PAIR_REQUIRED_PROXY_UNSUPPORTED",
            consumer_roles=(DecisionTimeRole.TRAIN_LABEL, DecisionTimeRole.EVAL_OUTCOME),
            availability_basis=AvailabilityBasis.POSTHOC_ONLY,
            evidence_class=EvidenceClass.DERIVED,
            support_ceiling=EvidenceClass.DERIVED,
            status=TransformationStatus.FROZEN,
        ),

        TransformationRule(
            transformation_rule_id="TURNAROUND_REFERENCE",
            version="0.1.0",
            construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
            input_object_types=("OperationalEventRecord",),
            input_fields=("actual_arrival_utc", "actual_departure_utc"),
            relation_keys=("airport_id", "aircraft_group"),
            temporal_rule="TRAIN_PARTITION_ONLY",
            formula_or_algorithm="OBJECT_DEFINED_STATISTIC_NOT_FROZEN",
            output_variable="turnaround_reference",
            output_unit="minutes",
            evidence_rule="EMPIRICAL_REFERENCE",
            support_rule="MINIMUM_SUPPORT_AND_FALLBACK_NOT_FROZEN",
            consumer_roles=(DecisionTimeRole.FROZEN_REFERENCE,),
            availability_basis=AvailabilityBasis.REFERENCE_PERIOD,
            evidence_class=EvidenceClass.EMPIRICAL_REFERENCE,
            support_ceiling=EvidenceClass.EMPIRICAL_REFERENCE,
            status=TransformationStatus.DEVELOPMENT_CANDIDATE,
            reason_code="CONSTRUCTION_RULE_NOT_FROZEN",
        ),
        TransformationRule(
            transformation_rule_id="TURNAROUND_REFERENCE",
            version="1.0.0",
            construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
            input_object_types=("FlightRecord",),
            input_fields=("aircraft_id", "aircraft_id_namespace", "origin_airport_id",
                          "destination_airport_id", "first_seen_utc", "last_seen_utc"),
            relation_keys=("aircraft_id", "aircraft_id_namespace",
                           "predecessor.destination_airport_id=successor.origin_airport_id"),
            group_by_keys=("connection_airport_id",),
            order_by_keys=(),
            join_on_keys=("aircraft_id", "aircraft_id_namespace"),
            window_rule="ADJACENT_ROWS_WITHIN_AIRCRAFT_GROUP",
            adjacency_rule="POSITIVE_GAP_WITHIN_MAX_360_MINUTES",
            tie_break_rule="EVENT_END_TIME_THEN_FLIGHT_ID",
            duplicate_rule="REJECT_EXACT_DUPLICATE_ORDERING_KEY",
            missing_key_rule="REJECT_LINK",
            temporal_rule="TRAIN_PARTITION_ONLY",
            formula_or_algorithm="MEDIAN(successor.first_seen_utc - predecessor.last_seen_utc) "
                                 "BY connection_airport_id; MIN_CELL_SIZE_50; "
                                 "FALLBACK AIRPORT_CELL_TO_GLOBAL",
            output_variable="turnaround_reference",
            output_unit="minutes",
            evidence_rule="EMPIRICAL_REFERENCE_FROM_FLIGHTLIST_PROXY_GAP",
            support_rule="PROXY_GAP_DEGRADED_MIN_CELL_50_FALLBACK_CELL_TO_GLOBAL",
            consumer_roles=(DecisionTimeRole.FROZEN_REFERENCE,),
            availability_basis=AvailabilityBasis.REFERENCE_PERIOD,
            evidence_class=EvidenceClass.EMPIRICAL_REFERENCE,
            support_ceiling=EvidenceClass.EMPIRICAL_REFERENCE,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="TAXI_REFERENCE",
            version="0.1.0",
            construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
            input_object_types=("OperationalEventRecord",),
            input_fields=("taxi_out_minutes",),
            relation_keys=("airport_id", "time_group"),
            temporal_rule="TRAIN_PARTITION_ONLY",
            formula_or_algorithm="OBJECT_DEFINED_STATISTIC_NOT_FROZEN",
            output_variable="taxi_reference",
            output_unit="minutes",
            evidence_rule="EMPIRICAL_REFERENCE",
            support_rule="MINIMUM_SUPPORT_AND_FALLBACK_NOT_FROZEN",
            consumer_roles=(DecisionTimeRole.FROZEN_REFERENCE,),
            availability_basis=AvailabilityBasis.REFERENCE_PERIOD,
            evidence_class=EvidenceClass.EMPIRICAL_REFERENCE,
            support_ceiling=EvidenceClass.EMPIRICAL_REFERENCE,
            status=TransformationStatus.DEVELOPMENT_CANDIDATE,
            reason_code="CONSTRUCTION_RULE_NOT_FROZEN",
        ),
        TransformationRule(
            transformation_rule_id="TAXI_REFERENCE",
            version="1.0.0",
            construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
            input_object_types=("FlightRecord", "OperationalEventRecord"),
            input_fields=("aircraft_id", "origin_airport_id", "first_seen_utc",
                          "last_seen_utc", "event_type", "event_time", "quality_flags"),
            relation_keys=("aircraft_id",),
            group_by_keys=("origin_airport_id",),
            order_by_keys=(),
            join_on_keys=("aircraft_id",),
            window_rule="EVENT_WITHIN_FLIGHT_INTERVAL_LATEST_PER_TYPE",
            adjacency_rule="TAKEOFF_AFTER_OUT_BLOCK_PROXY",
            tie_break_rule="LATEST_EVENT_TIME_PER_TYPE",
            duplicate_rule="REJECT_EXACT_DUPLICATE_ORDERING_KEY",
            missing_key_rule="NO_COVERAGE_ABSTAIN",
            temporal_rule="TRAIN_PARTITION_ONLY",
            formula_or_algorithm="MEDIAN(TAKEOFF - OUT_BLOCK_PROXY) BY origin_airport_id; "
                                 "MIN_CELL_SIZE_50; FALLBACK AIRPORT_CELL_TO_GLOBAL; "
                                 "ZERO_COVERAGE_ABSTAIN",
            output_variable="taxi_reference",
            output_unit="minutes",
            evidence_rule="EMPIRICAL_REFERENCE_FROM_TRAJECTORY_PAIR",
            support_rule="TRAJECTORY_PAIR_DEGRADED_MIN_CELL_50_FALLBACK_CELL_TO_GLOBAL",
            consumer_roles=(DecisionTimeRole.FROZEN_REFERENCE,),
            availability_basis=AvailabilityBasis.REFERENCE_PERIOD,
            evidence_class=EvidenceClass.EMPIRICAL_REFERENCE,
            support_ceiling=EvidenceClass.EMPIRICAL_REFERENCE,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="EXPECTED_DOWNSTREAM_EXPOSURE",
            version="1.0.0",
            construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
            input_object_types=("FlightRecord",),
            input_fields=("aircraft_id", "aircraft_id_namespace", "origin_airport_id",
                          "destination_airport_id", "first_seen_utc",
                          "event_start_time", "event_end_time"),
            relation_keys=("aircraft_id", "aircraft_id_namespace"),
            group_by_keys=("connection_airport_id",),
            order_by_keys=(),
            join_on_keys=("aircraft_id", "aircraft_id_namespace"),
            window_rule="ADJACENT_ROWS_WITHIN_AIRCRAFT_GROUP",
            adjacency_rule="POSITIVE_GAP_WITHIN_MAX_360_MINUTES",
            tie_break_rule="EVENT_END_TIME_THEN_FLIGHT_ID",
            duplicate_rule="REJECT_EXACT_DUPLICATE_ORDERING_KEY",
            missing_key_rule="NO_COVERAGE_ABSTAIN",
            temporal_rule="TRAIN_PARTITION_ONLY",
            formula_or_algorithm="MEDIAN(N_down(H=360)) BY connection_airport_id; "
                                 "N_down = #{chain successors with first_seen within 360 min}; "
                                 "MIN_CELL_SIZE_50; FALLBACK AIRPORT_CELL_TO_GLOBAL; "
                                 "ZERO_COVERAGE_ABSTAIN",
            output_variable="expected_downstream_exposure",
            output_unit="legs",
            evidence_rule="EMPIRICAL_REFERENCE_FROM_TRAIN_CHAIN",
            support_rule="TRAIN_CHAIN_DEGRADED_MIN_CELL_50_FALLBACK_CELL_TO_GLOBAL",
            consumer_roles=(DecisionTimeRole.FROZEN_REFERENCE,),
            availability_basis=AvailabilityBasis.REFERENCE_PERIOD,
            evidence_class=EvidenceClass.EMPIRICAL_REFERENCE,
            support_ceiling=EvidenceClass.EMPIRICAL_REFERENCE,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="EXPECTED_DOWNSTREAM_EXPOSURE",
            version="0.1.0",
            construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
            input_object_types=("EpisodeRecord", "FlightRecord"),
            input_fields=("aircraft_id", "scheduled_departure_utc"),
            relation_keys=("aircraft_id",),
            temporal_rule="TRAIN_PARTITION_SCHEDULE_ONLY",
            formula_or_algorithm="OBJECT_DEFINED_STATISTIC_NOT_FROZEN",
            output_variable="expected_downstream_exposure",
            output_unit="exposure",
            evidence_rule="EMPIRICAL_REFERENCE",
            support_rule="CHAIN_AND_MINIMUM_SUPPORT_NOT_FROZEN",
            consumer_roles=(DecisionTimeRole.FROZEN_REFERENCE,),
            availability_basis=AvailabilityBasis.REFERENCE_PERIOD,
            evidence_class=EvidenceClass.EMPIRICAL_REFERENCE,
            support_ceiling=EvidenceClass.EMPIRICAL_REFERENCE,
            status=TransformationStatus.DEVELOPMENT_CANDIDATE,
            reason_code="CONSTRUCTION_RULE_NOT_FROZEN",
        ),
        TransformationRule(
            transformation_rule_id="DATA2_SAME_AIRCRAFT_AIRPORT_GAP",
            version="1.0.0",
            construction_type=ConstructionType.RELATIONAL_DERIVATION,
            input_object_types=("FlightRecord", "OperationalEventRecord"),
            input_fields=(
                "aircraft_id",
                "aircraft_id_namespace",
                "origin_airport_id",
                "destination_airport_id",
                "actual_arrival_utc",
                "actual_departure_utc",
                "event_start_time",
                "event_end_time",
                "flight_id",
            ),
            relation_keys=("aircraft_id_namespace", "aircraft_id"),
            group_by_keys=(
                "dataset_instance_id",
                "aircraft_id_namespace",
                "aircraft_id",
            ),
            order_by_keys=("actual_departure_utc", "actual_arrival_utc", "flight_id"),
            join_on_keys=(
                "dataset_instance_id",
                "aircraft_id_namespace",
                "aircraft_id",
                "predecessor.destination_airport_id=successor.origin_airport_id",
            ),
            window_rule="ADJACENT_ROWS_WITHIN_GROUP",
            adjacency_rule="POSITIVE_ACTUAL_GATE_GAP_WITHIN_MAX_360_MINUTES",
            tie_break_rule="ACTUAL_DEPARTURE_THEN_ACTUAL_ARRIVAL_THEN_FLIGHT_ID",
            duplicate_rule="REJECT_EXACT_DUPLICATE_ORDERING_KEY",
            missing_key_rule="REJECT_LINK",
            temporal_rule="ORDER_BY_ACTUAL_GATE_TIMES_THEN_ADJACENT",
            formula_or_algorithm=("SAME_AIRCRAFT_AND_AIRPORT_CONTINUITY_WITH_MAX_GAP_360_ON_ACTUAL_GATE_TIMES; "
                             "EPISODE_ANCHORS=CRS_TURNAROUND_WINDOW"),
            output_variable="predecessor_successor_episode",
            output_unit="episode",
            evidence_rule="DERIVED_FROM_DIRECT_GATE_EVENT_RECORDS",
            support_rule="ALL_IDENTITY_TIME_AND_CONTINUITY_PARENTS_REQUIRED",
            consumer_roles=(DecisionTimeRole.EPISODE_CONSTRUCTION,),
            availability_basis=AvailabilityBasis.ARCHIVE_PUBLICATION_RULE,
            evidence_class=EvidenceClass.DIRECT,
            support_ceiling=EvidenceClass.DIRECT,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="DATA2_TURNAROUND_REFERENCE",
            version="1.0.0",
            construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
            input_object_types=("FlightRecord", "OperationalEventRecord"),
            input_fields=(
                "aircraft_id",
                "aircraft_id_namespace",
                "origin_airport_id",
                "destination_airport_id",
                "actual_arrival_utc",
                "actual_departure_utc",
                "event_start_time",
                "event_end_time",
            ),
            relation_keys=(
                "aircraft_id",
                "aircraft_id_namespace",
                "predecessor.destination_airport_id=successor.origin_airport_id",
            ),
            group_by_keys=("connection_airport_id",),
            order_by_keys=(),
            join_on_keys=("aircraft_id", "aircraft_id_namespace"),
            window_rule="ADJACENT_ROWS_WITHIN_AIRCRAFT_GROUP",
            adjacency_rule="POSITIVE_ACTUAL_GATE_GAP_WITHIN_MAX_360_MINUTES",
            tie_break_rule="ACTUAL_DEPARTURE_THEN_ACTUAL_ARRIVAL_THEN_FLIGHT_ID",
            duplicate_rule="REJECT_EXACT_DUPLICATE_ORDERING_KEY",
            missing_key_rule="REJECT_LINK",
            temporal_rule="TRAIN_PARTITION_ONLY",
            formula_or_algorithm=("MEDIAN(successor.actual_departure_utc - predecessor.actual_arrival_utc) "
                                 "BY connection_airport_id; MIN_CELL_SIZE_50; "
                                 "FALLBACK AIRPORT_CELL_TO_GLOBAL"),
            output_variable="turnaround_reference",
            output_unit="minutes",
            evidence_rule="DIRECT_GATE_TURNAROUND_MEDIAN_FROM_ARCHIVE_ACTUALS",
            support_rule="DIRECT_ACTUAL_MIN_CELL_50_FALLBACK_CELL_TO_GLOBAL",
            consumer_roles=(DecisionTimeRole.FROZEN_REFERENCE,),
            availability_basis=AvailabilityBasis.REFERENCE_PERIOD,
            evidence_class=EvidenceClass.DIRECT,
            support_ceiling=EvidenceClass.DIRECT,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="DATA2_TAXI_REFERENCE",
            version="1.0.0",
            construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
            input_object_types=("OperationalEventRecord",),
            input_fields=("aircraft_id", "origin_airport_id", "taxi_out_minutes"),
            relation_keys=(),
            group_by_keys=("origin_airport_id",),
            order_by_keys=(),
            join_on_keys=(),
            window_rule=None,
            adjacency_rule=None,
            tie_break_rule=None,
            duplicate_rule="REJECT_EXACT_DUPLICATE_SCIENTIFIC_KEY",
            missing_key_rule="NO_COVERAGE_ABSTAIN",
            temporal_rule="TRAIN_PARTITION_ONLY",
            formula_or_algorithm="MEDIAN(TaxiOut) BY origin_airport_id; MIN_CELL_SIZE_50; "
                                 "FALLBACK AIRPORT_CELL_TO_GLOBAL; ZERO_COVERAGE_ABSTAIN",
            output_variable="taxi_reference",
            output_unit="minutes",
            evidence_rule="DIRECT_TAXI_OUT_MEDIAN_FROM_ARCHIVE_ACTUALS",
            support_rule="DIRECT_ACTUAL_MIN_CELL_50_FALLBACK_CELL_TO_GLOBAL_ZERO_COVERAGE_ABSTAIN",
            consumer_roles=(DecisionTimeRole.FROZEN_REFERENCE,),
            availability_basis=AvailabilityBasis.REFERENCE_PERIOD,
            evidence_class=EvidenceClass.DIRECT,
            support_ceiling=EvidenceClass.DIRECT,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="DATA2_DOWNSTREAM_EXPOSURE",
            version="1.0.0",
            construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
            input_object_types=("FlightRecord",),
            input_fields=(
                "aircraft_id",
                "aircraft_id_namespace",
                "origin_airport_id",
                "destination_airport_id",
                "event_start_time",
                "event_end_time",
            ),
            relation_keys=("aircraft_id_namespace", "aircraft_id"),
            group_by_keys=("connection_airport_id",),
            order_by_keys=(),
            join_on_keys=(),
            window_rule="SCHEDULED_DEPARTURES_WITHIN_HORIZON_WINDOW",
            adjacency_rule="SAME_AIRCRAFT_AND_AIRPORT_CONTINUITY_WITHIN_HORIZON",
            tie_break_rule="SCHEDULED_DEPARTURE_THEN_FLIGHT_ID",
            duplicate_rule="REJECT_EXACT_DUPLICATE_SCIENTIFIC_KEY",
            missing_key_rule="NO_COVERAGE_ABSTAIN",
            temporal_rule="TRAIN_PARTITION_ONLY",
            formula_or_algorithm=("MEDIAN(N_down) BY connection_airport_id; "
                                 "N_down = #{same-aircraft CRS scheduled departures from connection airport "
                                 "with CRSDep in (t0, t0+360min], t0 = pred.CRSArr}; "
                                 "MIN_CELL_SIZE_50; FALLBACK AIRPORT_CELL_TO_GLOBAL; ZERO_COVERAGE_ABSTAIN"),
            output_variable="expected_downstream_exposure",
            output_unit="legs",
            evidence_rule="CRS_SCHEDULE_COUNT_WITHIN_HORIZON_TRAIN_FROZEN",
            support_rule="CRS_SCHEDULE_MIN_CELL_50_FALLBACK_CELL_TO_GLOBAL_ZERO_COVERAGE_ABSTAIN",
            consumer_roles=(DecisionTimeRole.FROZEN_REFERENCE,),
            availability_basis=AvailabilityBasis.REFERENCE_PERIOD,
            evidence_class=EvidenceClass.DERIVED,
            support_ceiling=EvidenceClass.DERIVED,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="DATA2_PASSENGER_REFERENCE",
            version="1.0.0",
            construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
            input_object_types=("AggregateReference",),
            input_fields=(
                "join_key.origin",
                "join_key.destination",
                "value",
                "reference_period",
            ),
            relation_keys=(),
            group_by_keys=("origin_airport_id", "destination_airport_id"),
            order_by_keys=(),
            join_on_keys=(),
            window_rule=None,
            adjacency_rule=None,
            tie_break_rule=None,
            duplicate_rule="SUM_PASSENGERS_WITHIN_ROUTE",
            missing_key_rule="NO_COVERAGE_ABSTAIN",
            temporal_rule="REFERENCE_PERIOD_ONLY",
            formula_or_algorithm=("SUM(Passengers) x10 BY (origin, destination) OVER 2019-Q1; "
                                 "OFFICIAL_BTS_10PCT_TICKET_SAMPLE_SCALE_FACTOR_10; "
                                 "ZERO_COVERAGE_ABSTAIN"),
            output_variable="passenger_reference",
            output_unit="passengers",
            evidence_rule="OFFICIAL_DB1B_10PCT_SAMPLE_QUARTER_SUM_X10",
            support_rule="DB1B_COUPON_OFFICIAL_QUARTER_SCALE_X10_ZERO_COVERAGE_ABSTAIN",
            consumer_roles=(DecisionTimeRole.FROZEN_REFERENCE,),
            availability_basis=AvailabilityBasis.REFERENCE_PERIOD,
            evidence_class=EvidenceClass.DOMAIN_PROXY,
            support_ceiling=EvidenceClass.DOMAIN_PROXY,
            status=TransformationStatus.FROZEN,
        ),
                TransformationRule(
            transformation_rule_id="DATA2_PASSENGER_REFERENCE_H1",
            version="1.0.0",
            construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
            input_object_types=("AggregateReference",),
            input_fields=(
                "join_key.origin",
                "join_key.destination",
                "value",
                "reference_period",
            ),
            relation_keys=(),
            group_by_keys=("origin_airport_id", "destination_airport_id"),
            order_by_keys=(),
            join_on_keys=(),
            window_rule=None,
            adjacency_rule=None,
            tie_break_rule=None,
            duplicate_rule="SUM_PASSENGERS_WITHIN_ROUTE",
            missing_key_rule="NO_COVERAGE_ABSTAIN",
            temporal_rule="REFERENCE_PERIOD_ONLY",
            formula_or_algorithm=("SUM(Passengers) x10 BY (origin, destination) OVER 2019-H1 (Q1+Q2 coupon files); "
                                 "OFFICIAL_BTS_10PCT_TICKET_SAMPLE_SCALE_FACTOR_10; "
                                 "ZERO_COVERAGE_ABSTAIN"),
            output_variable="passenger_reference",
            output_unit="passengers",
            evidence_rule="OFFICIAL_DB1B_10PCT_SAMPLE_H1_SUM_X10",
            support_rule="DB1B_COUPON_OFFICIAL_H1_SCALE_X10_ZERO_COVERAGE_ABSTAIN",
            consumer_roles=(DecisionTimeRole.FROZEN_REFERENCE,),
            availability_basis=AvailabilityBasis.REFERENCE_PERIOD,
            evidence_class=EvidenceClass.DOMAIN_PROXY,
            support_ceiling=EvidenceClass.DOMAIN_PROXY,
            status=TransformationStatus.FROZEN,
        ),
TransformationRule(
            transformation_rule_id="DATA2_LABEL_R_IB",
            version="1.0.0",
            construction_type=ConstructionType.DETERMINISTIC_DERIVATION,
            input_object_types=("OperationalEventRecord", "DecisionNodeRecord"),
            input_fields=(
                "predecessor.actual_arrival_utc",
                "decision_time",
                "operational_stage",
            ),
            relation_keys=(),
            group_by_keys=(),
            order_by_keys=(),
            join_on_keys=(),
            window_rule=None,
            adjacency_rule=None,
            tie_break_rule=None,
            duplicate_rule="REJECT_EXACT_DUPLICATE_DECISION_NODE",
            missing_key_rule="MISSING_OUTCOME_ABSTAIN",
            temporal_rule="POSTHOC_ONLY",
            formula_or_algorithm=("R_IB = max(0, pred.actual_arrival_utc - decision_time); "
                                 "m1_r_ib_max_finite_minutes=360; OVERFLOW bin, no clip; "
                                 "STAGE_GATED"),
            output_variable="r_ib_label",
            output_unit="minutes",
            evidence_rule="DIRECT_GATE_ARRIVAL_MINUS_DECISION_TIME",
            support_rule="DIRECT_OUTCOME_STAGE_GATED_MISSING_ABSTAIN",
            consumer_roles=(DecisionTimeRole.TRAIN_LABEL, DecisionTimeRole.EVAL_OUTCOME),
            availability_basis=AvailabilityBasis.POSTHOC_ONLY,
            evidence_class=EvidenceClass.DIRECT,
            support_ceiling=EvidenceClass.DIRECT,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="DATA2_LABEL_R_OB",
            version="1.0.0",
            construction_type=ConstructionType.DETERMINISTIC_DERIVATION,
            input_object_types=("OperationalEventRecord", "FlightRecord", "DecisionNodeRecord"),
            input_fields=(
                "successor.actual_departure_utc",
                "successor.scheduled_departure_utc",
                "operational_stage",
            ),
            relation_keys=(),
            group_by_keys=(),
            order_by_keys=(),
            join_on_keys=(),
            window_rule=None,
            adjacency_rule=None,
            tie_break_rule=None,
            duplicate_rule="REJECT_EXACT_DUPLICATE_DECISION_NODE",
            missing_key_rule="MISSING_OUTCOME_ABSTAIN",
            temporal_rule="POSTHOC_ONLY",
            formula_or_algorithm=("R_OB = max(0, succ.actual_departure_utc - succ.scheduled_departure_utc); "
                                 "m1_r_ob_max_finite_minutes=180; OVERFLOW bin, no clip; "
                                 "STAGE_GATED"),
            output_variable="r_ob_label",
            output_unit="minutes",
            evidence_rule="DIRECT_GATE_DEPARTURE_MINUS_CRS_DEPARTURE",
            support_rule="DIRECT_OUTCOME_STAGE_GATED_MISSING_ABSTAIN",
            consumer_roles=(DecisionTimeRole.TRAIN_LABEL, DecisionTimeRole.EVAL_OUTCOME),
            availability_basis=AvailabilityBasis.POSTHOC_ONLY,
            evidence_class=EvidenceClass.DIRECT,
            support_ceiling=EvidenceClass.DIRECT,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="DATA2_LABEL_T_TX",
            version="1.0.0",
            construction_type=ConstructionType.DETERMINISTIC_DERIVATION,
            input_object_types=("OperationalEventRecord", "DecisionNodeRecord"),
            input_fields=("successor.taxi_out_minutes", "operational_stage"),
            relation_keys=(),
            group_by_keys=(),
            order_by_keys=(),
            join_on_keys=(),
            window_rule=None,
            adjacency_rule=None,
            tie_break_rule=None,
            duplicate_rule="REJECT_EXACT_DUPLICATE_DECISION_NODE",
            missing_key_rule="MISSING_OUTCOME_ABSTAIN",
            temporal_rule="POSTHOC_ONLY",
            formula_or_algorithm=("T_TX = succ.taxi_out_minutes; "
                                 "m1_t_tx_max_finite_minutes=60; OVERFLOW bin, no clip; "
                                 "STAGE_GATED"),
            output_variable="t_tx_label",
            output_unit="minutes",
            evidence_rule="DIRECT_TAXI_OUT_MINUTES",
            support_rule="DIRECT_OUTCOME_STAGE_GATED_MISSING_ABSTAIN",
            consumer_roles=(DecisionTimeRole.TRAIN_LABEL, DecisionTimeRole.EVAL_OUTCOME),
            availability_basis=AvailabilityBasis.POSTHOC_ONLY,
            evidence_class=EvidenceClass.DIRECT,
            support_ceiling=EvidenceClass.DIRECT,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="DATA2_M1_TRAINING_COVERAGE",
            version="1.0.0",
            construction_type=ConstructionType.DETERMINISTIC_DERIVATION,
            input_object_types=("DecisionNodeRecord", "OperationalEventRecord", "FlightRecord"),
            input_fields=(
                "decision_time",
                "node_index",
                "operational_stage",
                "predecessor.actual_arrival_utc",
                "successor.actual_departure_utc",
                "successor.taxi_out_minutes",
            ),
            relation_keys=(),
            group_by_keys=("episode_id",),
            order_by_keys=("node_index",),
            join_on_keys=(),
            window_rule=None,
            adjacency_rule=None,
            tie_break_rule=None,
            duplicate_rule="ONE_EXAMPLE_PER_DECISION_NODE",
            missing_key_rule="MISSING_OUTCOME_ABSTAIN",
            temporal_rule="POSTHOC_ONLY",
            formula_or_algorithm=("all rolling grid nodes -> one M1 training example per node; "
                                 "D2-2 anchors unchanged; stage-gated labels "
                                 "(R_IB:{PRE_IB}; R_OB:{PRE_IB,POST_IB_PRE_OB}; "
                                 "T_TX:{PRE_IB,POST_IB_PRE_OB,POST_OB_PRE_TO}); "
                                 "node-level equal weight; "
                                 "nodes with no active target (all realized) excluded"),
            output_variable="m1_training_coverage",
            output_unit="sample",
            evidence_rule="STAGE_GATED_LABEL_ACTIVATION_ALL_NODES",
            support_rule="DIRECT_OUTCOME_STAGE_GATED_MISSING_ABSTAIN",
            consumer_roles=(DecisionTimeRole.TRAIN_LABEL,),
            availability_basis=AvailabilityBasis.POSTHOC_ONLY,
            evidence_class=EvidenceClass.DERIVED,
            support_ceiling=EvidenceClass.DIRECT,
            status=TransformationStatus.FROZEN,
        ),
        TransformationRule(
            transformation_rule_id="DATA2_TEMPORAL_SPLIT",
            version="1.0.0",
            construction_type=ConstructionType.DETERMINISTIC_DERIVATION,
            input_object_types=("EpisodeRecord", "FlightRecord"),
            input_fields=("successor.service_date",),
            relation_keys=(),
            group_by_keys=(),
            order_by_keys=(),
            join_on_keys=(),
            window_rule=None,
            adjacency_rule=None,
            tie_break_rule=None,
            duplicate_rule="ONE_SPLIT_PER_EPISODE",
            missing_key_rule="MISSING_SERVICE_DATE_ABSTAIN",
            temporal_rule="TRAIN_PARTITION_ONLY",
            formula_or_algorithm=("temporal split by successor service_date: "
                                 "train<=2019-06-30; calibration 2019-07-01..2019-07-31; "
                                 "development 2019-08-01..2019-09-30; test>=2019-10-01; "
                                 "cohort sampled per split; no cross-split leakage"),
            output_variable="dataset_partition",
            output_unit="partition",
            evidence_rule="SUCCESSOR_SERVICE_DATE_WINDOW",
            support_rule="EXPLICIT_DATE_ABSTAIN",
            consumer_roles=(DecisionTimeRole.EPISODE_CONSTRUCTION,),
            availability_basis=AvailabilityBasis.POSTHOC_ONLY,
            evidence_class=EvidenceClass.DERIVED,
            support_ceiling=EvidenceClass.DERIVED,
            status=TransformationStatus.FROZEN,
        ),    )
    return TransformationRegistry(registry_version="1.0.0", rules=rules)
