from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from model.common.enums import (
    AvailabilityBasis,
    DecisionTimeRole,
    EvidenceClass,
    SupportState,
    weaker_or_equal,
)
from model.common.errors import ContractError
from model.common.value_objects import SupportedValue
from model.PRE.contracts.canonical import CanonicalSourceRecord
from model.PRE.contracts.pre_state import (
    AirportReferenceSlot,
    EvidenceLedgerEntry,
    KeyedAirportReference,
    VariableLineageEntry,
)
from model.PRE.feature_registry.loader import RegistryBundle, load_registry_bundle

_PRE_FAMILIES = {
    "predecessor_state",
    "current_state",
    "successor_state",
    "reference_state",
}
_POSTHOC_ROLES = {DecisionTimeRole.TRAIN_LABEL, DecisionTimeRole.EVAL_OUTCOME}


@dataclass(frozen=True)
class MappedScientificObject:
    scientific_variable: str
    pre_family: str
    value: SupportedValue
    canonical: CanonicalSourceRecord | None
    rule_id: str | None
    source_name: str


def _canonical_value(record: CanonicalSourceRecord, variable: str) -> Any:
    if variable == "predecessor_motion":
        return {
            key: getattr(record, key)
            for key in (
                "latitude_deg",
                "longitude_deg",
                "velocity_mps",
                "on_ground",
                "baro_altitude_m",
                "geo_altitude_m",
                "heading_deg",
                "vertical_rate_mps",
            )
        }
    if variable == "current_weather":
        excluded = {
            "canonical_record_id",
            "dataset_instance_id",
            "canonical_object_type",
            "event_time",
            "availability_time",
            "availability_basis",
            "decision_time_role",
            "provenance_rule_id",
            "provenance",
            "source_path",
            "source_fingerprint",
            "source_row_number",
            "quality_flags",
        }
        return {
            key: value
            for key, value in record.model_dump(mode="python").items()
            if key not in excluded
        }
    if variable == "schedule_reference":
        return {
            "flight_id": getattr(record, "flight_id"),
            "scheduled_departure_utc": getattr(record, "scheduled_departure_utc"),
            "scheduled_arrival_utc": getattr(record, "scheduled_arrival_utc"),
            "origin_airport_id": getattr(record, "origin_airport_id"),
            "destination_airport_id": getattr(record, "destination_airport_id"),
            "carrier_id": getattr(record, "carrier_id"),
            "aircraft_id": getattr(record, "aircraft_id"),
            "aircraft_id_namespace": getattr(record, "aircraft_id_namespace"),
            "schedule_semantics": getattr(record, "schedule_semantics"),
        }
    if variable in {"passenger_reference", "segment_reference"}:
        return {
            "reference_name": getattr(record, "reference_name"),
            "grain": getattr(record, "grain"),
            "join_key": getattr(record, "join_key"),
            "reference_period": getattr(record, "reference_period"),
            "value": getattr(record, "value"),
        }
    if variable == "airport_reference":
        return {
            key: getattr(record, key)
            for key in (
                "airport_id",
                "airport_id_namespace",
                "icao_code",
                "iata_code",
                "latitude_deg",
                "longitude_deg",
                "elevation_m",
                "airport_type",
            )
        }
    if variable == "airport_timezone":
        return {
            "airport_id": getattr(record, "airport_id"),
            "timezone": getattr(record, "timezone"),
        }
    raise ContractError(f"SCIENTIFIC_TRANSFORMATION_NOT_IMPLEMENTED:{variable}")


class RegistryPREMapper:
    def __init__(self, bundle: RegistryBundle):
        self.bundle = bundle
        self._rules = {rule.rule_id: rule for rule in bundle.data_usage_rules}
        self._variables = {
            item.scientific_variable: item for item in bundle.scientific_variables
        }

    @classmethod
    def from_path(cls, path: Path) -> "RegistryPREMapper":
        return cls(load_registry_bundle(path))

    def map_record(
        self, record: CanonicalSourceRecord, *, consumer: str = "PRE"
    ) -> MappedScientificObject | None:
        rule = self._rules.get(record.provenance_rule_id)
        if rule is None:
            raise ContractError(f"UNKNOWN_REGISTRY_RULE:{record.provenance_rule_id}")
        if rule.dataset_id != record.dataset_instance_id:
            raise ContractError("REGISTRY_DATASET_CONTRADICTION")
        if rule.canonical_object != record.canonical_object_type:
            raise ContractError("REGISTRY_CANONICAL_OBJECT_CONTRADICTION")
        if rule.decision_time_role is not record.decision_time_role:
            raise ContractError("REGISTRY_DECISION_ROLE_CONTRADICTION")
        if record.decision_time_role is DecisionTimeRole.EPISODE_CONSTRUCTION:
            return None
        if consumer not in rule.downstream_consumers:
            if record.decision_time_role in _POSTHOC_ROLES:
                return None
            raise ContractError("REGISTRY_CONSUMER_NOT_PERMITTED")
        if record.availability_basis is AvailabilityBasis.POSTHOC_ONLY:
            return None
        definition = next(
            (
                item
                for item in self.bundle.scientific_variables
                if rule.canonical_variable in item.canonical_inputs
            ),
            None,
        )
        if definition is None:
            raise ContractError(
                f"UNDECLARED_SCIENTIFIC_VARIABLE:{rule.canonical_variable}"
            )
        if (
            definition.pre_family not in _PRE_FAMILIES
            or rule.pre_family != definition.pre_family
        ):
            raise ContractError("REGISTRY_PRE_FAMILY_CONTRADICTION")
        if not weaker_or_equal(rule.evidence_class, rule.support_ceiling):
            raise ContractError("SUPPORT_UPGRADE_FORBIDDEN")
        support = definition.dataset_support[record.dataset_instance_id]
        if support.formal_input_support is EvidenceClass.UNSUPPORTED:
            raise ContractError("UNSUPPORTED_RECORD_CANNOT_PUBLISH_VALUE")
        value = SupportedValue(
            value=_canonical_value(record, definition.scientific_variable),
            unit=definition.unit,
            evidence_class=rule.evidence_class,
            support_ceiling=rule.support_ceiling,
            support_state=SupportState.SUPPORTED,
            formal_input_support=support.formal_input_support,
            realized_outcome_support=support.realized_outcome_support,
            quality_flags=record.quality_flags,
        )
        return MappedScientificObject(
            definition.scientific_variable,
            definition.pre_family,
            value,
            record,
            rule.rule_id,
            record.provenance.logical_source,
        )

    def complete_missing(
        self, dataset_instance_id: str, present: set[str]
    ) -> tuple[MappedScientificObject, ...]:
        result = []
        for definition in self.bundle.scientific_variables:
            if definition.pre_family not in _PRE_FAMILIES:
                continue
            if definition.scientific_variable in present:
                continue
            support = definition.dataset_support[dataset_instance_id]
            if support.reason_code in {"NOT_REQUIRED_IN_FOUNDATION"}:
                continue
            reason = support.reason_code or "NO_LEGAL_RECORD_AT_DECISION_TIME"
            value = SupportedValue(
                value=None,
                unit=definition.unit,
                evidence_class=EvidenceClass.UNSUPPORTED,
                support_ceiling=EvidenceClass.UNSUPPORTED,
                support_state=SupportState.ABSTAIN,
                formal_input_support=support.formal_input_support,
                realized_outcome_support=support.realized_outcome_support,
                reason_code=reason,
            )
            result.append(
                MappedScientificObject(
                    definition.scientific_variable,
                    definition.pre_family,
                    value,
                    None,
                    None,
                    "DATASET_CAPABILITY",
                )
            )
        return tuple(result)


def _missing_airport_slot(role: str) -> AirportReferenceSlot:
    return AirportReferenceSlot(
        reference_role=role,
        supported_value=SupportedValue(
            value=None,
            unit="canonical",
            evidence_class=EvidenceClass.UNSUPPORTED,
            support_ceiling=EvidenceClass.UNSUPPORTED,
            support_state=SupportState.ABSTAIN,
            reason_code=f"MISSING_{role.upper()}_AIRPORT_REFERENCE",
        ),
    )


def publish_mapped(
    objects: tuple[MappedScientificObject, ...],
    *,
    cutoff: datetime,
    decision_node_id: str,
    airport_roles: dict[str, str | None] | None = None,
    weather_max_age_minutes: int | None = None,
):
    families = {name: {} for name in _PRE_FAMILIES}
    ledger, lineage, legal_ids = [], [], []
    grouped: dict[tuple[str, str], list[MappedScientificObject]] = {}
    weather_max_age_seconds = (
        None if weather_max_age_minutes is None else weather_max_age_minutes * 60
    )
    dropped_groups: dict[tuple[str, str], str] = {}
    for item in objects:
        if item.canonical is not None:
            record = item.canonical
            if record.availability_basis in {
                AvailabilityBasis.OBSERVED_AVAILABILITY,
                AvailabilityBasis.REPLAY_EVENT_TIME,
            }:
                if (
                    record.availability_time is None
                    or record.availability_time > cutoff
                ):
                    dropped_groups.setdefault(
                        (item.pre_family, item.scientific_variable),
                        "NO_LEGAL_RECORD_AT_DECISION_TIME",
                    )
                    continue
                if (
                    item.scientific_variable == "current_weather"
                    and weather_max_age_seconds is not None
                    and (cutoff - record.availability_time).total_seconds()
                    > weather_max_age_seconds
                ):
                    dropped_groups[(item.pre_family, item.scientific_variable)] = (
                        "WEATHER_STALE_AT_CUTOFF"
                    )
                    continue
        grouped.setdefault((item.pre_family, item.scientific_variable), []).append(item)
    for (family, variable), candidates in sorted(grouped.items()):
        if variable == "airport_reference" and airport_roles is not None:
            by_airport = {}
            for item in candidates:
                if item.canonical is None or item.value.value is None:
                    continue
                for field in ("airport_id", "icao_code", "iata_code"):
                    alias = item.value.value.get(field)
                    if alias:
                        by_airport[str(alias).upper()] = item
            slots = {}
            selected_items = []
            for role in ("origin", "destination", "connection"):
                item = by_airport.get(str(airport_roles.get(role)).upper())
                if item is None:
                    slots[role] = _missing_airport_slot(role)
                    continue
                slots[role] = AirportReferenceSlot(
                    reference_role=role,
                    supported_value=item.value,
                    source_record_id=item.canonical.canonical_record_id,
                    rule_id=item.rule_id,
                )
                selected_items.append((role, item))
            if not selected_items:
                families[family][variable] = candidates[0].value
                continue
            keyed = KeyedAirportReference(**slots)
            missing = [
                role
                for role, slot in slots.items()
                if slot.supported_value.support_state is SupportState.ABSTAIN
            ]
            base = selected_items[0][1].value if selected_items else candidates[0].value
            families[family][variable] = base.model_copy(
                update={
                    "value": keyed,
                    "support_state": (
                        SupportState.DEGRADED if missing else SupportState.SUPPORTED
                    ),
                    "reason_code": (
                        "MISSING_KEYED_AIRPORT_REFERENCE" if missing else None
                    ),
                }
            )
            for role, item in selected_items:
                record = item.canonical
                legal_ids.append(record.canonical_record_id)
                common = dict(
                    decision_node_id=decision_node_id,
                    source_name=item.source_name,
                    source_record_id=record.canonical_record_id,
                    event_time=record.event_time,
                    availability_time=record.availability_time,
                    availability_basis=record.availability_basis.value,
                )
                ledger.append(
                    EvidenceLedgerEntry(
                        **common,
                        scientific_object="airport_reference",
                        decision_time_role=record.decision_time_role.value,
                        evidence_class=item.value.evidence_class,
                        support_ceiling=item.value.support_ceiling,
                        episode_support=item.value.support_state,
                        quality_flags=record.quality_flags,
                    )
                )
                lineage.append(
                    VariableLineageEntry(
                        **common,
                        scientific_variable="airport_reference",
                        supported_value=item.value,
                        canonical_variable="airport_reference",
                        rule_id=item.rule_id or "DATASET_CAPABILITY",
                        quality_flags=record.quality_flags,
                        reference_role=role,
                    )
                )
            continue
        selected = sorted(
            candidates,
            key=lambda item: (
                (
                    (item.canonical.availability_time or item.canonical.event_time)
                    if item.canonical
                    else datetime.min.replace(tzinfo=cutoff.tzinfo)
                ),
                item.canonical.canonical_record_id if item.canonical else "",
            ),
        )[-1]
        families[family][variable] = selected.value
        if selected.canonical is None:
            continue
        record = selected.canonical
        legal_ids.append(record.canonical_record_id)
        common = dict(
            decision_node_id=decision_node_id,
            source_name=selected.source_name,
            source_record_id=record.canonical_record_id,
            event_time=record.event_time,
            availability_time=record.availability_time,
            availability_basis=record.availability_basis.value,
        )
        ledger.append(
            EvidenceLedgerEntry(
                **common,
                scientific_object=variable,
                decision_time_role=record.decision_time_role.value,
                evidence_class=selected.value.evidence_class,
                support_ceiling=selected.value.support_ceiling,
                episode_support=selected.value.support_state,
                freshness_seconds=(
                    (cutoff - record.availability_time).total_seconds()
                    if record.availability_time
                    else None
                ),
                abstention_reason=selected.value.reason_code,
                quality_flags=record.quality_flags,
            )
        )
        lineage.append(
            VariableLineageEntry(
                **common,
                scientific_variable=variable,
                supported_value=selected.value,
                canonical_variable=variable,
                rule_id=selected.rule_id or "DATASET_CAPABILITY",
                age_seconds=(
                    (cutoff - record.availability_time).total_seconds()
                    if record.availability_time
                    else None
                ),
                quality_flags=record.quality_flags,
            )
        )
    for (family, variable), reason in dropped_groups.items():
        if variable not in families[family]:
            families[family][variable] = SupportedValue(
                value=None,
                unit="canonical",
                evidence_class=EvidenceClass.UNSUPPORTED,
                support_ceiling=EvidenceClass.UNSUPPORTED,
                support_state=SupportState.ABSTAIN,
                reason_code=reason,
            )

    return families, tuple(ledger), tuple(lineage), tuple(sorted(set(legal_ids)))
