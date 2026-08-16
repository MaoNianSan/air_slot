from __future__ import annotations

from collections.abc import Callable, Iterable
from hashlib import sha256
import json
from typing import Any

from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from model.common.value_objects import SupportedValue
from .contracts import (
    ConstructionType,
    ReferenceFitManifest,
    ScientificObjectValue,
    TransformationRule,
    TransformationStatus,
)

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
